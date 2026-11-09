"""Read-only, fail-visible snapshot of Falco/Toro RUNNING PAPER stop telemetry.

The classic runner's 15m OHLC evaluation is periodic, never tick-by-tick or
an exchange stop order. An observed cycle is not an execution guarantee.
No file writes, HTTP requests or privileged actions.
"""
from __future__ import annotations

import math

MAX_HEARTBEAT_AGE_S = 60
MAX_COMPLETED_CYCLE_AGE_MS = 36 * 60_000
BAR_MS = 15 * 60_000


def running_stop_health(hb: dict | None, portfolio: str, open_symbols: list[str],
                        *, now_s: float) -> dict:
    """Interpret the runner's own heartbeat, never RC80's maintenance heartbeat."""
    symbols = sorted({s for s in open_symbols if type(s) is str and s})
    result = {
        "scope": "classic_runner_15m_ohlc", "state": "unverified",
        "reason": "runner_stop_unverified", "alarm": bool(symbols),
        "stop_certified": False, "quote_coverage": False,
        "execution": "periodic_15m_ohlc", "intrabar_wick": "not_realtime",
        "heartbeat_age_s": None, "blocked_symbols": [], "feed_states": {},
        "limitations": ["15m_ohlc_periodic_15m_scalp_30m_other",
                        "not_continuous", "not_exchange_stop_order",
                        "entry_candle_wick_not_replayed"],
    }
    if portfolio not in ("hawk", "bull"):
        return dict(result, state="unverified", reason="invalid_portfolio", alarm=True)
    if not isinstance(hb, dict):
        return dict(result, state="unverified", reason="missing_runner_heartbeat", alarm=bool(symbols))
    if hb.get("portfolio") != portfolio or hb.get("exec_mode") != "paper":
        return dict(result, state="unverified", reason="wrong_portfolio_or_mode", alarm=True)
    stamp = hb.get("ts")
    if type(stamp) not in (int, float) or not math.isfinite(stamp):
        return dict(result, state="unverified", reason="invalid_heartbeat_time", alarm=True)
    age = now_s - stamp
    if not -2 <= age <= MAX_HEARTBEAT_AGE_S:
        return dict(result, state="stale", reason="runner_heartbeat_stale", alarm=True,
                    heartbeat_age_s=max(0, round(age, 1)))
    result["heartbeat_age_s"] = max(0, round(age, 1))
    if hb.get("last_ok") is not True:
        return dict(result, state="degraded", reason="runner_cycle_not_ok", alarm=True)
    end = hb.get("last_end_ms")
    now_ms = now_s * 1000
    if (type(end) is not int or end <= 0 or end > now_ms + 2000 or
            now_ms - end > MAX_COMPLETED_CYCLE_AGE_MS):
        return dict(result, state="stale", reason="no_recent_completed_cycle", alarm=True)

    feed = hb.get("stop_feed")
    blocked = hb.get("new_exposure")
    if not isinstance(feed, dict) or not isinstance(blocked, dict):
        return dict(result, reason="missing_stop_feed_or_exposure", alarm=True)
    if (feed.get("timeframe") != "15m" or feed.get("bar_ms") != BAR_MS or
            feed.get("stop_certified") is not False or
            hb.get("stop_certified") is not False or
            blocked.get("stop_certified") is not False or
            type(feed.get("alarm")) is not bool or
            not isinstance(feed.get("symbols"), dict) or
            type(blocked.get("blocked_symbols")) is not list):
        return dict(result, reason="invalid_stop_feed_contract", alarm=True)
    raw_blocked = blocked["blocked_symbols"]
    if not all(type(s) is str and s and len(s) <= 32 for s in raw_blocked):
        return dict(result, reason="invalid_blocked_symbols", alarm=True)
    result["blocked_symbols"] = sorted(set(raw_blocked))[:12]
    feed_states = {}
    all_checked = True
    for symbol in symbols:
        row = feed["symbols"].get(symbol)
        if not isinstance(row, dict) or type(row.get("status")) is not str or row.get("checked") is not True:
            feed_states[symbol] = "unverified"
            all_checked = False
            continue
        feed_states[symbol] = row["status"][:36]
        if row["status"] != "ok":
            all_checked = False
    result["feed_states"] = feed_states
    if feed["alarm"] or result["blocked_symbols"] or not all_checked:
        return dict(result, state="degraded", reason="feed_alarm_or_unchecked_positions", alarm=True)
    if not symbols:
        return dict(result, state="idle", reason="no_open_positions", alarm=False)
    return dict(result, state="observed", reason="recent_runner_ohlc_evaluation", alarm=False)
