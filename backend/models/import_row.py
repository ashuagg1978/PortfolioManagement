from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base
from db.types import Money, Nav, Units


class ImportRow(Base):
    """One parsed row from an uploaded workbook/statement, before commit.

    action tracks the resolution state: NEW (ready to commit), DUPLICATE
    (source_hash already exists), UNMAPPED (raw_scheme_name has no
    resolved_scheme_code yet - surfaced to the user for manual mapping), or
    ERROR (row could not be parsed at all).
    """

    __tablename__ = "import_rows"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("import_batches.id"), index=True)
    row_index: Mapped[int] = mapped_column(Integer)
    sheet_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    raw_json: Mapped[str] = mapped_column(Text)  # original row, for audit/debugging

    account_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    raw_scheme_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # The scheme code as given in the file's own "Scheme Code" column, if
    # any - kept distinct from resolved_scheme_code so a wrong/unknown code
    # can be shown back to the user rather than silently discarded.
    scheme_code_hint: Mapped[str | None] = mapped_column(String(20), nullable=True)
    resolved_scheme_code: Mapped[str | None] = mapped_column(String(20), nullable=True)

    transaction_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    type: Mapped[str | None] = mapped_column(String(20), nullable=True)  # TransactionType
    amount: Mapped[Decimal | None] = mapped_column(Money(), nullable=True)
    nav: Mapped[Decimal | None] = mapped_column(Nav(), nullable=True)
    units: Mapped[Decimal | None] = mapped_column(Units(), nullable=True)
    folio_no: Mapped[str | None] = mapped_column(String(40), nullable=True)
    source_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    action: Mapped[str] = mapped_column(String(20))  # ImportRowAction
    error: Mapped[str | None] = mapped_column(String(255), nullable=True)
