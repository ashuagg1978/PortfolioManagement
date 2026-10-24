from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.deps import get_current_user
from db.session import get_db
from models.user import User
from schemas.advisor import PortfolioAdviceOut, SchemeAdviceOut
from services.advisor import (
    AdvisorError,
    advise_on_portfolio,
    advise_on_scheme,
    load_portfolio_advice,
    load_scheme_advice,
    save_advice,
)

router = APIRouter(prefix="/advisor", tags=["advisor"])


@router.get("/portfolio", response_model=PortfolioAdviceOut | None)
def saved_portfolio_advice(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> PortfolioAdviceOut | None:
    return load_portfolio_advice(db, user)


@router.get("/schemes/{scheme_code}", response_model=SchemeAdviceOut | None)
def saved_scheme_advice(
    scheme_code: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> SchemeAdviceOut | None:
    return load_scheme_advice(db, user, scheme_code)


def _raise_http_error(error: AdvisorError) -> HTTPException:
    return HTTPException(status_code=error.status_code, detail=error.message)


@router.post("/portfolio", response_model=PortfolioAdviceOut)
def portfolio_advice(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> PortfolioAdviceOut:
    try:
        return save_advice(db, user, "PORTFOLIO", "", advise_on_portfolio(db, user))
    except AdvisorError as error:
        raise _raise_http_error(error) from error


@router.post("/schemes/{scheme_code}", response_model=SchemeAdviceOut)
def scheme_advice(
    scheme_code: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> SchemeAdviceOut:
    try:
        return save_advice(db, user, "SCHEME", scheme_code, advise_on_scheme(db, user, scheme_code))
    except AdvisorError as error:
        raise _raise_http_error(error) from error