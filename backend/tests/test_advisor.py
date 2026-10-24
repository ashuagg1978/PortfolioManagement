"""Advisor endpoints with Gemini HTTP calls mocked; no network or API cost."""

import json
from datetime import date
from decimal import Decimal

import httpx
import pytest

from core.config import settings
from models.account import Account
from models.scheme import Scheme
from models.transaction import Transaction
from services import advisor


@pytest.fixture()
def holding(db_session):
    db_session.add(
        Scheme(
            scheme_code="100001",
            scheme_name="Test Flexi Cap Fund - Direct Plan - Growth",
            latest_nav=Decimal("120"),
            nav_date=date(2026, 10, 8),
        )
    )
    account = db_session.query(Account).first()
    db_session.add(
        Transaction(
            account_id=account.id,
            scheme_code="100001",
            transaction_date=date(2025, 1, 10),
            type="PURCHASE",
            source="MANUAL",
            amount=Decimal("10000"),
            nav=Decimal("100"),
            units=Decimal("100"),
            commission=Decimal("0"),
            signed_amount=Decimal("-10000"),
            source_hash="h1",
        )
    )
    db_session.commit()


@pytest.fixture()
def with_key(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")


def _gemini_reply(payload: dict, *, fenced: bool = False):
    text = json.dumps(payload)
    if fenced:
        text = f"```json\n{text}\n```"
    body = {
        "candidates": [
            {
                "content": {"parts": [{"text": text}]},
                "groundingMetadata": {
                    "groundingChunks": [
                        {"web": {"uri": "https://example.com/factsheet", "title": "Factsheet"}},
                        {"web": {"uri": "https://example.com/factsheet", "title": "Dup"}},
                    ]
                },
            }
        ]
    }
    return httpx.Response(200, json=body)


def test_scheme_advice_parses_fenced_json_and_dedupes_sources(client, holding, with_key, monkeypatch):
    seen = {}

    def fake_post(url, *, json, headers, timeout):
        seen["json"], seen["headers"] = json, headers
        return _gemini_reply(
            {"action": "hold", "confidence": "HIGH", "rationale": "Solid.", "risks": ["Volatility"]},
            fenced=True,
        )

    monkeypatch.setattr(advisor.httpx, "post", fake_post)
    response = client.post("/api/advisor/schemes/100001")

    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "HOLD"
    assert body["confidence"] == "HIGH"
    assert body["sources"] == [{"title": "Factsheet", "url": "https://example.com/factsheet"}]
    assert seen["headers"]["x-goog-api-key"] == "test-key"
    assert seen["json"]["tools"] == [{"google_search": {}}]
    assert "100001|2025-01-10|PURCHASE" in seen["json"]["contents"][0]["parts"][0]["text"]


def test_portfolio_advice_drops_invalid_actions(client, holding, with_key, monkeypatch):
    monkeypatch.setattr(
        advisor.httpx,
        "post",
        lambda *args, **kwargs: _gemini_reply(
            {
                "summary": "Concentrated.",
                "actions": [
                    {"scheme_code": "100001", "scheme_name": "Test", "action": "REDUCE",
                     "suggestion": "Trim", "rationale": "Overweight"},
                    {"scheme_code": None, "scheme_name": "Bogus", "action": "YOLO",
                     "suggestion": "", "rationale": ""},
                ],
                "diversification_notes": ["Only one fund"],
            }
        ),
    )
    response = client.post("/api/advisor/portfolio")
    assert response.status_code == 200
    assert [item["action"] for item in response.json()["actions"]] == ["REDUCE"]


def test_missing_api_key_is_a_clear_503(client, holding, monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "")
    response = client.post("/api/advisor/portfolio")
    assert response.status_code == 503
    assert "config.json" in response.json()["detail"]


def test_unknown_scheme_is_404(client, with_key):
    assert client.post("/api/advisor/schemes/999999").status_code == 404


def test_gemini_http_error_is_surfaced_as_502(client, holding, with_key, monkeypatch):
    monkeypatch.setattr(
        advisor.httpx,
        "post",
        lambda *args, **kwargs: httpx.Response(429, json={"error": {"message": "quota exceeded"}}),
    )
    response = client.post("/api/advisor/schemes/100001")
    assert response.status_code == 502
    assert "quota exceeded" in response.json()["detail"]


def test_non_json_answer_is_502(client, holding, with_key, monkeypatch):
    monkeypatch.setattr(
        advisor.httpx,
        "post",
        lambda *args, **kwargs: httpx.Response(
            200, json={"candidates": [{"content": {"parts": [{"text": "no idea"}]}}]}
        ),
    )
    assert client.post("/api/advisor/schemes/100001").status_code == 502


def test_advice_is_saved_and_returned_by_get(client, holding, with_key, monkeypatch):
    assert client.get("/api/advisor/portfolio").json() is None
    assert client.get("/api/advisor/schemes/100001").json() is None
    monkeypatch.setattr(
        advisor.httpx,
        "post",
        lambda *args, **kwargs: _gemini_reply(
            {"action": "BUY", "confidence": "LOW", "rationale": "v1", "risks": []}
        ),
    )
    posted = client.post("/api/advisor/schemes/100001").json()
    assert posted["generated_at"].endswith("Z") or "+00:00" in posted["generated_at"]

    saved = client.get("/api/advisor/schemes/100001").json()
    assert saved["rationale"] == "v1"
    assert saved["generated_at"] == posted["generated_at"]
    assert saved["sources"][0]["url"] == "https://example.com/factsheet"

    monkeypatch.setattr(
        advisor.httpx,
        "post",
        lambda *args, **kwargs: _gemini_reply(
            {"action": "SELL", "confidence": "LOW", "rationale": "v2", "risks": []}
        ),
    )
    client.post("/api/advisor/schemes/100001")
    assert client.get("/api/advisor/schemes/100001").json()["rationale"] == "v2"
    assert client.get("/api/advisor/portfolio").json() is None


def test_failed_run_keeps_previous_saved_advice(client, holding, with_key, monkeypatch):
    monkeypatch.setattr(
        advisor.httpx,
        "post",
        lambda *args, **kwargs: _gemini_reply(
            {"summary": "good", "actions": [], "diversification_notes": []}
        ),
    )
    client.post("/api/advisor/portfolio")
    monkeypatch.setattr(
        advisor.httpx, "post", lambda *args, **kwargs: httpx.Response(500, json={})
    )
    assert client.post("/api/advisor/portfolio").status_code == 502
    assert client.get("/api/advisor/portfolio").json()["summary"] == "good"