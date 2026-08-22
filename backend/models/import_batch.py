from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class ImportBatch(Base):
    """One uploaded file, staged for preview before commit.

    A stateless backend cannot hold parsed rows in server memory between the
    preview and commit calls, so they are persisted here instead (in
    ImportRow) - which doubles as an audit trail and lets the user resume
    resolving unmapped schemes later rather than losing the upload.
    """

    __tablename__ = "import_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    # The single account every row in this batch is imported into - chosen
    # up front on the upload screen rather than inferred from sheet names.
    # Nullable only because an old batch predates this column.
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    filename: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), default="PENDING")  # ImportBatchStatus
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    committed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
