"""The metrics engine: per-scheme holdings and the portfolio KPI rollup.

Everything here is computed in Python from the transaction ledger and the
latest synced NAVs - nothing is cached or stored, so a soft-deleted or
edited transaction is reflected immediately on the next request. At this
data volume (~1,000s of transactions) that's microseconds of work, not a
performance concern.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from models.account import Account
from models.scheme import Scheme
from models.transaction import Transaction
from models.user import User
from services.fifo import LedgerEntry, run_fifo
from services.scheme_names import display_name_for, full_scheme_name
from services.xirr import scheme_xirr


@dataclass(frozen=True, slots=True)
class SchemeHolding:
    scheme_code: str
    display_name: str
    net_units: Decimal
    net_invested: Decimal
    avg_cost_nav: Decimal | None
    latest_nav: Decimal | None
    nav_date: date | None
    nav_source: str  # "NAVAll" | "Last txn NAV" | "Redeemed"
    current_value: Decimal
    unrealized_gain: Decimal
    realized_gain: Decimal
    total_gain: Decimal
    pct_gain: Decimal | None
    status: str  # "In Profit" | "In Loss" | "Redeemed" | "Flat"
    xirr: Decimal | None


@dataclass(frozen=True, slots=True)
class AccountHoldings:
    account_id: int
    account_name: str
    net_invested: Decimal
    current_value: Decimal
    net_gain_loss: Decimal
    pct_gain: Decimal | None
    xirr: Decimal | None
    schemes: list[SchemeHolding]


@dataclass(frozen=True, slots=True)
class DashboardSummary:
    net_invested: Decimal
    current_value: Decimal
    net_gain_loss: Decimal
    total_realized_gain: Decimal
    total_return_pct: Decimal | None
    active_schemes: int
    total_commission_paid: Decimal
    portfolio_xirr: Decimal | None
    nav_as_of: date | None
    holdings: list[SchemeHolding]
    by_account: list[AccountHoldings]


def _resolve_nav(
    scheme: Scheme | None, last_txn_nav: Decimal | None
) -> tuple[Decimal | None, date | None, str]:
    """Mirrors the workbook's fallback chain: feed NAV -> last transaction
    NAV -> "Redeemed" when nothing is available at all.
    """
    if scheme is not None and scheme.latest_nav is not None:
        return scheme.latest_nav, scheme.nav_date, "NAVAll"
    if last_txn_nav is not None:
        return last_txn_nav, None, "Last txn NAV"
    return None, None, "Redeemed"


def _build_scheme_holdings(
    db: Session,
    user: User,
    txns: list[Transaction],
    schemes: dict[str, Scheme],
    as_of: date,
) -> list[SchemeHolding]:
    """Groups a (already is_deleted-filtered) list of transactions by scheme
    and runs FIFO within each group. Shared by the portfolio-wide breakdown
    (one row per scheme, across every account) and the per-account breakdown
    (one row per scheme, within a single account's transactions only) -
    same math, different slice of the ledger fed in.
    """
    by_scheme: dict[str, list[Transaction]] = {}
    for r in txns:
        by_scheme.setdefault(r.scheme_code, []).append(r)

    holdings: list[SchemeHolding] = []
    for scheme_code, scheme_txns in by_scheme.items():
        entries = [
            LedgerEntry(id=t.id, date=t.transaction_date, type=t.type, units=t.units, amount=t.amount)
            for t in scheme_txns
        ]
        fifo = run_fifo(entries)

        last_txn = max(scheme_txns, key=lambda t: (t.transaction_date, t.id))
        scheme = schemes.get(scheme_code)
        latest_nav, nav_date, nav_source = _resolve_nav(scheme, last_txn.nav)

        units_held = fifo.units_held
        current_value = (units_held * latest_nav) if latest_nav is not None else Decimal("0")

        # Net Invested = the FIFO cost basis of units still held (what you
        # actually paid for what you're still holding) - NOT current value
        # netted against cash flows. That earlier formula (current_value -
        # signed_sum) silently added current_value on top of the real
        # invested amount for any scheme with no redemptions, since
        # signed_sum there is just -total_purchased: a $63,000 purchase-only
        # holding worth $64,582 today showed "Net Invested: $127,582" -
        # roughly double the real figure - and a diluted % Gain as a direct
        # consequence. fifo.cost_remaining is exactly "cost of units held"
        # and needs no such adjustment.
        net_invested = fifo.cost_remaining

        unrealized_gain = current_value - fifo.cost_remaining
        realized_gain = fifo.realized_gain
        total_gain = unrealized_gain + realized_gain

        pct_gain = (total_gain / net_invested * 100) if net_invested != 0 else None

        if units_held == 0:
            status = "Redeemed"
        elif total_gain > 0:
            status = "In Profit"
        elif total_gain < 0:
            status = "In Loss"
        else:
            status = "Flat"

        xirr = scheme_xirr(
            [(t.transaction_date, t.signed_amount) for t in scheme_txns], current_value, as_of
        )

        display_name = display_name_for(
            db, user.id, scheme_code, full_scheme_name(scheme) if scheme else scheme_code
        )

        holdings.append(
            SchemeHolding(
                scheme_code=scheme_code,
                display_name=display_name,
                net_units=units_held,
                net_invested=net_invested,
                avg_cost_nav=fifo.avg_cost_nav,
                latest_nav=latest_nav,
                nav_date=nav_date,
                nav_source=nav_source,
                current_value=current_value,
                unrealized_gain=unrealized_gain,
                realized_gain=realized_gain,
                total_gain=total_gain,
                pct_gain=pct_gain,
                status=status,
                xirr=xirr,
            )
        )

    holdings.sort(key=lambda h: h.display_name)
    return holdings


def compute_holdings(db: Session, user: User, *, as_of: date | None = None) -> list[SchemeHolding]:
    as_of = as_of or date.today()

    account_ids = [a.id for a in db.query(Account.id).filter(Account.user_id == user.id).all()]
    if not account_ids:
        return []

    rows = (
        db.query(Transaction)
        .filter(Transaction.account_id.in_(account_ids), Transaction.is_deleted.is_(False))
        .all()
    )
    scheme_codes = {r.scheme_code for r in rows}
    schemes = {s.scheme_code: s for s in db.query(Scheme).filter(Scheme.scheme_code.in_(scheme_codes)).all()}

    return _build_scheme_holdings(db, user, rows, schemes, as_of)


def compute_account_breakdown(db: Session, user: User, *, as_of: date | None = None) -> list[AccountHoldings]:
    """Same ledger, sliced the other way: one group per account, each holding
    only that account's own schemes. Every number here (net invested, current
    value, gain/loss, XIRR) is computed from that account's transactions
    alone - it is not the portfolio-wide per-scheme figure split by account,
    it's genuinely recomputed at the account level, so the schemes list under
    each account sums to that account's own totals.
    """
    as_of = as_of or date.today()

    accounts = db.query(Account).filter(Account.user_id == user.id).order_by(Account.account_name).all()
    if not accounts:
        return []

    account_ids = [a.id for a in accounts]
    rows = (
        db.query(Transaction)
        .filter(Transaction.account_id.in_(account_ids), Transaction.is_deleted.is_(False))
        .all()
    )
    scheme_codes = {r.scheme_code for r in rows}
    schemes = {s.scheme_code: s for s in db.query(Scheme).filter(Scheme.scheme_code.in_(scheme_codes)).all()}

    by_account_id: dict[int, list[Transaction]] = {}
    for r in rows:
        by_account_id.setdefault(r.account_id, []).append(r)

    breakdown: list[AccountHoldings] = []
    for account in accounts:
        acc_txns = by_account_id.get(account.id)
        if not acc_txns:
            continue  # nothing invested through this account - skip it, not a zero row

        scheme_holdings = _build_scheme_holdings(db, user, acc_txns, schemes, as_of)

        net_invested = sum((h.net_invested for h in scheme_holdings), Decimal("0"))
        current_value = sum((h.current_value for h in scheme_holdings), Decimal("0"))
        net_gain_loss = sum((h.unrealized_gain for h in scheme_holdings), Decimal("0"))
        pct_gain = (net_gain_loss / net_invested * 100) if net_invested != 0 else None

        flows = [(t.transaction_date, t.signed_amount) for t in acc_txns]
        xirr = scheme_xirr(flows, current_value, as_of)

        breakdown.append(
            AccountHoldings(
                account_id=account.id,
                account_name=account.account_name,
                net_invested=net_invested,
                current_value=current_value,
                net_gain_loss=net_gain_loss,
                pct_gain=pct_gain,
                xirr=xirr,
                schemes=scheme_holdings,
            )
        )

    return breakdown


def compute_dashboard(db: Session, user: User, *, as_of: date | None = None) -> DashboardSummary:
    as_of = as_of or date.today()
    holdings = compute_holdings(db, user, as_of=as_of)

    net_invested = sum((h.net_invested for h in holdings), Decimal("0"))
    current_value = sum((h.current_value for h in holdings), Decimal("0"))
    # Unrealized only (current_value - cost of units still held). Gains
    # booked from past redemptions are reported separately as
    # total_realized_gain so the two aren't blended in one number.
    net_gain_loss = sum((h.unrealized_gain for h in holdings), Decimal("0"))
    total_realized_gain = sum((h.realized_gain for h in holdings), Decimal("0"))
    total_return_pct = (net_gain_loss / net_invested * 100) if net_invested != 0 else None
    active_schemes = sum(1 for h in holdings if h.net_units > 0)

    account_ids = [a.id for a in db.query(Account.id).filter(Account.user_id == user.id).all()]
    total_commission_paid = (
        db.query(Transaction)
        .filter(Transaction.account_id.in_(account_ids), Transaction.is_deleted.is_(False))
        .with_entities(Transaction.commission)
        .all()
    )
    total_commission_paid = sum((c[0] for c in total_commission_paid), Decimal("0"))

    # Portfolio XIRR: every scheme's flows concatenated, plus one synthetic
    # total-current-value flow (not one per scheme - a single flow keeps
    # the portfolio-level result matching what you'd get selling everything
    # on the same day, rather than pyxirr solving as if each scheme's
    # current value could be realized on a different notional trade).
    account_ids_set = account_ids
    rows = (
        db.query(Transaction)
        .filter(Transaction.account_id.in_(account_ids_set), Transaction.is_deleted.is_(False))
        .all()
    )
    all_flows = [(t.transaction_date, t.signed_amount) for t in rows]
    portfolio_xirr = scheme_xirr(all_flows, current_value, as_of)

    nav_as_of = max((h.nav_date for h in holdings if h.net_units > 0 and h.nav_date), default=None)

    by_account = compute_account_breakdown(db, user, as_of=as_of)

    return DashboardSummary(
        net_invested=net_invested,
        current_value=current_value,
        net_gain_loss=net_gain_loss,
        total_realized_gain=total_realized_gain,
        total_return_pct=total_return_pct,
        active_schemes=active_schemes,
        total_commission_paid=total_commission_paid,
        portfolio_xirr=portfolio_xirr,
        nav_as_of=nav_as_of,
        holdings=holdings,
        by_account=by_account,
    )
