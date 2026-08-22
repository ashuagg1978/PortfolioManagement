from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base
from db.types import Money


class Sip(Base):
    """A SIP mandate definition.

    Editing an active SIP (e.g. bumping the amount) does not update this row
    in place - it uses "close and clone": the current row's end_date is set
    and a new row is inserted with parent_sip_id pointing back, preserving
    exact history of what was scheduled at any point in time. See
    app/services/sips.py::close_and_clone().

    No occurrence of a SIP is ever auto-generated into transactions. This
    table only describes the mandate; app/services/sips.py projects due
    occurrences on read and a transaction is written only once the user
    confirms the actual NAV and units from their statement.
    """

    __tablename__ = "sips"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    scheme_code: Mapped[str] = mapped_column(ForeignKey("schemes.scheme_code"), index=True)
    amount: Mapped[Decimal] = mapped_column(Money())
    frequency: Mapped[str] = mapped_column(String(20))  # SipFrequency
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)  # NULL = perpetual
    folio_no: Mapped[str | None] = mapped_column(String(40), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    parent_sip_id: Mapped[int | None] = mapped_column(ForeignKey("sips.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
