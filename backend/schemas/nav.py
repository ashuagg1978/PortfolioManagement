from datetime import date

from pydantic import BaseModel

from schemas.types import NavField


class SyncResponse(BaseModel):
    rows_parsed: int
    rows_upserted: int
    rows_skipped: int
    feed_date: date | None
    duration_ms: int
    # The held-scheme daily NAV history top-up, run in the same click - see
    # services/portfolio_history.py::sync_nav_history().
    history_schemes_synced: int
    history_schemes_failed: int
    history_points_inserted: int
    history_duration_ms: int


class SchemeSearchResult(BaseModel):
    scheme_code: str
    scheme_name: str
    plan: str | None
    option: str | None
    latest_nav: NavField | None
    nav_date: date | None


class NavHistoryOut(BaseModel):
    nav: NavField
    nav_date: date
