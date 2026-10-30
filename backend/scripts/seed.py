"""Seeds the single user, the 5 known account streams, and the NSE holiday
calendar. Safe to re-run - every insert is idempotent.

Usage:
    python -m scripts.seed
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from core.config import settings
from core.security import hash_password
from db.session import SessionLocal, engine
from db.base import Base
import models  # noqa: F401 - registers models on Base.metadata
from models.account import Account
from models.market_holiday import MarketHoliday
from models.user import User

ACCOUNTS = [
    ("ICICI Direct - Ashu", "ICICI Direct"),
    ("Maniqm - Ashu", "Maniqm"),
    ("Maniqm - Hars", "Maniqm"),
    ("Zerodha - Ashu", "Zerodha"),
    ("Zerodha - Hars", "Zerodha"),
]

HOLIDAYS_FILE = Path(__file__).resolve().parent.parent / "data" / "nse_holidays.json"


def seed() -> None:
    Base.metadata.create_all(engine)  # no-op once Alembic has already run
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == settings.seed_user_email).first()
        if user is None:
            user = User(
                name=settings.seed_user_name,
                email=settings.seed_user_email,
                password_hash=hash_password(settings.seed_user_password),
            )
            db.add(user)
            db.flush()
            print(f"created user: {user.email}")
        else:
            print(f"user already exists: {user.email}")

        if db.query(User).filter(User.email == settings.admin_username).first() is None:
            db.add(
                User(
                    name=settings.admin_name,
                    email=settings.admin_username,
                    password_hash=hash_password(settings.admin_password),
                    is_admin=True,
                )
            )
            print(f"created admin: {settings.admin_username}")

        for account_name, platform in ACCOUNTS:
            exists = (
                db.query(Account)
                .filter(Account.user_id == user.id, Account.account_name == account_name)
                .first()
            )
            if exists is None:
                db.add(Account(user_id=user.id, account_name=account_name, platform=platform))
                print(f"created account: {account_name} ({platform})")

        holidays = json.loads(HOLIDAYS_FILE.read_text(encoding="utf-8"))
        added = 0
        for _year, entries in holidays.items():
            for entry in entries:
                d = date.fromisoformat(entry["date"])
                exists = db.get(MarketHoliday, d)
                if exists is None:
                    db.add(MarketHoliday(holiday_date=d, description=entry.get("description")))
                    added += 1
        print(f"added {added} new market holidays")

        db.commit()
        print("seed complete.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
