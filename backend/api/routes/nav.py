from fastapi import APIRouter, Depends
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from db.session import get_db
from models.scheme import Scheme
from schemas.nav import SchemeSearchResult, SyncResponse
from services.amfi import sync_navs

router = APIRouter(tags=["nav"])


@router.post("/nav/sync", response_model=SyncResponse)
def sync_nav(db: Session = Depends(get_db)) -> SyncResponse:
    """The 'Sync NAV' button - the only way NAVs ever refresh. No cron, no
    background job; this is a plain on-demand POST.
    """
    result = sync_navs(db)
    return SyncResponse(
        rows_parsed=result.rows_parsed,
        rows_upserted=result.rows_upserted,
        rows_skipped=result.rows_skipped,
        feed_date=result.feed_date,
        duration_ms=result.duration_ms,
    )


@router.get("/schemes/search", response_model=list[SchemeSearchResult])
def search_schemes(q: str, limit: int = 20, db: Session = Depends(get_db)) -> list[SchemeSearchResult]:
    """Typeahead for scheme mapping, and the backing search for the Schemes
    browser page. Matches on a few words in any order - each word is
    required (AND'd together), but each can land anywhere in the name or
    code (OR'd per word) - so "sbi contra direct" matches "SBI CONTRA FUND"
    with a Direct-plan row even though that's not one contiguous substring
    of the scheme name.
    """
    if len(q.strip()) < 2:
        return []
    words = [w for w in q.strip().split() if w]
    conditions = [or_(Scheme.scheme_name.ilike(f"%{w}%"), Scheme.scheme_code.like(f"%{w}%")) for w in words]
    rows = (
        db.query(Scheme)
        .filter(and_(*conditions))
        .order_by(Scheme.scheme_name)
        .limit(limit)
        .all()
    )
    return [
        SchemeSearchResult(
            scheme_code=r.scheme_code,
            scheme_name=r.scheme_name,
            plan=r.plan,
            option=r.option,
            latest_nav=r.latest_nav,
            nav_date=r.nav_date,
        )
        for r in rows
    ]
