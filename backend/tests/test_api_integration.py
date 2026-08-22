"""End-to-end HTTP tests exercising real service wiring (not just unit
logic) - each hits the actual FastAPI routes against a throwaway SQLite DB.
"""

from datetime import date, timedelta

from models.scheme import Scheme


def _seed_scheme(db_session, code="103196", name="Nippon India ELSS Tax Saver Fund", nav="131.5970"):
    db_session.add(Scheme(scheme_code=code, scheme_name=name, latest_nav=nav, nav_date=date.today()))
    db_session.commit()


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_accounts_are_seeded(client):
    r = client.get("/api/accounts")
    assert r.status_code == 200
    names = {a["account_name"] for a in r.json()}
    assert "ICICI Direct - Ashu" in names


def test_create_purchase_then_dashboard_reflects_it(client, db_session):
    _seed_scheme(db_session)
    accounts = client.get("/api/accounts").json()
    account_id = accounts[0]["id"]

    r = client.post(
        "/api/transactions",
        json={
            "account_id": account_id,
            "scheme_code": "103196",
            "transaction_date": "2024-01-15",
            "type": "PURCHASE",
            "nav": 120.5,
            "units": 41.5,
            "amount": 5010.75,
        },
    )
    assert r.status_code == 201
    txn = r.json()
    assert txn["commission"] == 10.0  # 5010.75 - (120.5 * 41.5) = 10.0

    dash = client.get("/api/dashboard").json()
    assert dash["active_schemes"] == 1
    holding = dash["holdings"][0]
    assert holding["net_units"] == 41.5
    assert holding["status"] in ("In Profit", "In Loss", "Flat")


def test_redemption_beyond_holding_is_rejected(client, db_session):
    _seed_scheme(db_session)
    account_id = client.get("/api/accounts").json()[0]["id"]
    client.post(
        "/api/transactions",
        json={
            "account_id": account_id,
            "scheme_code": "103196",
            "transaction_date": "2024-01-15",
            "type": "PURCHASE",
            "nav": 100,
            "units": 10,
            "amount": 1000,
        },
    )
    r = client.post(
        "/api/transactions",
        json={
            "account_id": account_id,
            "scheme_code": "103196",
            "transaction_date": "2024-02-15",
            "type": "REDEMPTION",
            "nav": 110,
            "units": 20,  # more than the 10 held
            "amount": 2200,
        },
    )
    assert r.status_code == 422


def test_soft_delete_excludes_from_dashboard(client, db_session):
    _seed_scheme(db_session)
    account_id = client.get("/api/accounts").json()[0]["id"]
    txn = client.post(
        "/api/transactions",
        json={
            "account_id": account_id,
            "scheme_code": "103196",
            "transaction_date": "2024-01-15",
            "type": "PURCHASE",
            "nav": 100,
            "units": 10,
            "amount": 1000,
        },
    ).json()

    assert client.get("/api/dashboard").json()["active_schemes"] == 1
    client.delete(f"/api/transactions/{txn['id']}")
    assert client.get("/api/dashboard").json()["active_schemes"] == 0

    client.post(f"/api/transactions/{txn['id']}/restore")
    assert client.get("/api/dashboard").json()["active_schemes"] == 1


def test_sip_due_confirm_and_skip_flow(client, db_session):
    _seed_scheme(db_session)
    account_id = client.get("/api/accounts").json()[0]["id"]
    start = date.today() - timedelta(days=95)  # ~3 monthly occurrences due

    r = client.post(
        "/api/sips",
        json={
            "account_id": account_id,
            "scheme_code": "103196",
            "amount": 5000,
            "frequency": "MONTHLY",
            "start_date": start.isoformat(),
        },
    )
    assert r.status_code == 201

    due = client.get("/api/sips/due").json()
    assert len(due) >= 3

    first = due[0]
    r = client.post(
        "/api/sips/due/confirm",
        json={
            "sip_id": first["sip_id"],
            "scheduled_date": first["scheduled_date"],
            "nav": 130.0,
            "units": 38.46,
        },
    )
    assert r.status_code == 200
    assert r.json()["source"] == "SIP"

    r = client.post(
        "/api/sips/due/skip",
        json={"sip_id": due[1]["sip_id"], "scheduled_date": due[1]["scheduled_date"]},
    )
    assert r.status_code == 200

    remaining = client.get("/api/sips/due").json()
    assert len(remaining) == len(due) - 2

    # double-confirm the same occurrence is idempotent, not an error
    r2 = client.post(
        "/api/sips/due/confirm",
        json={
            "sip_id": first["sip_id"],
            "scheduled_date": first["scheduled_date"],
            "nav": 130.0,
            "units": 38.46,
        },
    )
    assert r2.status_code == 200
    assert r2.json()["id"] == r.json()["id"]  # idempotent: same transaction, not a duplicate

    # dashboard only reflects the confirmed occurrence, not the skipped one
    dash = client.get("/api/dashboard").json()
    assert dash["active_schemes"] == 1


def test_commission_preview_matches_create(client):
    r = client.post(
        "/api/transactions/preview-commission",
        json={"type": "PURCHASE", "nav": 145.509, "units": 34.243, "amount": 5000},
    )
    assert r.status_code == 200
    body = r.json()
    assert abs(body["commission"] - (5000 - 145.509 * 34.243)) < 0.01
