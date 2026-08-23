from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.deps import get_current_user
from db.session import get_db
from models.account import Account
from models.user import User
from schemas.account import AccountCreate, AccountOut, AccountUpdate

router = APIRouter(prefix="/accounts", tags=["accounts"])


def _get_owned_account(db: Session, user: User, account_id: int) -> Account:
    account = db.get(Account, account_id)
    if account is None or account.user_id != user.id:
        raise HTTPException(status_code=404, detail="Account not found")
    return account


@router.get("", response_model=list[AccountOut])
def list_accounts(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[Account]:
    return db.query(Account).filter(Account.user_id == user.id).order_by(Account.account_name).all()


@router.post("", response_model=AccountOut, status_code=201)
def create_account(
    payload: AccountCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Account:
    account = Account(user_id=user.id, account_name=payload.account_name, platform=payload.platform)
    db.add(account)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=422, detail=f"An account named {payload.account_name!r} already exists."
        ) from exc
    db.refresh(account)
    return account


@router.patch("/{account_id}", response_model=AccountOut)
def update_account(
    account_id: int,
    payload: AccountUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Account:
    account = _get_owned_account(db, user, account_id)
    account.account_name = payload.account_name
    account.platform = payload.platform
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=422, detail=f"An account named {payload.account_name!r} already exists."
        ) from exc
    db.refresh(account)
    return account
