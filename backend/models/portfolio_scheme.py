from __future__ import annotations

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class PortfolioScheme(Base):
    """A user's own display label for a scheme code they hold.

    e.g. scheme_code 103196 -> "Nippon India ELSS Tax Saver (Regular Growth)"
    even though models.scheme.Scheme.scheme_name carries AMFI's official,
    often noisier, name.
    """

    __tablename__ = "portfolio_schemes"
    __table_args__ = (UniqueConstraint("user_id", "scheme_code", name="uq_portfolio_scheme"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    scheme_code: Mapped[str] = mapped_column(ForeignKey("schemes.scheme_code"), index=True)
    display_name: Mapped[str] = mapped_column(String(150))
