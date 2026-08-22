"""Shared FastAPI dependencies.

get_current_user is the one seam where real authentication plugs in later:
today it always returns the single seeded user; swapping in JWT/session
auth means changing the body of this one function, not every route that
calls it.
"""

from collections.abc import Generator

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from core.config import settings
from db.session import get_db
from models.user import User


def get_current_user(db: Session = Depends(get_db)) -> User:
    user = db.query(User).filter(User.email == settings.seed_user_email).first()
    if user is None:
        raise HTTPException(
            status_code=500,
            detail="No seeded user found - run `python -m scripts.seed` first.",
        )
    return user
