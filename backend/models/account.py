from __future__ import annotations

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class Account(Base):
    """One brokerage/RTA relationship, e.g. 'ICICI Direct - Ashu'."""

    __tablename__ = "accounts"
    __table_args__ = (UniqueConstraint("user_id", "account_name", name="uq_account_user_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    account_name: Mapped[str] = mapped_column(String(120))
    platform: Mapped[str] = mapped_column(String(60))
