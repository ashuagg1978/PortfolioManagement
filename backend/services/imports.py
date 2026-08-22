"""Two-phase import pipeline: stage (parse + persist rows for preview) ->
resolve mappings -> commit (write real transactions).

Parsed rows are persisted in import_rows rather than held in server memory -
that's what lets preview and commit be two separate, stateless HTTP calls,
and doubles as an audit trail / a place to resume resolving unmapped
schemes without re-uploading the file.

The target account is chosen once on the upload screen and applies to every
row in the batch (see stage_import) - a statement is one account's history,
not several interleaved.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.account import Account
from models.enums import ImportBatchStatus, ImportRowAction, TransactionSource
from models.import_batch import ImportBatch
from models.import_row import ImportRow
from models.portfolio_scheme import PortfolioScheme
from models.scheme import Scheme
from models.scheme_alias import SchemeAlias
from models.transaction import Transaction
from models.user import User
from services.charges import InvalidCommissionError
from services.importers.excel_workbook import WorkbookParseResult, parse_workbook
from services.transactions import (
    DuplicateTransactionError,
    OverRedemptionError,
    compute_source_hash,
    create_transaction,
)


class ImportBatchNotFoundError(ValueError):
    pass


class AccountNotFoundError(ValueError):
    pass


def _ensure_scheme_placeholder(db: Session, scheme_code: str, scheme_name: str) -> None:
    """A scheme_alias/portfolio_scheme row needs its scheme_code to already
    exist in the global `schemes` table (FK). Inserts a bare placeholder
    (no NAV yet) if a sync hasn't reached this code yet - the next NAV sync
    fills in latest_nav/nav_date on top of it.
    """
    if db.get(Scheme, scheme_code) is None:
        db.add(Scheme(scheme_code=scheme_code, scheme_name=scheme_name))
        db.flush()


def _seed_mappings_from_workbook(
    db: Session, user: User, nav_ref_by_display: dict[str, str], scheme_map: list
) -> None:
    """Applies a workbook's own Scheme Map + NAV Reference sheets, if
    present, as global (not batch-scoped) scheme_aliases/portfolio_schemes -
    this is reusable name -> code knowledge, not ledger data, so it's
    seeded immediately rather than gated behind commit.
    """
    for entry in scheme_map:
        code = nav_ref_by_display.get(entry.display_scheme)
        if not code:
            continue
        _ensure_scheme_placeholder(db, code, entry.display_scheme)
        exists = (
            db.query(SchemeAlias)
            .filter(SchemeAlias.user_id == user.id, SchemeAlias.raw_name == entry.raw_name)
            .first()
        )
        if exists is None:
            db.add(SchemeAlias(user_id=user.id, raw_name=entry.raw_name, scheme_code=code))

    for display, code in nav_ref_by_display.items():
        _ensure_scheme_placeholder(db, code, display)
        exists = (
            db.query(PortfolioScheme)
            .filter(PortfolioScheme.user_id == user.id, PortfolioScheme.scheme_code == code)
            .first()
        )
        if exists is None:
            db.add(PortfolioScheme(user_id=user.id, scheme_code=code, display_name=display))
    db.flush()


def _unmapped_key(raw_scheme_name: str | None, scheme_code_hint: str | None) -> str:
    """The single identifier the unmapped-scheme resolution UI groups and
    matches on. Almost always the raw name; falls back to the attempted
    code when a row has a scheme code that doesn't exist yet but no name at
    all, so that case is still visible and resolvable rather than silently
    swallowed into an unlabeled bucket.
    """
    if raw_scheme_name:
        return raw_scheme_name
    if scheme_code_hint:
        return f"[unknown scheme code {scheme_code_hint}]"
    return "[no scheme identified]"


def _resolve_scheme(
    db: Session,
    *,
    raw_scheme_name: str | None,
    scheme_code_hint: str | None,
    user_aliases: dict[str, str],
    nav_ref_by_display: dict[str, str],
) -> str | None:
    """Priority: an explicit, valid Scheme Code column wins outright (it's
    the authoritative AMFI identifier - see DATABASE.md#schemes on why
    names alone are ambiguous). Falls back to name-based resolution via
    previously-learned aliases or a workbook's own NAV Reference sheet.
    """
    if scheme_code_hint and db.get(Scheme, scheme_code_hint) is not None:
        return scheme_code_hint
    if raw_scheme_name:
        return user_aliases.get(raw_scheme_name) or nav_ref_by_display.get(raw_scheme_name)
    return None


@dataclass(frozen=True, slots=True)
class StageResult:
    batch: ImportBatch
    sheet_used: str | None
    other_sheets_ignored: list[str]


def stage_import(
    db: Session, user: User, filename: str, file_bytes: bytes, account_id: int
) -> StageResult:
    account = db.get(Account, account_id)
    if account is None or account.user_id != user.id:
        raise AccountNotFoundError(f"Account {account_id} not found")

    result: WorkbookParseResult = parse_workbook(file_bytes)
    nav_ref_by_display = {e.display_scheme: e.scheme_code for e in result.nav_reference if e.scheme_code}
    _seed_mappings_from_workbook(db, user, nav_ref_by_display, result.scheme_map)

    user_aliases = {
        a.raw_name: a.scheme_code
        for a in db.query(SchemeAlias).filter(SchemeAlias.user_id == user.id).all()
    }

    batch = ImportBatch(
        user_id=user.id, account_id=account.id, filename=filename, status=ImportBatchStatus.PENDING
    )
    db.add(batch)
    db.flush()

    for row in result.rows:
        resolved_code = _resolve_scheme(
            db,
            raw_scheme_name=row.raw_scheme_name,
            scheme_code_hint=row.scheme_code_hint,
            user_aliases=user_aliases,
            nav_ref_by_display=nav_ref_by_display,
        )

        if row.error:
            action = ImportRowAction.ERROR
        elif resolved_code is None:
            action = ImportRowAction.UNMAPPED
        else:
            action = ImportRowAction.NEW
            # Best-effort early dedupe so the preview shows DUPLICATE
            # honestly instead of only discovering it at commit. A match
            # that's soft-deleted is NOT a duplicate - create_transaction
            # will restore it at commit instead (see services/transactions.py).
            if row.type and row.transaction_date:
                source_hash = compute_source_hash(
                    account_id=account.id,
                    scheme_code=resolved_code,
                    transaction_date=row.transaction_date,
                    type=row.type,
                    amount=row.amount,
                    units=row.units,
                    folio_no=row.folio_no,
                )
                dup = (
                    db.query(Transaction)
                    .filter(Transaction.account_id == account.id, Transaction.source_hash == source_hash)
                    .first()
                )
                if dup is not None and not dup.is_deleted:
                    action = ImportRowAction.DUPLICATE

        db.add(
            ImportRow(
                batch_id=batch.id,
                row_index=row.row_index,
                sheet_name=row.sheet_name,
                raw_json=json.dumps(row.raw, default=str),
                account_name=account.account_name,
                raw_scheme_name=row.raw_scheme_name,
                scheme_code_hint=row.scheme_code_hint,
                resolved_scheme_code=resolved_code,
                transaction_date=row.transaction_date,
                type=row.type,
                amount=row.amount,
                nav=row.nav,
                units=row.units,
                folio_no=row.folio_no,
                action=action,
                error=row.error,
            )
        )

    db.commit()
    db.refresh(batch)
    return StageResult(
        batch=batch, sheet_used=result.sheet_used, other_sheets_ignored=result.other_sheets_ignored
    )


@dataclass(frozen=True, slots=True)
class BatchSummary:
    batch: ImportBatch
    account: Account | None  # plain lookup, not an ORM relationship - this codebase queries explicitly
    row_count: int
    action_counts: dict[str, int]
    unmapped_scheme_keys: list[str]


def _get_owned_batch(db: Session, user: User, batch_id: int) -> ImportBatch:
    batch = db.get(ImportBatch, batch_id)
    if batch is None or batch.user_id != user.id:
        raise ImportBatchNotFoundError(f"Import batch {batch_id} not found")
    return batch


def batch_summary(db: Session, user: User, batch_id: int) -> BatchSummary:
    batch = _get_owned_batch(db, user, batch_id)
    rows = db.query(ImportRow).filter(ImportRow.batch_id == batch.id).all()

    action_counts: dict[str, int] = {}
    for r in rows:
        action_counts[r.action] = action_counts.get(r.action, 0) + 1

    unmapped_keys = sorted(
        {
            _unmapped_key(r.raw_scheme_name, r.scheme_code_hint)
            for r in rows
            if r.action == ImportRowAction.UNMAPPED
        }
    )

    account = db.get(Account, batch.account_id) if batch.account_id is not None else None

    return BatchSummary(
        batch=batch,
        account=account,
        row_count=len(rows),
        action_counts=action_counts,
        unmapped_scheme_keys=unmapped_keys,
    )


def apply_scheme_mapping(db: Session, user: User, batch_id: int, key: str, scheme_code: str) -> None:
    """key is whatever batch_summary().unmapped_scheme_keys returned for
    this row group - the raw scheme name in the overwhelming majority of
    cases (see _unmapped_key). Learns the mapping as a scheme_alias so
    future imports resolve it automatically.
    """
    batch = _get_owned_batch(db, user, batch_id)
    scheme = db.get(Scheme, scheme_code)
    if scheme is None:
        raise ValueError(
            f"Unknown scheme code {scheme_code!r} - sync NAVs first, or search for a different scheme."
        )

    existing = (
        db.query(SchemeAlias).filter(SchemeAlias.user_id == user.id, SchemeAlias.raw_name == key).first()
    )
    if existing is None:
        db.add(SchemeAlias(user_id=user.id, raw_name=key, scheme_code=scheme_code))
    else:
        existing.scheme_code = scheme_code

    rows = db.query(ImportRow).filter(ImportRow.batch_id == batch.id).all()
    for row in rows:
        if _unmapped_key(row.raw_scheme_name, row.scheme_code_hint) != key:
            continue
        row.resolved_scheme_code = scheme_code
        if row.action == ImportRowAction.UNMAPPED:
            row.action = ImportRowAction.NEW
    db.commit()


@dataclass(frozen=True, slots=True)
class CommitResult:
    committed: int
    restored: int
    duplicates: int
    unresolved: int
    errors: int


# Historical statements record NAV and units already rounded, so NAV*units
# can land a few paise above/below the recorded amount even when nothing
# was actually wrong. This tolerance absorbs that rounding noise without
# weakening the strict (tolerance=0) check manual entry and SIP
# confirmation still use, where a negative commission really does mean a
# mistyped field.
_IMPORT_COMMISSION_TOLERANCE = Decimal("1.00")


def commit_batch(db: Session, user: User, batch_id: int) -> CommitResult:
    batch = _get_owned_batch(db, user, batch_id)
    if batch.status == ImportBatchStatus.COMMITTED:
        raise ValueError("This batch has already been committed.")
    if batch.account_id is None:
        raise ValueError("This batch has no account assigned - it predates the account-per-batch model.")

    # Chronological order (not row-insertion order) so a redemption is
    # never processed - and FIFO-rejected as an over-redemption - before an
    # earlier purchase that happens to appear later in the sheet.
    rows = (
        db.query(ImportRow)
        .filter(ImportRow.batch_id == batch.id)
        .order_by(ImportRow.transaction_date, ImportRow.id)
        .all()
    )

    committed = restored = duplicates = unresolved = errors = 0
    for row in rows:
        if row.action == ImportRowAction.ERROR:
            errors += 1
            continue
        if not row.resolved_scheme_code or not row.transaction_date or not row.type:
            unresolved += 1
            continue

        # A cheap pre-check purely for the committed-vs-restored headline
        # count below - create_transaction does the same lookup again
        # internally (it's the authority on what actually happens; this
        # doesn't change behavior, only which counter gets incremented).
        pre_check_hash = compute_source_hash(
            account_id=batch.account_id,
            scheme_code=row.resolved_scheme_code,
            transaction_date=row.transaction_date,
            type=row.type,
            amount=row.amount,
            units=row.units,
            folio_no=row.folio_no,
        )
        was_soft_deleted = (
            db.query(Transaction)
            .filter(
                Transaction.account_id == batch.account_id,
                Transaction.source_hash == pre_check_hash,
                Transaction.is_deleted.is_(True),
            )
            .first()
            is not None
        )

        try:
            create_transaction(
                db,
                account_id=batch.account_id,
                scheme_code=row.resolved_scheme_code,
                transaction_date=row.transaction_date,
                type=row.type,
                nav=row.nav,
                units=row.units,
                amount=row.amount,
                folio_no=row.folio_no,
                source=TransactionSource.IMPORT,
                commission_tolerance=_IMPORT_COMMISSION_TOLERANCE,
            )
            row.action = ImportRowAction.NEW
            db.commit()
            if was_soft_deleted:
                restored += 1
            else:
                committed += 1
        except DuplicateTransactionError:
            db.rollback()
            row.action = ImportRowAction.DUPLICATE
            db.commit()
            duplicates += 1
        except IntegrityError:
            # Defensive fallback only - create_transaction's proactive
            # check should catch real duplicates before ever reaching an
            # INSERT. Still here in case of a genuine race.
            db.rollback()
            row.action = ImportRowAction.DUPLICATE
            db.commit()
            duplicates += 1
        except (InvalidCommissionError, OverRedemptionError) as exc:
            db.rollback()
            row.action = ImportRowAction.ERROR
            row.error = str(exc)
            db.commit()
            errors += 1

    batch.status = ImportBatchStatus.COMMITTED
    batch.committed_at = datetime.now()
    db.commit()

    return CommitResult(
        committed=committed, restored=restored, duplicates=duplicates, unresolved=unresolved, errors=errors
    )
