from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.deps import get_current_user
from db.session import get_db
from models.account import Account
from models.sip import Sip
from models.user import User
from schemas.sip import (
    ConfirmEntryRequest,
    DueEntryOut,
    SipCreate,
    SipOut,
    SipVersion,
    SkipEntryRequest,
    UpcomingOccurrenceOut,
)
from schemas.transaction import TransactionOut
from services.charges import InvalidCommissionError
from services.transactions import DuplicateTransactionError, OverRedemptionError
from services.sips import (
    SipNotFoundError,
    close_and_clone,
    confirm_entry,
    due_count,
    due_entries,
    project_upcoming,
    skip_entry,
)

router = APIRouter(prefix="/sips", tags=["sips"])


def _own_account_ids(db: Session, user: User) -> list[int]:
    return [a.id for a in db.query(Account.id).filter(Account.user_id == user.id).all()]


@router.get("", response_model=list[SipOut])
def list_sips(
    active_only: bool = True,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[Sip]:
    query = db.query(Sip).filter(Sip.account_id.in_(_own_account_ids(db, user)))
    if active_only:
        query = query.filter(Sip.is_active.is_(True))
    return query.order_by(Sip.start_date.desc()).all()


@router.post("", response_model=SipOut, status_code=201)
def create_sip(
    payload: SipCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> Sip:
    if payload.account_id not in _own_account_ids(db, user):
        raise HTTPException(status_code=404, detail="Account not found")
    sip = Sip(
        account_id=payload.account_id,
        scheme_code=payload.scheme_code,
        amount=payload.amount,
        frequency=payload.frequency,
        start_date=payload.start_date,
        end_date=payload.end_date,
        folio_no=payload.folio_no,
    )
    db.add(sip)
    db.commit()
    db.refresh(sip)
    return sip


@router.post("/{sip_id}/version", response_model=SipOut)
def version_sip(
    sip_id: int,
    payload: SipVersion,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Sip:
    try:
        return close_and_clone(
            db,
            user,
            sip_id=sip_id,
            effective_date=payload.effective_date,
            amount=payload.amount,
            frequency=payload.frequency,
            folio_no=payload.folio_no,
        )
    except SipNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/due", response_model=list[DueEntryOut])
def get_due_entries(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list:
    return due_entries(db, user)


@router.get("/due/count")
def get_due_count(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    return {"count": due_count(db, user)}


@router.post("/due/confirm", response_model=TransactionOut)
def confirm_due_entry(
    payload: ConfirmEntryRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        return confirm_entry(
            db,
            user,
            sip_id=payload.sip_id,
            scheduled_date=payload.scheduled_date,
            nav=payload.nav,
            units=payload.units,
        )
    except SipNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidCommissionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OverRedemptionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except DuplicateTransactionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/due/skip")
def skip_due_entry(
    payload: SkipEntryRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    try:
        skip = skip_entry(
            db, user, sip_id=payload.sip_id, scheduled_date=payload.scheduled_date, reason=payload.reason
        )
    except SipNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"id": skip.id, "sip_id": skip.sip_id, "scheduled_date": skip.scheduled_date}


@router.get("/upcoming", response_model=list[UpcomingOccurrenceOut])
def get_upcoming(n: int = 5, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list:
    return project_upcoming(db, user, n=n)
