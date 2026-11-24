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


def test_reframe_reuses_id_across_epochs_without_double_count(tmp_path):
    """Position id can restart at one in V2 without representing old V1 trade."""
    p = tmp_path / "brain.sqlite3"
    with sqlite3.connect(p) as db:
        db.execute("CREATE TABLE state(id INTEGER PRIMARY KEY,body TEXT)")
        db.execute("CREATE TABLE events(seq INTEGER PRIMARY KEY,id TEXT,kind TEXT,ts INTEGER,body TEXT)")
        db.execute("INSERT INTO state VALUES(1,?)", (
            json.dumps({"mode":"paper","account_id":"brain-free-paper",
                        "cash":2013,"positions":{},"v2_start_equity":2005}),))
        ev = [
            ("open", {"kind":"open","symbol":"BTC","position_id":1}),
            ("trade_closed", {"kind":"trade_closed","symbol":"BTC","position_id":1,
                              "net":5,"segment":{"net":5,"gross":6,"fees":1,"funding":0}}),
            ("experiment_reframed", {"old_state":{"cash":2005,"positions":{}},
                                    "old_cash":2005,"new_cash":2005}),
            ("open", {"kind":"open","symbol":"BTC","position_id":1}),
            ("trade_closed", {"kind":"trade_closed","symbol":"BTC","position_id":1,
                              "net":8,"segment":{"net":8,"gross":9,"fees":1,"funding":0}}),
        ]
        for idx,(kind,body) in enumerate(ev,1):
            db.execute("INSERT INTO events VALUES(?,?,?,?,?)",
                       (idx,str(idx),kind,idx,json.dumps(body)))
    report = audit_brain_books(p)
    assert report.eligible, report.issues
    assert report.opened == report.finalized == 2
    assert report.summed_closed_net == "13"
    assert report.cash_pass


def test_reframe_fake_topup_is_blocked(tmp_path):
    p = tmp_path / "brain.sqlite3"
    with sqlite3.connect(p) as db:
        db.execute("CREATE TABLE state(id INTEGER PRIMARY KEY,body TEXT)")
        db.execute("CREATE TABLE events(seq INTEGER PRIMARY KEY,id TEXT,kind TEXT,ts INTEGER,body TEXT)")
        db.execute("INSERT INTO state VALUES(1,?)", (
            json.dumps({"mode":"paper","account_id":"brain-free-paper",
                        "cash":2100,"positions":{},"v2_start_equity":2100}),))
        db.execute("INSERT INTO events VALUES(1,'1','experiment_reframed',1,?)",
                   (json.dumps({"old_state":{"cash":2000,"positions":{}},
                                "old_cash":2000,"new_cash":2100}),))
    report = audit_brain_books(p)
    assert not report.eligible
    assert "REFRAME_NOT_CASH_NEUTRAL" in report.issues


def test_p1_4_reject_reversed_brain_event_time(tmp_path):
    p = make_db(tmp_path)
    with sqlite3.connect(p) as db:
        db.execute("UPDATE events SET ts=1 WHERE seq=5")
    report = audit_brain_books(p)
    assert not report.eligible
    assert "EPOCH_TIME_ORDER" in report.issues


def test_p1_5_reject_multiple_experiment_started(tmp_path):
    p = make_db(tmp_path)
    with sqlite3.connect(p) as db:
        for n in (6, 7):
            db.execute("INSERT INTO events VALUES(?,?,?,?,?)",
                       (n, str(n), "experiment_started", n,
                        json.dumps({"experiment_id": "test-" + str(n)})))
    report = audit_brain_books(p)
    assert not report.eligible
    assert "MULTIPLE_EXPERIMENT_START" in report.issues
