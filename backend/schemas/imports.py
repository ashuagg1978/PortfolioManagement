from datetime import date

from pydantic import BaseModel

from schemas.types import MoneyField, NavField, UnitsField


class ImportBatchOut(BaseModel):
    id: int
    filename: str
    status: str
    account_id: int | None
    account_name: str | None
    row_count: int
    action_counts: dict[str, int]
    unmapped_scheme_keys: list[str]
    # Only populated on the upload response itself (not on a later GET) -
    # informational, not persisted. See services/imports.py::stage_import.
    sheet_used: str | None = None
    other_sheets_ignored: list[str] = []


class ImportRowOut(BaseModel):
    id: int
    row_index: int
    sheet_name: str | None
    raw_scheme_name: str | None
    scheme_code_hint: str | None
    resolved_scheme_code: str | None
    transaction_date: date | None
    type: str | None
    amount: MoneyField | None
    nav: NavField | None
    units: UnitsField | None
    folio_no: str | None
    action: str
    error: str | None


class SchemeMappingRequest(BaseModel):
    key: str
    scheme_code: str


class CommitResultOut(BaseModel):
    committed: int
    restored: int
    duplicates: int
    unresolved: int
    errors: int
