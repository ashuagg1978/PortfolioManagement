from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.deps import get_current_user
from db.session import get_db
from models.user import User
from schemas.dashboard import DashboardSummaryOut, SchemeHoldingOut
from services.portfolio import compute_dashboard, compute_holdings

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _holding_out(h) -> SchemeHoldingOut:
    return SchemeHoldingOut(
        scheme_code=h.scheme_code,
        display_name=h.display_name,
        net_units=h.net_units,
        net_invested=h.net_invested,
        avg_cost_nav=h.avg_cost_nav,
        latest_nav=h.latest_nav,
        nav_date=h.nav_date,
        nav_source=h.nav_source,
        current_value=h.current_value,
        unrealized_gain=h.unrealized_gain,
        realized_gain=h.realized_gain,
        total_gain=h.total_gain,
        pct_gain=float(h.pct_gain) if h.pct_gain is not None else None,
        status=h.status,
        xirr=float(h.xirr) if h.xirr is not None else None,
    )


@router.get("", response_model=DashboardSummaryOut)
def dashboard(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> DashboardSummaryOut:
    summary = compute_dashboard(db, user)
    return DashboardSummaryOut(
        net_invested=summary.net_invested,
        current_value=summary.current_value,
        net_gain_loss=summary.net_gain_loss,
        total_return_pct=float(summary.total_return_pct) if summary.total_return_pct is not None else None,
        active_schemes=summary.active_schemes,
        total_commission_paid=summary.total_commission_paid,
        portfolio_xirr=float(summary.portfolio_xirr) if summary.portfolio_xirr is not None else None,
        nav_as_of=summary.nav_as_of,
        holdings=[_holding_out(h) for h in summary.holdings],
    )


@router.get("/holdings", response_model=list[SchemeHoldingOut])
def holdings(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[SchemeHoldingOut]:
    return [_holding_out(h) for h in compute_holdings(db, user)]
