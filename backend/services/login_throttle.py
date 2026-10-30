"""In-memory brute-force guard for the login endpoint.

After `login_max_failures` consecutive failures for a (client ip, username)
pair, further attempts are refused until `login_lockout_seconds` pass. State
is per-process - fine for the single-instance deployment, and a restart only
ever relaxes it.
"""

import time

from core.config import settings

_failures: dict[tuple[str, str], tuple[int, float]] = {}


def _key(ip: str, username: str) -> tuple[str, str]:
    return ip, username.strip().lower()


def seconds_locked(ip: str, username: str) -> int:
    entry = _failures.get(_key(ip, username))
    if entry is None:
        return 0
    count, last = entry
    if count < settings.login_max_failures:
        return 0
    remaining = settings.login_lockout_seconds - (time.monotonic() - last)
    if remaining <= 0:
        _failures.pop(_key(ip, username), None)
        return 0
    return int(remaining) + 1


def record_failure(ip: str, username: str) -> None:
    key = _key(ip, username)
    count, _ = _failures.get(key, (0, 0.0))
    _failures[key] = (count + 1, time.monotonic())


def record_success(ip: str, username: str) -> None:
    _failures.pop(_key(ip, username), None)


def reset() -> None:
    _failures.clear()
