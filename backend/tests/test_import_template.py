from services.import_template import build_template_workbook
from services.importers.excel_workbook import parse_workbook


def test_generated_template_has_one_transactions_sheet_and_round_trips():
    content = build_template_workbook()
    result = parse_workbook(content)

    assert result.sheet_used == "Transactions"
    assert result.other_sheets_ignored == []  # "Instructions" has no Date/Amount header, correctly skipped
    assert len(result.rows) == 3  # the three example rows
    assert all(r.error is None for r in result.rows)


def test_template_example_rows_carry_both_a_valid_and_a_blank_scheme_code():
    content = build_template_workbook()
    result = parse_workbook(content)
    codes = [r.scheme_code_hint for r in result.rows]
    assert "118989" in codes
    assert any(c is None for c in codes)  # the row demonstrating name-only resolution
