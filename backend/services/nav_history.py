"""Historical per-scheme NAV lookup via the community mfapi.in API - used to
pre-fill NAV when confirming a SIP entry dated in the past, where the
official AMFI feed (services/amfi.py) is same-day only and has nothing to
offer for a historical date.

Not authoritative: this is a third-party aggregation of AMFI's own daily
NAV files, offered purely as a starting point the user can review and
override - never written to the ledger without their explicit confirm.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

import httpx

_BASE_URL = "https://api.mfapi.in/mf"

# How far back from the requested date to accept a NAV as "close enough" -
# covers a long weekend/holiday cluster around the requested date without
# silently reaching back into an unrelated month if the scheme has a gap.
_LOOKBACK_DAYS = 10


@dataclass(frozen=True, slots=True)
class NavHistoryPoint:
    nav_date: date
    nav: Decimal


def _parse_entry(entry: dict) -> NavHistoryPoint | None:
    try:
        nav_date = datetime.strptime(entry["date"], "%d-%m-%Y").date()
        nav = Decimal(str(entry["nav"]))
    except (KeyError, ValueError, InvalidOperation, TypeError):
        return None
    return NavHistoryPoint(nav_date=nav_date, nav=nav)


def fetch_nav_on_or_before(scheme_code: str, target_date: date) -> NavHistoryPoint | None:
    """The scheme's NAV on target_date, or the closest trading day before it
    within _LOOKBACK_DAYS.

    mfapi.in's documented startDate/endDate query params were tested live
    against the real API and do NOT actually filter the response - it
    always returns the scheme's entire history regardless - so the date
    match happens here in Python instead of trusting server-side filtering.
    An unknown scheme code returns HTTP 200 with an empty data array (not a
    404), which is handled the same as any other "nothing found" case.

    Returns None on any failure (network, unknown scheme, no data in
    range) rather than raising - this is a convenience prefill, not a
    dependency the rest of the app should ever hard-fail on.
    """
    try:
        resp = httpx.get(f"{_BASE_URL}/{scheme_code}", timeout=20.0)
        resp.raise_for_status()
        payload = resp.json()
    except (httpx.HTTPError, ValueError):
        return None

    points = [p for e in payload.get("data", []) if (p := _parse_entry(e)) is not None]
    if not points:
        return None

    earliest_acceptable = target_date - timedelta(days=_LOOKBACK_DAYS)
    candidates = [p for p in points if earliest_acceptable <= p.nav_date <= target_date]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.nav_date)
