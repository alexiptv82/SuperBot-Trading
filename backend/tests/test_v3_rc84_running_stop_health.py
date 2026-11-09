"""RC84: read-only Falco/Toro running-feed telemetry; synthetic payloads only."""
from __future__ import annotations

import time

import pytest

from backend.v3.observability.classic_running_stop_health import running_stop_health


def _beat(now: float, portfolio: str = "hawk", **extra):
    b = {
        "portfolio": portfolio, "exec_mode": "paper", "mode": "running",
        "ts": now, "last_ok": True, "last_end_ms": int(now * 1000) - 60_000,
        "stop_certified": False,
        "stop_feed": {"timeframe": "15m", "bar_ms": 900_000, "alarm": False,
                      "stop_certified": False,
                      "symbols": {"BTC": {"checked": True, "status": "ok"}}},
        "new_exposure": {"blocked_symbols": [], "stop_certified": False},
    }
    b.update(extra)
    return b


def _view(b, now=None, symbols=None, portfolio="hawk"):
    return running_stop_health(b, portfolio, ["BTC"] if symbols is None else symbols,
                               now_s=time.time() if now is None else now)


def test_recent_completed_cycle_is_observed_but_never_certified():
    now = time.time()
    h = _view(_beat(now), now)
    assert h["state"] == "observed" and h["alarm"] is False
    assert h["stop_certified"] is False and h["quote_coverage"] is False
    assert "not_continuous" in h["limitations"]
    assert h["execution"] == "periodic_15m_ohlc"


@pytest.mark.parametrize("bad", [
    None,
    {},
    {"portfolio": "hawk", "exec_mode": "live", "ts": 1700000000},
])
def test_invalid_heartbeat_never_proves_a_stop(bad):
    now = 1700000000
    h = _view(bad, now)
    assert h["alarm"] is True
    assert h["state"] in ("unverified", "stale")
    assert h["stop_certified"] is False


def test_wrong_portfolio_and_stale_or_future_timestamp_fail_visible():
    now = time.time()
    assert _view(_beat(now, "bull"), now)["reason"] == "wrong_portfolio_or_mode"
    assert _view(_beat(now - 120), now)["state"] == "stale"
    assert _view(_beat(now + 20), now)["state"] == "stale"


def test_old_cycle_and_failed_cycle_do_not_look_healthy():
    now = time.time()
    assert _view(_beat(now, last_end_ms=int(now * 1000) - 50 * 60_000), now)["state"] == "stale"
    assert _view(_beat(now, last_ok=False), now)["state"] == "degraded"


@pytest.mark.parametrize("status", ["missing", "stale", "future", "unusable",
                                      "latest_rejected", "close_not_durable"])
def test_unchecked_or_bad_position_feed_is_alarm(status):
    now = time.time()
    b = _beat(now)
    b["stop_feed"]["symbols"]["BTC"]["status"] = status
    assert _view(b, now)["state"] == "degraded"
    assert _view(b, now)["alarm"] is True


def test_mismatched_symbols_and_feed_alarm_cannot_show_observed():
    now = time.time()
    b = _beat(now)
    assert _view(b, now, symbols=["ETH"])["state"] == "degraded"
    b["stop_feed"]["alarm"] = True
    assert _view(b, now)["state"] == "degraded"


def test_zero_open_positions_still_reveals_blocked_new_exposure():
    now = time.time()
    b = _beat(now)
    b["new_exposure"]["blocked_symbols"] = ["ARB"]
    h = _view(b, now, symbols=[])
    assert h["alarm"] is True and h["state"] == "degraded"
    assert h["blocked_symbols"] == ["ARB"]
    b["new_exposure"]["blocked_symbols"] = []
    assert _view(b, now, symbols=[])["state"] == "idle"


def test_bad_contract_or_claimed_stop_certificate_denied():
    now = time.time()
    b = _beat(now, stop_certified=True)
    assert _view(b, now)["state"] == "unverified"
    b = _beat(now)
    b["new_exposure"] = {"blocked_symbols": "BTC", "stop_certified": False}
    assert _view(b, now)["state"] == "unverified"
    b = _beat(now)
    b["stop_feed"]["timeframe"] = "1m"
    assert _view(b, now)["state"] == "unverified"


def test_running_overview_uses_running_not_maintenance_heartbeat(tmp_path, monkeypatch):
    from backend import v3_api

    now = time.time()
    b = _beat(now)
    state = {"main": {"positions": {"BTC": {"total_margin": "100"}}}}
    monkeypatch.setattr(v3_api.dv, "read_state", lambda *_a, **_k: state)
    monkeypatch.setattr(v3_api.dv, "read_heartbeat", lambda *_a, **_k: b)
    monkeypatch.setattr(v3_api.dv, "pause_requested", lambda *_a, **_k: False)
    monkeypatch.setattr(v3_api.dv, "build_performance", lambda *_a, **_k: None)
    monkeypatch.setattr(v3_api.dv, "build_trades", lambda *_a, **_k: [])
    monkeypatch.setattr(v3_api.dv, "build_status", lambda *_a, **_k: {
        "available": False, "positions": [], "close_worker_mode": "classic_runner"
    })
    view = v3_api._classic("falco", str(tmp_path), now)
    health = view["stop_health"]
    assert health["scope"] == "classic_runner_15m_ohlc"
    assert health["state"] == "observed"
    assert health["stop_certified"] is False
    other = v3_api._classic("toro", str(tmp_path), now)
    assert other["stop_health"]["state"] == "unverified"
    assert other["stop_health"]["reason"] == "wrong_portfolio_or_mode"
