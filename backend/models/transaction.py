from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base
from db.types import Money, Nav, Units


class Transaction(Base):
    """A single confirmed unit allotment or redemption.

    type answers *what* happened (PURCHASE/REDEMPTION); source answers
    *where it came from* (MANUAL/SIP/IMPORT). A SIP credit is a PURCHASE
    whose source is SIP - collapsing "what" and "where from" into one enum
    (as the original PRD did with type ∈ Purchase/Redemption/SIP) makes a
    SIP redemption inexpressible.

    nav and units are NOT NULL: a row only exists once a human has supplied
    the real NAV and quantity from a statement. Nothing in this system
    fabricates a transaction with a guessed or missing NAV.

    commission is derived (see app/services/charges.py) from amount, nav and
    units, then stored - not because it can't be recomputed, but because it
    is what the user actually confirmed at entry time.
    """

    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint("account_id", "source_hash", name="uq_txn_account_source_hash"),
        # Idempotency key for SIP confirmations: (sip_id, sip_scheduled_date).
        # A partial index because both columns are NULL for MANUAL/IMPORT rows.
        Index(
            "uq_txn_sip_occurrence",
            "sip_id",
            "sip_scheduled_date",
            unique=True,
            sqlite_where=text("sip_id IS NOT NULL"),
        ),
        Index("ix_txn_account_scheme_date", "account_id", "scheme_code", "transaction_date"),
        Index("ix_txn_not_deleted", "is_deleted"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    scheme_code: Mapped[str] = mapped_column(ForeignKey("schemes.scheme_code"), index=True)
    transaction_date: Mapped[date] = mapped_column(Date, index=True)

    type: Mapped[str] = mapped_column(String(20))  # TransactionType
    source: Mapped[str] = mapped_column(String(20), default="MANUAL")  # TransactionSource
    sip_id: Mapped[int | None] = mapped_column(ForeignKey("sips.id"), nullable=True)
    sip_scheduled_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    amount: Mapped[Decimal] = mapped_column(Money())  # actual money moved at the bank
    nav: Mapped[Decimal] = mapped_column(Nav())
    units: Mapped[Decimal] = mapped_column(Units())
    commission: Mapped[Decimal] = mapped_column(Money(), default=Decimal("0"))
    # -amount for PURCHASE, +amount for REDEMPTION - mirrors the workbook's
    # _CashFlows sheet so reconciliation is a direct comparison, and is what
    # feeds XIRR directly.
    signed_amount: Mapped[Decimal] = mapped_column(Money())

    folio_no: Mapped[str | None] = mapped_column(String(40), nullable=True)
    status: Mapped[str | None] = mapped_column(String(40), nullable=True)

    # Dedupe key for imports: the broker's own Transaction ID when present,
    # else sha256(account, scheme, date, type, amount, units, folio).
    source_hash: Mapped[str] = mapped_column(String(64), index=True)

    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
