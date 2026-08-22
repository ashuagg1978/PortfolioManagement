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


def insert_ignore(db: Session, table: Table, rows: Sequence[Mapping[str, Any]]) -> None:
    """Insert rows, silently skipping any that violate a unique/PK constraint."""
    if not rows:
        return
    stmt = sqlite_insert(table).values(list(rows))
    stmt = stmt.on_conflict_do_nothing()
    db.execute(stmt)


def upsert(
    db: Session,
    table: Table,
    rows: Sequence[Mapping[str, Any]],
    index_elements: Sequence[str],
) -> None:
    """Insert new rows; update existing rows matched on index_elements."""
    if not rows:
        return
    stmt = sqlite_insert(table).values(list(rows))
    update_cols = {
        col.name: col for col in stmt.excluded if col.name not in index_elements
    }
    stmt = stmt.on_conflict_do_update(index_elements=list(index_elements), set_=update_cols)
    db.execute(stmt)
