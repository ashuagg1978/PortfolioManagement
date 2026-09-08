from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base
from db.types import Nav


class SchemeNavHistory(Base):
    """One row per scheme per trading day whose NAV has been synced.

    Populated incrementally by services/portfolio_history.py::sync_nav_history()
    on every "Sync NAV" click, scoped to only the schemes the user has ever
    transacted - not the full AMFI universe (see that module's docstring).
    Historical NAVs are immutable once published, so rows are written with
    insert_ignore() (db/upsert.py) and never updated once inserted - unlike
    schemes.latest_nav, which is upserted/overwritten every sync.

    Feeds services/portfolio_history.py::compute_portfolio_value_history(),
    which recomputes the day-wise portfolio value series live from this table
    plus the transaction ledger - nothing derived from this table is cached.
    """

    __tablename__ = "scheme_nav_history"
    __table_args__ = (
        Index("ix_scheme_nav_history_scheme_date", "scheme_code", "nav_date", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    scheme_code: Mapped[str] = mapped_column(ForeignKey("schemes.scheme_code"), index=True)
    nav_date: Mapped[date] = mapped_column(Date)
    nav: Mapped[Decimal] = mapped_column(Nav())
