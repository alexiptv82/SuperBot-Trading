"""Read-only V3 view of RC80 maintenance-only PAPER stop supervision.

This never executes a stop, certifies a strategy runner, or alters wallet files.
In particular, a healthy manual-close worker is not evidence of live stop coverage.
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path

from desk.paper_stop_monitor import protection_alarm

HEARTBEAT_NAME = "exit_only_heartbeat.json"
HEARTBEAT_MAX_BYTES = 16_384
HEARTBEAT_MAX_AGE_S = 12
STATES = frozenset(("off", "unverified", "idle", "covered", "partial",
                    "blind", "blocked", "telemetry_failed"))
MODEL = "closed_1m_close_only"


def classic_stop_health(data_dir: str, portfolio: str, *, now_s: float | None = None,
                        open_positions: int | None = None,
                        worker_mode: str = "offline") -> dict:
    """Sanitized health for overview; fail-visible on missing or untrusted signals.

    `covered` means only that the maintenance sidecar observed closed 1m
    prices for its positions at the last tick. No intra-bar or live-runner
    protection is asserted by this read-only endpoint.
    """
    now = time.time() if now_s is None else now_s
    count = open_positions if type(open_positions) is int and open_positions >= 0 else None
    result = {
        "scope": "maintenance_exit_only",
        "state": "unverified",
        "quote_coverage": False,
        "alarm": count is None or count > 0,
        "reason": "monitor_not_verified",
        "fresh_heartbeat": False,
        "heartbeat_age_s": None,
        "monitor_opt_in": False,
        "stop_certified": False,
        "execution": MODEL,
        "intrabar_wick": "not_a_fill",
        "limitations": ["stop_only_on_completed_1m_close", "no_intrabar_fill"],
    }
    if portfolio not in ("hawk", "bull"):
        return dict(result, reason="invalid_portfolio")
    if worker_mode != "exit_only":
        return dict(result, reason="maintenance_worker_not_active")

    path = Path(data_dir) / HEARTBEAT_NAME
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > HEARTBEAT_MAX_BYTES:
            return dict(result, reason="heartbeat_missing_or_invalid")
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        return dict(result, reason="heartbeat_unreadable")
    if not isinstance(payload, dict) or payload.get("mode") != "paper-exit-only" or payload.get("portfolio") != portfolio:
        return dict(result, reason="heartbeat_identity_invalid")
    ts = payload.get("ts")
    if type(ts) not in (int, float) or not math.isfinite(ts):
        return dict(result, reason="heartbeat_time_invalid")
    age = now - ts
    if not (-2 <= age < HEARTBEAT_MAX_AGE_S):
        return dict(result, state="stale", reason="heartbeat_stale", heartbeat_age_s=max(0, round(age, 1)))
    result = dict(result, fresh_heartbeat=True, heartbeat_age_s=max(0, round(age, 1)),
                  monitor_opt_in=payload.get("stop_monitor_opt_in") is True)
    if payload.get("stop_certified") is not False:
        return dict(result, reason="certificate_claim_invalid")
    if payload.get("ready") is not True:
        return dict(result, state="blocked", reason="worker_not_ready")
    if payload.get("telemetry_ok") is not True:
        return dict(result, state="telemetry_failed", reason="telemetry_unavailable")
    if payload.get("stop_monitor_opt_in") is not True:
        return dict(result, state="off", reason="monitor_disabled")
    state = payload.get("stop_protection")
    if state not in STATES:
        return dict(result, reason="coverage_unknown")
    if state == "idle" and count != 0:
        return dict(result, reason="idle_with_open_positions")
    if state == "covered" and count == 0:
        return dict(result, reason="covered_without_positions")
    probe = protection_alarm(payload, now=now)
    if "heartbeat_stale" in probe.get("reasons", ()):
        return dict(result, state="stale", reason="heartbeat_stale")
    covered = state == "covered"
    alarm = not covered and (count is None or count > 0)
    return dict(result, state=state, quote_coverage=covered, alarm=alarm,
                reason=("one_minute_close_only" if covered else "coverage_" + state))
