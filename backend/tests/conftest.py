"""Shared pytest fixtures.

Each test gets its own throwaway SQLite file (not :memory:, so the
connection-pool PRAGMAs - foreign keys, busy_timeout - behave the same way
they do in production) created fresh via Base.metadata.create_all(), torn
down after. At this schema size that's a few milliseconds, so per-test
isolation via a fresh file is simpler and just as fast as the
nested-transaction/savepoint pattern - and it doesn't fight with the fact
that most service functions call db.commit() directly.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

import models  # noqa: F401 - registers every model on Base.metadata
from api.deps import get_current_user
from core.config import settings
from db.base import Base
from db.session import get_db
from main import app as fastapi_app
from models.account import Account
from models.user import User


@pytest.fixture()
def db_session(tmp_path):
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def seeded_user(db_session) -> User:
    user = User(name=settings.seed_user_name, email=settings.seed_user_email)
    db_session.add(user)
    db_session.flush()
    # Mirrors scripts/seed.py's ACCOUNTS - kept in sync so the real-workbook
    # import integration test (test_imports_integration.py) can expect all
    # 5 account sheets to auto-resolve, same as it would against a freshly
    # seeded dev database.
    for name, platform in [
        ("ICICI Direct - Ashu", "ICICI Direct"),
        ("Maniqm - Ashu", "Maniqm"),
        ("Maniqm - Hars", "Maniqm"),
        ("Zerodha - Ashu", "Zerodha"),
        ("Zerodha - Hars", "Zerodha"),
    ]:
        db_session.add(Account(user_id=user.id, account_name=name, platform=platform))
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture()
def client(db_session, seeded_user):
    fastapi_app.dependency_overrides[get_db] = lambda: db_session
    fastapi_app.dependency_overrides[get_current_user] = lambda: seeded_user
    with TestClient(fastapi_app) as test_client:
        yield test_client
    fastapi_app.dependency_overrides.clear()
