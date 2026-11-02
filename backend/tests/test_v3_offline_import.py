"""Safety regression tests for offline-only V3 classic history imports."""
import json
import sqlite3

import pytest

from v3.events import Event, EventJournal, EventConflict
from v3.offline_import import import_verified_classic_copy


def _one(ident, stamp, net):
    return {"id": ident, "symbol": "BTC/USDT:USDT", "side": -1,
            "open_ms": stamp - 60000, "close_ms": stamp,
            "net": net, "why": "stop", "fees": 0.2, "funding": 0.0}


def make_snapshot(tmp_path, port="hawk"):
    src = tmp_path / ("snapshot-" + port)
    src.mkdir()
    earlier = _one(1, 1793500000000, -2)
    current = _one(1, 1793600000000, 10)
    state = {"run_no": 8, "main": {
        "cash": 909., "closed": [current],
        "positions": {"ETH": {"id": 3, "symbol": "ETH",
                               "total_margin": 100, "fee_open": 1, "qty": 1}},
        "limits": {"start_equity": 1000},
    }}
    (src / "state_v2.json").write_text(json.dumps(state))
    (src / "trade_history.jsonl").write_text(
        json.dumps(earlier) + "\n" + json.dumps(current) + "\n"
    )
    (src / "learning_log.jsonl").write_text(
        json.dumps({"ev": "close", "run_no": 7, "portfolio": port, **earlier}) + "\n" +
        json.dumps({"ev": "close", "run_no": 8, "portfolio": port, **current}) + "\n"
    )
    return src


def call(workspace, src, port="hawk"):
    return import_verified_classic_copy(
        workspace=workspace, source_copy=src, portfolio_id=port
    )


def test_atomic_import_and_exact_double_run_idempotency(tmp_path):
    snapshot = make_snapshot(tmp_path)
    work = tmp_path / "lab"
    work.mkdir()
    before = {p.name: p.read_bytes() for p in snapshot.iterdir()}
    first = call(work, snapshot)
    assert first.inserted == 2 and first.already_present == 0
    assert first.event_count == 2 and first.run_count == 2
    j = EventJournal(work / "v3-import.sqlite3")
    assert j.verify_chain() == (2, first.chain_head)
    assert len(j.list_run("hawk", "legacy-hawk-7")) == 1
    assert len(j.list_run("hawk", "legacy-hawk-8")) == 1

    again = call(work, snapshot)
    assert again.inserted == 0 and again.already_present == 2
    assert again.chain_head == first.chain_head
    assert again.source_digest == first.source_digest
    assert {p.name: p.read_bytes() for p in snapshot.iterdir()} == before


def test_distinct_portfolios_same_ledger_preserve_global_chain(tmp_path):
    a, b = make_snapshot(tmp_path, "hawk"), make_snapshot(tmp_path, "bull")
    work = tmp_path / "lab"
    work.mkdir()
    call(work, a, "hawk")
    call(work, b, "bull")
    j = EventJournal(work / "v3-import.sqlite3")
    assert j.verify_chain()[0] == 4
    assert len(j.list_run("bull", "legacy-bull-7")) == 1
    assert call(work, a, "hawk").inserted == 0


def test_changed_source_manifest_fails_without_partial_append(tmp_path):
    src = make_snapshot(tmp_path)
    work = tmp_path / "lab"
    work.mkdir()
    first = call(work, src)
    with (src / "learning_log.jsonl").open("a") as f:
        f.write(json.dumps({"ev": "observer_note", "note": "unchanged closes"}) + "\n")
    with pytest.raises(EventConflict, match="import_manifest_mismatch"):
        call(work, src)
    assert EventJournal(work / "v3-import.sqlite3").verify_chain() == (2, first.chain_head)


def test_reconciler_fail_does_not_create_destination(tmp_path):
    src = make_snapshot(tmp_path)
    work = tmp_path / "lab"
    work.mkdir()
    state_path = src / "state_v2.json"
    original = json.loads(state_path.read_text())
    original["main"]["cash"] = 999
    state_path.write_text(json.dumps(original))
    with pytest.raises(ValueError, match="legacy_reconciliation_not_eligible"):
        call(work, src)
    assert not (work / "v3-import.sqlite3").exists()


def test_trigger_failure_rolls_back_entire_batch(tmp_path):
    src = make_snapshot(tmp_path)
    work = tmp_path / "lab"
    work.mkdir()
    dbpath = work / "v3-import.sqlite3"
    j = EventJournal(dbpath)
    j.init_schema()
    with sqlite3.connect(dbpath) as db:
        db.execute("""
            CREATE TRIGGER test_reject_second
            BEFORE INSERT ON v3_events
            WHEN NEW.event_id LIKE '%.closed.2'
            BEGIN SELECT RAISE(ABORT, 'forced_insert_error'); END
        """)
    with pytest.raises(sqlite3.IntegrityError, match="forced_insert_error"):
        call(work, src)
    assert j.verify_chain()[0] == 0
    with sqlite3.connect(dbpath) as db:
        assert db.execute(
            "SELECT COUNT(*) FROM v3_import_manifest"
        ).fetchone()[0] == 0 if db.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE name='v3_import_manifest'"
        ).fetchone()[0] else True
        db.execute("DROP TRIGGER test_reject_second")
    assert call(work, src).inserted == 2
    assert j.verify_chain()[0] == 2


def test_preexisting_matching_id_without_manifest_is_not_silently_adopted(tmp_path):
    src = make_snapshot(tmp_path)
    work = tmp_path / "lab"
    work.mkdir()
    j = EventJournal(work / "v3-import.sqlite3")
    j.init_schema()
    j.append(Event(
        "legacy.hawk.7.closed.1", "hawk", "legacy-hawk-7",
        "legacy_trade_closed", 1793500000000, "legacy_paper_history",
        {"origin": "unaudited_import"}
    ))
    before = j.verify_chain()
    with pytest.raises(EventConflict, match="preexisting_event_without_manifest"):
        call(work, src)
    assert j.verify_chain() == before


def test_tampered_chain_blocks_new_import(tmp_path):
    src = make_snapshot(tmp_path)
    work = tmp_path / "lab"
    work.mkdir()
    call(work, src)
    dbpath = work / "v3-import.sqlite3"
    with sqlite3.connect(dbpath) as db:
        db.execute("DROP TRIGGER v3_no_update")
        db.execute("UPDATE v3_events SET kind='fabricated' WHERE seq=1")
    with pytest.raises(ValueError, match="v3_journal_chain_invalid"):
        call(work, src)


def test_workspace_or_source_alias_and_brain_are_blocked(tmp_path):
    src = make_snapshot(tmp_path)
    work = tmp_path / "lab"
    work.mkdir()
    with pytest.raises(ValueError, match="workspace_and_source_must_be_separate"):
        call(src, src)
    with pytest.raises(ValueError, match="brain_import_not_supported"):
        call(work, src, "brain")
    with pytest.raises(ValueError, match="invalid_journal_name"):
        import_verified_classic_copy(
            workspace=work, source_copy=src, portfolio_id="hawk",
            journal_name="../legacy.sqlite3"
        )
