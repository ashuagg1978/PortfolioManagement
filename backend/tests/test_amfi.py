from decimal import Decimal
from pathlib import Path

from services.amfi import parse_navall

FIXTURE = Path(__file__).parent / "fixtures" / "navall_sample.txt"


def _parse():
    return parse_navall(FIXTURE.read_text(encoding="utf-8"))


def test_skips_headers_and_blanks():
    result = _parse()
    # 6 Aditya Birla/Bandhan rows + 4 SBI rows + 1 stale + 1 N.A. (skipped) = 12 seen
    assert result.rows_seen == 12
    assert result.rows_skipped == 1  # the N.A. NAV row
    assert len(result.rows) == 11


def test_empty_plan_and_option_do_not_break_parsing():
    result = _parse()
    sbi_rows = [r for r in result.rows if r.scheme_name == "SBI FLEXICAP FUND"]
    assert len(sbi_rows) == 4
    assert all(r.plan is None and r.option is None for r in sbi_rows)


def test_dash_isin_becomes_none():
    result = _parse()
    row = next(r for r in result.rows if r.scheme_code == "121936")
    assert row.isin_reinvestment is None


def test_nav_and_date_parsed_correctly():
    result = _parse()
    row = next(r for r in result.rows if r.scheme_code == "119551")
    assert row.nav == Decimal("106.9996")
    assert row.nav_date.isoformat() == "2026-08-20"


def test_stale_dated_row_still_parses():
    result = _parse()
    row = next(r for r in result.rows if r.scheme_code == "999999")
    assert row.nav_date.isoformat() == "2018-07-02"


def test_na_nav_row_is_skipped_not_fatal():
    result = _parse()
    assert not any(r.scheme_code == "999998" for r in result.rows)


def test_scheme_name_not_unique_is_fine_at_parse_time():
    # Parsing doesn't need uniqueness - that's what scheme_code is for.
    result = _parse()
    names = [r.scheme_name for r in result.rows]
    assert names.count("SBI FLEXICAP FUND") == 4
