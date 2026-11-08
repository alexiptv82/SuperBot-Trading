"""RC81 read-only stop visibility contract. Synthetic files only; no VPS access."""
import json
import time
from pathlib import Path

import pytest

from backend.v3.observability.classic_stop_health import classic_stop_health


def _sample(base: Path, *, now: float, portfolio: str = "hawk", state: str = "covered", **kw):
    payload = {
        "mode": "paper-exit-only", "portfolio": portfolio, "ready": True,
        "ts": now, "stop_monitor_opt_in": True, "stop_protection": state,
        "telemetry_ok": True, "stop_certified": False,
        "execution": "closed_1m_close_only", "intrabar_wick": "not_a_fill",
    }
    payload.update(kw)
    (base / "exit_only_heartbeat.json").write_text(json.dumps(payload), encoding="utf-8")


def _read(base: Path, now: float, *, n: int = 1, portfolio: str = "hawk",
          mode: str = "exit_only"):
    return classic_stop_health(str(base), portfolio, now_s=now,
                               open_positions=n, worker_mode=mode)


def test_covered_is_only_quote_coverage_not_a_stop_certificate(tmp_path):
    now = time.time()
    _sample(tmp_path, now=now)
    out = _read(tmp_path, now)
    assert out["state"] == "covered"
    assert out["quote_coverage"] is True and out["stop_certified"] is False
    assert out["alarm"] is False
    assert out["execution"] == "closed_1m_close_only"
    assert "no_intrabar_fill" in out["limitations"]


@pytest.mark.parametrize("state", ["blind", "partial", "blocked", "unverified", "telemetry_failed"])
def test_uncovered_positions_show_an_alarm(tmp_path, state):
    now = time.time()
    _sample(tmp_path, now=now, state=state)
    out = _read(tmp_path, now)
    assert out["state"] == state and out["alarm"] is True
    assert out["quote_coverage"] is False


def test_stale_and_future_heartbeat_never_show_coverage(tmp_path):
    now = time.time()
    for stamp in (now - 15, now + 15):
        _sample(tmp_path, now=stamp)
        out = _read(tmp_path, now)
        assert out["state"] == "stale"
        assert out["quote_coverage"] is False
        assert out["alarm"] is True


def test_off_is_not_described_as_covered(tmp_path):
    now = time.time()
    _sample(tmp_path, now=now, state="covered", stop_monitor_opt_in=False)
    out = _read(tmp_path, now)
    assert out["state"] == "off" and not out["quote_coverage"]
    assert out["alarm"]


def test_worker_not_ready_and_telemetry_fail_are_visible(tmp_path):
    now = time.time()
    _sample(tmp_path, now=now, ready=False)
    assert _read(tmp_path, now)["state"] == "blocked"
    _sample(tmp_path, now=now, telemetry_ok=False)
    assert _read(tmp_path, now)["state"] == "telemetry_failed"


def test_no_live_runner_coverage_claim_even_with_recent_maintenance_file(tmp_path):
    now = time.time()
    _sample(tmp_path, now=now)
    out = _read(tmp_path, now, mode="classic_runner")
    assert out["state"] == "unverified"
    assert out["quote_coverage"] is False


def test_idle_with_no_positions_is_informational(tmp_path):
    now = time.time()
    _sample(tmp_path, now=now, state="idle")
    out = _read(tmp_path, now, n=0)
    assert out["state"] == "idle" and out["alarm"] is False
    assert out["quote_coverage"] is False
    assert _read(tmp_path, now, n=1)["state"] == "unverified"


def test_missing_malformed_symlink_and_wrong_portfolio_fail_visible(tmp_path):
    now = time.time()
    assert _read(tmp_path, now)["state"] == "unverified"
    p = tmp_path / "exit_only_heartbeat.json"
    p.write_text("{", encoding="utf-8")
    assert _read(tmp_path, now)["state"] == "unverified"
    _sample(tmp_path, now=now, portfolio="bull")
    assert _read(tmp_path, now, portfolio="hawk")["state"] == "unverified"
    p.unlink()
    p.symlink_to(tmp_path / "not-a-worker")
    assert _read(tmp_path, now)["state"] == "unverified"


def test_certificate_claim_and_bad_field_types_are_rejected(tmp_path):
    now = time.time()
    _sample(tmp_path, now=now, stop_certified=True)
    assert _read(tmp_path, now)["reason"] == "certificate_claim_invalid"
    _sample(tmp_path, now=now, ts=True)
    assert _read(tmp_path, now)["reason"] == "heartbeat_time_invalid"
