"""RC80 offline hardening of the dormant PAPER stop monitor. Synthetic data only."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from desk import cli
from desk.paper_stop_monitor import (
    DIAG_NAME,
    STOP_WORK_NAME,
    PaperStopRefused,
    apply_paper_stop_protection,
    classify_candle,
)


def _load_rc78():
    path = Path(__file__).with_name("test_v3_rc78_paper_stop_monitor.py")
    spec = importlib.util.spec_from_file_location("rc78_stop_tests", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rc78 = _load_rc78()


def _refresh(base, backup):
    for name in ("state_v2.json", "trade_history.jsonl", "learning_log.jsonl", "lessons.md"):
        shutil.copy2(base / name, backup / name)


def _hb(base):
    return json.loads((base / "exit_only_heartbeat.json").read_text())


def test_startup_heartbeat_is_not_coverage(tmp_path, monkeypatch):
    base, backup = rc78.prepare(tmp_path, monkeypatch)
    monkeypatch.setenv("DESK_PAPER_STOP_MONITOR", "1")
    with rc78.worker(base, backup):
        assert _hb(base)["stop_monitor_opt_in"] is True
        assert _hb(base)["stop_protection"] == "unverified"
        assert _hb(base)["ready"] is True


def test_fresh_quiet_price_is_covered_without_a_close(tmp_path, monkeypatch):
    base, backup = rc78.prepare(tmp_path, monkeypatch)
    monkeypatch.setenv("DESK_PAPER_STOP_MONITOR", "1")
    now = rc78._now_ms()
    monkeypatch.setattr(cli, "fetch_candles", rc78._feed(now, 100.0))
    with rc78.worker(base, backup) as service:
        report = service.tick()
        assert report["stop_monitor"]["stop_protection"] == "covered"
        assert report["stop_monitor"]["closed"] == []
        assert _hb(base)["stop_protection"] == "covered"
        assert "BTC" in rc78._positions(base)


def test_missing_feed_is_blind_and_does_not_close_or_claim_coverage(tmp_path, monkeypatch):
    base, backup = rc78.prepare(tmp_path, monkeypatch)
    monkeypatch.setenv("DESK_PAPER_STOP_MONITOR", "1")
    now = rc78._now_ms()
    monkeypatch.setattr(cli, "fetch_candles", rc78._feed(now, 100.0))
    with rc78.worker(base, backup) as service:
        service.tick()
        monkeypatch.setattr(cli, "fetch_candles", lambda *a, **k: [])
        blind = service.tick()
        monkeypatch.setattr(cli, "fetch_candles", rc78._feed(rc78._now_ms(), 100.0))
        back = service.tick()
    assert blind["stop_monitor"]["stop_protection"] == "blind"
    assert blind["stop_monitor"]["closed"] == []
    assert "BTC" in rc78._positions(base)
    assert back["stop_monitor"]["stop_protection"] == "covered"
    kinds = [json.loads(line)["kind"] for line in (base / DIAG_NAME).read_text().splitlines()]
    assert "feed_lost" in kinds and "feed_recovered" in kinds
    assert len(rc78._history(base)) == 1


def test_wick_through_stop_with_a_close_back_inside_does_not_close(tmp_path, monkeypatch):
    base, backup = rc78.prepare(tmp_path, monkeypatch)
    monkeypatch.setenv("DESK_PAPER_STOP_MONITOR", "1")
    now = rc78._now_ms()

    def fetch(symbol, bar, limit):
        # High pierces the short stop at 102. The close came back to 100.
        return [[now - 5_000, 100, 103, 99, 100, 1]]

    monkeypatch.setattr(cli, "fetch_candles", fetch)
    with rc78.worker(base, backup) as service:
        report = service.tick()
    assert report["stop_monitor"]["stop_protection"] == "covered"
    assert report["stop_monitor"]["closed"] == []
    assert "BTC" in rc78._positions(base)


@pytest.mark.parametrize("bar,status", (
    (None, "anomalous"),
    ([1_000, True, 1, 1, 1], "anomalous"),
    ([1_000, 10, 9, 11, 10], "anomalous"),
    ([1_000, "10", 10, 10, 10], "anomalous"),
))
def test_anomalous_bars_have_no_price(bar, status):
    found = classify_candle(bar, 2_000)
    assert found["status"] == status
    assert found["price"] is None


def test_future_and_stale_bars_do_not_close(tmp_path, monkeypatch):
    base, backup = rc78.prepare(tmp_path, monkeypatch)
    monkeypatch.setenv("DESK_PAPER_STOP_MONITOR", "1")
    now = rc78._now_ms()
    monkeypatch.setattr(cli, "fetch_candles", lambda *a, **k: [[now + 5_000, 130, 130, 130, 130, 1]])
    with rc78.worker(base, backup) as service:
        future = service.tick()
        monkeypatch.setattr(cli, "fetch_candles", lambda *a, **k: [[now - 180_000, 130, 130, 130, 130, 1]])
        stale = service.tick()
    assert future["stop_monitor"]["positions"][0]["status"] == "future"
    assert stale["stop_monitor"]["positions"][0]["status"] == "stale"
    assert future["stop_monitor"]["closed"] == stale["stop_monitor"]["closed"] == []
    assert "BTC" in rc78._positions(base)
    assert len(rc78._history(base)) == 1


def test_partial_coverage_closes_only_the_fresh_symbol(tmp_path, monkeypatch):
    base, _backup = rc78.prepare(tmp_path, monkeypatch, side=-1, sl=102.0, tp=95.0)
    state = json.loads((base / "state_v2.json").read_text())
    acc = cli.make_account(state)
    opened, msg = acc.open("ETH", -1, 100, 20, 100.0, 102.0, 95.0, rc78._now_ms() - 1000, {})
    assert opened is not None, msg
    cli.save_account(acc, state)
    cli.save_state(state, str(base / "state_v2.json"))
    monkeypatch.setenv("DESK_PAPER_STOP_MONITOR", "1")
    now = rc78._now_ms()
    quotes = {
        "BTC": {"status": "fresh", "reason": "ok", "price": 103.0, "ts": now - 1000, "age_ms": 1000},
        "ETH": {"status": "missing", "reason": "empty_feed", "price": None},
    }
    report = apply_paper_stop_protection(
        cli, {}, now, lock_held=True, legacy_stopped=lambda: True, quotes=quotes)
    assert report["stop_protection"] == "partial"
    assert [row["symbol"] for row in report["closed"]] == ["BTC"]
    assert "ETH" in rc78._positions(base)
    assert "BTC" not in rc78._positions(base)
    assert len(rc78._history(base)) == 2


def test_gap_close_uses_liquidation_before_stop(tmp_path, monkeypatch):
    base, backup = rc78.prepare(tmp_path, monkeypatch)
    monkeypatch.setenv("DESK_PAPER_STOP_MONITOR", "1")
    state = json.loads((base / "state_v2.json").read_text())
    pos = state["main"]["positions"]["BTC"]
    now = rc78._now_ms()
    gap = pos["liq"] + 5
    monkeypatch.setattr(cli, "fetch_candles", lambda *a, **k: [[now - 1000, gap, gap, gap, gap, 1]])
    with rc78.worker(base, backup) as service:
        report = service.tick()
    assert report["stop_monitor"]["closed"][0]["why"] == "liquidazione"
    assert rc78._history(base)[-1]["net"] == pytest.approx(round(-pos["total_margin"] - pos["fee_open"], 4))


def test_rapid_second_tick_does_not_duplicate(tmp_path, monkeypatch):
    base, backup = rc78.prepare(tmp_path, monkeypatch)
    monkeypatch.setenv("DESK_PAPER_STOP_MONITOR", "1")
    now = rc78._now_ms()
    prices = {"n": 103.0}
    monkeypatch.setattr(cli, "fetch_candles", lambda *a, **k: rc78._candle(now, prices["n"]))
    with rc78.worker(base, backup) as service:
        service.tick()
        prices["n"] = 120.0
        service.tick()
    assert len(rc78._history(base)) == 2
    assert rc78._positions(base) == {}


def test_save_failure_after_history_does_not_close_twice(tmp_path, monkeypatch):
    base, _backup = rc78.prepare(tmp_path, monkeypatch)
    monkeypatch.setenv("DESK_PAPER_STOP_MONITOR", "1")
    original_save = cli.save_state

    def fail_save(*_a, **_k):
        raise RuntimeError("disk full")

    monkeypatch.setattr(cli, "save_state", fail_save)
    with pytest.raises(RuntimeError, match="disk full"):
        apply_paper_stop_protection(cli, {"BTC": 130.0}, rc78._now_ms(),
                                    lock_held=True, legacy_stopped=lambda: True)
    assert "BTC" in rc78._positions(base)
    assert len(rc78._history(base)) == 2
    assert (base / STOP_WORK_NAME).is_file()
    monkeypatch.setattr(cli, "save_state", original_save)
    again = apply_paper_stop_protection(cli, {"BTC": 130.0}, rc78._now_ms(),
                                        lock_held=True, legacy_stopped=lambda: True)
    assert again["blocked"] == "mismatch"
    assert len(rc78._history(base)) == 2
    assert "BTC" in rc78._positions(base)


def test_swallowed_history_write_does_not_drop_the_position(tmp_path, monkeypatch):
    base, _backup = rc78.prepare(tmp_path, monkeypatch)
    monkeypatch.setenv("DESK_PAPER_STOP_MONITOR", "1")
    before = (base / "state_v2.json").read_bytes()
    monkeypatch.setattr(cli, "append_trade_history", lambda *_a, **_k: None)
    with pytest.raises(PaperStopRefused, match="history_not_durable"):
        apply_paper_stop_protection(cli, {"BTC": 130.0}, rc78._now_ms(),
                                    lock_held=True, legacy_stopped=lambda: True)
    assert (base / "state_v2.json").read_bytes() == before
    assert len(rc78._history(base)) == 1
    assert (base / STOP_WORK_NAME).is_file()


def test_string_claim_id_still_blocks_the_open_position(tmp_path, monkeypatch):
    base, _backup = rc78.prepare(tmp_path, monkeypatch)
    state = json.loads((base / "state_v2.json").read_text())
    pos_id = state["main"]["positions"]["BTC"]["id"]
    (base / STOP_WORK_NAME).write_text(
        json.dumps({"claims": [{"symbol": "BTC", "id": str(pos_id)}]}), encoding="utf-8")
    monkeypatch.setenv("DESK_PAPER_STOP_MONITOR", "1")
    report = apply_paper_stop_protection(cli, {"BTC": 130.0}, rc78._now_ms(),
                                         lock_held=True, legacy_stopped=lambda: True)
    assert report["blocked"] == "open"
    assert len(rc78._history(base)) == 1


def test_proven_claim_is_archived_on_startup_without_a_second_close(tmp_path, monkeypatch):
    base, backup = rc78.prepare(tmp_path, monkeypatch)
    monkeypatch.setenv("DESK_PAPER_STOP_MONITOR", "1")
    now = rc78._now_ms()
    monkeypatch.setattr(cli, "fetch_candles", rc78._feed(now, 103.0))
    with rc78.worker(base, backup) as service:
        service.tick()
    closed = rc78._history(base)[-1]
    (base / STOP_WORK_NAME).write_text(
        json.dumps({"claims": [{"symbol": "BTC", "id": closed["id"]}]}), encoding="utf-8")
    _refresh(base, backup)
    with rc78.worker(base, backup):
        pass
    assert len(rc78._history(base)) == 2
    assert not (base / STOP_WORK_NAME).exists()
    archived = list(base.glob("paper_stop_protect.reconciled-*.json"))
    assert len(archived) == 1
    assert json.loads(archived[0].read_text())["claims"][0]["id"] == closed["id"]


def test_running_legacy_container_blocks_protection(tmp_path, monkeypatch):
    base, backup = rc78.prepare(tmp_path, monkeypatch)
    monkeypatch.setenv("DESK_PAPER_STOP_MONITOR", "1")
    monkeypatch.setattr(cli, "fetch_candles", rc78._feed(rc78._now_ms(), 130.0))
    probed = {"stopped": True}
    service = rc78.worker(base, backup, stopped=lambda _name: probed["stopped"])
    with service:
        probed["stopped"] = False
        with pytest.raises(Exception):
            service.tick()
    assert "BTC" in rc78._positions(base)
    assert len(rc78._history(base)) == 1


def test_other_process_cannot_close_under_the_writer_lock(tmp_path, monkeypatch):
    base, _backup = rc78.prepare(tmp_path, monkeypatch)
    lock_path = base / ".exit_only_writer.lock"
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    import fcntl
    fcntl.flock(fd, fcntl.LOCK_EX)
    script = """
import os, sys
sys.path[:0] = os.environ["PYTHONPATH"].split(":")
from desk import cli
from desk.paper_stop_monitor import PaperStopRefused, apply_paper_stop_protection
base = sys.argv[1]
os.environ["DESK_MODE"] = "paper"
os.environ["DESK_PAPER_STOP_MONITOR"] = "1"
cli.DATA_DIR = base
cli.STATE_FILE = base + "/state_v2.json"
cli.LIVE._live = False
try:
    apply_paper_stop_protection(cli, {"BTC": 130.0}, int(sys.argv[2]),
                                lock_held=True, legacy_stopped=lambda: True)
    print("CLOSED")
except PaperStopRefused as exc:
    print("REFUSED " + str(exc))
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = ".:backend"
    env["DESK_MODE"] = "paper"
    proc = subprocess.run([sys.executable, "-c", script, str(base), str(rc78._now_ms())],
                          cwd=str(Path.cwd()), env=env, capture_output=True, text=True, check=False)
    fcntl.flock(fd, fcntl.LOCK_UN)
    os.close(fd)
    assert proc.returncode == 0, proc.stderr
    assert "REFUSED ownership_lock_required" in proc.stdout
    assert "BTC" in rc78._positions(base)
    assert len(rc78._history(base)) == 1


def test_bool_clock_and_live_mode_do_not_close(tmp_path, monkeypatch):
    base, _backup = rc78.prepare(tmp_path, monkeypatch)
    monkeypatch.setenv("DESK_PAPER_STOP_MONITOR", "1")
    with pytest.raises(PaperStopRefused, match="clock"):
        apply_paper_stop_protection(cli, {"BTC": 130.0}, True,
                                    lock_held=True, legacy_stopped=lambda: True)
    monkeypatch.setattr(cli.LIVE, "_live", True)
    with pytest.raises(PaperStopRefused, match="paper_only"):
        apply_paper_stop_protection(cli, {"BTC": 130.0}, rc78._now_ms(),
                                    lock_held=True, legacy_stopped=lambda: True)
    assert len(rc78._history(base)) == 1
    assert (base / "lessons.md").read_text().startswith("Historic lesson")
