"""Defensive app-only migration gate; does NOT change desk or Brain workers.

Only enabled during an authorized dashboard PAPER cutover. Login/password
endpoints remain functional, but every trading command route is refused.
This is an HTTP guard, not a substitute for PAUSED worker/risk checks.
"""
from __future__ import annotations

_BLOCKED_PREFIXES = (
    "/api/bot",
    "/api/desk",
    "/api/v3",
    "/api/brain",
    "/api/supervisor",
)
_READ_METHODS = frozenset(("GET", "HEAD", "OPTIONS"))


def should_refuse_mutation(method: str, path: str, *, readonly: bool) -> bool:
    if not readonly or type(method) is not str or type(path) is not str:
        return False
    if method.upper() in _READ_METHODS:
        return False
    return any(path == prefix or path.startswith(prefix + "/")
               for prefix in _BLOCKED_PREFIXES)
