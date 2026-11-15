"""No-network journal integration tests for FRRD observational-only pipeline."""
from __future__ import annotations

import csv
import json
import sqlite3

import pytest

from research.brain_frrd import offline
from research.brain_frrd.test_detector import END, _down


def _journal(path, *, with_close=True):
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE v3_events (seq INTEGER PRIMARY KEY AUTOINCREMENT, "
        "event_id TEXT, portfolio_id TEXT, run_id TEXT, kind TEXT, "
        "occurred_at_ms INTEGER, payload_json TEXT)"
    )
    ev = [("paper_open", END, {
        "position_id": "p1", "symbol": "BTCUSDT", "side": -1,
        "decision_event_id": "d1", "regime": "EXPANSION",
    })]
    if with_close:
        ev.append(("paper_close", END + 3_600_000, {
            "position_id": "p1", "realized_pnl": "12.34",
            "reason": "take_profit",
        }))
    for i, (kind, ts, body) in enumerate(ev):
        conn.execute(
            "INSERT INTO v3_events(event_id, portfolio_id, run_id, kind, "
            "occurred_at_ms, payload_json) VALUES (?, 'brain', 'brain-test', ?, ?, ?)",
            (f"e{i}", kind, ts, json.dumps(body)),
        )
    conn.commit()
    conn.close()


def _csv(path, bars):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fd:
        writer = csv.writer(fd)
        writer.writerow(("open_time_ms", "open", "high", "low", "close", "volume"))
        for b in bars:
            writer.writerow((
                b.open_time_ms, str(b.open), str(b.high), str(b.low),
                str(b.close), str(b.volume),
            ))


def _data(tmp_path):
    journal = tmp_path / "run" / "journal.db"
    journal.parent.mkdir(parents=True)
    _journal(journal)
    candle_folder = tmp_path / "candles" / "BTCUSDT"
    for name, bars in zip(("15m", "1h", "4h"), _down()):
        _csv(candle_folder / (name + ".csv"), bars)
    return journal, tmp_path / "candles"


def test_journal_is_read_only_and_outcome_never_enters_signal(tmp_path):
    journal, candles = _data(tmp_path)
    before = journal.read_bytes()
    with_outcome = offline.analyze(journal, "brain-test", candles)
    assert journal.read_bytes() == before
    assert len(with_outcome) == 1
    row = with_outcome[0]
    assert row["frrd"]["state"] == "CONTINUAZIONE_SHORT"
    assert row["frrd"]["regime"] == "EXPANSION"
    assert row["frrd"]["advisory_only"] is True
    assert row["outcome_after_entry"]["realized_pnl_usdt"] == "12.34"
    assert row["decision_event_id"] == "d1"
    # Identical entry candles, no close event: signal must be identical.
    no_close = tmp_path / "no_close.db"
    _journal(no_close, with_close=False)
    without = offline.analyze(no_close, "brain-test", candles)
    assert without[0]["frrd"] == row["frrd"]
    assert without[0]["outcome_after_entry"] is None


def test_missing_candles_fail_as_uncertain_instead_of_short(tmp_path):
    journal, candles = _data(tmp_path)
    (candles / "BTCUSDT" / "1h.csv").unlink()
    rows = offline.analyze(journal, "brain-test", candles)
    assert rows[0]["frrd"]["state"] == "INCERTO"
    assert rows[0]["frrd"]["reason"] == "offline_missing_candle_file"


def test_cli_writes_only_new_research_artifact(tmp_path, capsys):
    journal, candles = _data(tmp_path)
    output = tmp_path / "research.jsonl"
    before = journal.read_bytes()
    args = ["--journal", str(journal), "--run-id", "brain-test",
            "--candles-dir", str(candles), "--out", str(output)]
    offline.main(args)
    assert journal.read_bytes() == before
    assert json.loads(output.read_text().splitlines()[0])["frrd"]["advisory_only"]
    result = json.loads(capsys.readouterr().out)
    assert result["orders_sent"] == 0 and result["journal_modified"] is False
    with pytest.raises(FileExistsError):
        offline.main(args)


def test_refuses_to_write_into_journal_directory(tmp_path):
    journal, candles = _data(tmp_path)
    with pytest.raises(SystemExit):
        offline.main([
            "--journal", str(journal), "--run-id", "brain-test",
            "--candles-dir", str(candles), "--out", str(journal.parent / "illegal.jsonl"),
        ])


def test_invalid_csv_header_or_nonfinite_number_cannot_be_silently_processed(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("not,a,candle\n1,2,3\n")
    with pytest.raises(ValueError):
        offline.read_bars(bad)
    bad.write_text("open_time_ms,open,high,low,close,volume\n0,NaN,1,1,1,1\n")
    # Parsing as Decimal succeeds, but the market view rejects non-finite
    # values as INCERTO rather than generating directional signals.
    rows = offline.read_bars(bad)
    from research.brain_frrd.detector import observe
    obs = observe(rows, rows, as_of_ms=END)
    assert obs.state == "INCERTO"
