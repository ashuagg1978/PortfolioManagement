import pytest
from fastapi.testclient import TestClient

from core.config import settings
from core.security import hash_password, verify_password
from db.session import get_db
from main import app as fastapi_app
from models.user import User
from services import login_throttle


@pytest.fixture()
def auth_client(db_session):
    """Unlike `client`, does NOT override get_current_user - real token auth."""
    login_throttle.reset()
    admin = User(name="Admin", email="admin", password_hash=hash_password("adminpass1"), is_admin=True)
    alice = User(name="Alice", email="alice@example.com", password_hash=hash_password("alicepass1"))
    db_session.add_all([admin, alice])
    db_session.commit()
    fastapi_app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(fastapi_app) as c:
        yield c
    fastapi_app.dependency_overrides.clear()


def _login(c, username, password):
    return c.post("/api/auth/login", json={"username": username, "password": password})


def _headers(c, username, password):
    token = _login(c, username, password).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_password_hash_roundtrip():
    stored = hash_password("secret-pw")
    assert verify_password("secret-pw", stored)
    assert not verify_password("other", stored)
    assert not verify_password("secret-pw", None)


@pytest.mark.parametrize(
    "path", ["/api/dashboard", "/api/accounts", "/api/transactions", "/api/sips", "/api/imports/template", "/api/admin/users"]
)
def test_api_requires_token(auth_client, path):
    assert auth_client.get(path).status_code == 401
    assert auth_client.get(path, headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_health_stays_public(auth_client):
    assert auth_client.get("/health").status_code == 200


def test_login_success_and_me(auth_client):
    res = _login(auth_client, "alice@example.com", "alicepass1")
    assert res.status_code == 200
    body = res.json()
    assert body["user"]["email"] == "alice@example.com"
    assert body["user"]["is_admin"] is False
    me = auth_client.get("/api/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.json()["name"] == "Alice"


def test_login_rejects_bad_credentials(auth_client):
    assert _login(auth_client, "alice@example.com", "wrong").status_code == 401
    assert _login(auth_client, "nobody", "whatever1").status_code == 401


def test_login_lockout_after_repeated_failures(auth_client):
    for _ in range(settings.login_max_failures):
        assert _login(auth_client, "alice@example.com", "wrong").status_code == 401
    assert _login(auth_client, "alice@example.com", "alicepass1").status_code == 429


def test_users_only_see_their_own_data(auth_client):
    alice = _headers(auth_client, "alice@example.com", "alicepass1")
    admin = _headers(auth_client, "admin", "adminpass1")
    created = auth_client.post("/api/accounts", json={"account_name": "Mine", "platform": "Z"}, headers=alice)
    assert created.status_code == 201
    assert [a["account_name"] for a in auth_client.get("/api/accounts", headers=alice).json()] == ["Mine"]
    assert auth_client.get("/api/accounts", headers=admin).json() == []
    assert auth_client.patch(
        f"/api/accounts/{created.json()['id']}", json={"account_name": "X", "platform": "Z"}, headers=admin
    ).status_code == 404


def test_admin_endpoints_are_admin_only(auth_client):
    alice = _headers(auth_client, "alice@example.com", "alicepass1")
    assert auth_client.get("/api/admin/users", headers=alice).status_code == 403
    assert auth_client.post(
        "/api/admin/users", json={"name": "B", "email": "b@x.com", "password": "password1"}, headers=alice
    ).status_code == 403


def test_admin_creates_user_who_can_log_in_then_deactivates(auth_client):
    admin = _headers(auth_client, "admin", "adminpass1")
    res = auth_client.post(
        "/api/admin/users", json={"name": "Bob", "email": "bob@x.com", "password": "bobpass12"}, headers=admin
    )
    assert res.status_code == 201
    bob_id = res.json()["id"]
    bob = _headers(auth_client, "bob@x.com", "bobpass12")
    assert auth_client.get("/api/accounts", headers=bob).status_code == 200

    dup = auth_client.post(
        "/api/admin/users", json={"name": "Bob", "email": "bob@x.com", "password": "bobpass12"}, headers=admin
    )
    assert dup.status_code == 422

    auth_client.patch(f"/api/admin/users/{bob_id}", json={"is_active": False}, headers=admin)
    assert auth_client.get("/api/accounts", headers=bob).status_code == 401  # existing token dies too
    assert _login(auth_client, "bob@x.com", "bobpass12").status_code == 401


def test_admin_cannot_lock_themselves_out(auth_client):
    admin = _headers(auth_client, "admin", "adminpass1")
    me = auth_client.get("/api/auth/me", headers=admin).json()
    res = auth_client.patch(f"/api/admin/users/{me['id']}", json={"is_active": False}, headers=admin)
    assert res.status_code == 400


def test_change_password(auth_client):
    alice = _headers(auth_client, "alice@example.com", "alicepass1")
    bad = auth_client.post(
        "/api/auth/change-password", json={"current_password": "nope", "new_password": "newpass123"}, headers=alice
    )
    assert bad.status_code == 400
    ok = auth_client.post(
        "/api/auth/change-password",
        json={"current_password": "alicepass1", "new_password": "newpass123"},
        headers=alice,
    )
    assert ok.status_code == 204
    assert _login(auth_client, "alice@example.com", "alicepass1").status_code == 401
    assert _login(auth_client, "alice@example.com", "newpass123").status_code == 200
