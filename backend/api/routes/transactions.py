from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.deps import get_current_user
from db.session import get_db
from models.account import Account
from models.transaction import Transaction
from models.user import User
from services.charges import InvalidCommissionError, compute_commission
from services.transactions import (
    DuplicateTransactionError,
    OverRedemptionError,
    create_transaction,
    restore_transaction,
    soft_delete_transaction,
    update_transaction,
)
from schemas.transaction import (
    CommissionPreviewRequest,
    CommissionPreviewResponse,
    TransactionCreate,
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


@router.get("", response_model=list[TransactionOut])
def list_transactions(
    account_id: int | None = None,
    scheme_code: str | None = None,
    type: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    include_deleted: bool = False,
    limit: int = 200,
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[Transaction]:
    account_ids = _own_account_ids(db, user)
    query = db.query(Transaction).filter(Transaction.account_id.in_(account_ids))
    if not include_deleted:
        query = query.filter(Transaction.is_deleted.is_(False))
    if account_id is not None:
        query = query.filter(Transaction.account_id == account_id)
    if scheme_code is not None:
        query = query.filter(Transaction.scheme_code == scheme_code)
    if type is not None:
        query = query.filter(Transaction.type == type)
    if date_from is not None:
        query = query.filter(Transaction.transaction_date >= date_from)
    if date_to is not None:
        query = query.filter(Transaction.transaction_date <= date_to)
    return (
        query.order_by(Transaction.transaction_date.desc(), Transaction.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


@router.post("", response_model=TransactionOut, status_code=201)
def create(
    payload: TransactionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Transaction:
    if payload.account_id not in _own_account_ids(db, user):
        raise HTTPException(status_code=404, detail="Account not found")
    try:
        return create_transaction(
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


@router.patch("/{transaction_id}", response_model=TransactionOut)
def update(
    transaction_id: int,
    payload: TransactionUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Transaction:
    txn = _get_owned_transaction(db, user, transaction_id)
    try:
        return update_transaction(
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


@router.delete("/{transaction_id}", response_model=TransactionOut)
def soft_delete(
    transaction_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Transaction:
    txn = _get_owned_transaction(db, user, transaction_id)
    return soft_delete_transaction(db, txn)


@router.post("/{transaction_id}/restore", response_model=TransactionOut)
def restore(
    transaction_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Transaction:
    txn = _get_owned_transaction(db, user, transaction_id)
    return restore_transaction(db, txn)


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
