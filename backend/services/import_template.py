"""Generates the downloadable .xlsx bulk-upload template - one flat
'Transactions' sheet shaped exactly the way
services/importers/excel_workbook.py expects to parse it. The account is
chosen on the upload screen, not encoded in the file, so the template
needs no per-account structure.
"""

from __future__ import annotations

import io

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.worksheet.worksheet import Worksheet

_HEADERS = ["Date", "Transaction Type", "Scheme Code", "Scheme Name", "Folio No", "NAV", "Amount", "Units"]
_EXAMPLE_ROWS = [
    ["2024-06-15", "Purchase", "118989", "HDFC Mid Cap Fund - Direct Growth", "1234567", 236.42, 5000, 21.152],
    ["15-Jul-2024", "Purchase", "", "Nippon India ELSS Tax Saver Fund - Growth", "1234567", 145.5090, 5000, 34.360],
    ["01/09/2024", "Redemption", "103196", "Nippon India ELSS Tax Saver Fund - Growth", "1234567", 150.0000, 3000, 20.000],
]


def _write_instructions(ws: Worksheet) -> None:
    ws.title = "Instructions"
    ws.column_dimensions["A"].width = 105
    lines = [
        "Transaction import template",
        "",
        "Fill in one row per transaction on the 'Transactions' sheet. Delete the example rows",
        "before uploading - they're there to show the expected format only.",
        "",
        "You'll pick the account this file imports into on the Import screen itself - every row",
        "in this file goes to that one account, so use a separate upload per account.",
        "",
        "Columns:",
        "  Date              Any common format works - 2024-06-15, 15-Jun-2024, 15/06/2024, etc.",
        "  Transaction Type  Purchase or Redemption",
        "  Scheme Code       The AMFI scheme code, if you know it - strongly recommended. It's",
        "                    the only fully reliable identifier (the same fund name can cover",
        "                    several codes for Direct/Regular and Growth/IDCW variants), so a",
        "                    correct code here guarantees an exact match with no guessing.",
        "  Scheme Name       Used to find the right scheme when Scheme Code is blank or doesn't",
        "                    match - if it can't be resolved automatically, you'll be asked to",
        "                    pick the right one on the Import screen (Sync NAV first so the",
        "                    picker has data to search).",
        "  Folio No          Optional",
        "  NAV               Price per unit on the transaction date",
        "  Amount            The actual amount that moved at your bank - purchases: what you",
        "                    paid; redemptions: what you received.",
        "  Units             Quantity transacted",
        "",
        "Re-uploading a file you've already imported is safe - already-imported rows are",
        "detected and skipped automatically, so it won't create duplicates.",
    ]
    for i, line in enumerate(lines, start=1):
        cell = ws.cell(row=i, column=1, value=line)
        if i == 1:
            cell.font = Font(bold=True, size=14)


def _write_transactions_sheet(ws: Worksheet) -> None:
    ws.title = "Transactions"
    for col, header in enumerate(_HEADERS, start=1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = Font(bold=True)
    for row_offset, example in enumerate(_EXAMPLE_ROWS, start=2):
        for col, value in enumerate(example, start=1):
            cell = ws.cell(row=row_offset, column=col, value=value)
            cell.font = Font(italic=True, color="888888")
    for col, header in enumerate(_HEADERS, start=1):
        ws.column_dimensions[chr(64 + col)].width = max(14, len(header) + 4)


def build_template_workbook() -> bytes:
    wb = Workbook()
    _write_instructions(wb.active)
    _write_transactions_sheet(wb.create_sheet())

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
