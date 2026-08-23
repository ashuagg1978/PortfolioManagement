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
    SipStopRequest,
    SipVersion,
    SkipEntryRequest,
    UpcomingOccurrenceOut,
)
from api.routes.transactions import enrich_txn_out
from schemas.transaction import TransactionOut
from services.charges import InvalidCommissionError
from services.transactions import DuplicateTransactionError, OverRedemptionError, enrich_display_names
from services.sips import (
    SipNotFoundError,
    close_and_clone,
    confirm_entry,
    due_count,
    due_entries,
    hold_sip,
    project_upcoming,
    resume_sip,
    skip_entry,
    stop_sip,
)

router = APIRouter(prefix="/sips", tags=["sips"])


def _own_account_ids(db: Session, user: User) -> list[int]:
    return [a.id for a in db.query(Account.id).filter(Account.user_id == user.id).all()]


def to_sip_out(sip: Sip, account_name: str, scheme_display_name: str) -> SipOut:
    return SipOut(
        id=sip.id,
        account_id=sip.account_id,
        account_name=account_name,
        scheme_code=sip.scheme_code,
        scheme_display_name=scheme_display_name,
        amount=sip.amount,
        frequency=sip.frequency,
        start_date=sip.start_date,
        end_date=sip.end_date,
        folio_no=sip.folio_no,
        is_active=sip.is_active,
        parent_sip_id=sip.parent_sip_id,
    )


def enrich_sip_out(db: Session, user: User, sip: Sip) -> SipOut:
    account_name, scheme_display_name = enrich_display_names(db, user, [sip])[sip.id]
    return to_sip_out(sip, account_name, scheme_display_name)


@router.get("", response_model=list[SipOut])
def list_sips(
    active_only: bool = True,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[SipOut]:
    query = db.query(Sip).filter(Sip.account_id.in_(_own_account_ids(db, user)))
    if active_only:
        query = query.filter(Sip.is_active.is_(True))
    rows = query.order_by(Sip.start_date.desc()).all()
    names = enrich_display_names(db, user, rows)
    return [to_sip_out(s, *names[s.id]) for s in rows]


@router.post("", response_model=SipOut, status_code=201)
def create_sip(
    payload: SipCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> SipOut:
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
    return enrich_sip_out(db, user, sip)


@router.post("/{sip_id}/version", response_model=SipOut)
def version_sip(
    sip_id: int,
    payload: SipVersion,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SipOut:
    try:
        new_sip = close_and_clone(
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
    return enrich_sip_out(db, user, new_sip)


@router.post("/{sip_id}/hold", response_model=SipOut)
def hold(
    sip_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> SipOut:
    """Pauses a SIP - no due entries or upcoming projections while held.
    Resumable later with the exact same terms via /resume.
    """
    try:
        sip = hold_sip(db, user, sip_id=sip_id)
    except SipNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return enrich_sip_out(db, user, sip)


@router.post("/{sip_id}/resume", response_model=SipOut)
def resume(
    sip_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> SipOut:
    """Reactivates a held or stopped SIP - always perpetual again (any prior
    end_date is cleared) unless stopped or edited again afterward.
    """
    try:
        sip = resume_sip(db, user, sip_id=sip_id)
    except SipNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return enrich_sip_out(db, user, sip)


@router.post("/{sip_id}/stop", response_model=SipOut)
def stop(
    sip_id: int,
    payload: SipStopRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SipOut:
    """Permanently ends a SIP as of end_date (default: today)."""
    try:
        sip = stop_sip(db, user, sip_id=sip_id, end_date=payload.end_date)
    except SipNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return enrich_sip_out(db, user, sip)


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
        txn = confirm_entry(
            db,
            user,
            sip_id=payload.sip_id,
            scheduled_date=payload.scheduled_date,
            transaction_date=payload.transaction_date,
            nav=payload.nav,
            units=payload.units,
        )
        return enrich_txn_out(db, user, txn)
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
