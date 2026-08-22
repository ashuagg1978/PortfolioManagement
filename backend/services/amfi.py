"""Parses and syncs the AMFI NAVAll.txt feed.

The feed is semicolon-delimited with 8 columns as of 2026:

    Scheme Code;ISIN Div Payout/ ISIN Growth;ISIN Div Reinvestment;
    Scheme Name;Plan;Option;Net Asset Value;Date

interleaved with AMC-name and category-heading lines (1 field, no
semicolons) and blank lines. Columns are located BY NAME from the header
row, not by position - the feed used to be 6 columns and gained Plan/Option
without warning, silently breaking any code (including the spreadsheet this
app replaces) that indexed by position.

Only rows where field 1 is entirely digits are treated as data rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import httpx
from sqlalchemy import Table
from sqlalchemy.orm import Session

from core.config import settings
from db.upsert import upsert
from models.scheme import Scheme

_EXPECTED_HEADERS = {
    "scheme_code": "Scheme Code",
    "isin_growth": "ISIN Div Payout/ ISIN Growth",
    "isin_reinvestment": "ISIN Div Reinvestment",
    "scheme_name": "Scheme Name",
    "plan": "Plan",
    "option": "Option",
    "nav": "Net Asset Value",
    "date": "Date",
}


@dataclass(frozen=True, slots=True)
class SchemeRow:
    scheme_code: str
    scheme_name: str
    isin_growth: str | None
    isin_reinvestment: str | None
    plan: str | None
    option: str | None
    nav: Decimal
    nav_date: date


@dataclass(frozen=True, slots=True)
class ParseResult:
    rows: list[SchemeRow]
    rows_seen: int
    rows_skipped: int


def _null(value: str) -> str | None:
    value = value.strip()
    return None if value in ("", "-") else value


def parse_navall(text: str) -> ParseResult:
    """Pure function, no I/O - directly unit-testable against a fixture."""
    lines = text.splitlines()
    if not lines:
        return ParseResult(rows=[], rows_seen=0, rows_skipped=0)

    header = [h.strip() for h in lines[0].split(";")]
    try:
        col = {key: header.index(label) for key, label in _EXPECTED_HEADERS.items()}
    except ValueError as exc:
        raise ValueError(
            f"AMFI feed header changed shape - expected column {exc} not found. "
            f"Got headers: {header!r}"
        ) from exc

    rows: list[SchemeRow] = []
    seen = 0
    skipped = 0

    for line in lines[1:]:
        fields = line.split(";")
        if len(fields) != len(header):
            continue  # blank line, AMC name, or category heading
        scheme_code = fields[col["scheme_code"]].strip()
        if not scheme_code.isdigit():
            continue  # header/section line, not a data row

        seen += 1
        try:
            nav = Decimal(fields[col["nav"]].strip())
            nav_date = datetime.strptime(fields[col["date"]].strip(), "%d-%b-%Y").date()
        except (InvalidOperation, ValueError):
            # A handful of stale/dead schemes carry "N.A." or a malformed
            # date instead of a real NAV - skip just that row, not the batch.
            skipped += 1
            continue

        rows.append(
            SchemeRow(
                scheme_code=scheme_code,
                scheme_name=fields[col["scheme_name"]].strip(),
                isin_growth=_null(fields[col["isin_growth"]]),
                isin_reinvestment=_null(fields[col["isin_reinvestment"]]),
                plan=_null(fields[col["plan"]]),
                option=_null(fields[col["option"]]),
                nav=nav,
                nav_date=nav_date,
            )
        )

    return ParseResult(rows=rows, rows_seen=seen, rows_skipped=skipped)


@dataclass(frozen=True, slots=True)
class SyncResult:
    rows_parsed: int
    rows_upserted: int
    rows_skipped: int
    feed_date: date | None
    duration_ms: int


# SQLite caps bound parameters per statement (default ~32k, but keeping a
# safe margin) - 14k+ rows x 8 columns needs chunking regardless.
_CHUNK_SIZE = 1000


def fetch_navall_text(url: str | None = None) -> str:
    resp = httpx.get(url or settings.amfi_nav_url, timeout=60.0)
    resp.raise_for_status()
    return resp.text


def sync_navs(db: Session, *, text: str | None = None) -> SyncResult:
    """Fetches (unless `text` is supplied, e.g. by a test) and upserts the
    full AMFI feed inside one transaction, so a mid-feed failure leaves the
    previously-synced NAVs intact rather than half-updating them.
    """
    started = datetime.now()
    raw = text if text is not None else fetch_navall_text()
    result = parse_navall(raw)

    table: Table = Scheme.__table__
    for i in range(0, len(result.rows), _CHUNK_SIZE):
        chunk = result.rows[i : i + _CHUNK_SIZE]
        upsert(
            db,
            table,
            [
                {
                    "scheme_code": r.scheme_code,
                    "scheme_name": r.scheme_name,
                    "isin_growth": r.isin_growth,
                    "isin_reinvestment": r.isin_reinvestment,
                    "plan": r.plan,
                    "option": r.option,
                    "latest_nav": r.nav,
                    "nav_date": r.nav_date,
                }
                for r in chunk
            ],
            index_elements=["scheme_code"],
        )
    db.commit()

    feed_date = max((r.nav_date for r in result.rows), default=None)
    duration_ms = int((datetime.now() - started).total_seconds() * 1000)
    return SyncResult(
        rows_parsed=len(result.rows),
        rows_upserted=len(result.rows),
        rows_skipped=result.rows_skipped,
        feed_date=feed_date,
        duration_ms=duration_ms,
    )
