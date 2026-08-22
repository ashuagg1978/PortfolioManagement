from datetime import date

from pydantic import BaseModel, ConfigDict

from schemas.transaction import TransactionOut
from schemas.types import MoneyField, NavField, UnitsField


class SipCreate(BaseModel):
    account_id: int
    scheme_code: str
    amount: MoneyField
    frequency: str  # "MONTHLY" | "BIWEEKLY"
    start_date: date
    end_date: date | None = None
    folio_no: str | None = None


class SipVersion(BaseModel):
    """Close-and-clone: only the fields being changed need to be supplied."""

    effective_date: date
    amount: MoneyField | None = None
    frequency: str | None = None
    folio_no: str | None = None


class SipOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    scheme_code: str
    amount: MoneyField
    frequency: str
    start_date: date
    end_date: date | None
    folio_no: str | None
    is_active: bool
    parent_sip_id: int | None


class DueEntryOut(BaseModel):
    sip_id: int
    account_id: int
    account_name: str
    scheme_code: str
    display_name: str
    scheduled_date: date
    adjusted_date: date
    expected_amount: MoneyField
    folio_no: str | None
    calendar_complete: bool


class ConfirmEntryRequest(BaseModel):
    sip_id: int
    scheduled_date: date
    nav: NavField
    units: UnitsField


class SkipEntryRequest(BaseModel):
    sip_id: int
    scheduled_date: date
    reason: str | None = None


class UpcomingOccurrenceOut(BaseModel):
    sip_id: int
    account_name: str
    scheme_code: str
    display_name: str
    scheduled_date: date
    adjusted_date: date
    amount: MoneyField


__all__ = [
    "SipCreate",
    "SipVersion",
    "SipOut",
    "DueEntryOut",
    "ConfirmEntryRequest",
    "SkipEntryRequest",
    "UpcomingOccurrenceOut",
    "TransactionOut",
]
