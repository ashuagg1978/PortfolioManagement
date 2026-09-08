"""The one place that knows SQLite's ON CONFLICT syntax.

Isolated here so a future move to Postgres (which spells this differently)
touches a single function instead of every call site that needs upsert
semantics (NAV sync, SIP idempotency, import dedupe).
"""

from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import Table
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

# SQLite caps bound parameters per statement (its default limit is in the
# tens of thousands, but older builds go as low as 999) - a single call with
# enough rows x columns can exceed it and raise "too many SQL variables".
# Chunking here, once, means every caller (current and future) gets this for
# free rather than needing to remember it - see services/amfi.py::sync_navs
# for the bug this guards against: an unchunked call with a real portfolio's
# full NAV history (tens of thousands of 3-column rows) hit exactly this.
_CHUNK_SIZE = 500


def insert_ignore(db: Session, table: Table, rows: Sequence[Mapping[str, Any]]) -> None:
    """Insert rows, silently skipping any that violate a unique/PK constraint."""
    rows = list(rows)
    for i in range(0, len(rows), _CHUNK_SIZE):
        chunk = rows[i : i + _CHUNK_SIZE]
        stmt = sqlite_insert(table).values(chunk)
        stmt = stmt.on_conflict_do_nothing()
        db.execute(stmt)


def upsert(
    db: Session,
    table: Table,
    rows: Sequence[Mapping[str, Any]],
    index_elements: Sequence[str],
) -> None:
    """Insert new rows; update existing rows matched on index_elements."""
    rows = list(rows)
    for i in range(0, len(rows), _CHUNK_SIZE):
        chunk = rows[i : i + _CHUNK_SIZE]
        stmt = sqlite_insert(table).values(chunk)
        update_cols = {
            col.name: col for col in stmt.excluded if col.name not in index_elements
        }
        stmt = stmt.on_conflict_do_update(index_elements=list(index_elements), set_=update_cols)
        db.execute(stmt)
