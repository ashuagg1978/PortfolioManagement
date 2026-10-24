"""AI recommendations using Gemini and Google Search grounding."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import TypeVar

import httpx
from sqlalchemy.orm import Session

from core.config import settings
from models.account import Account
from models.advice import Advice
from models.transaction import Transaction
from models.user import User
from schemas.advisor import PortfolioAdviceOut, SchemeAdviceOut, SourceOut
from services.portfolio import SchemeHolding, compute_dashboard, compute_holdings

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

DISCLAIMER = (
    "AI-generated from your transaction history and public web sources. It is not "
    "SEBI-registered investment advice - verify with the fund's official documents "
    "or a registered advisor before acting."
)

_SYSTEM = (
    "You are a careful Indian mutual-fund analyst. Use Google Search and rely only on "
    "authoritative sources: AMC factsheets and scheme information documents, AMFI, SEBI, "
    "Value Research, Morningstar India, Moneycontrol, and similar. Never invent returns, "
    "ratings or AUM figures - if you cannot verify something, say so and lower your "
    "confidence. Tax context is India (LTCG/STCG on mutual funds). Answer with a single "
    "JSON object and nothing else."
)


class AdvisorError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def _money(value: Decimal | None) -> str:
    return "n/a" if value is None else f"{value:.2f}"


def _holding_line(holding: SchemeHolding) -> str:
    xirr = "n/a" if holding.xirr is None else f"{float(holding.xirr) * 100:.2f}%"
    pct = "n/a" if holding.pct_gain is None else f"{float(holding.pct_gain):.2f}%"
    return (
        f"- {holding.display_name} [code {holding.scheme_code}]: units={holding.net_units:.3f}, "
        f"cost_basis={_money(holding.net_invested)}, current_value={_money(holding.current_value)}, "
        f"latest_nav={_money(holding.latest_nav)} (as of {holding.nav_date}), "
        f"unrealized={_money(holding.unrealized_gain)}, realized={_money(holding.realized_gain)}, "
        f"gain_pct={pct}, xirr={xirr}, status={holding.status}"
    )


def _ledger_lines(db: Session, user: User, scheme_code: str | None) -> list[str]:
    query = (
        db.query(Transaction)
        .join(Account, Account.id == Transaction.account_id)
        .filter(Account.user_id == user.id, Transaction.is_deleted.is_(False))
    )
    if scheme_code is not None:
        query = query.filter(Transaction.scheme_code == scheme_code)
    rows = query.order_by(Transaction.scheme_code, Transaction.transaction_date, Transaction.id).all()
    return [
        f"{row.scheme_code}|{row.transaction_date}|{row.type}|{row.source}|"
        f"amount={row.amount:.2f}|nav={row.nav}|units={row.units}"
        for row in rows
    ]


def _extract_json(text: str) -> dict:
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    candidate = fenced.group(1) if fenced else text[text.find("{") : text.rfind("}") + 1]
    try:
        data = json.loads(candidate)
    except (json.JSONDecodeError, ValueError) as error:
        raise AdvisorError(502, "Gemini returned a response that was not valid JSON - try again.") from error
    if not isinstance(data, dict):
        raise AdvisorError(502, "Gemini returned an unexpected response shape - try again.")
    return data


def _call_gemini(prompt: str) -> tuple[dict, list[SourceOut]]:
    if not settings.gemini_api_key or settings.gemini_api_key.startswith("PASTE_"):
        raise AdvisorError(
            503, "Gemini API key is not configured - set gemini_api_key in backend/config.json."
        )

    body = {
        "systemInstruction": {"parts": [{"text": _SYSTEM}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "tools": [{"google_search": {}}],
        "generationConfig": {"temperature": 0.3},
    }
    try:
        response = httpx.post(
            GEMINI_URL.format(model=settings.gemini_model),
            json=body,
            headers={"x-goog-api-key": settings.gemini_api_key},
            timeout=settings.gemini_timeout_seconds,
        )
    except httpx.HTTPError as error:
        raise AdvisorError(502, f"Could not reach Gemini: {type(error).__name__}") from error

    if response.status_code != 200:
        try:
            detail = response.json()["error"]["message"]
        except Exception:  # Google's error body shape is outside our control.
            detail = response.text[:200]
        raise AdvisorError(502, f"Gemini API error ({response.status_code}): {detail}")

    payload = response.json()
    candidates = payload.get("candidates") or []
    if not candidates:
        reason = (payload.get("promptFeedback") or {}).get("blockReason", "no candidates returned")
        raise AdvisorError(502, f"Gemini returned no answer ({reason}).")

    candidate = candidates[0]
    text = "".join(
        part.get("text", "") for part in (candidate.get("content") or {}).get("parts", [])
    )
    if not text.strip():
        raise AdvisorError(
            502,
            f"Gemini returned an empty answer ({candidate.get('finishReason', 'unknown')}).",
        )

    sources: list[SourceOut] = []
    seen: set[str] = set()
    for chunk in (candidate.get("groundingMetadata") or {}).get("groundingChunks", []):
        web = chunk.get("web") or {}
        uri = web.get("uri")
        if uri and uri not in seen:
            seen.add(uri)
            sources.append(SourceOut(title=web.get("title") or uri, url=uri))
    return _extract_json(text), sources


AdviceOut = TypeVar("AdviceOut", SchemeAdviceOut, PortfolioAdviceOut)


def save_advice(
    db: Session, user: User, kind: str, scope: str, result: AdviceOut
) -> AdviceOut:
    now = datetime.now(timezone.utc)
    row = (
        db.query(Advice)
        .filter(Advice.user_id == user.id, Advice.kind == kind, Advice.scope == scope)
        .one_or_none()
    )
    payload = result.model_dump_json(exclude={"generated_at"})
    if row is None:
        db.add(Advice(user_id=user.id, kind=kind, scope=scope, result_json=payload, created_at=now))
    else:
        row.result_json = payload
        row.created_at = now
    db.commit()
    return result.model_copy(update={"generated_at": now})


def _load(
    db: Session, user: User, kind: str, scope: str, model: type[AdviceOut]
) -> AdviceOut | None:
    row = (
        db.query(Advice)
        .filter(Advice.user_id == user.id, Advice.kind == kind, Advice.scope == scope)
        .one_or_none()
    )
    if row is None:
        return None
    result = model.model_validate_json(row.result_json)
    return result.model_copy(
        update={"generated_at": row.created_at.replace(tzinfo=timezone.utc)}
    )


def load_scheme_advice(db: Session, user: User, scheme_code: str) -> SchemeAdviceOut | None:
    return _load(db, user, "SCHEME", scheme_code, SchemeAdviceOut)


def load_portfolio_advice(db: Session, user: User) -> PortfolioAdviceOut | None:
    return _load(db, user, "PORTFOLIO", "", PortfolioAdviceOut)


def advise_on_scheme(db: Session, user: User, scheme_code: str) -> SchemeAdviceOut:
    holding = next(
        (item for item in compute_holdings(db, user) if item.scheme_code == scheme_code), None
    )
    if holding is None:
        raise AdvisorError(404, f"No transactions found for scheme {scheme_code}.")

    transactions = "\n".join(_ledger_lines(db, user, scheme_code))
    prompt = f"""Advise whether the investor should BUY more, SELL, or HOLD this mutual fund.

Fund and position (amounts in INR):
{_holding_line(holding)}

Every transaction (scheme|date|type|source|amount|nav|units):
{transactions}

Look up the fund's current standing: category, 1/3/5-year returns vs. its benchmark and category
peers, expense ratio, AUM, fund-manager changes, portfolio concentration, and any recent news.
Weigh that against the investor's own cost basis, holding period (tax impact) and XIRR.

Respond with JSON exactly like:
{{"action": "BUY|SELL|HOLD", "confidence": "LOW|MEDIUM|HIGH",
  "rationale": "3-6 sentences citing concrete figures you verified",
  "risks": ["short risk", "..."]}}"""

    data, sources = _call_gemini(prompt)
    action = str(data.get("action", "")).upper()
    confidence = str(data.get("confidence", "LOW")).upper()
    if action not in {"BUY", "SELL", "HOLD"}:
        raise AdvisorError(502, "Gemini gave an unrecognised recommendation - try again.")
    return SchemeAdviceOut(
        scheme_code=scheme_code,
        display_name=holding.display_name,
        action=action,
        confidence=confidence if confidence in {"LOW", "MEDIUM", "HIGH"} else "LOW",
        rationale=str(data.get("rationale", "")),
        risks=[str(risk) for risk in data.get("risks", [])],
        sources=sources,
        model=settings.gemini_model,
        disclaimer=DISCLAIMER,
    )


_PORTFOLIO_ACTIONS = {"INCREASE", "REDUCE", "EXIT", "REPLACE", "HOLD"}


def advise_on_portfolio(db: Session, user: User) -> PortfolioAdviceOut:
    summary = compute_dashboard(db, user)
    held = [holding for holding in summary.holdings if holding.net_units > 0]
    if not held:
        raise AdvisorError(404, "No current holdings to analyse.")

    xirr = "n/a" if summary.portfolio_xirr is None else f"{float(summary.portfolio_xirr) * 100:.2f}%"
    transactions = "\n".join(_ledger_lines(db, user, None))
    holding_lines = "\n".join(_holding_line(holding) for holding in held)
    prompt = f"""Review this mutual-fund portfolio and say how to optimise it (amounts in INR).

Totals: invested={_money(summary.net_invested)}, current_value={_money(summary.current_value)},
unrealized_gain={_money(summary.net_gain_loss)}, realized_gain={_money(summary.total_realized_gain)},
portfolio_xirr={xirr}, commission_paid={_money(summary.total_commission_paid)}.

Current holdings:
{holding_lines}

Every transaction across all accounts (scheme_code|date|type|source|amount|nav|units):
{transactions}

Research each fund's category, performance vs. benchmark/peers, expense ratio and risk. Then judge the
portfolio as a whole: overlap between funds, category/market-cap/sector concentration, too many
funds doing the same job, laggards worth replacing, and gaps. Consider the tax cost of any exit.
Only recommend changes that are justified; HOLD is a valid answer.

Respond with JSON exactly like:
{{"summary": "4-6 sentence overall assessment",
  "actions": [{{"scheme_code": "code from above or null for a new fund", "scheme_name": "...",
               "action": "INCREASE|REDUCE|EXIT|REPLACE|HOLD", "suggestion": "what to do, specifically",
               "rationale": "why, with verified figures"}}],
  "diversification_notes": ["short observation", "..."]}}"""

    data, sources = _call_gemini(prompt)
    actions = []
    for item in data.get("actions", []):
        if not isinstance(item, dict):
            continue
        action = str(item.get("action", "")).upper()
        if action not in _PORTFOLIO_ACTIONS:
            continue
        code = item.get("scheme_code")
        actions.append(
            {
                "scheme_code": str(code) if code not in (None, "", "null") else None,
                "scheme_name": str(item.get("scheme_name", "")),
                "action": action,
                "suggestion": str(item.get("suggestion", "")),
                "rationale": str(item.get("rationale", "")),
            }
        )
    return PortfolioAdviceOut(
        summary=str(data.get("summary", "")),
        actions=actions,
        diversification_notes=[str(note) for note in data.get("diversification_notes", [])],
        sources=sources,
        model=settings.gemini_model,
        disclaimer=DISCLAIMER,
    )