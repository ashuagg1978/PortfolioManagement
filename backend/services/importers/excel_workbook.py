"""Imports a single-sheet transaction statement (the template downloaded
from GET /api/imports/template, or any similarly-shaped .xlsx), plus two
optional enrichment sheets carried over from the legacy multi-account
workbook this app replaced: 'Scheme Map' (raw name -> Display Scheme) and
'NAV Reference' (Display Scheme -> AMFI Scheme Code).

The target account for every row is chosen once on the upload screen (see
services/imports.py::stage_import), not inferred from the sheet - so
exactly one transaction sheet is used. If a file has more than one
sheet whose header looks like a transaction table (e.g. an old multi-
account workbook), only the first is parsed; the rest are reported back
via WorkbookParseResult.other_sheets_ignored so the caller can warn about
it rather than silently dropping data.

Column positions are NOT hardcoded - the header row is located by scanning
the first 10 rows for recognizable column names (case-insensitive, tolerant
of the exact label). This is deliberate: the same lesson that broke the
legacy workbook's own AMFI NAV lookup (a hardcoded VLOOKUP column index)
applies here.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from dateutil import parser as dateutil_parser
from openpyxl import load_workbook

from models.enums import TransactionType
from services.importers.base import ParsedRow

_HEADER_ALIASES: dict[str, list[str]] = {
    "date": ["date", "transaction date", "txn date"],
    "transaction_type": ["transaction type", "txn type", "type"],
    "scheme_code": ["scheme code", "amfi code", "amfi scheme code", "scheme code (amfi)"],
    "display_scheme": ["display scheme"],
    "scheme_name": ["scheme name", "fund name", "scheme name (raw)"],
    "folio_no": ["folio no", "folio no.", "folio"],
    "nav": ["last recorded nav", "nav"],
    "amount": ["amount"],
    "units": ["unit", "units"],
    "signed_amount": ["signed amount"],
}


def _locate_header(
    ws, required: set[str], aliases: dict[str, list[str]]
) -> tuple[int, dict[str, int]] | None:
    """Scans the first 10 rows; returns (row_index, {purpose: col_index})
    for the first row whose headers cover every purpose in `required`.

    Matching is tolerant on purpose: an exact match against the known
    aliases is tried first, falling back to "header text contains the
    shortest alias" - real files label the same concept slightly
    differently (e.g. 'Scheme Name' vs 'Scheme Name (raw)').
    """
    for row_idx in range(1, 11):
        try:
            values = [c.value for c in ws[row_idx]]
        except IndexError:
            # Read-only worksheets raise rather than returning an empty row
            # once row_idx exceeds the sheet's actual row count (a short
            # sheet, e.g. a handful of example rows in the template).
            break
        lowered = {str(v).strip().lower(): i for i, v in enumerate(values) if v is not None}
        col_map: dict[str, int] = {}
        claimed_cols: set[int] = set()

        # Pass 1: exact alias matches take priority, and claim their column
        # so pass 2 can't also match it for a different purpose - without
        # this, "amount" being a substring of "signed amount" would let the
        # signed_amount column double as an (incorrect) amount match.
        for purpose, alias_list in aliases.items():
            for alias in alias_list:
                if alias in lowered:
                    col_map[purpose] = lowered[alias]
                    claimed_cols.add(lowered[alias])
                    break

        # Pass 2: fallback substring matching for anything still unresolved.
        for purpose, alias_list in aliases.items():
            if purpose in col_map:
                continue
            for header_text, idx in lowered.items():
                if idx in claimed_cols:
                    continue
                if any(alias in header_text for alias in alias_list):
                    col_map[purpose] = idx
                    claimed_cols.add(idx)
                    break

        if required.issubset(col_map.keys()):
            return row_idx, col_map
    return None


def _to_decimal(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def _to_date(value: object) -> date | None:
    """Accepts a real Excel date cell (already a datetime/date once openpyxl
    parses it), or a string in essentially any common format - '2024-01-15',
    '15-Jan-2024', '15/01/2024', 'January 15, 2024', etc. dayfirst=True
    because this app's dates are Indian-statement dates (DD/MM over MM/DD
    when a numeric format is ambiguous).
    """
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return dateutil_parser.parse(str(value), dayfirst=True).date()
    except (ValueError, OverflowError, dateutil_parser.ParserError):
        return None


def _to_scheme_code(value: object) -> str | None:
    if value is None or value == "":
        return None
    # Excel often stores a numeric-looking code as a float (e.g. 103196.0)
    # when the cell isn't explicitly text-formatted.
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip() or None


def _classify_type(raw_type: str | None, signed_amount: Decimal | None) -> str | None:
    if raw_type:
        t = raw_type.strip().lower()
        # "redeem" is NOT a substring of "redemption" (they diverge at the
        # 5th letter: redEEm vs redEMption) - both real-world spellings
        # need checking explicitly, not just one.
        if "redeem" in t or "redemption" in t:
            return TransactionType.REDEMPTION
        if "purchase" in t or "sip" in t or "buy" in t or "switch in" in t:
            return TransactionType.PURCHASE
    if signed_amount is not None and signed_amount != 0:
        return TransactionType.REDEMPTION if signed_amount > 0 else TransactionType.PURCHASE
    return None


def _cell(values: list, col_map: dict[str, int], purpose: str) -> object:
    idx = col_map.get(purpose)
    return values[idx] if idx is not None and idx < len(values) else None


def _parse_txn_sheet(ws, sheet_name: str) -> list[ParsedRow]:
    header = _locate_header(ws, required={"date", "amount", "units"}, aliases=_HEADER_ALIASES)
    if header is None:
        return []
    header_row_idx, col_map = header
    header_labels = [str(c.value) if c.value is not None else "" for c in ws[header_row_idx]]

    rows: list[ParsedRow] = []
    for row_idx, row in enumerate(
        ws.iter_rows(min_row=header_row_idx + 1), start=header_row_idx + 1
    ):
        values = [c.value for c in row]
        if all(v is None for v in values):
            continue

        raw = {
            header_labels[i]: (v.isoformat() if isinstance(v, (date, datetime)) else v)
            for i, v in enumerate(values)
            if i < len(header_labels) and header_labels[i]
        }

        txn_date = _to_date(_cell(values, col_map, "date"))
        amount = _to_decimal(_cell(values, col_map, "amount"))
        units = _to_decimal(_cell(values, col_map, "units"))
        nav = _to_decimal(_cell(values, col_map, "nav"))
        signed_amount = _to_decimal(_cell(values, col_map, "signed_amount"))
        raw_type = _cell(values, col_map, "transaction_type")
        scheme_name = _cell(values, col_map, "display_scheme") or _cell(values, col_map, "scheme_name")
        scheme_code_hint = _to_scheme_code(_cell(values, col_map, "scheme_code"))
        folio_no = _cell(values, col_map, "folio_no")

        txn_type = _classify_type(str(raw_type) if raw_type else None, signed_amount)

        error = None
        if txn_date is None:
            error = "missing or unparseable date"
        elif amount is None:
            error = "missing or unparseable amount"
        elif units is None:
            error = "missing or unparseable units"
        elif nav is None:
            error = "missing or unparseable NAV"
        elif txn_type is None:
            error = "could not classify transaction type (purchase vs redemption)"
        elif not scheme_name and not scheme_code_hint:
            error = "missing scheme name and scheme code"

        rows.append(
            ParsedRow(
                sheet_name=sheet_name,
                row_index=row_idx,
                raw=raw,
                transaction_date=txn_date,
                type=txn_type,
                raw_scheme_name=str(scheme_name).strip() if scheme_name else None,
                scheme_code_hint=scheme_code_hint,
                folio_no=str(folio_no).strip() if folio_no else None,
                nav=abs(nav) if nav is not None else None,
                amount=abs(amount) if amount is not None else None,
                units=abs(units) if units is not None else None,
                error=error,
            )
        )
    return rows


@dataclass(frozen=True, slots=True)
class SchemeMapEntry:
    raw_name: str
    display_scheme: str


@dataclass(frozen=True, slots=True)
class NavReferenceEntry:
    display_scheme: str
    scheme_code: str | None


@dataclass(frozen=True, slots=True)
class WorkbookParseResult:
    sheet_used: str | None
    other_sheets_ignored: list[str]
    rows: list[ParsedRow]
    scheme_map: list[SchemeMapEntry]
    nav_reference: list[NavReferenceEntry]


def _parse_scheme_map(wb) -> list[SchemeMapEntry]:
    if "Scheme Map" not in wb.sheetnames:
        return []
    ws = wb["Scheme Map"]
    header = _locate_header(ws, required={"scheme_name", "display_scheme"}, aliases=_HEADER_ALIASES)
    if header is None:
        return []
    header_row_idx, col_map = header
    entries = []
    for row in ws.iter_rows(min_row=header_row_idx + 1):
        values = [c.value for c in row]
        raw_name = _cell(values, col_map, "scheme_name")
        display = _cell(values, col_map, "display_scheme")
        if raw_name and display:
            entries.append(SchemeMapEntry(str(raw_name).strip(), str(display).strip()))
    return entries


def _parse_nav_reference(wb) -> list[NavReferenceEntry]:
    if "NAV Reference" not in wb.sheetnames:
        return []
    ws = wb["NAV Reference"]
    aliases = {**_HEADER_ALIASES, "scheme_code": ["scheme code"]}
    header = _locate_header(ws, required={"display_scheme", "scheme_code"}, aliases=aliases)
    if header is None:
        return []
    header_row_idx, col_map = header
    entries = []
    for row in ws.iter_rows(min_row=header_row_idx + 1):
        values = [c.value for c in row]
        display = _cell(values, col_map, "display_scheme")
        code = _to_scheme_code(_cell(values, col_map, "scheme_code"))
        if display:
            entries.append(NavReferenceEntry(str(display).strip(), code))
    return entries


def parse_workbook(file_bytes: bytes) -> WorkbookParseResult:
    wb = load_workbook(io.BytesIO(file_bytes), data_only=True, read_only=True)

    sheet_used: str | None = None
    other_sheets_ignored: list[str] = []
    rows: list[ParsedRow] = []

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        if _locate_header(ws, required={"date", "amount", "units"}, aliases=_HEADER_ALIASES) is None:
            continue  # not a transaction sheet (e.g. Instructions, Scheme Map, NAV Reference)
        if sheet_used is None:
            sheet_used = sheet_name
            rows = _parse_txn_sheet(ws, sheet_name)
        else:
            # Single-tab import: only the first transaction-shaped sheet is
            # used. Reported back rather than silently merged or dropped.
            other_sheets_ignored.append(sheet_name)

    return WorkbookParseResult(
        sheet_used=sheet_used,
        other_sheets_ignored=other_sheets_ignored,
        rows=rows,
        scheme_map=_parse_scheme_map(wb),
        nav_reference=_parse_nav_reference(wb),
    )
