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


_SINGLE_PAPER_CLOSE_PATHS = frozenset((
    "/api/desk/close-position",
    "/api/desk/bull/close-position",
))


def classic_single_close_enabled(env) -> bool:
    """Only an explicit PAPER+readonly opt-in can unlock single classic exits."""
    return (env.get("V3_CUTOVER_READONLY") == "1"
            and env.get("V3_ALLOW_CLASSIC_SINGLE_CLOSE") == "1"
            and env.get("TRADING_MODE") == "paper"
            and env.get("DESK_MODE") == "paper")


def brain_single_close_enabled(env) -> bool:
    """Opt-in only; a separate live exit-owner lease is also required by V3 API."""
    return (env.get("V3_CUTOVER_READONLY") == "1"
            and env.get("V3_ALLOW_BRAIN_SINGLE_CLOSE") == "1"
            and env.get("TRADING_MODE") == "paper"
            and env.get("DESK_MODE") == "paper")


def should_refuse_mutation(method: str, path: str, *, readonly: bool,
                           allow_paper_single_close: bool = False,
                           allow_paper_brain_single_close: bool = False) -> bool:
    if not readonly or type(method) is not str or type(path) is not str:
        return False
    if method.upper() in _READ_METHODS:
        return False
    if (allow_paper_single_close and method.upper() == "POST"
            and path in _SINGLE_PAPER_CLOSE_PATHS):
        return False
    if (allow_paper_brain_single_close and method.upper() == "POST"
            and path == "/api/v3/brain/close"):
        return False
    return any(path == prefix or path.startswith(prefix + "/")
               for prefix in _BLOCKED_PREFIXES)
