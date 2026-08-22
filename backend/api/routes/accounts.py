from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.deps import get_current_user
from db.session import get_db
from models.account import Account
from models.user import User
from schemas.account import AccountCreate, AccountOut

router = APIRouter(prefix="/accounts", tags=["accounts"])


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
    db.commit()
    db.refresh(account)
    return account
