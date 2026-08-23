from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from api.deps import get_current_user
from db.session import get_db
from models.account import Account
from models.transaction import Transaction
from models.user import User
from services.charges import InvalidCommissionError, compute_commission
from services.transaction_export import build_transactions_export
from services.transactions import (
    DuplicateTransactionError,
    OverRedemptionError,
    TransactionFilters,
    create_transaction,
    enrich_display_names,
    list_all_matching_transactions,
    list_transactions as list_transactions_service,
    restore_transaction,
    soft_delete_transaction,
    update_transaction,
)
from schemas.transaction import (
    CommissionPreviewRequest,
    CommissionPreviewResponse,
    TransactionCreate,
    TransactionListOut,
    TransactionOut,
    TransactionUpdate,
)

router = APIRouter(prefix="/transactions", tags=["transactions"])


def _own_account_ids(db: Session, user: User) -> list[int]:
    return [a.id for a in db.query(Account.id).filter(Account.user_id == user.id).all()]


def _get_owned_transaction(db: Session, user: User, transaction_id: int) -> Transaction:
    txn = db.get(Transaction, transaction_id)
    if txn is None or txn.account_id not in _own_account_ids(db, user):
        raise HTTPException(status_code=404, detail="Transaction not found")
    return txn


def enrich_txn_out(db: Session, user: User, txn: Transaction) -> TransactionOut:
    account_name, scheme_display_name = enrich_display_names(db, user, [txn])[txn.id]
    return to_transaction_out(txn, account_name, scheme_display_name)


def to_transaction_out(txn: Transaction, account_name: str, scheme_display_name: str) -> TransactionOut:
    return TransactionOut(
        id=txn.id,
        account_id=txn.account_id,
        account_name=account_name,
        scheme_code=txn.scheme_code,
        scheme_display_name=scheme_display_name,
        transaction_date=txn.transaction_date,
        type=txn.type,
        source=txn.source,
        sip_id=txn.sip_id,
        amount=txn.amount,
        nav=txn.nav,
        units=txn.units,
        commission=txn.commission,
        signed_amount=txn.signed_amount,
        folio_no=txn.folio_no,
        is_deleted=txn.is_deleted,
    )


@router.get("", response_model=TransactionListOut)
def list_transactions(
    account_id: int | None = None,
    scheme_code: str | None = None,
    scheme_name: str | None = None,
    type: str | None = None,
    source: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    include_deleted: bool = False,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TransactionListOut:
    filters = TransactionFilters(
        account_id=account_id,
        scheme_code=scheme_code,
        scheme_name=scheme_name,
        type=type,
        source=source,
        date_from=date_from,
        date_to=date_to,
        include_deleted=include_deleted,
    )
    rows, total = list_transactions_service(db, user, filters, limit=limit, offset=offset)
    names = enrich_display_names(db, user, rows)
    return TransactionListOut(
        items=[to_transaction_out(t, *names[t.id]) for t in rows],
        total=total,
    )


@router.get("/export")
def export_transactions(
    account_id: int | None = None,
    scheme_code: str | None = None,
    scheme_name: str | None = None,
    type: str | None = None,
    source: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    """The full filtered result set as .xlsx - the same filters as the list
    above, minus pagination, so exporting covers everything the search bar
    is showing rather than just the current page.
    """
    filters = TransactionFilters(
        account_id=account_id,
        scheme_code=scheme_code,
        scheme_name=scheme_name,
        type=type,
        source=source,
        date_from=date_from,
        date_to=date_to,
        include_deleted=include_deleted,
    )
    rows = list_all_matching_transactions(db, user, filters)
    names = enrich_display_names(db, user, rows)
    content = build_transactions_export(rows, names)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="transactions_export.xlsx"'},
    )


@router.post("", response_model=TransactionOut, status_code=201)
def create(
    payload: TransactionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TransactionOut:
    if payload.account_id not in _own_account_ids(db, user):
        raise HTTPException(status_code=404, detail="Account not found")
    try:
        txn = create_transaction(
            db,
            account_id=payload.account_id,
            scheme_code=payload.scheme_code,
            transaction_date=payload.transaction_date,
            type=payload.type,
            nav=payload.nav,
            units=payload.units,
            amount=payload.amount,
            folio_no=payload.folio_no,
        )
    except InvalidCommissionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OverRedemptionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except DuplicateTransactionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return enrich_txn_out(db, user, txn)


@router.patch("/{transaction_id}", response_model=TransactionOut)
def update(
    transaction_id: int,
    payload: TransactionUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TransactionOut:
    txn = _get_owned_transaction(db, user, transaction_id)
    try:
        updated = update_transaction(
            db,
            txn,
            transaction_date=payload.transaction_date,
            nav=payload.nav,
            units=payload.units,
            amount=payload.amount,
            folio_no=payload.folio_no,
        )
    except InvalidCommissionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OverRedemptionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return enrich_txn_out(db, user, updated)


@router.delete("/{transaction_id}", response_model=TransactionOut)
def soft_delete(
    transaction_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TransactionOut:
    txn = _get_owned_transaction(db, user, transaction_id)
    return enrich_txn_out(db, user, soft_delete_transaction(db, txn))


@router.post("/{transaction_id}/restore", response_model=TransactionOut)
def restore(
    transaction_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TransactionOut:
    txn = _get_owned_transaction(db, user, transaction_id)
    return enrich_txn_out(db, user, restore_transaction(db, txn))


@router.post("/preview-commission", response_model=CommissionPreviewResponse)
def preview_commission(payload: CommissionPreviewRequest) -> CommissionPreviewResponse:
    """Lets the form show the server's derived commission live, without
    duplicating the compute_commission rule in TypeScript.
    """
    try:
        commission = compute_commission(payload.type, payload.nav, payload.units, payload.amount)
    except InvalidCommissionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return CommissionPreviewResponse(commission=commission, gross=payload.nav * payload.units)
