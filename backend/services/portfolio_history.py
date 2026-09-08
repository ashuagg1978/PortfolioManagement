"""Historical portfolio-value time series.

Two distinct jobs live here, deliberately kept apart from services/portfolio.py:

1. sync_nav_history() - fetches and PERSISTS daily NAV history (from
   services/nav_history.py's mfapi.in client) for every scheme the user has
   ever transacted, run only when the user clicks "Sync NAV". This is the one
   place in the whole app that stores third-party data as a growing history
   rather than a single current value - portfolio.py's own file header states
   its philosophy as "nothing is cached or stored", so this doesn't belong
   there. mfapi.in has no server-side date filtering (verified live - see
   nav_history.py), so every sync re-fetches each held scheme's *entire*
   history; scheme_nav_history.py's unique (scheme_code, nav_date) index plus
   insert_ignore() makes re-inserting already-known dates a no-op.

2. compute_portfolio_value_history() - the day-wise sweep that turns that
   stored NAV history plus the transaction ledger into a plottable series.
   This half DOES follow portfolio.py's philosophy: nothing here is cached,
   it's recomputed from scratch on every call, so an edited/backdated/deleted
   transaction is reflected immediately on the next request.
"""

from __future__ import annotations

from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import Table
from sqlalchemy.orm import Session

from db.upsert import insert_ignore
from models.account import Account
from models.enums import TransactionType
from models.scheme_nav_history import SchemeNavHistory
from models.transaction import Transaction
from models.user import User
from services.nav_history import fetch_full_history

# Pure I/O-bound HTTP calls (one per held scheme) - a small thread pool cuts
# wall-clock time roughly proportionally without touching the DB session from
# worker threads (SQLAlchemy Sessions aren't thread-safe; all DB writes below
# happen back on the calling thread after as_completed() drains).
_MAX_WORKERS = 6


@dataclass(frozen=True, slots=True)
class HistorySyncResult:
    schemes_synced: int
    schemes_failed: int
    points_inserted: int
    duration_ms: int


@dataclass(frozen=True, slots=True)
class TxnEvent:
    """One purchase/redemption, as the sweep needs it - enough to replay
    FIFO lot accounting incrementally, day by day (see _sweep). `id` is a
    same-day tiebreaker only (matches services/fifo.py::run_fifo's own
    (date, id) sort - a purchase and redemption of the same scheme recorded
    on the same day need a stable, deterministic order to consume lots
    consistently); it doesn't need to be a real transaction id, just unique
    and stable per scheme."""

    txn_date: date
    id: int
    type: str  # TransactionType
    units: Decimal
    amount: Decimal  # PURCHASE: money invested (nav*units + commission)


@dataclass(frozen=True, slots=True)
class PortfolioValuePoint:
    as_of: date
    current_value: Decimal
    net_invested: Decimal
    pct_gain: Decimal | None  # None when net_invested is 0 (nothing held yet, or fully exited with no cost basis)


def _held_scheme_codes(db: Session, user: User) -> list[str]:
    account_ids = [a.id for a in db.query(Account.id).filter(Account.user_id == user.id).all()]
    if not account_ids:
        return []
    rows = (
        db.query(Transaction.scheme_code)
        .filter(Transaction.account_id.in_(account_ids), Transaction.is_deleted.is_(False))
        .distinct()
        .all()
    )
    return [r[0] for r in rows]


def sync_nav_history(db: Session, user: User) -> HistorySyncResult:
    """Tops up scheme_nav_history for every scheme the user has ever
    transacted. Safe to call repeatedly - already-stored dates are skipped
    via insert_ignore(), and one scheme's fetch failing doesn't block the
    others (mirrors services/amfi.py's "skip the bad row, not the batch").
    """
    started = datetime.now()
    scheme_codes = _held_scheme_codes(db, user)
    if not scheme_codes:
        return HistorySyncResult(0, 0, 0, int((datetime.now() - started).total_seconds() * 1000))

    results: dict[str, list] = {}
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
        futures = {pool.submit(fetch_full_history, code): code for code in scheme_codes}
        for future in as_completed(futures):
            code = futures[future]
            try:
                results[code] = future.result()
            except Exception:
                # fetch_full_history already swallows its own errors and
                # returns [] - this is a defensive backstop only, so one
                # unexpected exception can't take down the whole sync.
                results[code] = []

    schemes_failed = sum(1 for points in results.values() if not points)
    schemes_synced = len(scheme_codes) - schemes_failed

    rows = [
        {"scheme_code": code, "nav_date": p.nav_date, "nav": p.nav}
        for code, points in results.items()
        for p in points
    ]
    table: Table = SchemeNavHistory.__table__
    if rows:
        insert_ignore(db, table, rows)
    db.commit()

    duration_ms = int((datetime.now() - started).total_seconds() * 1000)
    return HistorySyncResult(
        schemes_synced=schemes_synced,
        schemes_failed=schemes_failed,
        # insert_ignore()'s ON CONFLICT DO NOTHING doesn't report how many
        # rows actually landed vs. were skipped as already-known - this is
        # "rows attempted", good enough for a user-facing summary, not
        # depended on for correctness anywhere (the sweep re-reads the table
        # fresh on every request).
        points_inserted=len(rows),
        duration_ms=duration_ms,
    )


class _Lot:
    __slots__ = ("units_remaining", "cost_per_unit")

    def __init__(self, units: Decimal, cost_per_unit: Decimal) -> None:
        self.units_remaining = units
        self.cost_per_unit = cost_per_unit


class _SchemeCursor:
    """Per-scheme state carried forward across the whole sweep: FIFO lot
    queue (for net_invested, i.e. cost basis of units still held - same
    definition services/portfolio.py uses, NOT a plain cumulative-purchase
    sum, so a redemption correctly removes that lot's cost rather than just
    netting cash flows), units held (for current_value), and the latest
    known NAV (forward-filled - see _sweep)."""

    __slots__ = ("txn_i", "nav_i", "lots", "units", "cost_remaining", "nav")

    def __init__(self) -> None:
        self.txn_i = 0
        self.nav_i = 0
        self.lots: deque[_Lot] = deque()
        self.units = Decimal("0")
        self.cost_remaining = Decimal("0")
        self.nav: Decimal | None = None

    def apply(self, event: TxnEvent) -> None:
        if event.type == TransactionType.PURCHASE:
            if event.units <= 0:
                return
            cost_per_unit = event.amount / event.units
            self.lots.append(_Lot(event.units, cost_per_unit))
            self.units += event.units
            self.cost_remaining += event.amount
        else:  # REDEMPTION
            remaining = event.units
            self.units -= event.units
            while remaining > 0 and self.lots:
                lot = self.lots[0]
                take = min(lot.units_remaining, remaining)
                self.cost_remaining -= take * lot.cost_per_unit
                lot.units_remaining -= take
                remaining -= take
                if lot.units_remaining == 0:
                    self.lots.popleft()
            # If `remaining` is still > 0 here the ledger is inconsistent
            # (e.g. an earlier purchase was soft-deleted after this
            # redemption was recorded) - services/fifo.py raises on this for
            # the authoritative FIFO run; this sweep feeds a read-only chart,
            # so it degrades gracefully (cost_remaining just stops going
            # lower) rather than 500-ing the whole dashboard over it.


def _sweep(
    txn_events: dict[str, list[TxnEvent]],
    nav_events: dict[str, list[tuple[date, Decimal]]],
    start: date,
    end: date,
) -> list[PortfolioValuePoint]:
    """Pure day-wise sweep, no DB access - directly unit-testable.

    txn_events: per scheme_code, TxnEvents already sorted ascending by date.
    nav_events: per scheme_code, (nav_date, nav) pairs already sorted ascending.

    For every calendar day from start to end inclusive, holds one forward-
    only cursor per scheme into each event list, replaying FIFO lot
    accounting incrementally (see _SchemeCursor.apply) so net_invested at
    any day is the true cost basis of units held *as of that day* - matches
    services/portfolio.py's definition exactly, just recomputed at every
    historical point instead of only today. NAV forward-fills automatically:
    a day with no new nav_events entry just leaves the cursor's last value
    in place, covering weekends/holidays with no gap or dip. A scheme with
    no nav_events at all (or none yet as of a given day) contributes 0 to
    current_value, never crashes.

    Cost: each scheme's cursor only ever advances forward across the WHOLE
    sweep, at most len(events) times total - not per day - so total work is
    O(days * schemes) for the outer loop/None-checks plus O(total events)
    for the actual FIFO/pointer advances, not a per-day recompute from scratch.
    """
    schemes = set(txn_events) | set(nav_events)
    cursors = {code: _SchemeCursor() for code in schemes}

    series: list[PortfolioValuePoint] = []
    one_day = timedelta(days=1)
    d = start
    while d <= end:
        total_value = Decimal("0")
        total_invested = Decimal("0")
        for code, cur in cursors.items():
            events = txn_events.get(code, [])
            while cur.txn_i < len(events) and events[cur.txn_i].txn_date <= d:
                cur.apply(events[cur.txn_i])
                cur.txn_i += 1
            navs = nav_events.get(code, [])
            while cur.nav_i < len(navs) and navs[cur.nav_i][0] <= d:
                cur.nav = navs[cur.nav_i][1]
                cur.nav_i += 1
            if cur.units != 0 and cur.nav is not None:
                total_value += cur.units * cur.nav
            total_invested += cur.cost_remaining
        pct_gain = (
            (total_value - total_invested) / total_invested * 100 if total_invested != 0 else None
        )
        series.append(
            PortfolioValuePoint(
                as_of=d, current_value=total_value, net_invested=total_invested, pct_gain=pct_gain
            )
        )
        d += one_day

    return series


def compute_portfolio_value_history(db: Session, user: User) -> list[PortfolioValuePoint]:
    account_ids = [a.id for a in db.query(Account.id).filter(Account.user_id == user.id).all()]
    if not account_ids:
        return []

    txns = (
        db.query(Transaction)
        .filter(Transaction.account_id.in_(account_ids), Transaction.is_deleted.is_(False))
        .all()
    )
    if not txns:
        return []

    scheme_codes = {t.scheme_code for t in txns}
    nav_rows = (
        db.query(SchemeNavHistory)
        .filter(SchemeNavHistory.scheme_code.in_(scheme_codes))
        .all()
    )

    txn_events: dict[str, list[TxnEvent]] = {}
    for t in txns:
        txn_events.setdefault(t.scheme_code, []).append(
            TxnEvent(txn_date=t.transaction_date, id=t.id, type=t.type, units=t.units, amount=t.amount)
        )
    for events in txn_events.values():
        events.sort(key=lambda e: (e.txn_date, e.id))

    nav_events: dict[str, list[tuple[date, Decimal]]] = {}
    for r in nav_rows:
        nav_events.setdefault(r.scheme_code, []).append((r.nav_date, r.nav))
    for events in nav_events.values():
        events.sort(key=lambda p: p[0])

    start = min(t.transaction_date for t in txns)
    end = date.today()
    if start > end:
        return []

    return _sweep(txn_events, nav_events, start, end)
