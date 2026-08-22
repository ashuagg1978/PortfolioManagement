from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from sqlalchemy.orm import Session

from api.deps import get_current_user
from db.session import get_db
from models.import_row import ImportRow
from models.user import User
from schemas.imports import CommitResultOut, ImportBatchOut, ImportRowOut, SchemeMappingRequest
from services.import_template import build_template_workbook
from services.imports import (
    AccountNotFoundError,
    BatchSummary,
    ImportBatchNotFoundError,
    StageResult,
    apply_scheme_mapping,
    batch_summary,
    commit_batch,
    stage_import,
)

router = APIRouter(prefix="/imports", tags=["imports"])


def _to_batch_out(
    summary: BatchSummary, *, sheet_used: str | None = None, other_sheets_ignored: list[str] | None = None
) -> ImportBatchOut:
    return ImportBatchOut(
        id=summary.batch.id,
        filename=summary.batch.filename,
        status=summary.batch.status,
        account_id=summary.batch.account_id,
        account_name=summary.account.account_name if summary.account else None,
        row_count=summary.row_count,
        action_counts=summary.action_counts,
        unmapped_scheme_keys=summary.unmapped_scheme_keys,
        sheet_used=sheet_used,
        other_sheets_ignored=other_sheets_ignored or [],
    )


@router.get("/template")
def download_template() -> Response:
    """A ready-to-fill .xlsx: one flat 'Transactions' sheet - the account is
    chosen on the upload screen, not inferred from the file, so the
    template needs no per-account structure. Registered before /{batch_id}
    - a static path segment must be matched first or "template" would be
    parsed as a batch id.
    """
    content = build_template_workbook()
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="transaction_import_template.xlsx"'},
    )


@router.post("", response_model=ImportBatchOut, status_code=201)
async def upload(
    file: UploadFile = File(...),
    account_id: int = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ImportBatchOut:
    content = await file.read()
    try:
        result: StageResult = stage_import(db, user, file.filename or "upload.xlsx", content, account_id)
    except AccountNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    summary = batch_summary(db, user, result.batch.id)
    return _to_batch_out(summary, sheet_used=result.sheet_used, other_sheets_ignored=result.other_sheets_ignored)


@router.get("/{batch_id}", response_model=ImportBatchOut)
def get_batch(
    batch_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> ImportBatchOut:
    try:
        summary = batch_summary(db, user, batch_id)
    except ImportBatchNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_batch_out(summary)


@router.get("/{batch_id}/rows", response_model=list[ImportRowOut])
def get_rows(
    batch_id: int,
    action: str | None = None,
    limit: int = 1000,
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ImportRow]:
    try:
        summary = batch_summary(db, user, batch_id)  # also validates ownership
    except ImportBatchNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    query = db.query(ImportRow).filter(ImportRow.batch_id == summary.batch.id)
    if action:
        query = query.filter(ImportRow.action == action)
    return query.order_by(ImportRow.id).offset(offset).limit(limit).all()


@router.post("/{batch_id}/mappings/scheme", response_model=ImportBatchOut)
def map_scheme(
    batch_id: int,
    payload: SchemeMappingRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ImportBatchOut:
    try:
        apply_scheme_mapping(db, user, batch_id, payload.key, payload.scheme_code)
        summary = batch_summary(db, user, batch_id)
    except ImportBatchNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _to_batch_out(summary)


@router.post("/{batch_id}/commit", response_model=CommitResultOut)
def commit(
    batch_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> CommitResultOut:
    try:
        result = commit_batch(db, user, batch_id)
    except ImportBatchNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return CommitResultOut(
        committed=result.committed,
        restored=result.restored,
        duplicates=result.duplicates,
        unresolved=result.unresolved,
        errors=result.errors,
    )
