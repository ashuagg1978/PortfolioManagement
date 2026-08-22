"""The interface any future broker-statement importer implements, so the
staging/preview/commit machinery in services/imports.py (and the
/api/imports routes) stays the same regardless of source format.

The target account is chosen once, up front, on the upload screen (see
services/imports.py::stage_import) rather than inferred per row - so a
ParsedRow carries no account hint of its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ParsedRow:
    sheet_name: str | None
    row_index: int
    raw: dict
    transaction_date: date | None
    type: str | None  # TransactionType, or None if unclassifiable
    raw_scheme_name: str | None
    # The scheme code as given in the file's own "Scheme Code" column, if
    # the template/statement has one - preferred over name-based resolution
    # when it matches a known scheme (see services/imports.py::_resolve_scheme).
    scheme_code_hint: str | None
    folio_no: str | None
    nav: Decimal | None
    amount: Decimal | None
    units: Decimal | None
    error: str | None  # set when the row could not be parsed at all


class StatementImporter(Protocol):
    def parse(self, file_bytes: bytes) -> list[ParsedRow]: ...
