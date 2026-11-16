"""Tests for VPS replay orchestration. No public web, no VPS, no trading."""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest

from research.brain_counterfactual import replay_vps as R


def _journal(path: Path) -> None:
    db = sqlite3.connect(path)
    db.execute(
        "CREATE TABLE v3_events(seq INTEGER PRIMARY KEY AUTOINCREMENT,"
        " event_id TEXT, portfolio_id TEXT, run_id TEXT,kind TEXT,"
        "occurred_at_ms INTEGER,payload_json TEXT)"
    )
    for idx, ts in enumerate((1_800_000_000_000, 1_800_000_060_000)):
        db.execute(
            "INSERT INTO v3_events(event_id,portfolio_id,run_id,kind,occurred_at_ms,payload_json) "
            "VALUES (?, 'brain', ?, 'brain_decision', ?, ?)",
            (f"decision-{idx}", R.RUN_ID, ts, json.dumps(
                {"kind": "NO_TRADE", "status": "DRAFT", "symbol": "BTCUSDT"}
            )),
        )
    db.commit()
    db.close()


def test_sqlite_online_backup_reads_existing_run_without_modifying_it(tmp_path, monkeypatch):
    run = tmp_path / "live"
    run.mkdir()
    journal = run / "journal.db"
    _journal(journal)
    monkeypatch.setattr(R, "LIVE_RUN", run)
    before = journal.read_bytes()
    scratch = tmp_path / "separate"
    scratch.mkdir()
    copy, n, first, last = R.consistent_snapshot(scratch)
    assert n == 2
    assert last - first == 60_000
    assert copy.is_file() and copy != journal
    assert journal.read_bytes() == before
    con = sqlite3.connect(copy)
    try:
        assert con.execute("PRAGMA quick_check").fetchone() == ("ok",)
        assert con.execute("SELECT COUNT(*) FROM v3_events").fetchone()[0] == 2
    finally:
        con.close()


def test_candle_window_excludes_forming_bar_and_rejects_large_backfill():
    m = 1_800_000_000_000
    assert R.candle_window(m, m + 2 * R.M1, m + 4 * R.M1 + 20_000) == (
        m, m + 4 * R.M1
    )
    with pytest.raises(RuntimeError, match="12_days"):
        R.candle_window(m, m + 13 * 86_400_000, m + 14 * 86_400_000)


def test_partial_public_data_remains_visible_as_coverage_limit(tmp_path, monkeypatch):
    def data(sym, start, end, *, candle_ms, window_bars, max_requests):
        assert candle_ms == R.M1 and max_requests <= 110
        if sym == "ETHUSDT":
            raise TimeoutError("synthetic_exchange_failure")
        return {
            1_800_000_000_000: ("100", "101", "99", "100", "10"),
            1_800_000_060_000: ("100", "101", "99", "100", "10"),
        }

    def save(path, rows):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("open_time_ms,open,high,low,close,volume\n", encoding="utf-8")
        return "test_sha256"

    monkeypatch.setattr(R, "import_fetch", lambda _scratch: SimpleNamespace(fetch_rows=data, write_csv=save))
    start, end = 1_800_000_000_000, 1_800_000_180_000
    meta = R.fetch_data(tmp_path, start, end)
    assert meta["BTCUSDT"]["received"] == 2
    assert meta["BTCUSDT"]["coverage"] == pytest.approx(2 / 3, rel=1e-4)
    assert meta["ETHUSDT"]["received"] == 0
    assert meta["ETHUSDT"]["error_type"] == "TimeoutError"
    assert not (tmp_path / "candles" / "ETHUSDT" / "1m.csv").exists()
    assert (tmp_path / "candles" / "BTCUSDT" / "1m.csv").exists()


def test_unsafe_or_missing_journal_fails_before_network(tmp_path, monkeypatch):
    run = tmp_path / "run"
    run.mkdir()
    monkeypatch.setattr(R, "LIVE_RUN", run)
    with pytest.raises(RuntimeError, match="journal_not_regular"):
        R.consistent_snapshot(tmp_path)
    foreign = tmp_path / "foreign.db"
    _journal(foreign)
    (run / "journal.db").symlink_to(foreign)
    with pytest.raises(RuntimeError, match="journal_not_regular"):
        R.consistent_snapshot(tmp_path)
