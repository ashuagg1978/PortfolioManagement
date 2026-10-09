"""Create/update/soft-delete for confirmed transactions.

Every write here derives commission and signed_amount rather than trusting
the caller to have computed them (see app/services/charges.py), and
validates a redemption against actual units held before it is allowed to
touch the ledger.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from models.account import Account
from models.enums import TransactionSource, TransactionType
from models.portfolio_scheme import PortfolioScheme
from models.scheme import Scheme
from models.transaction import Transaction
from models.user import User
from services.charges import compute_commission, compute_signed_amount
from services.fifo import LedgerEntry, run_fifo
from services.scheme_names import display_name_for, full_scheme_name

_AMOUNT_QUANT = Decimal("0.01")  # matches db.types.Money's 2dp
_UNITS_QUANT = Decimal("0.000001")  # matches db.types.Units's 6dp


class OverRedemptionError(ValueError):
    """Raised when a REDEMPTION would sell more units than are held in the
    given (account, scheme, folio) at the time of the transaction.
    """


class DuplicateTransactionError(ValueError):
    """Raised when an ACTIVE (not soft-deleted) transaction already exists
    with the same (account_id, source_hash). A soft-deleted match is not an
    error - see create_transaction: it's restored instead, so re-entering a
    transaction you'd previously deleted (by hand, or via a repeat import)
    brings it back rather than being silently blocked forever by its own
    old, deleted row still occupying the uniqueness slot.
    """

    def __init__(self, existing_id: int) -> None:
        self.existing_id = existing_id
        super().__init__(
            f"A transaction with these exact details already exists (id={existing_id})."
        )


def compute_source_hash(
    *,
    account_id: int,
    scheme_code: str,
    transaction_date: date,
    type: str,
    amount: Decimal,
    units: Decimal,
    folio_no: str | None,
) -> str:
    """Dedupe key. Prefer the broker's own Transaction ID when the caller
    has one (pass it as folio_no-adjacent context via the importer instead -
    this fallback hash is for manual entry and any statement without a
    stable transaction id).

    amount/units are quantized to the same precision the Money/Units DB
    columns use before hashing, regardless of the precision the caller
    happened to pass in. Without this, the same logical value hashes
    differently depending on whether it arrived fresh (e.g. Decimal("120.5")
    parsed from a spreadsheet cell) or after a DB round-trip (which
    quantizes to Decimal("120.50")) - breaking dedupe/restore matching
    between a fresh import and the transaction it should recognize as the
    same one.
    """
    amount_q = amount.quantize(_AMOUNT_QUANT, rounding=ROUND_HALF_UP)
    units_q = units.quantize(_UNITS_QUANT, rounding=ROUND_HALF_UP)
    raw = f"{account_id}|{scheme_code}|{transaction_date.isoformat()}|{type}|{amount_q}|{units_q}|{folio_no or ''}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _units_held(
    db: Session,
    account_id: int,
    scheme_code: str,
    folio_no: str | None,
    before_date: date | None = None,
    exclude_transaction_id: int | None = None,
) -> Decimal:
    query = db.query(Transaction).filter(
        Transaction.account_id == account_id,
        Transaction.scheme_code == scheme_code,
        Transaction.is_deleted.is_(False),
    )
    # A blank folio (e.g. the manual-entry form's optional field) means
    # "any folio" - imported rows carry a folio number, so matching only
    # NULL folios would report 0 units held.
    if folio_no:
        query = query.filter(Transaction.folio_no == folio_no)
    if before_date is not None:
        query = query.filter(Transaction.transaction_date <= before_date)
    if exclude_transaction_id is not None:
        query = query.filter(Transaction.id != exclude_transaction_id)
    rows = query.all()
    if not rows:
        return Decimal("0")
    entries = [
        LedgerEntry(id=r.id, date=r.transaction_date, type=r.type, units=r.units, amount=r.amount)
        for r in rows
    ]
    return run_fifo(entries).units_held


def _hash_taken(db: Session, account_id: int, source_hash: str) -> bool:
    return (
        db.query(Transaction.id)
        .filter(Transaction.account_id == account_id, Transaction.source_hash == source_hash)
        .first()
        is not None
    )


def create_transaction(
    db: Session,
    *,
    account_id: int,
    scheme_code: str,
    transaction_date: date,
    type: str,
    nav: Decimal,
    units: Decimal,
    amount: Decimal,
    folio_no: str | None = None,
    source: str = TransactionSource.MANUAL,
    sip_id: int | None = None,
    sip_scheduled_date: date | None = None,
    commission_tolerance: Decimal = Decimal("0"),
    allow_duplicate: bool = False,
) -> Transaction:
    """Creates a transaction - or, if one with these exact details was
    previously soft-deleted, restores it instead of erroring. The unique
    (account_id, source_hash) index has no exemption for is_deleted rows,
    so without this check re-entering something you'd deleted (by hand, or
    via a repeat statement import) would otherwise be permanently blocked
    by its own old row. An ACTIVE match raises DuplicateTransactionError,
    unless allow_duplicate is set (the user confirmed it's intentional) -
    then the row is stored under a unique salted hash instead.
    """
    # raises InvalidCommissionError beyond commission_tolerance (see
    # services/charges.py for why the importer passes a small nonzero
    # tolerance here while manual/SIP entry stay strict at 0).
    commission = compute_commission(type, nav, units, amount, tolerance=commission_tolerance)
    signed_amount = compute_signed_amount(type, amount)

    if type == TransactionType.REDEMPTION:
        held = _units_held(db, account_id, scheme_code, folio_no, before_date=transaction_date)
        if units > held:
            raise OverRedemptionError(
                f"Cannot redeem {units} units - only {held} units held in this "
                f"account/scheme/folio as of {transaction_date}."
            )

    source_hash = compute_source_hash(
        account_id=account_id,
        scheme_code=scheme_code,
        transaction_date=transaction_date,
        type=type,
        amount=amount,
        units=units,
        folio_no=folio_no,
    )

    existing = (
        db.query(Transaction)
        .filter(Transaction.account_id == account_id, Transaction.source_hash == source_hash)
        .first()
    )
    if existing is not None:
        if not existing.is_deleted:
            if not allow_duplicate:
                raise DuplicateTransactionError(existing.id)
            existing = None
    if existing is not None:
        existing.is_deleted = False
        existing.scheme_code = scheme_code
        existing.transaction_date = transaction_date
        existing.type = type
        existing.source = source
        existing.sip_id = sip_id
        existing.sip_scheduled_date = sip_scheduled_date
        existing.amount = amount
        existing.nav = nav
        existing.units = units
        existing.commission = commission
        existing.signed_amount = signed_amount
        existing.folio_no = folio_no
        db.commit()
        db.refresh(existing)
        return existing

    if existing is None and allow_duplicate and _hash_taken(db, account_id, source_hash):
        source_hash = hashlib.sha256(f"{source_hash}|dup|{uuid.uuid4()}".encode("utf-8")).hexdigest()

    txn = Transaction(
        account_id=account_id,
        scheme_code=scheme_code,
        transaction_date=transaction_date,
        type=type,
        source=source,
        sip_id=sip_id,
        sip_scheduled_date=sip_scheduled_date,
        amount=amount,
        nav=nav,
        units=units,
        commission=commission,
        signed_amount=signed_amount,
        folio_no=folio_no,
        source_hash=source_hash,
    )
    db.add(txn)
    db.commit()
    db.refresh(txn)
    return txn


def update_transaction(
    db: Session,
    txn: Transaction,
    *,
    transaction_date: date,
    nav: Decimal,
    units: Decimal,
    amount: Decimal,
    folio_no: str | None,
) -> Transaction:
    """Edits a manual transaction in place. SIP-sourced and imported rows
    can still be edited here (the immutability that matters is the
    idempotency key, not the row itself) - callers may choose to restrict
    that at the route/UI level.
    """
    commission = compute_commission(txn.type, nav, units, amount)
    signed_amount = compute_signed_amount(txn.type, amount)

    if txn.type == TransactionType.REDEMPTION:
        held = _units_held(
            db,
            txn.account_id,
            txn.scheme_code,
            folio_no,
            before_date=transaction_date,
            exclude_transaction_id=txn.id,
        )
        if units > held:
            raise OverRedemptionError(
                f"Cannot redeem {units} units - only {held} units held in this "
                f"account/scheme/folio as of {transaction_date} (excluding this transaction)."
            )

    txn.transaction_date = transaction_date
    txn.nav = nav
    txn.units = units
    txn.amount = amount
    txn.folio_no = folio_no
    txn.commission = commission
    txn.signed_amount = signed_amount
    txn.source_hash = compute_source_hash(
        account_id=txn.account_id,
        scheme_code=txn.scheme_code,
        transaction_date=transaction_date,
        type=txn.type,
        amount=amount,
        units=units,
        folio_no=folio_no,
    )
    db.commit()
    db.refresh(txn)
    return txn


def soft_delete_transaction(db: Session, txn: Transaction) -> Transaction:
    txn.is_deleted = True
    db.commit()
    db.refresh(txn)
    return txn


def restore_transaction(db: Session, txn: Transaction) -> Transaction:
    txn.is_deleted = False
    db.commit()
    db.refresh(txn)
    return txn


@dataclass(frozen=True, slots=True)
class TransactionFilters:
    account_id: int | None = None
    scheme_code: str | None = None
    # Free-text: matches the AMFI scheme name, the user's own display name,
    # or the scheme code itself - lets the ledger page's search box work
    # without first resolving to an exact code via the scheme picker.
    scheme_name: str | None = None
    type: str | None = None
    source: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    include_deleted: bool = False


def _scheme_codes_matching_name(db: Session, user_id: int, q: str) -> list[str]:
    like = f"%{q}%"
    from_schemes = db.query(Scheme.scheme_code).filter(Scheme.scheme_name.ilike(like))
    from_display_names = db.query(PortfolioScheme.scheme_code).filter(
        PortfolioScheme.user_id == user_id, PortfolioScheme.display_name.ilike(like)
    )
    return [c for (c,) in from_schemes.union(from_display_names).all()]


def _filtered_query(db: Session, user: User, filters: TransactionFilters):
    account_ids = [a.id for a in db.query(Account.id).filter(Account.user_id == user.id).all()]
    query = db.query(Transaction).filter(Transaction.account_id.in_(account_ids))

    if not filters.include_deleted:
        query = query.filter(Transaction.is_deleted.is_(False))
    if filters.account_id is not None:
        query = query.filter(Transaction.account_id == filters.account_id)
    if filters.scheme_code is not None:
        query = query.filter(Transaction.scheme_code == filters.scheme_code)
    if filters.scheme_name:
        matching_codes = _scheme_codes_matching_name(db, user.id, filters.scheme_name)
        code_condition = Transaction.scheme_code.in_(matching_codes) if matching_codes else False
        query = query.filter(or_(Transaction.scheme_code.ilike(f"%{filters.scheme_name}%"), code_condition))
    if filters.type is not None:
        query = query.filter(Transaction.type == filters.type)
    if filters.source is not None:
        query = query.filter(Transaction.source == filters.source)
    if filters.date_from is not None:
        query = query.filter(Transaction.transaction_date >= filters.date_from)
    if filters.date_to is not None:
        query = query.filter(Transaction.transaction_date <= filters.date_to)
    return query


def list_transactions(
    db: Session,
    user: User,
    filters: TransactionFilters,
    *,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Transaction], int]:
    """Returns (page of transactions, total matching count) - the count
    query mirrors every filter but not limit/offset, so pagination controls
    know how many pages exist.
    """
    query = _filtered_query(db, user, filters)
    total = query.with_entities(func.count(Transaction.id)).scalar() or 0
    rows = (
        query.order_by(Transaction.transaction_date.desc(), Transaction.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return rows, total


def list_all_matching_transactions(
    db: Session, user: User, filters: TransactionFilters
) -> list[Transaction]:
    """Every transaction matching the filters, unpaginated - for the Excel
    export, which should cover the full filtered result set rather than
    just whatever page the ledger happens to be showing. Chronological
    ascending (oldest first), unlike the ledger's newest-first view - a
    spreadsheet export reads more naturally as a running history.
    """
    return _filtered_query(db, user, filters).order_by(
        Transaction.transaction_date.asc(), Transaction.id.asc()
    ).all()


class _HasAccountAndScheme(Protocol):
    id: int
    account_id: int
    scheme_code: str


def enrich_display_names(
    db: Session, user: User, rows: Sequence[_HasAccountAndScheme]
) -> dict[int, tuple[str, str]]:
    """Maps row id -> (account_name, scheme_display_name), resolved per
    unique account/scheme rather than per row (a page is at most a few
    dozen rows, but typically holds far fewer distinct accounts/schemes).

    Works for anything with (id, account_id, scheme_code) - Transaction and
    Sip both qualify, so this is shared between the ledger and SIP list
    rather than duplicated.
    """
    if not rows:
        return {}
    account_names = {
        a.id: a.account_name
        for a in db.query(Account).filter(Account.id.in_({r.account_id for r in rows})).all()
    }
    scheme_names = {
        s.scheme_code: full_scheme_name(s)
        for s in db.query(Scheme).filter(Scheme.scheme_code.in_({r.scheme_code for r in rows})).all()
    }
    display_names = {
        code: display_name_for(db, user.id, code, scheme_names.get(code, code))
        for code in {r.scheme_code for r in rows}
    }
    return {
        r.id: (account_names.get(r.account_id, "—"), display_names.get(r.scheme_code, r.scheme_code))
        for r in rows
    }
