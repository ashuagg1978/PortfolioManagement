"""End-to-end tests for the single-sheet, explicit-account import flow."""

import io
from datetime import date
from pathlib import Path

import pytest
from openpyxl import Workbook

from models.scheme import Scheme

WORKBOOK = Path(__file__).resolve().parents[2] / "MFs Portfolio Dashboard.xlsx"

_HEADERS = ["Date", "Transaction Type", "Scheme Code", "Scheme Name", "Folio No", "NAV", "Amount", "Units"]


def _build_sheet(rows: list[list]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Transactions"
    ws.append(_HEADERS)
    for row in rows:
        ws.append(row)
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def _seed_scheme(db_session, code="103196", name="Nippon India ELSS Tax Saver Fund"):
    db_session.add(Scheme(scheme_code=code, scheme_name=name, latest_nav="131.5970", nav_date=date.today()))
    db_session.commit()


def _upload(client, content: bytes, account_id: int):
    return client.post(
        "/api/imports", files={"file": ("statement.xlsx", content)}, data={"account_id": str(account_id)}
    )


def test_single_sheet_upload_resolves_via_scheme_code_and_commits(client, db_session):
    _seed_scheme(db_session)
    account_id = client.get("/api/accounts").json()[0]["id"]

    content = _build_sheet(
        [["2024-01-15", "Purchase", "103196", "Nippon India ELSS Tax Saver Fund", "", 120.5, 5000, 41.494]]
    )
    r = _upload(client, content, account_id)
    assert r.status_code == 201
    batch = r.json()
    assert batch["sheet_used"] == "Transactions"
    assert batch["account_id"] == account_id
    assert batch["action_counts"] == {"NEW": 1}

    r = client.post(f"/api/imports/{batch['id']}/commit")
    assert r.status_code == 200
    assert r.json()["committed"] == 1

    txns = client.get("/api/transactions").json()
    assert len(txns) == 1
    assert txns[0]["scheme_code"] == "103196"
    assert txns[0]["source"] == "IMPORT"


def test_flexible_date_formats_all_parse(client, db_session):
    _seed_scheme(db_session)
    account_id = client.get("/api/accounts").json()[0]["id"]
    content = _build_sheet(
        [
            ["15-Jan-2024", "Purchase", "103196", "", "", 100, 1000, 10],
            ["15/02/2024", "Purchase", "103196", "", "", 100, 1000, 10],
            ["March 15, 2024", "Purchase", "103196", "", "", 100, 1000, 10],
        ]
    )
    r = _upload(client, content, account_id)
    assert r.json()["action_counts"].get("NEW") == 3


def test_unresolvable_scheme_asks_for_mapping_on_screen(client, db_session):
    _seed_scheme(db_session)
    account_id = client.get("/api/accounts").json()[0]["id"]
    content = _build_sheet(
        [["2024-01-15", "Purchase", "", "Some Totally Unknown Fund Name", "", 100, 1000, 10]]
    )
    r = _upload(client, content, account_id)
    batch = r.json()
    assert batch["action_counts"] == {"UNMAPPED": 1}
    assert batch["unmapped_scheme_keys"] == ["Some Totally Unknown Fund Name"]

    r = client.post(
        f"/api/imports/{batch['id']}/mappings/scheme",
        json={"key": "Some Totally Unknown Fund Name", "scheme_code": "103196"},
    )
    assert r.status_code == 200
    assert r.json()["action_counts"] == {"NEW": 1}


def test_unresolvable_scheme_code_alone_is_also_surfaced(client, db_session):
    """A row with an invalid/unknown code and no name at all still shows up
    for resolution, keyed by the attempted code rather than being silently
    dropped into an unlabeled bucket.
    """
    _seed_scheme(db_session)
    account_id = client.get("/api/accounts").json()[0]["id"]
    content = _build_sheet([["2024-01-15", "Purchase", "999999", "", "", 100, 1000, 10]])
    r = _upload(client, content, account_id)
    batch = r.json()
    assert batch["action_counts"] == {"UNMAPPED": 1}
    assert batch["unmapped_scheme_keys"] == ["[unknown scheme code 999999]"]


def test_soft_deleted_transaction_is_restored_not_blocked_on_reimport(client, db_session):
    _seed_scheme(db_session)
    account_id = client.get("/api/accounts").json()[0]["id"]
    content = _build_sheet(
        [["2024-01-15", "Purchase", "103196", "", "", 120.5, 5000, 41.494]]
    )

    batch_id = _upload(client, content, account_id).json()["id"]
    client.post(f"/api/imports/{batch_id}/commit")

    txn = client.get("/api/transactions").json()[0]
    client.delete(f"/api/transactions/{txn['id']}")
    assert client.get("/api/transactions").json() == []

    # Re-upload the exact same statement - should NOT be flagged a duplicate.
    batch2 = _upload(client, content, account_id).json()
    assert batch2["action_counts"] == {"NEW": 1}

    result = client.post(f"/api/imports/{batch2['id']}/commit").json()
    assert result["restored"] == 1
    assert result["committed"] == 0
    assert len(client.get("/api/transactions").json()) == 1


def test_true_duplicate_is_skipped_not_recommitted(client, db_session):
    _seed_scheme(db_session)
    account_id = client.get("/api/accounts").json()[0]["id"]
    content = _build_sheet(
        [["2024-01-15", "Purchase", "103196", "", "", 120.5, 5000, 41.494]]
    )
    batch_id = _upload(client, content, account_id).json()["id"]
    client.post(f"/api/imports/{batch_id}/commit")

    # Re-upload without deleting anything first - a genuine duplicate.
    batch2 = _upload(client, content, account_id).json()
    assert batch2["action_counts"] == {"DUPLICATE": 1}

    result = client.post(f"/api/imports/{batch2['id']}/commit").json()
    assert result["duplicates"] == 1
    assert result["committed"] == 0
    assert len(client.get("/api/transactions").json()) == 1


@pytest.mark.skipif(not WORKBOOK.exists(), reason="legacy workbook not present")
def test_legacy_multi_sheet_workbook_uses_only_the_first_transaction_sheet(client):
    """The old multi-account workbook this app replaced still uploads
    without error under the new single-tab model - it just imports the
    first Txn-* sheet found and reports the rest as ignored, rather than
    silently merging several accounts' data into the one chosen account.
    """
    account_id = client.get("/api/accounts").json()[0]["id"]
    with WORKBOOK.open("rb") as f:
        r = client.post(
            "/api/imports",
            files={"file": ("workbook.xlsx", f)},
            data={"account_id": str(account_id)},
        )
    assert r.status_code == 201
    batch = r.json()
    assert batch["sheet_used"] is not None
    assert batch["sheet_used"].startswith("Txn-")
    assert len(batch["other_sheets_ignored"]) == 4
    assert batch["row_count"] > 0
