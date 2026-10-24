from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class Advice(Base):
    __tablename__ = "advice"
    __table_args__ = (UniqueConstraint("user_id", "kind", "scope", name="uq_advice_user_kind_scope"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    scope: Mapped[str] = mapped_column(String(20), default="")
    result_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())