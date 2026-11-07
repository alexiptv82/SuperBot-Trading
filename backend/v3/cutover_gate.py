"""Defensive app-only migration gate; does NOT change desk or Brain workers.

Only enabled during an authorized dashboard PAPER cutover. Login/password
endpoints remain functional, but every trading command route is refused.
This is an HTTP guard, not a substitute for PAUSED worker/risk checks.
"""
from __future__ import annotations

import json
from pathlib import Path
import time

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


def brain_single_close_enabled(env, now_ms=None) -> bool:
    """Allow only when a PAPER Brain runner proves it consumes manual requests.

    The prepared, paused Brain without a running consumer MUST stay locked.
    The normal heartbeat is not sufficient: the runner must advertise
    manual_close_capable on this exact run, with a fresh timestamp.
    """
    if not (env.get('V3_CUTOVER_READONLY') == '1'
            and env.get('V3_ALLOW_BRAIN_SINGLE_CLOSE') == '1'
            and env.get('DESK_MODE') == 'paper'
            and env.get('TRADING_MODE') == 'paper'):
        return False
    heartbeat = env.get('V3_HEARTBEAT_PATH')
    run_id = env.get('V3_RUN_ID')
    if not heartbeat or not run_id:
        return False
    try:
        path = Path(heartbeat)
        if path.is_symlink() or not path.is_file():
            return False
        hb = json.loads(path.read_text(encoding='utf-8'))
        now = int(time.time() * 1000) if now_ms is None else now_ms
        age = now - hb['ts_ms']
        return (type(hb['ts_ms']) is int and 0 <= age < 15_000
                and hb.get('run_id') == run_id
                and hb.get('state') in ('running', 'paused', 'halted')
                and hb.get('manual_close_capable') is True)
    except (OSError, ValueError, TypeError, KeyError, OverflowError):
        return False


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
