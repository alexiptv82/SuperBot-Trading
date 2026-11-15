"""Synthetic, offline tests for symbol-specific Brain risk research."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from research.brain_asset_risk.audit import build_report


def _journal(db: Path, *, tamper: str = "") -> None:
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE v3_events (seq INTEGER PRIMARY KEY AUTOINCREMENT,"
        "event_id TEXT,portfolio_id TEXT,run_id TEXT,kind TEXT,"
        "occurred_at_ms INTEGER,payload_json TEXT)"
    )
    events = [
        ("d1", "brain_decision", 1000, {
            "kind": "OPEN", "status": "APPROVED", "symbol": "ETHUSDT", "regime": "EXPANSION"
        }),
        ("o1", "paper_open", 1100, {
            "position_id": "e1", "symbol": "ETHUSDT", "side": -1,
            "fill_price": "100", "stop_price": "101", "quantity": "10",
            "decision_event_id": "d1",
        }),
        ("c1", "paper_close", 2000, {
            "position_id": "e1", "symbol": "ETHUSDT", "side": -1,
            "realized_pnl": "-50", "fees": "5", "reason": "stop",
        }),
        ("d2", "brain_decision", 2100, {
            "kind": "OPEN", "status": "APPROVED", "symbol": "BTCUSDT", "regime": "TREND_DOWN"
        }),
        ("o2", "paper_open", 2200, {
            "position_id": "b1", "symbol": "BTCUSDT", "side": -1,
            "fill_price": "100", "stop_price": "101", "quantity": "20",
            "decision_event_id": "d2",
        }),
        ("c2", "paper_close", 2500, {
            "position_id": "b1", "symbol": "BTCUSDT", "side": -1,
            "realized_pnl": "90", "fees": "10", "reason": "take_profit",
        }),
        ("o3", "paper_open", 3000, {
            "position_id": "e2", "symbol": "ETHUSDT", "side": 1,
            "fill_price": "100", "stop_price": "99", "quantity": "10",
            "decision_event_id": "",
        }),
    ]
    if tamper == "bad_close":
        events[2][3]["symbol"] = "BTCUSDT"
    if tamper == "nan":
        events[2][3]["realized_pnl"] = "NaN"
    if tamper == "duplicate":
        events.append(("c3", "paper_close", 2900, {
            "position_id": "e1", "symbol": "ETHUSDT", "side": -1,
            "realized_pnl": "1", "fees": "0", "reason": "stop",
        }))
    for eid, kind, ts, payload in events:
        conn.execute(
            "INSERT INTO v3_events(event_id,portfolio_id,run_id,kind,occurred_at_ms,payload_json)"
            " VALUES (?, 'brain','brain-test', ?,?,?)",
            (eid, kind, ts, json.dumps(payload)),
        )
    conn.commit()
    conn.close()


def test_realized_net_not_double_charged_and_open_excluded(tmp_path):
    db = tmp_path / "journal.db"
    _journal(db)
    before = db.read_bytes()
    r = build_report(db, "brain-test")
    assert db.read_bytes() == before
    assert r["mode"] == "PAPER_READ_ONLY"
    assert r["symbols_excluded"] == [] and r["orders_sent"] == 0
    assert r["closed_total"] == 2 and r["open_total"] == 1
    assert r["overall"]["net_usdt"] == "40.00"
    assert r["overall"]["fees_usdt_included_in_net"] == "15.00"
    assert r["symbols"]["ETHUSDT"]["overall"]["net_usdt"] == "-50.00"
    assert r["symbols"]["ETHUSDT"]["open_positions"] == 1
    assert r["symbols"]["ETHUSDT"]["by_regime"]["EXPANSION"]["stop_closes"] == 1
    assert r["symbols"]["BTCUSDT"]["by_regime"]["TREND_DOWN"]["wins"] == 1


def test_small_sample_never_autobans_symbols(tmp_path):
    db = tmp_path / "journal.db"
    _journal(db)
    r = build_report(db, "brain-test")
    for rows in r["symbols"].values():
        assert rows["overall"]["sample_status"] == "TOO_SMALL_TO_EXCLUDE"


def test_unknown_run_empty_instead_of_cross_contaminating(tmp_path):
    db = tmp_path / "journal.db"
    _journal(db)
    r = build_report(db, "another-run")
    assert r["closed_total"] == 0
    assert r["symbols"] == {}


@pytest.mark.parametrize("tamper", ["bad_close", "nan", "duplicate"])
def test_corruption_is_not_silently_counted(tmp_path, tamper):
    db = tmp_path / "journal.db"
    _journal(db, tamper=tamper)
    with pytest.raises(ValueError):
        build_report(db, "brain-test")
