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
from desk.exit_only import ExitOnlyError
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
        # Forming bar: high already through the short stop, close not a finished price.
        return [[now - 5_000, 100, 103, 99, 103, 1]]

    monkeypatch.setattr(cli, "fetch_candles", fetch)
    with rc78.worker(base, backup) as service:
        report = service.tick()
    assert report["stop_monitor"]["stop_protection"] == "blind"
    assert report["stop_monitor"]["positions"][0]["status"] == "incomplete"
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
    monkeypatch.setattr(cli, "fetch_candles", lambda *a, **k: [[now - 70_000, gap, gap, gap, gap, 1]])
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
        json.dumps({"claims": [{"symbol": "BTC", "id": str(pos_id),
                                "open_ms": state["main"]["positions"]["BTC"]["open_ms"]}]}),
        encoding="utf-8")
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
        json.dumps({"claims": [{"symbol": "BTC", "id": closed["id"],
                                "open_ms": closed["open_ms"], "portfolio": "hawk"}]}),
        encoding="utf-8")
    _refresh(base, backup)
    from desk.exit_only import recovery_root
    published = recovery_root(backup)
    if published.exists():
        shutil.rmtree(published)
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


def test_open_but_unlocked_fd_is_not_ownership(tmp_path, monkeypatch):
    """P0-A: a path-matching fd that is not flocked must not close."""
    base, _backup = rc78.prepare(tmp_path, monkeypatch)
    monkeypatch.setenv("DESK_PAPER_STOP_MONITOR", "1")
    import fcntl
    held = os.open(base / ".exit_only_writer.lock", os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(held, fcntl.LOCK_EX)
    script = """
import os, sys
sys.path[:0] = os.environ["PYTHONPATH"].split(":")
from desk import cli
from desk.paper_stop_monitor import PaperStopRefused, apply_paper_stop_protection
base, now = sys.argv[1], int(sys.argv[2])
os.environ["DESK_MODE"] = "paper"
os.environ["DESK_PAPER_STOP_MONITOR"] = "1"
cli.DATA_DIR = base
cli.STATE_FILE = base + "/state_v2.json"
cli.LIVE._live = False
fd = os.open(base + "/.exit_only_writer.lock", os.O_RDWR)
try:
    apply_paper_stop_protection(cli, {"BTC": 130.0}, now, lock_held=True,
                                legacy_stopped=lambda: True, lock_fd=fd)
    print("CLOSED")
except PaperStopRefused as exc:
    print("REFUSED " + str(exc))
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = ".:backend"
    proc = subprocess.run([sys.executable, "-c", script, str(base), str(rc78._now_ms())],
                          cwd=str(Path.cwd()), env=env, capture_output=True, text=True, check=False)
    fcntl.flock(held, fcntl.LOCK_UN)
    os.close(held)
    assert proc.returncode == 0, proc.stderr
    assert "REFUSED ownership_lock_required" in proc.stdout
    assert "BTC" in rc78._positions(base)
    assert len(rc78._history(base)) == 1


def test_reused_id_from_an_older_run_is_not_this_position(tmp_path, monkeypatch):
    base, _backup = rc78.prepare(tmp_path, monkeypatch)
    state = json.loads((base / "state_v2.json").read_text())
    pos = state["main"]["positions"]["BTC"]
    old_open = pos["open_ms"] - 86_400_000
    (base / "trade_history.jsonl").write_text(
        json.dumps({"id": pos["id"], "symbol": "BTC", "open_ms": old_open, "close_ms": old_open + 1000,
                    "why": "stop loss", "net": -1, "partial": False}) + "\n",
        encoding="utf-8")
    (base / "learning_log.jsonl").write_text(
        json.dumps({"ev": "close", "id": pos["id"], "symbol": "BTC", "open_ms": old_open,
                    "close_ms": old_open + 1000, "why": "stop loss", "portfolio": "hawk", "run_no": 1}) + "\n",
        encoding="utf-8")
    partial = {"id": pos["id"], "symbol": "BTC", "open_ms": pos["open_ms"], "close_ms": pos["open_ms"] + 10,
               "why": "TP parziale", "partial": True, "net": 1}
    with (base / "trade_history.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(partial) + "\n")
    monkeypatch.setenv("DESK_PAPER_STOP_MONITOR", "1")
    report = apply_paper_stop_protection(
        cli, {"BTC": 130.0}, rc78._now_ms(), lock_held=True, legacy_stopped=lambda: True)
    assert report["blocked"] is None
    assert report["closed"][0]["why"] == "liquidazione" or report["closed"][0]["why"] == "stop loss"
    rows = rc78._history(base)
    finals = [row for row in rows if row.get("open_ms") == pos["open_ms"] and row.get("partial") is not True]
    assert len(finals) == 1
    assert "BTC" not in rc78._positions(base)


def test_closed_bar_wick_is_not_a_fill(tmp_path, monkeypatch):
    base, backup = rc78.prepare(tmp_path, monkeypatch)
    monkeypatch.setenv("DESK_PAPER_STOP_MONITOR", "1")
    now = rc78._now_ms()

    def fetch(symbol, bar, limit):
        # Closed bar: wick through the short stop, close back inside. Not a fill.
        return [[now - 70_000, 100, 103, 99, 100, 1]]

    monkeypatch.setattr(cli, "fetch_candles", fetch)
    with rc78.worker(base, backup) as service:
        report = service.tick()
        assert report["stop_monitor"]["stop_protection"] == "covered"
        assert report["stop_monitor"]["closed"] == []
        assert report["stop_monitor"]["intrabar_wick"] == "not_a_fill"
        assert _hb(base)["stop_certified"] is False
        assert "BTC" in rc78._positions(base)


def test_health_write_failure_is_not_reported_as_coverage(tmp_path, monkeypatch):
    base, _backup = rc78.prepare(tmp_path, monkeypatch)
    monkeypatch.setenv("DESK_PAPER_STOP_MONITOR", "1")

    def broken(*_a, **_k):
        raise OSError("disk")

    monkeypatch.setattr("desk.paper_stop_monitor._save_health", broken)
    report = apply_paper_stop_protection(
        cli, {"BTC": 130.0}, rc78._now_ms(), lock_held=True, legacy_stopped=lambda: True)
    assert report["stop_protection"] == "telemetry_failed"
    assert report["telemetry_ok"] is False
    assert report["closed"] == []
    assert "BTC" in rc78._positions(base)
    assert len(rc78._history(base)) == 1


def _terminal(symbol, pos_id, open_ms, close_ms, net, why="stop loss"):
    return {"id": pos_id, "symbol": symbol, "open_ms": open_ms, "close_ms": close_ms,
            "why": why, "net": net, "gross": net, "fees": 0.1, "exit": 1.0, "partial": False}


def test_history_and_learning_must_be_the_same_closure(tmp_path, monkeypatch):
    """P0-E: same position with two different close_ms values is not resolved."""
    from desk.paper_stop_monitor import find_same_closure, inspect_claims
    base, _backup = rc78.prepare(tmp_path, monkeypatch)
    state = json.loads((base / "state_v2.json").read_text())
    pos = state["main"]["positions"].pop("BTC")
    (base / "state_v2.json").write_text(json.dumps(state), encoding="utf-8")
    history = _terminal("BTC", pos["id"], pos["open_ms"], 2000, -1.0)
    learning_other = dict(_terminal("BTC", pos["id"], pos["open_ms"], 3000, -1.0), ev="close", portfolio="hawk")
    (base / "trade_history.jsonl").write_text(json.dumps(history) + "\n", encoding="utf-8")
    (base / "learning_log.jsonl").write_text(json.dumps(learning_other) + "\n", encoding="utf-8")
    (base / STOP_WORK_NAME).write_text(json.dumps({
        "claims": [{"symbol": "BTC", "id": pos["id"], "open_ms": pos["open_ms"], "portfolio": "hawk"}]}),
        encoding="utf-8")
    acc = cli.make_account(json.loads((base / "state_v2.json").read_text()))
    assert find_same_closure(base, "BTC", pos["id"], pos["open_ms"]) is None
    assert inspect_claims(base, acc) == "unproven"
    learning_same = dict(history, ev="close", portfolio="hawk")
    (base / "learning_log.jsonl").write_text(json.dumps(learning_same) + "\n", encoding="utf-8")
    assert find_same_closure(base, "BTC", pos["id"], pos["open_ms"]) is not None
    assert inspect_claims(base, acc) == "resolved"
    partial = dict(history, close_ms=1500, partial=True, why="TP parziale", net=0.4)
    (base / "trade_history.jsonl").write_text(
        json.dumps(partial) + "\n" + json.dumps(history) + "\n", encoding="utf-8")
    assert inspect_claims(base, acc) == "resolved"
    mismatched_net = dict(learning_same, net=-9.0)
    (base / "learning_log.jsonl").write_text(json.dumps(mismatched_net) + "\n", encoding="utf-8")
    assert find_same_closure(base, "BTC", pos["id"], pos["open_ms"]) is None
    assert inspect_claims(base, acc) == "unproven"


def test_restart_after_one_of_two_closes_keeps_the_other_and_the_backup(tmp_path, monkeypatch):
    """P0-F: original snapshot is not rewritten; the remaining position stays protectable."""
    from desk.exit_only import recovery_root
    base, backup = rc78.prepare(tmp_path, monkeypatch)
    state = json.loads((base / "state_v2.json").read_text())
    acc = cli.make_account(state)
    opened, message = acc.open("ETH", -1, 100, 20, 100.0, 102.0, 95.0, rc78._now_ms() - 5_000, {})
    assert opened is not None, message
    cli.save_account(acc, state)
    cli.save_state(state, str(base / "state_v2.json"))
    for name in ("state_v2.json", "trade_history.jsonl", "learning_log.jsonl", "lessons.md"):
        shutil.copy2(base / name, backup / name)
    original = {name: (backup / name).read_bytes() for name in
                ("state_v2.json", "trade_history.jsonl", "learning_log.jsonl", "lessons.md")}
    monkeypatch.setenv("DESK_PAPER_STOP_MONITOR", "1")
    now = rc78._now_ms()

    def fetch(symbol, bar, limit):
        price = 130.0 if symbol == "BTC" else 100.0
        return rc78._candle(now, price)

    monkeypatch.setattr(cli, "fetch_candles", fetch)
    with rc78.worker(base, backup) as service:
        first = service.tick()
    assert [row["symbol"] for row in first["stop_monitor"]["closed"]] == ["BTC"]
    assert "BTC" not in rc78._positions(base)
    assert "ETH" in rc78._positions(base)
    for name, payload in original.items():
        assert (backup / name).read_bytes() == payload
    root = recovery_root(backup)
    assert root.is_dir() and backup.resolve() not in root.resolve().parents
    # Crash before the recovery directory is considered: restart still uses the original snapshot.
    shutil.rmtree(root)
    with rc78.worker(base, backup) as service:
        assert "ETH" in rc78._positions(base)
        assert "BTC" not in rc78._positions(base)
        monkeypatch.setattr(cli, "fetch_candles", lambda symbol, bar, limit: rc78._candle(rc78._now_ms(), 130.0))
        second = service.tick()
    assert [row["symbol"] for row in second["stop_monitor"]["closed"]] == ["ETH"]
    assert rc78._positions(base) == {}
    for name, payload in original.items():
        assert (backup / name).read_bytes() == payload
    closures = [row for row in rc78._history(base) if row.get("symbol") in ("BTC", "ETH") and row.get("partial") is not True]
    assert {row["symbol"] for row in closures} == {"BTC", "ETH"}


def test_restart_fails_closed_when_the_close_pair_or_snapshot_is_bad(tmp_path, monkeypatch):
    base, backup = rc78.prepare(tmp_path, monkeypatch)
    state = json.loads((base / "state_v2.json").read_text())
    acc = cli.make_account(state)
    opened, message = acc.open("ETH", -1, 100, 20, 100.0, 102.0, 95.0, rc78._now_ms() - 5_000, {})
    assert opened is not None, message
    cli.save_account(acc, state)
    cli.save_state(state, str(base / "state_v2.json"))
    for name in ("state_v2.json", "trade_history.jsonl", "learning_log.jsonl", "lessons.md"):
        shutil.copy2(base / name, backup / name)
    original = {name: (backup / name).read_bytes() for name in
                ("state_v2.json", "trade_history.jsonl", "learning_log.jsonl", "lessons.md")}
    monkeypatch.setenv("DESK_PAPER_STOP_MONITOR", "1")
    now = rc78._now_ms()
    monkeypatch.setattr(
        cli, "fetch_candles",
        lambda symbol, bar, limit: rc78._candle(now, 130.0 if symbol == "BTC" else 100.0))
    with rc78.worker(base, backup) as service:
        service.tick()
    # Drop the learning proof of BTC's close. State must not be restored from the old snapshot.
    (base / "learning_log.jsonl").write_bytes(original["learning_log.jsonl"])
    eth_open = rc78._positions(base)["ETH"]["open_ms"]
    with pytest.raises(ExitOnlyError, match="restart_lineage_degraded:close_not_proven:BTC"):
        with rc78.worker(base, backup):
            pass
    assert "BTC" not in rc78._positions(base)
    assert rc78._positions(base)["ETH"]["open_ms"] == eth_open
    for name, payload in original.items():
        assert (backup / name).read_bytes() == payload
    # Restore the learning line by replaying the tick is not allowed; put a corrupt manifest
    # only after the files are consistent again would block on corruption. Rebuild consistency
    # is out of scope: the degraded start must leave both the backup and the open position.
    from desk.exit_only import recovery_root
    root = recovery_root(backup)
    if root.exists():
        shutil.rmtree(root)
    bad = root / "rc80-corrupt"
    bad.mkdir(parents=True)
    (bad / "MANIFEST.json").write_text("{", encoding="utf-8")
    # Lineage is still degraded, so the corrupt manifest is not required to be the first error.
    # Repair learning by copying the post-close file back from the recovery copy if present.
    # Here learning was truncated and no recovery copy remains, so start stays degraded.
    with pytest.raises(ExitOnlyError, match="restart_lineage_degraded:close_not_proven:BTC"):
        with rc78.worker(base, backup):
            pass


def test_corrupt_recovery_manifest_refuses_start_without_touching_backup(tmp_path, monkeypatch):
    base, backup = rc78.prepare(tmp_path, monkeypatch)
    original = {name: (backup / name).read_bytes() for name in
                ("state_v2.json", "trade_history.jsonl", "learning_log.jsonl", "lessons.md")}
    from desk.exit_only import recovery_root
    root = recovery_root(backup)
    bad = root / "rc80-corrupt"
    bad.mkdir(parents=True)
    (bad / "MANIFEST.json").write_text("{", encoding="utf-8")
    monkeypatch.setenv("DESK_MODE", "paper")
    with pytest.raises(ExitOnlyError, match="recovery_snapshot_corrupt:json"):
        with rc78.worker(base, backup):
            pass
    assert "BTC" in rc78._positions(base)
    for name, payload in original.items():
        assert (backup / name).read_bytes() == payload


def test_stale_heartbeat_is_an_alarm_and_ready_is_not_coverage():
    from desk.paper_stop_monitor import protection_alarm
    fresh = {"ready": True, "ts": 1_000.0, "stop_protection": "blind",
             "stop_certified": False, "telemetry_ok": True, "intrabar_wick": "not_a_fill",
             "stop_monitor_opt_in": True}
    alarm = protection_alarm(fresh, now=1_001.0)
    assert alarm["alarm"] is True
    assert "blind" in alarm["reasons"]
    assert "ready_is_not_stop_coverage" in alarm["reasons"]
    stale = dict(fresh, stop_protection="covered")
    aged = protection_alarm(stale, now=1_030.0)
    assert "heartbeat_stale" in aged["reasons"]
    certified = dict(fresh, stop_protection="idle", stop_certified=True, ts=1_000.0)
    bad = protection_alarm(certified, now=1_001.0)
    assert "stop_certified_must_stay_false" in bad["reasons"]
