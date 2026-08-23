"""SIP due-entry workflow: nothing is ever written automatically.

Occurrences are projected on read from the SIP mandate + trading calendar
(see app/services/sip_schedule.py) and diffed against what's already
confirmed or explicitly skipped. A transaction is written only when the
user supplies the real NAV and units from their statement and confirms -
see confirm_entry, which reuses services.transactions.create_transaction
so commission derivation and redemption validation stay in one place.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.account import Account
from models.enums import TransactionSource, TransactionType
from models.scheme import Scheme
from models.sip import Sip
from models.sip_skip import SipSkip
from models.transaction import Transaction
from models.user import User
from services.charges import InvalidCommissionError
from services.scheme_names import display_name_for, full_scheme_name
from services.sip_schedule import generate_schedule
from services.trading_calendar import load_holidays, next_trading_day
from services.transactions import DuplicateTransactionError, OverRedemptionError, create_transaction

# How far past `as_of` to project for the "upcoming" view. 120 days safely
# covers several occurrences at either supported frequency.
_UPCOMING_HORIZON_DAYS = 120


@dataclass(frozen=True, slots=True)
class DueEntry:
    sip_id: int
    account_id: int
    account_name: str
    scheme_code: str
    display_name: str
    scheduled_date: date
    adjusted_date: date
    expected_amount: Decimal
    folio_no: str | None
    calendar_complete: bool


@dataclass(frozen=True, slots=True)
class UpcomingOccurrence:
    sip_id: int
    account_name: str
    scheme_code: str
    display_name: str
    scheduled_date: date
    adjusted_date: date
    amount: Decimal


class SipNotFoundError(ValueError):
    pass


def _own_account_ids(db: Session, user: User) -> list[int]:
    return [a.id for a in db.query(Account.id).filter(Account.user_id == user.id).all()]


def _get_owned_sip(db: Session, user: User, sip_id: int) -> Sip:
    sip = db.get(Sip, sip_id)
    if sip is None or sip.account_id not in _own_account_ids(db, user):
        raise SipNotFoundError(f"SIP {sip_id} not found")
    return sip


def _confirmed_keys(db: Session, sip_ids: list[int]) -> set[tuple[int, date]]:
    """Occurrences that already have an ACTIVE transaction - a soft-deleted
    one doesn't count, so deleting a confirmed SIP entry correctly brings it
    back onto the due list rather than leaving it permanently confirmed.
    Re-confirming it goes through create_transaction's own restore-not-
    duplicate handling (services/transactions.py), so this composes
    correctly rather than fighting that logic.
    """
    if not sip_ids:
        return set()
    rows = (
        db.query(Transaction.sip_id, Transaction.sip_scheduled_date)
        .filter(Transaction.sip_id.in_(sip_ids), Transaction.is_deleted.is_(False))
        .all()
    )
    return {(sip_id, d) for sip_id, d in rows}


def _skipped_keys(db: Session, sip_ids: list[int]) -> set[tuple[int, date]]:
    if not sip_ids:
        return set()
    rows = db.query(SipSkip.sip_id, SipSkip.scheduled_date).filter(SipSkip.sip_id.in_(sip_ids)).all()
    return {(sip_id, d) for sip_id, d in rows}


def due_entries(db: Session, user: User, *, as_of: date | None = None) -> list[DueEntry]:
    as_of = as_of or date.today()
    account_ids = _own_account_ids(db, user)
    sips = (
        db.query(Sip)
        .filter(Sip.account_id.in_(account_ids), Sip.is_active.is_(True))
        .all()
    )
    if not sips:
        return []

    holidays = load_holidays(db)
    years_with_calendar = {d.year for d in holidays}
    confirmed = _confirmed_keys(db, [s.id for s in sips])
    skipped = _skipped_keys(db, [s.id for s in sips])
    accounts = {a.id: a for a in db.query(Account).filter(Account.id.in_(account_ids)).all()}
    schemes = {s.scheme_code: s for s in db.query(Scheme).filter(
        Scheme.scheme_code.in_({s.scheme_code for s in sips})
    ).all()}

    due: list[DueEntry] = []
    for sip in sips:
        occurrences = generate_schedule(
            frequency=sip.frequency,
            start_date=sip.start_date,
            end_date=sip.end_date,
            until=as_of,
            holidays=holidays,
            years_with_calendar=years_with_calendar,
        )
        for occ in occurrences:
            if occ.adjusted_date > as_of:
                continue
            key = (sip.id, occ.scheduled_date)
            if key in confirmed or key in skipped:
                continue
            scheme = schemes.get(sip.scheme_code)
            due.append(
                DueEntry(
                    sip_id=sip.id,
                    account_id=sip.account_id,
                    account_name=accounts[sip.account_id].account_name,
                    scheme_code=sip.scheme_code,
                    display_name=display_name_for(
                        db, user.id, sip.scheme_code, full_scheme_name(scheme) if scheme else sip.scheme_code
                    ),
                    scheduled_date=occ.scheduled_date,
                    adjusted_date=occ.adjusted_date,
                    expected_amount=sip.amount,
                    folio_no=sip.folio_no,
                    calendar_complete=occ.calendar_complete,
                )
            )

    due.sort(key=lambda e: (e.adjusted_date, e.account_name, e.display_name))
    return due


def due_count(db: Session, user: User, *, as_of: date | None = None) -> int:
    return len(due_entries(db, user, as_of=as_of))


def confirm_entry(
    db: Session,
    user: User,
    *,
    sip_id: int,
    scheduled_date: date,
    nav: Decimal,
    units: Decimal,
    transaction_date: date | None = None,
) -> Transaction:
    """Amount is taken from the SIP mandate (not user-entered - the mandate
    debits a fixed sum); commission falls out of create_transaction's shared
    derivation. The unique (sip_id, sip_scheduled_date) index makes a
    double-submit return the already-confirmed row instead of erroring.

    transaction_date lets the user override the system's trading-day-
    adjusted guess with whatever date their actual statement shows -
    scheduled_date (the idempotency key) is untouched either way, so
    editing the date can never create a duplicate or break re-confirm
    idempotency.
    """
    sip = _get_owned_sip(db, user, sip_id)
    holidays = load_holidays(db)
    resolved_date = transaction_date or next_trading_day(scheduled_date, holidays)

    try:
        return create_transaction(
            db,
            account_id=sip.account_id,
            scheme_code=sip.scheme_code,
            transaction_date=resolved_date,
            type=TransactionType.PURCHASE,
            nav=nav,
            units=units,
            amount=sip.amount,
            folio_no=sip.folio_no,
            source=TransactionSource.SIP,
            sip_id=sip.id,
            sip_scheduled_date=scheduled_date,
        )
    except IntegrityError:
        db.rollback()
        existing = (
            db.query(Transaction)
            .filter(Transaction.sip_id == sip.id, Transaction.sip_scheduled_date == scheduled_date)
            .first()
        )
        if existing is not None:
            return existing
        raise
    except DuplicateTransactionError as exc:
        # create_transaction's own (account_id, source_hash) check can fire
        # before the IntegrityError case above ever would, on a re-confirm
        # of the exact same occurrence with the exact same NAV/units - same
        # idempotent outcome, just caught one step earlier.
        existing = db.get(Transaction, exc.existing_id)
        if existing is not None and existing.sip_id == sip.id and existing.sip_scheduled_date == scheduled_date:
            return existing
        raise


def skip_entry(
    db: Session, user: User, *, sip_id: int, scheduled_date: date, reason: str | None = None
) -> SipSkip:
    sip = _get_owned_sip(db, user, sip_id)
    skip = SipSkip(sip_id=sip.id, scheduled_date=scheduled_date, reason=reason)
    db.add(skip)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = (
            db.query(SipSkip)
            .filter(SipSkip.sip_id == sip.id, SipSkip.scheduled_date == scheduled_date)
            .first()
        )
        if existing is not None:
            return existing
        raise
    db.refresh(skip)
    return skip


def hold_sip(db: Session, user: User, *, sip_id: int) -> Sip:
    """Pauses a SIP without ending it - no new due entries or upcoming
    projections while held (both already filter on is_active), but the
    mandate's own terms (amount, frequency, start_date) are untouched, so
    resuming picks up exactly where it left off. Distinct from stop: a
    held SIP records no end_date, since it isn't over - just paused.
    """
    sip = _get_owned_sip(db, user, sip_id)
    sip.is_active = False
    db.commit()
    db.refresh(sip)
    return sip


def resume_sip(db: Session, user: User, *, sip_id: int) -> Sip:
    """Reactivates a held or stopped SIP. Always clears end_date - resuming
    a SIP that was stopped as of some past date but leaving that end_date
    in place would reactivate it into a state that generates no due
    entries at all (generate_schedule has nothing to produce once
    start_date > end_date), which would look identical to still being
    paused. A fresh resume is perpetual again unless re-stopped or edited.
    """
    sip = _get_owned_sip(db, user, sip_id)
    sip.is_active = True
    sip.end_date = None
    db.commit()
    db.refresh(sip)
    return sip


def stop_sip(db: Session, user: User, *, sip_id: int, end_date: date | None = None) -> Sip:
    """Permanently ends a SIP as of end_date (default: today) - the mandate
    itself is the historical record of when it ran, so this is a direct
    mutation rather than a close-and-clone: there's no successor row to
    create, unlike editing terms (see close_and_clone).
    """
    sip = _get_owned_sip(db, user, sip_id)
    resolved_end = end_date or date.today()
    if resolved_end < sip.start_date:
        raise ValueError(f"End date {resolved_end} is before this SIP's start date {sip.start_date}.")
    sip.end_date = resolved_end
    sip.is_active = False
    db.commit()
    db.refresh(sip)
    return sip


def close_and_clone(
    db: Session,
    user: User,
    *,
    sip_id: int,
    effective_date: date,
    amount: Decimal | None = None,
    frequency: str | None = None,
    folio_no: str | None = None,
) -> Sip:
    """The versioning strategy for editing an active SIP: the old row is
    closed (end_date set the day before the change takes effect) rather
    than mutated, and a new row picks up from effective_date - so exactly
    what was scheduled at any point in the past stays reconstructable.
    """
    old = _get_owned_sip(db, user, sip_id)
    old.end_date = effective_date - timedelta(days=1)
    old.is_active = False

    new = Sip(
        account_id=old.account_id,
        scheme_code=old.scheme_code,
        amount=amount if amount is not None else old.amount,
        frequency=frequency if frequency is not None else old.frequency,
        start_date=effective_date,
        end_date=None,
        folio_no=folio_no if folio_no is not None else old.folio_no,
        is_active=True,
        parent_sip_id=old.id,
    )
    db.add(new)
    db.commit()
    db.refresh(new)
    return new


def project_upcoming(db: Session, user: User, *, n: int = 5) -> list[UpcomingOccurrence]:
    """Future occurrences, read-only - never written to the database."""
    as_of = date.today()
    horizon = as_of + timedelta(days=_UPCOMING_HORIZON_DAYS)
    account_ids = _own_account_ids(db, user)
    sips = db.query(Sip).filter(Sip.account_id.in_(account_ids), Sip.is_active.is_(True)).all()
    if not sips:
        return []

    holidays = load_holidays(db)
    years_with_calendar = {d.year for d in holidays}
    accounts = {a.id: a for a in db.query(Account).filter(Account.id.in_(account_ids)).all()}
    schemes = {s.scheme_code: s for s in db.query(Scheme).filter(
        Scheme.scheme_code.in_({s.scheme_code for s in sips})
    ).all()}

    results: list[UpcomingOccurrence] = []
    for sip in sips:
        occurrences = generate_schedule(
            frequency=sip.frequency,
            start_date=sip.start_date,
            end_date=sip.end_date,
            until=horizon,
            holidays=holidays,
            years_with_calendar=years_with_calendar,
        )
        future = [o for o in occurrences if o.adjusted_date > as_of][:n]
        scheme = schemes.get(sip.scheme_code)
        for occ in future:
            results.append(
                UpcomingOccurrence(
                    sip_id=sip.id,
                    account_name=accounts[sip.account_id].account_name,
                    scheme_code=sip.scheme_code,
                    display_name=display_name_for(
                        db, user.id, sip.scheme_code, full_scheme_name(scheme) if scheme else sip.scheme_code
                    ),
                    scheduled_date=occ.scheduled_date,
                    adjusted_date=occ.adjusted_date,
                    amount=sip.amount,
                )
            )

    results.sort(key=lambda r: r.adjusted_date)
    return results[:n]
