"""Strict Brain Free V2 reconciliation, on private synthetic databases only."""
import json
import sqlite3

from v3.legacy_brain_books import audit_brain_books


def make_db(tmp_path, *, cash=2017, mutate=None, leave_open=False):
    dbpath = tmp_path / "brain.sqlite3"
    s = {"mode": "paper", "account_id": "brain-free-paper",
         "cash": cash, "positions": {"BTC": {"id": 3}} if leave_open else {}}
    events = [
        ("open", {"kind": "open", "symbol": "BTC", "position_id": 1,
                  "qty": 10, "margin_added": 100, "fee_paid": 1}),
        ("trade_closed", {"kind": "trade_closed", "symbol": "BTC",
                          "position_id": 1,
                          "net": 10, "segment": {
                              "net": 10, "gross": 12, "fees": 2, "funding": 0}}),
        ("open", {"kind": "open", "symbol": "ETH", "position_id": 2,
                  "qty": 15, "margin_added": 150, "fee_paid": 1}),
        ("partial_trade", {"kind": "partial_trade", "symbol": "ETH",
                           "position_id": 2, "net": 3,
                           "segment": {"net": 3, "gross": 5,
                                       "fees": 1, "funding": 1}}),
        ("trade_closed", {"kind": "trade_closed", "symbol": "ETH",
                          "position_id": 2,
                          # Final net INCLUDES prior partial: 3 + 4 = 7.
                          "net": 7,
                          "segment": {"net": 4, "gross": 5,
                                      "fees": 1, "funding": 0}}),
    ]
    if mutate:
        mutate(events)
    with sqlite3.connect(dbpath) as db:
        db.execute("CREATE TABLE state(id INTEGER PRIMARY KEY,body TEXT)")
        db.execute("CREATE TABLE events(seq INTEGER PRIMARY KEY,id TEXT,kind TEXT,ts INTEGER,body TEXT)")
        db.execute("INSERT INTO state VALUES(1,?)", (json.dumps(s),))
        for i, (kind, e) in enumerate(events, 1):
            db.execute("INSERT INTO events VALUES(?,?,?,?,?)",
                       (i, str(i), kind, i, json.dumps(e)))
    return dbpath


def test_final_aggregates_partial_once(tmp_path):
    p = make_db(tmp_path)
    r = audit_brain_books(p)
    assert r.eligible
    assert r.opened == r.finalized == 2
    assert r.partial_segments == 1
    assert r.cash_pass and r.partial_segment_pass and r.entry_exit_pairing_pass
    assert r.summed_closed_net == "17"
    assert r.actual_cash == r.implied_cash == "2017"
    assert r.cash_residual == "0"


def test_detect_cash_residual(tmp_path):
    p = make_db(tmp_path, cash=2016)
    r = audit_brain_books(p)
    assert not r.eligible
    assert not r.cash_pass
    assert "BRAIN_CASH_NET_RESIDUAL" in r.issues


def test_detect_double_counting_partial_in_final(tmp_path):
    def tamper(events):
        events[-1][1]["net"] = 10
    p = make_db(tmp_path, mutate=tamper, cash=2020)
    r = audit_brain_books(p)
    assert not r.eligible
    assert not r.partial_segment_pass
    assert "SEGMENT_ACCOUNTING_MISMATCH" in r.issues


def test_reject_orphan_final_or_open(tmp_path):
    def tamper(events):
        events.pop(0)
    p = make_db(tmp_path, mutate=tamper)
    r = audit_brain_books(p)
    assert not r.eligible
    assert "FINAL_WITHOUT_ACTIVE_OPEN" in r.issues


def test_open_position_blocks_flat_cash_claim(tmp_path):
    p = make_db(tmp_path, leave_open=True)
    r = audit_brain_books(p)
    assert not r.eligible
    assert "POSITION_STILL_OPEN" in r.issues


def test_segment_component_mismatch(tmp_path):
    def tamper(events):
        events[3][1]["segment"]["fees"] = 999
    p = make_db(tmp_path, mutate=tamper)
    r = audit_brain_books(p)
    assert not r.eligible
    assert "SEGMENT_ACCOUNTING_MISMATCH" in r.issues
