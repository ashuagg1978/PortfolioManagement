"""Unit tests for the mfapi.in historical-NAV parsing/matching logic.
Mocked at the httpx layer - the live endpoint was verified manually against
real scheme 103196 while building this (confirmed: startDate/endDate query
params do NOT actually filter the response despite being documented, an
unknown scheme returns HTTP 200 with an empty data array rather than 404,
and a weekend date correctly falls back to the prior Friday) - these tests
lock in that already-verified behavior deterministically.
"""

from datetime import date
from decimal import Decimal
from unittest.mock import Mock, patch

from services.nav_history import fetch_full_history, fetch_nav_on_or_before

_SAMPLE_PAYLOAD = {
    "meta": {"scheme_code": 103196, "scheme_name": "Test Fund"},
    "data": [
        {"date": "21-08-2026", "nav": "131.47960"},
        {"date": "20-08-2026", "nav": "131.59700"},
        {"date": "14-06-2024", "nav": "122.70140"},  # a Friday
        {"date": "13-06-2024", "nav": "121.90000"},
        {"date": "bad-date", "nav": "100.0"},  # malformed - must be skipped, not crash
        {"date": "01-01-2020", "nav": "not-a-number"},  # malformed nav - also skipped
    ],
}


def _mock_response(payload):
    resp = Mock()
    resp.raise_for_status = Mock()
    resp.json = Mock(return_value=payload)
    return resp


def test_exact_date_match():
    with patch("services.nav_history.httpx.get", return_value=_mock_response(_SAMPLE_PAYLOAD)):
        result = fetch_nav_on_or_before("103196", date(2024, 6, 14))
    assert result.nav_date == date(2024, 6, 14)
    assert result.nav == Decimal("122.70140")


def test_weekend_falls_back_to_prior_trading_day():
    # 2024-06-15 is a Saturday; no entry for it in the sample data.
    with patch("services.nav_history.httpx.get", return_value=_mock_response(_SAMPLE_PAYLOAD)):
        result = fetch_nav_on_or_before("103196", date(2024, 6, 15))
    assert result.nav_date == date(2024, 6, 14)


def test_malformed_entries_are_skipped_not_fatal():
    with patch("services.nav_history.httpx.get", return_value=_mock_response(_SAMPLE_PAYLOAD)):
        result = fetch_nav_on_or_before("103196", date(2024, 6, 14))
    assert result is not None  # didn't blow up on the bad rows mixed into the same payload


def test_unknown_scheme_returns_none_not_an_error():
    empty_payload = {"meta": {}, "data": []}
    with patch("services.nav_history.httpx.get", return_value=_mock_response(empty_payload)):
        result = fetch_nav_on_or_before("999999999", date(2024, 6, 14))
    assert result is None


def test_date_outside_lookback_window_returns_none():
    with patch("services.nav_history.httpx.get", return_value=_mock_response(_SAMPLE_PAYLOAD)):
        result = fetch_nav_on_or_before("103196", date(1990, 1, 1))
    assert result is None


def test_network_failure_returns_none_rather_than_raising():
    import httpx

    with patch("services.nav_history.httpx.get", side_effect=httpx.ConnectError("boom")):
        result = fetch_nav_on_or_before("103196", date(2024, 6, 14))
    assert result is None


def test_fetch_full_history_returns_all_valid_points():
    with patch("services.nav_history.httpx.get", return_value=_mock_response(_SAMPLE_PAYLOAD)):
        points = fetch_full_history("103196")
    # 6 entries in the fixture, 2 malformed (bad date, bad nav) - excluded.
    assert len(points) == 4
    assert {p.nav_date for p in points} == {
        date(2026, 8, 21),
        date(2026, 8, 20),
        date(2024, 6, 14),
        date(2024, 6, 13),
    }


def test_fetch_full_history_unknown_scheme_returns_empty_list():
    with patch("services.nav_history.httpx.get", return_value=_mock_response({"meta": {}, "data": []})):
        assert fetch_full_history("999999999") == []


def test_fetch_full_history_network_failure_returns_empty_list_not_raise():
    import httpx

    with patch("services.nav_history.httpx.get", side_effect=httpx.ConnectError("boom")):
        assert fetch_full_history("103196") == []
