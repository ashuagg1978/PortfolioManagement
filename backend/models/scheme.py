from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base
from db.types import Nav


class Scheme(Base):
    """The global, AMFI-feed-owned master of every scheme code that exists.

    Deliberately separate from PortfolioScheme: this table is refreshed
    wholesale by every NAV sync and is not user data. A user's own label for
    a scheme lives in PortfolioScheme; a raw broker-statement name that maps
    to a scheme lives in SchemeAlias. Mixing all three into one row (as the
    original PRD schema did) breaks the moment two users hold the same fund
    under different display names, or a NAV sync needs to overwrite a row
    the user has customized.
    """

    __tablename__ = "schemes"

    scheme_code: Mapped[str] = mapped_column(String(20), primary_key=True)
    scheme_name: Mapped[str] = mapped_column(String(255), index=True)
    isin_growth: Mapped[str | None] = mapped_column(String(20), nullable=True)
    isin_reinvestment: Mapped[str | None] = mapped_column(String(20), nullable=True)
    plan: Mapped[str | None] = mapped_column(String(20), nullable=True)
    option: Mapped[str | None] = mapped_column(String(60), nullable=True)
    latest_nav: Mapped[Decimal | None] = mapped_column(Nav(), nullable=True)
    nav_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
