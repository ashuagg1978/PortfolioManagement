"""Password hashing and signed access tokens.

Hashing uses stdlib scrypt (no native dependency to build on the server);
tokens are short HS256 JWTs carrying just the user id - everything else
(active flag, admin flag) is re-read from the DB on every request so
deactivating a user takes effect immediately.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt

from core.config import settings

_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2**14, 8, 1
_SECRET_FILE = Path(__file__).resolve().parent.parent / ".auth_secret"
_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(
        password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32
    )
    return "scrypt${}${}${}${}${}".format(
        _SCRYPT_N,
        _SCRYPT_R,
        _SCRYPT_P,
        base64.b64encode(salt).decode(),
        base64.b64encode(digest).decode(),
    )


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        scheme, n, r, p, salt_b64, digest_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(digest_b64)
        actual = hashlib.scrypt(
            password.encode(),
            salt=base64.b64decode(salt_b64),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def _secret() -> str:
    """AUTH_SECRET from settings wins; otherwise a random secret is generated
    once and kept in backend/.auth_secret so tokens survive restarts without
    any manual setup.
    """
    if settings.auth_secret:
        return settings.auth_secret
    if _SECRET_FILE.exists():
        return _SECRET_FILE.read_text(encoding="utf-8").strip()
    value = secrets.token_urlsafe(48)
    _SECRET_FILE.write_text(value, encoding="utf-8")
    return value


def create_access_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(hours=settings.access_token_hours),
    }
    return jwt.encode(payload, _secret(), algorithm=_ALGORITHM)


def decode_access_token(token: str) -> int | None:
    """The user id the token was issued for, or None if it is invalid/expired."""
    try:
        payload = jwt.decode(token, _secret(), algorithms=[_ALGORITHM])
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
