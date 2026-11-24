"""Synthetic only, accounting fixtures are not live trading settings."""
import hashlib
import json
import sqlite3

import pytest

from v3.legacy_accounting import audit_classic_books, audit_brain_structure


def build_classic(tmp_path, *, cash="887.6", fee="0.4", margin="100"):
    root = tmp_path / "hawk"
    root.mkdir()
    closed = [{
        "id": 1, "symbol": "BTC/USDT:USDT", "side": 1,
        "open_ms": 1793600000000, "close_ms": 1793600300000,
        "net": -12, "why": "stop loss",
    }]
    position = {
        "id": 2, "symbol": "ETH/USDT:USDT",
        "margin": float(margin), "total_margin": float(margin),
        "qty": 10.0, "fee_open": float(fee),
    }
    state = {"run_no": 8, "main": {
        "closed": closed, "cash": float(cash),
        "positions": {"ETH/USDT:USDT": position},
        "limits": {"start_equity": 1000.0},
    }}
    (root / "state_v2.json").write_text(json.dumps(state))
    (root / "trade_history.jsonl").write_text(json.dumps(closed[0]) + "\n")
    (root / "learning_log.jsonl").write_text(
        json.dumps({"ev": "close", "portfolio": "hawk", "run_no": 8, **closed[0]}) + "\n"
    )
    return root


def test_book_equity_equal_cash_plus_margin_without_mark(tmp_path):
    root = build_classic(tmp_path)
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir()}
    report = audit_classic_books(root, "hawk")
    assert report.cash_formula_pass and report.multirun_pass
    assert report.residual == "0.0"
    assert report.book_equity == report.expected_book_equity == "987.6"
    assert report.realized_net == "-12"
    assert report.open_entry_fees == "0.4"
    assert report.open_count == 1
    assert {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir()} == before


def test_accounting_residual_rejected_without_guessing(tmp_path):
    root = build_classic(tmp_path, cash="897.6")
    report = audit_classic_books(root, "hawk")
    assert report.multirun_pass
    assert not report.cash_formula_pass
    assert "CURRENT_RUN_CASH_RESIDUAL" in report.issues
    assert report.residual == "10.0"


def test_position_fee_missing_refuses_assumption(tmp_path):
    root = build_classic(tmp_path)
    state_path = root / "state_v2.json"
    state = json.loads(state_path.read_text())
    del state["main"]["positions"]["ETH/USDT:USDT"]["fee_open"]
    state_path.write_text(json.dumps(state))
    with pytest.raises(ValueError, match="invalid_legacy_net"):
        audit_classic_books(root, "hawk")


def test_duplicate_position_id_refused(tmp_path):
    root = build_classic(tmp_path)
    state_path = root / "state_v2.json"
    state = json.loads(state_path.read_text())
    state["main"]["positions"]["SOL/USDT:USDT"] = dict(
        state["main"]["positions"]["ETH/USDT:USDT"], symbol="SOL/USDT:USDT"
    )
    state_path.write_text(json.dumps(state))
    with pytest.raises(ValueError, match="position_id_duplicate"):
        audit_classic_books(root, "hawk")


def test_brain_event_schema_inventory_is_not_import(tmp_path):
    db_path = tmp_path / "brain.sqlite3"
    with sqlite3.connect(db_path) as db:
        db.executescript("""
        CREATE TABLE state(id INTEGER PRIMARY KEY,body TEXT);
        CREATE TABLE events(seq INTEGER PRIMARY KEY,id TEXT,
                            kind TEXT,ts INTEGER,body TEXT);
        """)
        db.execute("INSERT INTO state VALUES(1,?)", (
            json.dumps({"account_id": "brain-free-paper", "mode": "paper",
                        "cash": 1980, "positions": {}}),))
        db.execute("INSERT INTO events VALUES(1,'evt-1','open',1,?)",
                   (json.dumps({"kind": "open", "margin": 100, "fee_paid": 1}),))
        db.execute("INSERT INTO events VALUES(2,'evt-2','partial_trade',2,?)",
                   (json.dumps({"kind": "partial_trade", "segment": {"net": 5}}),))
        db.execute("INSERT INTO events VALUES(3,'evt-3','trade_closed',3,?)",
                   (json.dumps({"kind": "trade_closed", "net": 10}),))
    before = hashlib.sha256(db_path.read_bytes()).hexdigest()
    report = audit_brain_structure(db_path)
    assert report.total_events == 3
    assert dict(report.kind_counts) == {"open": 1, "partial_trade": 1, "trade_closed": 1}
    assert "segment" in dict(report.relevant_fields)["partial_trade"]
    assert not report.import_allowed
    assert hashlib.sha256(db_path.read_bytes()).hexdigest() == before


def test_brain_live_account_rejected(tmp_path):
    path = tmp_path / "brain.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE state(id INTEGER PRIMARY KEY,body TEXT)")
        db.execute("CREATE TABLE events(seq INTEGER PRIMARY KEY,body TEXT,kind TEXT)")
        db.execute("INSERT INTO state VALUES(1,?)",
                   (json.dumps({"account_id": "live", "mode": "live",
                                "cash": 2000, "positions": {}}),))
    with pytest.raises(ValueError, match="foreign_or_live_brain"):
        audit_brain_structure(path)
