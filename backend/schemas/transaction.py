from datetime import date

from pydantic import BaseModel, ConfigDict

from schemas.types import MoneyField, NavField, UnitsField


class TransactionCreate(BaseModel):
    account_id: int
    scheme_code: str
    transaction_date: date
    type: str  # "PURCHASE" | "REDEMPTION"
    nav: NavField
    units: UnitsField
    amount: MoneyField
    folio_no: str | None = None
    allow_duplicate: bool = False


class TransactionUpdate(BaseModel):
    transaction_date: date
    nav: NavField
    units: UnitsField
    amount: MoneyField
    folio_no: str | None = None


class CommissionPreviewRequest(BaseModel):
    type: str
    nav: NavField
    units: UnitsField
    amount: MoneyField


class CommissionPreviewResponse(BaseModel):
    commission: MoneyField
    gross: MoneyField


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    account_name: str
    scheme_code: str
    scheme_display_name: str
    transaction_date: date
    type: str
    source: str
    sip_id: int | None
    amount: MoneyField
    nav: NavField
    units: UnitsField
    commission: MoneyField
    signed_amount: MoneyField
    folio_no: str | None
    is_deleted: bool


class TransactionListOut(BaseModel):
    items: list[TransactionOut]
    total: int
