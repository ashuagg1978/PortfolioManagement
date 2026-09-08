from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.deps import get_current_user
from db.session import get_db
from models.user import User
from schemas.dashboard import (
    AccountHoldingsOut,
    DashboardSummaryOut,
    PortfolioHistoryPointOut,
    SchemeHoldingOut,
)
from services.portfolio import compute_account_breakdown, compute_dashboard, compute_holdings
from services.portfolio_history import compute_portfolio_value_history

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


def _account_holdings_out(a) -> AccountHoldingsOut:
    return AccountHoldingsOut(
        account_id=a.account_id,
        account_name=a.account_name,
        net_invested=a.net_invested,
        current_value=a.current_value,
        net_gain_loss=a.net_gain_loss,
        pct_gain=float(a.pct_gain) if a.pct_gain is not None else None,
        xirr=float(a.xirr) if a.xirr is not None else None,
        schemes=[_holding_out(h) for h in a.schemes],
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
        by_account=[_account_holdings_out(a) for a in summary.by_account],
    )


@router.get("/holdings", response_model=list[SchemeHoldingOut])
def holdings(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[SchemeHoldingOut]:
    return [_holding_out(h) for h in compute_holdings(db, user)]


@router.get("/by-account", response_model=list[AccountHoldingsOut])
def by_account(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[AccountHoldingsOut]:
    return [_account_holdings_out(a) for a in compute_account_breakdown(db, user)]


@router.get("/history", response_model=list[PortfolioHistoryPointOut])
def history(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[PortfolioHistoryPointOut]:
    """Day-wise portfolio value/invested/gain-% history, from the first
    transaction to today - feeds the dashboard's performance-over-time
    chart. Computed fresh on every call from the transaction ledger +
    scheme_nav_history (see services/portfolio_history.py); nothing here is
    cached or stored. net_invested is the FIFO cost basis of units held *as
    of that day* (same definition as GET /api/dashboard's net_invested
    today - see services/portfolio.py), so pct_gain reflects true point-in-
    time performance, not today's holdings valued at yesterday's cost.
    """
    return [
        PortfolioHistoryPointOut(
            as_of=p.as_of,
            current_value=p.current_value,
            net_invested=p.net_invested,
            pct_gain=float(p.pct_gain) if p.pct_gain is not None else None,
        )
        for p in compute_portfolio_value_history(db, user)
    ]
