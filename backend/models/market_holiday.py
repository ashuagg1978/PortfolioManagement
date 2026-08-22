from __future__ import annotations

from datetime import date

from sqlalchemy import Date, String
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class MarketHoliday(Base):
    """Seeded from app/data/nse_holidays.json. If a given year has no rows
    here, trading-day adjustment degrades to weekend-only and the caller is
    expected to flag that (see app/services/trading_calendar.py).
    """

    __tablename__ = "market_holidays"

    holiday_date: Mapped[date] = mapped_column(Date, primary_key=True)
    exchange: Mapped[str] = mapped_column(String(10), default="NSE")
    description: Mapped[str | None] = mapped_column(String(120), nullable=True)
