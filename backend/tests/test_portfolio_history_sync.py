"""sync_nav_history() against a real (throwaway) DB - mocked at
services.nav_history.fetch_full_history, since that's what the orchestrator
calls directly (not httpx), following the project's "patch where it's used"
lesson.
"""

from datetime import date
from decimal import Decimal
from unittest.mock import patch

from models.account import Account
from models.enums import TransactionType
from models.scheme import Scheme
from models.scheme_nav_history import SchemeNavHistory
from models.transaction import Transaction
from services.nav_history import NavHistoryPoint
from services.portfolio_history import sync_nav_history


def _seed_scheme(db_session, code, name="Test Fund"):
    db_session.add(Scheme(scheme_code=code, scheme_name=name))
    db_session.commit()


def _add_transaction(db_session, account_id, scheme_code, txn_date=date(2024, 1, 10)):
    db_session.add(
        Transaction(
            account_id=account_id,
            scheme_code=scheme_code,
            transaction_date=txn_date,
            type=TransactionType.PURCHASE,
            amount="10000.00",
            nav=Decimal("100.0000"),
            units="100.000000",
            commission="0.00",
            signed_amount="-10000.00",
            source_hash=f"test-{account_id}-{scheme_code}-{txn_date}",
        )
    )
    db_session.commit()


def test_sync_inserts_only_held_scheme_history(db_session, seeded_user):
    _seed_scheme(db_session, "AAA")
    _seed_scheme(db_session, "BBB")  # exists but never transacted
    account_id = db_session.query(Account).filter(Account.user_id == seeded_user.id).first().id
    _add_transaction(db_session, account_id, "AAA")

    payload = {"AAA": [NavHistoryPoint(nav_date=date(2024, 1, 10), nav=Decimal("100.0000"))]}

    def fake_fetch(code):
        return payload.get(code, [])

    with patch("services.portfolio_history.fetch_full_history", side_effect=fake_fetch):
        result = sync_nav_history(db_session, seeded_user)

    assert result.schemes_synced == 1
    assert result.schemes_failed == 0
    rows = db_session.query(SchemeNavHistory).all()
    assert len(rows) == 1
    assert rows[0].scheme_code == "AAA"


def test_sync_is_idempotent_on_rerun(db_session, seeded_user):
    _seed_scheme(db_session, "AAA")
    account_id = db_session.query(Account).filter(Account.user_id == seeded_user.id).first().id
    _add_transaction(db_session, account_id, "AAA")

    points = [
        NavHistoryPoint(nav_date=date(2024, 1, 10), nav=Decimal("100.0000")),
        NavHistoryPoint(nav_date=date(2024, 1, 11), nav=Decimal("101.0000")),
    ]

    with patch("services.portfolio_history.fetch_full_history", return_value=points):
        sync_nav_history(db_session, seeded_user)
        sync_nav_history(db_session, seeded_user)  # same payload again

    rows = db_session.query(SchemeNavHistory).all()
    assert len(rows) == 2  # not 4 - insert_ignore dedupes on (scheme_code, nav_date)


def test_sync_tolerates_one_scheme_failing(db_session, seeded_user):
    _seed_scheme(db_session, "AAA")
    _seed_scheme(db_session, "BBB")
    account_id = db_session.query(Account).filter(Account.user_id == seeded_user.id).first().id
    _add_transaction(db_session, account_id, "AAA")
    _add_transaction(db_session, account_id, "BBB", txn_date=date(2024, 2, 1))

    def fake_fetch(code):
        if code == "AAA":
            return [NavHistoryPoint(nav_date=date(2024, 1, 10), nav=Decimal("100.0000"))]
        return []  # BBB fails / unresolvable

    with patch("services.portfolio_history.fetch_full_history", side_effect=fake_fetch):
        result = sync_nav_history(db_session, seeded_user)

    assert result.schemes_synced == 1
    assert result.schemes_failed == 1
    rows = db_session.query(SchemeNavHistory).all()
    assert len(rows) == 1
    assert rows[0].scheme_code == "AAA"


def test_sync_with_no_transactions_returns_zero_result(db_session, seeded_user):
    with patch("services.portfolio_history.fetch_full_history") as mock_fetch:
        result = sync_nav_history(db_session, seeded_user)
    mock_fetch.assert_not_called()
    assert result.schemes_synced == 0
    assert result.schemes_failed == 0
    assert result.points_inserted == 0
