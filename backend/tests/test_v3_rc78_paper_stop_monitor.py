"""RC78 offline: dormant PAPER stop/TP/liquidation monitor. Synthetic prices only."""
from __future__ import annotations

from dataclasses import replace
import fcntl
import json
import os
from pathlib import Path
import shutil
import threading
import time

import pytest

from desk import cli
from desk.engine import PaperAccount, liq_price
from desk.exit_only import ExitOnlyError, ExitOnlyWorker
from desk.paper_stop_monitor import (
    STOP_WORK_NAME,
    PaperStopRefused,
    apply_paper_stop_protection,
    monitor_opt_in,
    quote_protection,
)


def _now_ms() -> int:
    return int(time.time() * 1000)


def _candle(now_ms: int, close: float, age_ms: int = 10_000):
    return [[now_ms - age_ms, close, close, close, close, 1]]


def prepare(tmp_path, monkeypatch, *, side=-1, sl=102.0, tp=95.0, portfolio="hawk"):
    base = tmp_path / portfolio
    backup = tmp_path / "snapshot"
    base.mkdir()
    backup.mkdir()
    monkeypatch.setenv("DESK_MODE", "paper")
    monkeypatch.setenv("DESK_PORTFOLIO", portfolio)
    monkeypatch.delenv("DESK_PAPER_STOP_MONITOR", raising=False)
    monkeypatch.setenv("DESK_DATA_DIR", str(base))
    monkeypatch.setattr(cli, "DATA_DIR", str(base))
    monkeypatch.setattr(cli, "STATE_FILE", str(base / "state_v2.json"))
    monkeypatch.setattr(cli, "PORTFOLIO", replace(cli.PORTFOLIO, name=portfolio, data_dir=str(base)))
    monkeypatch.setattr(cli.LIVE, "_live", False)
    monkeypatch.setattr(cli, "notify_close", lambda *a, **k: None)
    for name in ("run_cycle", "iteration", "loop_step", "process_flags"):
        monkeypatch.setattr(cli, name, lambda *a, **k: pytest.fail("TRADING LOOP INVOKED"))
    monkeypatch.setattr(cli.LIVE, "open", lambda *a, **k: pytest.fail("LIVE OPEN"))
    monkeypatch.setattr(cli.LIVE, "close", lambda *a, **k: pytest.fail("LIVE CLOSE"))
    state = {}
    acc = cli.make_account(state)
    stamp = _now_ms() - 3_600_000
    pos, msg = acc.open("BTC", side, 100, 20, 100.0, sl, tp, stamp, {})
    assert pos is not None, msg
    cli.save_account(acc, state)
    cli.save_state(state, str(base / "state_v2.json"))
    (base / "trade_history.jsonl").write_text('{"id":0,"symbol":"OLD","net":1}\n', encoding="utf-8")
    (base / "learning_log.jsonl").write_text("", encoding="utf-8")
    (base / "lessons.md").write_text("Historic lesson: do not destroy memory\n", encoding="utf-8")
    (base / "errors.md").write_text("keep errors\n", encoding="utf-8")
    (base / "pause.flag").write_text("", encoding="utf-8")
    for name in ("state_v2.json", "trade_history.jsonl", "learning_log.jsonl", "lessons.md"):
        shutil.copy2(base / name, backup / name)
    return base, backup


def worker(base, backup, *, stopped=lambda _: True):
    return ExitOnlyWorker(base=base, backup=backup, portfolio=base.name, legacy=cli, stopped=stopped)


def _feed(now_ms, close, age_ms=10_000):
    def fetch(symbol, bar, limit):
        assert bar == "1m"
        return _candle(now_ms, close, age_ms)
    return fetch


def _positions(base):
    return json.loads((base / "state_v2.json").read_text())["main"]["positions"]


def _history(base):
    return [json.loads(line) for line in (base / "trade_history.jsonl").read_text().splitlines() if line.strip()]


def test_import_does_not_start_a_monitor(monkeypatch):
    monkeypatch.setenv("DESK_PAPER_STOP_MONITOR", "1")
    monkeypatch.setenv("DESK_MODE", "paper")
    before = {thread.ident for thread in threading.enumerate()}
    import desk.exit_only  # noqa: F401
    import desk.paper_stop_monitor as monitor
    assert monitor.monitor_opt_in() is True
    assert {thread.ident for thread in threading.enumerate()} == before


def test_quote_matches_engine_bar_and_liquidation_cap_is_not_the_gap_loss():
    """Document the existing PAPER boundary. Do not invent a new cash policy."""
    now = _now_ms()
    cases = (
        (1, 98.0, 110.0, (100.0, None), (98.0, "stop loss"), (111.0, "take profit"), (95.0, "liquidazione")),
        (-1, 102.0, 95.0, (100.0, None), (103.0, "stop loss"), (94.0, "take profit"), (110.0, "liquidazione")),
    )
    for side, sl, tp, inside, stop, take, gap in cases:
        left = PaperAccount()
        right = PaperAccount()
        assert left.open("SYN", side, 100, 20, 100.0, sl, tp, now - 1000, {})[0] is not None
        assert right.open("SYN", side, 100, 20, 100.0, sl, tp, now - 1000, {})[0] is not None
        idle_px, idle_why = inside
        assert quote_protection(left.positions["SYN"], idle_px) is None
        assert left.on_bar("SYN", now, idle_px, idle_px, idle_px, idle_px, 60_000) is None
        for mark, why in (stop, take, gap):
            a, b = PaperAccount(), PaperAccount()
            a.open("SYN", side, 100, 20, 100.0, sl, tp, now - 1000, {})
            b.open("SYN", side, 100, 20, 100.0, sl, tp, now - 1000, {})
            decision = quote_protection(a.positions["SYN"], mark)
            assert decision is not None and decision[0] == why
            bar = b.on_bar("SYN", now, mark, mark, mark, mark, 60_000)
            closed = a._close(a.positions["SYN"], decision[1], now + 60_000, decision[0])
            assert bar["why"] == closed["why"] == why
            assert bar["exit"] == closed["exit"]
            assert bar["net"] == closed["net"]
        gap_acc, liq_acc = PaperAccount(), PaperAccount()
        gap_acc.open("SYN", side, 100, 20, 100.0, sl, tp, now - 1000, {})
        opened, _ = liq_acc.open("SYN", side, 100, 20, 100.0, sl, tp, now - 1000, {})
        fee_open = opened.fee_open
        margin = opened.total_margin
        stored_liq = opened.liq
        assert stored_liq == pytest.approx(
            liq_price(side, opened.entry, opened.leverage, liq_acc.limits.maint))
        manual = gap_acc.close("SYN", gap[0], now, "chiusura manuale")
        protected = liq_acc._close(liq_acc.positions["SYN"], stored_liq, now, "liquidazione")
        assert manual["net"] < -(margin)
        assert protected["net"] == round(-margin - fee_open, 4)
        assert protected["net"] > manual["net"]
        assert "closed_by" not in protected


def test_pending_second_leg_is_not_filled_when_price_reaches_its_trigger(tmp_path, monkeypatch):
    base, _backup = prepare(tmp_path, monkeypatch, side=1, sl=98.0, tp=110.0)
    state = json.loads((base / "state_v2.json").read_text())
    pos = state["main"]["positions"]["BTC"]
    before_margin = pos["total_margin"]
    pos["pending_split"] = {"trigger": 99.0, "expire_ms": _now_ms() + 3_600_000, "margin": 80}
    (base / "state_v2.json").write_text(json.dumps(state), encoding="utf-8")
    monkeypatch.setenv("DESK_PAPER_STOP_MONITOR", "1")
    report = apply_paper_stop_protection(cli, {"BTC": 99.0}, _now_ms(), lock_held=True, legacy_stopped=lambda: True)
    assert report["enabled"] is True and report["closed"] == []
    kept = _positions(base)["BTC"]
    assert kept["total_margin"] == before_margin
    assert kept["pending_split"]["trigger"] == 99.0
    assert len(_history(base)) == 1


def test_opt_in_off_keeps_a_crossed_stop_open(tmp_path, monkeypatch):
    base, backup = prepare(tmp_path, monkeypatch)
    monkeypatch.setattr(cli, "fetch_candles", lambda *a, **k: pytest.fail("feed"))
    lessons = (base / "lessons.md").read_bytes()
    errors = (base / "errors.md").read_bytes()
    with worker(base, backup) as service:
        report = service.tick()
    assert report["stop_monitor"]["enabled"] is False
    assert "BTC" in _positions(base)
    assert _history(base) == [{"id": 0, "symbol": "OLD", "net": 1}]
    assert (base / "lessons.md").read_bytes() == lessons
    assert (base / "errors.md").read_bytes() == errors
    assert monitor_opt_in() is False


@pytest.mark.parametrize("side,sl,tp,mark,why", (
    (-1, 102.0, 95.0, 103.0, "stop loss"),
    (-1, 102.0, 95.0, 94.0, "take profit"),
    (1, 98.0, 110.0, 97.0, "stop loss"),
    (1, 98.0, 110.0, 111.0, "take profit"),
))
def test_fresh_quote_closes_long_and_short_stop_or_target(tmp_path, monkeypatch, side, sl, tp, mark, why):
    base, backup = prepare(tmp_path, monkeypatch, side=side, sl=sl, tp=tp)
    monkeypatch.setenv("DESK_PAPER_STOP_MONITOR", "1")
    now = _now_ms()
    monkeypatch.setattr(cli, "fetch_candles", _feed(now, mark))
    lessons = (base / "lessons.md").read_bytes()
    notified = []
    monkeypatch.setattr(cli, "notify_close", lambda *a, **k: notified.append(a))
    with worker(base, backup) as service:
        first = service.tick()
        second = service.tick()
    assert first["stop_monitor"]["closed"][0]["why"] == why
    assert second["stop_monitor"]["closed"] == []
    assert _positions(base) == {}
    rows = _history(base)
    assert rows[0]["symbol"] == "OLD"
    assert len(rows) == 2
    assert rows[1]["why"] == why
    assert "closed_by" not in rows[1]
    assert "manual_learning" not in rows[1]
    assert rows[1]["net"] != 0
    assert notified == []
    assert (base / "lessons.md").read_bytes() == lessons
    assert (base / "errors.md").read_text() == "keep errors\n"
    learning = (base / "learning_log.jsonl").read_text().strip().splitlines()
    assert learning and json.loads(learning[-1])["ev"] == "close"
    assert not (base / STOP_WORK_NAME).exists()


def test_price_inside_the_band_does_not_close(tmp_path, monkeypatch):
    base, backup = prepare(tmp_path, monkeypatch)
    monkeypatch.setenv("DESK_PAPER_STOP_MONITOR", "1")
    monkeypatch.setattr(cli, "fetch_candles", _feed(_now_ms(), 100.0))
    with worker(base, backup) as service:
        report = service.tick()
    assert report["stop_monitor"]["closed"] == []
    assert "BTC" in _positions(base)
    assert len(_history(base)) == 1


@pytest.mark.parametrize("age_or_empty", ("stale", "missing", "nan", "future"))
def test_stale_or_missing_quotes_do_not_close(tmp_path, monkeypatch, age_or_empty):
    base, backup = prepare(tmp_path, monkeypatch)
    monkeypatch.setenv("DESK_PAPER_STOP_MONITOR", "1")
    now = _now_ms()

    def fetch(symbol, bar, limit):
        if age_or_empty == "missing":
            return []
        if age_or_empty == "stale":
            return _candle(now, 130.0, age_ms=180_000)
        if age_or_empty == "future":
            return [[now + 5_000, 130, 130, 130, 130, 1]]
        return [[now - 1_000, 130, 130, 130, float("nan"), 1]]

    monkeypatch.setattr(cli, "fetch_candles", fetch)
    with worker(base, backup) as service:
        report = service.tick()
    assert report["stop_monitor"]["closed"] == []
    assert "BTC" in _positions(base)
    assert len(_history(base)) == 1


def test_pause_and_live_refuse_before_any_close(tmp_path, monkeypatch):
    base, backup = prepare(tmp_path, monkeypatch)
    monkeypatch.setenv("DESK_PAPER_STOP_MONITOR", "1")
    monkeypatch.setattr(cli, "fetch_candles", _feed(_now_ms(), 130.0))
    with worker(base, backup) as service:
        (base / "pause.flag").unlink()
        with pytest.raises(ExitOnlyError):
            service.tick()
    assert "BTC" in _positions(base)
    (base / "pause.flag").write_text("", encoding="utf-8")
    monkeypatch.setattr(cli.LIVE, "_live", True)
    with pytest.raises(PaperStopRefused, match="paper_only"):
        apply_paper_stop_protection(cli, {"BTC": 130.0}, _now_ms(), lock_held=True, legacy_stopped=lambda: True)
    monkeypatch.setattr(cli.LIVE, "_live", False)
    monkeypatch.setenv("DESK_MODE", "live")
    with pytest.raises(PaperStopRefused, match="paper_only"):
        apply_paper_stop_protection(cli, {"BTC": 130.0}, _now_ms(), lock_held=True, legacy_stopped=lambda: True)
    assert len(_history(base)) == 1


def test_opt_in_does_not_bypass_a_close_flag_left_before_startup(tmp_path, monkeypatch):
    base, backup = prepare(tmp_path, monkeypatch)
    monkeypatch.setenv("DESK_PAPER_STOP_MONITOR", "1")
    before = (base / "state_v2.json").read_bytes()
    (base / "close_position.flag").write_text(
        json.dumps({"symbols": ["BTC"], "ts": _now_ms()}), encoding="utf-8")
    with pytest.raises(ExitOnlyError, match="existing_close_request"):
        with worker(base, backup):
            pass
    assert (base / "close_position.flag").is_file()
    assert (base / "state_v2.json").read_bytes() == before
    assert len(_history(base)) == 1


def test_manual_close_keeps_priority_and_is_not_duplicated(tmp_path, monkeypatch):
    base, backup = prepare(tmp_path, monkeypatch)
    monkeypatch.setenv("DESK_PAPER_STOP_MONITOR", "1")
    now = _now_ms()
    monkeypatch.setattr(cli, "fetch_candles", _feed(now, 103.0))
    with worker(base, backup) as service:
        (base / "close_position.flag").write_text(
            json.dumps({"symbols": ["BTC"], "ts": now}), encoding="utf-8")
        service.tick()
    rows = _history(base)
    assert len(rows) == 2
    assert rows[1]["why"] == "chiusura manuale"
    assert rows[1]["closed_by"] == "utente"
    assert rows[1]["manual_learning"] == "loss_reduction_example"
    assert _positions(base) == {}


def test_stale_manual_flag_does_not_block_a_fresh_stop(tmp_path, monkeypatch):
    base, backup = prepare(tmp_path, monkeypatch)
    monkeypatch.setenv("DESK_PAPER_STOP_MONITOR", "1")
    now = _now_ms()
    monkeypatch.setattr(cli, "fetch_candles", _feed(now, 103.0))
    with worker(base, backup) as service:
        (base / "close_position.flag").write_text(
            json.dumps({"symbols": ["BTC"], "ts": now - 3_600_000}), encoding="utf-8")
        service.tick()
    rows = _history(base)
    assert len(rows) == 2
    assert rows[1]["why"] == "stop loss"
    assert "closed_by" not in rows[1]
    assert not (base / "close_position.flag").exists()
    assert not (base / "close_position.flag.work").exists()


def test_unreconciled_manual_work_blocks_stop_close(tmp_path, monkeypatch):
    base, _backup = prepare(tmp_path, monkeypatch)
    monkeypatch.setenv("DESK_PAPER_STOP_MONITOR", "1")
    (base / "close_position.flag.work").write_text(
        json.dumps({"symbols": ["BTC"], "ts": _now_ms()}), encoding="utf-8")
    report = apply_paper_stop_protection(cli, {"BTC": 130.0}, _now_ms(), lock_held=True, legacy_stopped=lambda: True)
    assert report["blocked"] == "unreconciled_manual_close"
    assert "BTC" in _positions(base)
    assert len(_history(base)) == 1


def test_interrupted_claim_is_not_replayed_and_blocks_startup(tmp_path, monkeypatch):
    base, backup = prepare(tmp_path, monkeypatch)
    state = json.loads((base / "state_v2.json").read_text())
    pos_id = state["main"]["positions"]["BTC"]["id"]
    (base / STOP_WORK_NAME).write_text(
        json.dumps({"claims": [{"symbol": "BTC", "id": pos_id}]}), encoding="utf-8")
    before = (base / "state_v2.json").read_bytes()
    with pytest.raises(ExitOnlyError, match="unreconciled_stop_protection"):
        with worker(base, backup):
            pass
    assert (base / "state_v2.json").read_bytes() == before
    monkeypatch.setenv("DESK_PAPER_STOP_MONITOR", "1")
    report = apply_paper_stop_protection(cli, {"BTC": 130.0}, _now_ms(), lock_held=True, legacy_stopped=lambda: True)
    assert report["blocked"] == "open"
    assert len(_history(base)) == 1
    assert (base / STOP_WORK_NAME).is_file()


def test_resolved_claim_for_a_closed_id_does_not_invent_a_trade(tmp_path, monkeypatch):
    base, _backup = prepare(tmp_path, monkeypatch)
    monkeypatch.setenv("DESK_PAPER_STOP_MONITOR", "1")
    (base / STOP_WORK_NAME).write_text(
        json.dumps({"claims": [{"symbol": "GONE", "id": 999}]}), encoding="utf-8")
    report = apply_paper_stop_protection(cli, {"BTC": 100.0}, _now_ms(), lock_held=True, legacy_stopped=lambda: True)
    assert report["closed"] == []
    assert report["blocked"] == "unproven"
    assert report["stop_protection"] == "blocked"
    assert "BTC" in _positions(base)
    assert (base / STOP_WORK_NAME).is_file()
    assert len(_history(base)) == 1


def test_directory_lock_and_second_writer_do_not_close(tmp_path, monkeypatch):
    base, backup = prepare(tmp_path, monkeypatch)
    monkeypatch.setenv("DESK_PAPER_STOP_MONITOR", "1")
    monkeypatch.setattr(cli, "fetch_candles", _feed(_now_ms(), 130.0))
    with pytest.raises(PaperStopRefused, match="ownership_lock_required"):
        apply_paper_stop_protection(cli, {"BTC": 130.0}, _now_ms(), lock_held=False, legacy_stopped=lambda: True)
    with worker(base, backup) as service:
        fd = os.open(base, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            report = service.tick()
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
        assert report["request_writer_busy"] is True
        with pytest.raises(ExitOnlyError, match="another_exit_writer_active"):
            with worker(base, backup):
                pass
    assert "BTC" in _positions(base)
    assert len(_history(base)) == 1


def test_gap_through_liquidation_uses_existing_liq_close_not_a_new_policy(tmp_path, monkeypatch):
    base, backup = prepare(tmp_path, monkeypatch)
    monkeypatch.setenv("DESK_PAPER_STOP_MONITOR", "1")
    state = json.loads((base / "state_v2.json").read_text())
    pos = state["main"]["positions"]["BTC"]
    assert pos["liq"] > pos["sl"] > pos["entry"]
    monkeypatch.setattr(cli, "fetch_candles", _feed(_now_ms(), pos["liq"] + 10))
    with worker(base, backup) as service:
        report = service.tick()
    closed = report["stop_monitor"]["closed"][0]
    assert closed["why"] == "liquidazione"
    assert closed["net"] == pytest.approx(round(-pos["total_margin"] - pos["fee_open"], 4))
    assert closed["net"] > -pos["total_margin"] - pos["fee_open"] - 1
    row = _history(base)[-1]
    assert row["why"] == "liquidazione"
    assert row["exit"] == pytest.approx(pos["liq"])
    assert "closed_by" not in row
