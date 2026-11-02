"""V3 legacy forensic audit: all synthetic, no production VPS/files."""
import hashlib
import json
import sqlite3

import pytest

from v3.legacy_audit import (
    audit_brain_snapshot,
    audit_classic_snapshot,
    plan_classic_closed_events,
)


def close(ident=1, *, net=2.5, stamp=1793631000000, partial=False):
    return {
        "id": ident, "symbol": "ADA/USDT:USDT", "side": -1,
        "close_ms": stamp, "net": net, "open_ms": stamp - 300000,
        "partial": partial, "why": "TP parziale" if partial else "time",
    }


def write_jsonl(path, rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def fixture_classic(tmp_path, *, state_rows=None, history_rows=None,
                    learning_rows=None, open_count=1):
    root = tmp_path / "hawk"
    root.mkdir()
    history = history_rows if history_rows is not None else [close()]
    state = state_rows if state_rows is not None else history
    learning = learning_rows if learning_rows is not None else [
        {"ev": "close", "run_no": 8, "id": x["id"], "net": x["net"]} for x in history
    ]
    (root / "state_v2.json").write_text(json.dumps({
        "run_no": 8, "main": {
            "closed": state,
            "positions": {f"pos-{n}": {"symbol": "SUI"} for n in range(open_count)},
        },
    }))
    write_jsonl(root / "trade_history.jsonl", history)
    write_jsonl(root / "learning_log.jsonl", learning)
    return root


def test_matching_state_and_log_produce_single_event(tmp_path):
    root = fixture_classic(tmp_path)
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir()}
    report = audit_classic_snapshot(root, "hawk")
    assert report.eligible
    assert (report.state_closed, report.history_closed, report.learning_closed) == (1, 1, 1)
    assert report.open_positions == 1
    assert report.history_net == "2.5"
    assert report.legacy_run_id == "legacy-hawk-8"
    assert len(report.files_sha256) == 3
    after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir()}
    assert after == before
    assert not any(x.suffix in (".sqlite3", ".db") for x in root.iterdir())


def test_partial_and_final_same_position_stay_separate(tmp_path):
    rows = [close(net=2, partial=True), close(net=-0.5, stamp=1793631600000)]
    root = fixture_classic(tmp_path, history_rows=rows)
    report = audit_classic_snapshot(root, "hawk")
    assert report.eligible
    assert report.history_closed == 2
    assert report.history_net == "1.5"


def test_reconciliation_refuses_missing_close_and_wrong_net(tmp_path):
    root = fixture_classic(tmp_path, state_rows=[close(net=3)])
    report = audit_classic_snapshot(root, "hawk")
    assert not report.eligible
    assert "CLOSED_ROW_MISMATCH" in report.issues
    assert "CLOSED_NET_MISMATCH" in report.issues



def test_learning_coverage_gap_explicitly_blocks(tmp_path):
    root = fixture_classic(tmp_path, learning_rows=[])
    report = audit_classic_snapshot(root, "hawk")
    assert report.state_closed == report.history_closed == 1
    assert "LEARNING_COVERAGE_GAP" in report.issues
    assert not report.eligible



def test_duplicated_jsonl_record_detected(tmp_path):
    row = close()
    root = fixture_classic(tmp_path, state_rows=[row, row],
                           history_rows=[row, row])
    report = audit_classic_snapshot(root, "hawk")
    assert "DUPLICATE_HISTORY_ROW" in report.issues



def test_invalid_json_line_refuses_import(tmp_path):
    root = fixture_classic(tmp_path)
    with (root / "trade_history.jsonl").open("a") as f:
        f.write("{ incomplete\n")
    with pytest.raises(json.JSONDecodeError):
        audit_classic_snapshot(root, "hawk")


def test_no_legacy_write_when_missing_file_or_symlink(tmp_path):
    root = fixture_classic(tmp_path)
    original = (root / "trade_history.jsonl").read_bytes()
    (root / "learning_log.jsonl").unlink()
    with pytest.raises(ValueError, match="missing_or_symlink_source"):
        audit_classic_snapshot(root, "hawk")
    (root / "learning_log.jsonl").symlink_to(root / "trade_history.jsonl")
    with pytest.raises(ValueError, match="missing_or_symlink_source"):
        audit_classic_snapshot(root, "hawk")
    assert (root / "trade_history.jsonl").read_bytes() == original


def test_old_run_learning_rows_ignored(tmp_path):
    learning = [
        {"ev": "close", "run_no": 7, "id": 4, "net": -3},
        {"ev": "close", "run_no": 8, "id": 1, "net": 2.5},
    ]
    root = fixture_classic(tmp_path, learning_rows=learning)
    report = audit_classic_snapshot(root, "hawk")
    assert report.eligible
    assert report.learning_closed == 1


def test_wrong_portfolio_and_missing_state_fail_closed(tmp_path):
    root = fixture_classic(tmp_path)
    with pytest.raises(ValueError, match="unsupported_portfolio"):
        audit_classic_snapshot(root, "brain")
    (root / "state_v2.json").unlink()
    with pytest.raises(ValueError, match="missing_or_symlink_source"):
        audit_classic_snapshot(root, "hawk")


def test_brain_read_only_audit_no_pnl_invented(tmp_path):
    path = tmp_path / "brain.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE state(id INTEGER PRIMARY KEY,body TEXT)")
        db.execute("CREATE TABLE events(seq INTEGER PRIMARY KEY,id TEXT,kind TEXT,ts INTEGER,body TEXT)")
        db.execute("INSERT INTO state VALUES(1,?)", (
            json.dumps({"mode": "paper", "account_id": "brain-free-paper",
                        "positions": {"BTC": {"side": 1}}}),))
        db.execute("INSERT INTO events VALUES(1, 'evt1', 'trade_closed', 1, '{}')")
        db.execute("INSERT INTO events VALUES(2, 'evt2', 'ai_decision', 2, '{}')")
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    report = audit_brain_snapshot(path)
    assert report["events"] == 2
    assert report["trade_closed_events"] == 1
    assert report["open_positions"] == 1
    assert report["import_eligible"] is False
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_brain_foreign_account_refused(tmp_path):
    path = tmp_path / "brain.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE state(id INTEGER PRIMARY KEY,body TEXT)")
        db.execute("CREATE TABLE events(seq INTEGER PRIMARY KEY,id TEXT,kind TEXT,ts INTEGER,body TEXT)")
        db.execute("INSERT INTO state VALUES(1,?)", (
            json.dumps({"mode": "live", "account_id": "live", "positions": {}}),))
    with pytest.raises(ValueError, match="foreign_brain_account"):
        audit_brain_snapshot(path)


def test_archived_run_explicit_shared_learning_log(tmp_path):
    root = fixture_classic(tmp_path)
    archived = tmp_path / "archive-8"
    archived.mkdir()
    for filename in ("state_v2.json", "trade_history.jsonl"):
        (archived / filename).write_bytes((root / filename).read_bytes())
    # The legacy archiver did not put learning_log.jsonl inside archive/.
    with pytest.raises(ValueError, match="missing_or_symlink_source"):
        audit_classic_snapshot(archived, "hawk")
    report = audit_classic_snapshot(
        archived, "hawk", learning_path=root / "learning_log.jsonl"
    )
    assert report.eligible
    assert report.history_closed == 1
    assert report.legacy_run_id == "legacy-hawk-8"
    assert report.legacy_run_id == "legacy-hawk-8"


def test_superseded_single_run_planner_is_disabled(tmp_path):
    root = fixture_classic(tmp_path)
    with pytest.raises(NotImplementedError, match="superseded_by_plan_classic_multirun_events"):
        plan_classic_closed_events(root, "hawk")
