"""Exact-decimal column types for SQLite.

SQLite has no native decimal storage class - SQLAlchemy's ``Numeric`` quietly
falls back to Python ``float`` on this dialect, and float drifts on ordinary
arithmetic (``0.1 + 0.2 == 0.30000000000000004``). That is not acceptable for
a financial ledger, so every money/NAV/units column is stored as fixed-
precision TEXT instead, round-tripping through ``Decimal`` exactly.

Trade-off accepted deliberately: SQL cannot ``SUM()``/``AVG()``/``ORDER BY``
these columns meaningfully (they are plain TEXT to the database engine). All
aggregation and sorting happens in Python, in the service layer - which the
metrics engine (FIFO lot walking, XIRR) already has to do anyway at this data
volume (~1,000s of rows).
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import String
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator


class DecimalText(TypeDecorator):
    """Persists a Decimal as a fixed-precision TEXT string."""

    impl = String
    cache_ok = True

    def __init__(self, precision: int, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.precision = precision
        self._quantizer = Decimal(1).scaleb(-precision)

    def process_bind_param(self, value: Any, dialect: Dialect) -> str | None:
        if value is None:
            return None
        d = value if isinstance(value, Decimal) else Decimal(str(value))
        return str(d.quantize(self._quantizer, rounding=ROUND_HALF_UP))

    def process_result_value(self, value: Any, dialect: Dialect) -> Decimal | None:
        if value is None:
            return None
        return Decimal(value)


class Money(DecimalText):
    """Rupees and paise - 2 decimal places."""

    cache_ok = True  # SQLAlchemy wants this re-declared on each subclass, not just inherited

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(precision=2, **kwargs)


class Nav(DecimalText):
    """Net Asset Value - 4 decimal places, matching the AMFI feed."""

    cache_ok = True

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(precision=4, **kwargs)


class Units(DecimalText):
    """Mutual fund unit allotment - 6 decimal places."""

    cache_ok = True

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(precision=6, **kwargs)
