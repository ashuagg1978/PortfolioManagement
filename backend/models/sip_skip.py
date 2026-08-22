from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class SipSkip(Base):
    """Records a scheduled SIP occurrence the user has confirmed never
    executed (bounced mandate, insufficient funds), so it stops showing up
    on the SIP Entries Due page without a fabricated transaction being
    written for it.
    """

    __tablename__ = "sip_skips"
    __table_args__ = (UniqueConstraint("sip_id", "scheduled_date", name="uq_sip_skip"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    sip_id: Mapped[int] = mapped_column(ForeignKey("sips.id"), index=True)
    scheduled_date: Mapped[date] = mapped_column(Date)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
