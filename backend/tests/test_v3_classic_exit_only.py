"""Isolated legacy PAPER exit-only worker: no orders, no new entries, no AI, no live mode."""
from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path
import shutil
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import desk_api
import desk_view as dv
from desk import cli
from desk.exit_only import ExitOnlyError, ExitOnlyWorker, recent_minute_prices, verify_snapshot


def prepare(tmp_path, monkeypatch, *, portfolio="hawk"):
    base = tmp_path / portfolio
    backup = tmp_path / "snapshot"
    base.mkdir()
    backup.mkdir()
    monkeypatch.setenv("DESK_MODE", "paper")
    monkeypatch.setenv("DESK_PORTFOLIO", portfolio)
    monkeypatch.setenv("DESK_DATA_DIR", str(base))
    monkeypatch.setattr(cli, "DATA_DIR", str(base))
    monkeypatch.setattr(cli, "STATE_FILE", str(base / "state_v2.json"))
    monkeypatch.setattr(cli, "PORTFOLIO", replace(cli.PORTFOLIO, name=portfolio, data_dir=str(base)))
    monkeypatch.setattr(cli.LIVE, "_live", False)
    monkeypatch.setattr(cli, "notify_close", lambda *args, **kw: None)
    state = {}
    acc = cli.make_account(state)
    stamp = int(time.time() * 1000) - 3_600_000
    p, msg = acc.open("BTC", -1, 100, 20, 100.0, 105.0, 95.0, stamp, {})
    assert p is not None, msg
    cli.save_account(acc, state)
    cli.save_state(state, str(base / "state_v2.json"))
    (base / "trade_history.jsonl").write_text("", encoding="utf-8")
    (base / "learning_log.jsonl").write_text("", encoding="utf-8")
    (base / "lessons.md").write_text("Historic lesson: do not destroy memory\n", encoding="utf-8")
    (base / "pause.flag").write_text("", encoding="utf-8")
    for name in ("state_v2.json", "trade_history.jsonl", "learning_log.jsonl", "lessons.md"):
        shutil.copy2(base / name, backup / name)
    return base, backup


def worker(base, backup, *, stopped=lambda _: True):
    return ExitOnlyWorker(base=base, backup=backup, portfolio=base.name, legacy=cli, stopped=stopped)


def _app(base, portfolio="hawk"):
    app = FastAPI()
    async def get_price(_):
        return {"price": 98.0}
    app.include_router(desk_api.make_router(portfolio, str(base), lambda: True, get_price), prefix="/api/desk")
    return app


def test_manual_close_through_authenticated_api_and_exit_only_worker(tmp_path, monkeypatch):
    base, backup = prepare(tmp_path, monkeypatch)
    before_history = (base / "trade_history.jsonl").read_bytes()
    before_lessons = (base / "lessons.md").read_bytes()
    monkeypatch.setattr(cli, "fetch_candles",
                        lambda symbol, bar, limit: [[int(time.time() * 1000) - 30_000,
                                                     100, 102, 96, 98, 123]]
                        if bar == "1m" else pytest.fail("not a 1m price"))
    # Anything but close operations is an error; the worker must not call ordinary entry loops.
    for name in ("run_cycle", "iteration", "loop_step", "process_flags"):
        monkeypatch.setattr(cli, name, lambda *a, **kw: pytest.fail("TRADING LOOP INVOKED"))
    with worker(base, backup) as service:
        assert dv.exit_only_close_ready(str(base), "hawk")
        assert not dv.exit_only_close_ready(str(base), "bull")
        with TestClient(_app(base)) as api:
            r = api.post("/api/desk/close-position", json={"symbol": "BTCUSDT"})
            assert r.status_code == 200
            assert r.json()["queued"] is True
            assert "BTC" in json.loads((base / "state_v2.json").read_text())["main"]["positions"]
        report = service.tick()
        assert report["manual_one_requested"] is True
        assert (base / "close_position.flag").exists() is False
        with TestClient(_app(base)) as api:
            st = api.get("/api/desk/status").json()
        assert st["open_positions"] == 0
        assert st["last_action"]["ok"] is True
        assert "chiusa BTC" in st["last_action"]["detail"]
        assert st["close_worker_mode"] == "exit_only"
    assert not dv.exit_only_close_ready(str(base), "hawk")
    assert (base / "pause.flag").is_file()
    assert (base / "lessons.md").read_bytes() == before_lessons
    history = (base / "trade_history.jsonl").read_bytes()
    assert history.startswith(before_history) and history != before_history
    closed = json.loads(history.decode().splitlines()[-1])
    assert closed["symbol"] == "BTC"
    assert closed["closed_by"] == "utente"
    assert closed["manual_learning"] == "profit_protection_example"
    assert closed["net"] > 0
    assert closed["fees"] > 0
    assert (base / "learning_log.jsonl").stat().st_size > 0


def test_active_exit_only_close_all_is_paper_and_preserves_pause(tmp_path, monkeypatch):
    base, backup = prepare(tmp_path, monkeypatch)
    monkeypatch.setattr(cli, "fetch_candles", lambda sym, bar, limit:
                        [[int(time.time() * 1000) - 15_000, 100, 101, 97, 98, 1]]
                        if bar == "1m" else [])
    with worker(base, backup) as service, TestClient(_app(base)) as api:
        close = api.post("/api/desk/close-all")
        assert close.status_code == 200
        assert close.json()["queued"]
        assert (base / "reset.flag").is_file()
        assert "BTC" in json.loads((base / "state_v2.json").read_text())["main"]["positions"]
        service.tick()
        assert not (base / "reset.flag").exists()
        assert not json.loads((base / "state_v2.json").read_text())["main"]["positions"]
        assert (base / "pause.flag").exists()


def test_worker_rejects_stale_quotes_and_does_not_fabricate_pnl(tmp_path, monkeypatch):
    base, backup = prepare(tmp_path, monkeypatch)
    stale = int(time.time() * 1000) - 86_400_000
    monkeypatch.setattr(cli, "fetch_candles", lambda *args:
                        [[stale, 100, 120, 80, 118, 1]])
    with worker(base, backup) as service, TestClient(_app(base)) as api:
        assert api.post("/api/desk/close-position", json={"symbol": "BTC"}).status_code == 200
        service.tick()
    state = json.loads((base / "state_v2.json").read_text())
    assert "BTC" in state["main"]["positions"]
    assert state["last_action"]["ok"] is False
    assert state["last_action"]["skipped"] == ["BTC"]
    assert not (base / "trade_history.jsonl").read_text()


def test_preflight_is_fail_closed_and_does_not_start_with_pending_flags(tmp_path, monkeypatch):
    base, backup = prepare(tmp_path, monkeypatch)
    state_before = (base / "state_v2.json").read_bytes()
    with pytest.raises(ExitOnlyError, match="legacy_container_not_proven"):
        with worker(base, backup, stopped=lambda _: False):
            pass
    (base / "close_position.flag").write_text('{"symbols":["BTC"],"ts":1}', encoding="utf-8")
    with pytest.raises(ExitOnlyError, match="existing_close_request"):
        with worker(base, backup):
            pass
    assert (base / "close_position.flag").is_file()  # do not silently consume it
    assert (base / "state_v2.json").read_bytes() == state_before
    assert not (base / "exit_only_heartbeat.json").exists()


@pytest.mark.parametrize("change", ("removed_backup", "bad_backup", "unpaused", "live"))
def test_worker_refuses_unsafe_startup(tmp_path, monkeypatch, change):
    base, backup = prepare(tmp_path, monkeypatch)
    if change == "removed_backup":
        (backup / "learning_log.jsonl").unlink()
    elif change == "bad_backup":
        (backup / "state_v2.json").write_text("not the same", encoding="utf-8")
    elif change == "unpaused":
        (base / "pause.flag").unlink()
    elif change == "live":
        monkeypatch.setenv("DESK_MODE", "live")
    with pytest.raises(ExitOnlyError):
        with worker(base, backup):
            pass
    assert not (base / "exit_only_heartbeat.json").exists()


def test_second_writer_refused_with_same_lock(tmp_path, monkeypatch):
    base, backup = prepare(tmp_path, monkeypatch)
    with worker(base, backup):
        with pytest.raises(ExitOnlyError, match="another_exit_writer_active"):
            with worker(base, backup):
                pass


def test_exit_only_stops_advertising_when_legacy_container_starts(tmp_path, monkeypatch):
    base, backup = prepare(tmp_path, monkeypatch)
    probed = {"stopped": True}
    w = worker(base, backup, stopped=lambda _: probed["stopped"])
    with w:
        assert dv.exit_only_close_ready(str(base), "hawk")
        probed["stopped"] = False
        with pytest.raises(ExitOnlyError, match="legacy_container_not_proven"):
            w.tick()
        assert not dv.exit_only_close_ready(str(base), "hawk")


def test_exit_only_quote_freshness_drops_future_stale_and_invalid():
    now_ms = int(time.time() * 1000)
    assert recent_minute_prices(["BTC"], {}, now_ms,
        fetch_candles=lambda *args: [[now_ms - 40_000, 1, 1, 1, 98, 1]]) == {"BTC": 98.0}
    for ts, px in [(now_ms - 180_000, 98), (now_ms + 5000, 98),
                   (now_ms, float("nan")), (now_ms, -3)]:
        assert recent_minute_prices(["BTC"], {}, now_ms,
            fetch_candles=lambda *args: [[ts, 1, 1, 1, px, 1]]) == {}


def test_exit_only_heartbeat_rejects_wrong_portfolio_stale_and_unpaused(tmp_path):
    data = tmp_path / "exit_only_heartbeat.json"
    (tmp_path / "pause.flag").write_text("", encoding="utf-8")
    hb = {"mode": "paper-exit-only", "portfolio": "hawk", "ready": True, "ts": time.time()}
    data.write_text(json.dumps(hb), encoding="utf-8")
    assert dv.exit_only_close_ready(str(tmp_path), "hawk")
    assert not dv.exit_only_close_ready(str(tmp_path), "bull")
    hb["ts"] = time.time() - 30
    data.write_text(json.dumps(hb), encoding="utf-8")
    assert not dv.exit_only_close_ready(str(tmp_path), "hawk")
    hb["ts"] = time.time()
    data.write_text(json.dumps(hb), encoding="utf-8")
    (tmp_path / "pause.flag").unlink()
    assert not dv.exit_only_close_ready(str(tmp_path), "hawk")


def test_snapshot_comparison_is_strict(tmp_path, monkeypatch):
    base, backup = prepare(tmp_path, monkeypatch)
    verify_snapshot(base, backup)
    (backup / "trade_history.jsonl").write_text("{}\n", encoding="utf-8")
    with pytest.raises(ExitOnlyError, match="snapshot_missing_or_mismatched"):
        verify_snapshot(base, backup)
