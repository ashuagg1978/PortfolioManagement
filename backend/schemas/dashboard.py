from datetime import date

from pydantic import BaseModel

from schemas.types import MoneyField, NavField, UnitsField


class SchemeHoldingOut(BaseModel):
    scheme_code: str
    display_name: str
    net_units: UnitsField
    net_invested: MoneyField
    avg_cost_nav: NavField | None
    latest_nav: NavField | None
    nav_date: date | None
    nav_source: str
    current_value: MoneyField
    unrealized_gain: MoneyField
    realized_gain: MoneyField
    total_gain: MoneyField
    pct_gain: float | None
    status: str
    xirr: float | None


class AccountHoldingsOut(BaseModel):
    account_id: int
    account_name: str
    net_invested: MoneyField
    current_value: MoneyField
    net_gain_loss: MoneyField
    pct_gain: float | None
    xirr: float | None
    schemes: list[SchemeHoldingOut]


class PortfolioHistoryPointOut(BaseModel):
    as_of: date
    current_value: MoneyField
    net_invested: MoneyField
    pct_gain: float | None


class DashboardSummaryOut(BaseModel):
    net_invested: MoneyField
    current_value: MoneyField
    net_gain_loss: MoneyField
    total_realized_gain: MoneyField
    total_return_pct: float | None
    active_schemes: int
    total_commission_paid: MoneyField
    portfolio_xirr: float | None
    nav_as_of: date | None
    holdings: list[SchemeHoldingOut]
    by_account: list[AccountHoldingsOut]
