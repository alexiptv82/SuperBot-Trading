"""Tests for the isolated V3 immutable event journal; no VPS or legacy state."""
import sqlite3
import pytest

from v3.events import Event, EventConflict, EventJournal


def event(eid="a1", *, portfolio="hawk", run="run-20261102",
          kind="trade_closed", stamp=1793631000000, payload=None):
    return Event(
        eid, portfolio, run, kind, stamp, "paper_engine",
        payload if payload is not None else {"pnl": "-7.25", "reason": "stop"},
    )


def test_empty_ledger_and_replay(tmp_path):
    journal = EventJournal(tmp_path / "events.sqlite3")
    journal.init_schema()
    assert journal.verify_chain() == (0, "0" * 64)
    assert journal.list_run("hawk", "run-20261102") == []
    first = journal.append(event())
    assert first.seq == 1
    assert first.previous_hash == "0" * 64
    assert len(first.event_hash) == 64
    second = journal.append(event("b2", portfolio="bull",
                                  run="run-20261102",
                                  kind="candidate_skipped",
                                  payload={"why": "no_edge"}))
    assert second.previous_hash == first.event_hash
    assert journal.list_run("hawk", "run-20261102") == [first]
    assert journal.list_run("bull", "run-20261102") == [second]
    assert journal.verify_chain() == (2, second.event_hash)


def test_idempotent_retries_and_collision(tmp_path):
    j = EventJournal(tmp_path / "journal.db")
    j.init_schema()
    first = j.append(event())
    assert j.append(event()) == first
    assert j.verify_chain()[0] == 1
    with pytest.raises(EventConflict):
        j.append(event(payload={"pnl": "100", "reason": "manual"}))
    assert j.verify_chain()[0] == 1


def test_run_namespace_does_not_erase_history(tmp_path):
    j = EventJournal(tmp_path / "journal.db")
    j.init_schema()
    old = j.append(event("old", run="legacy-08"))
    new = j.append(event("new", run="v3-01"))
    assert [x.seq for x in j.list_run("hawk", "legacy-08")] == [old.seq]
    assert [x.seq for x in j.list_run("hawk", "v3-01")] == [new.seq]
    assert j.verify_chain()[0] == 2


def test_triggers_block_update_and_delete(tmp_path):
    path = tmp_path / "events.db"
    j = EventJournal(path)
    j.init_schema()
    j.append(event())
    with sqlite3.connect(path) as conn:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            conn.execute("UPDATE v3_events SET kind='bad' WHERE seq=1")
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            conn.execute("DELETE FROM v3_events WHERE seq=1")
    assert j.verify_chain()[0] == 1


def test_hash_chain_detects_tampering_even_if_trigger_removed(tmp_path):
    path = tmp_path / "events.db"
    j = EventJournal(path)
    j.init_schema()
    j.append(event())
    j.append(event("b2", portfolio="brain"))
    with sqlite3.connect(path) as conn:
        conn.execute("DROP TRIGGER v3_no_update")
        conn.execute("UPDATE v3_events SET payload_json='{}' WHERE seq=1")
    with pytest.raises(ValueError, match="journal_hash_chain_invalid"):
        j.verify_chain()


def test_reject_invalid_payloads_and_identity(tmp_path):
    j = EventJournal(tmp_path / "j.db")
    j.init_schema()
    for invalid in (
        event(portfolio="unknown"),
        event(run="../bad"),
        event(stamp=0),
        event(payload={"bad": float("nan")}),
        event(payload={"bad": object()}),
    ):
        with pytest.raises((ValueError, TypeError)):
            j.append(invalid)
    assert j.verify_chain()[0] == 0


def test_does_not_create_legacy_files(tmp_path):
    legacy = tmp_path / "hawk"
    legacy.mkdir()
    original = legacy / "learning_log.jsonl"
    original.write_text('{"unchanged":true}\n')
    j = EventJournal(tmp_path / "v3" / "db.sqlite3")
    with pytest.raises(FileNotFoundError):
        j.init_schema()
    assert original.read_text() == '{"unchanged":true}\n'
    assert not (tmp_path / "v3").exists()


def test_external_anchor_detects_truncated_journal_tail(tmp_path):
    path = tmp_path / "v3.sqlite3"
    j = EventJournal(path)
    j.init_schema()
    j.append(event("a1"))
    j.append(event("b2"))
    anchor = j.verify_chain()
    with sqlite3.connect(path) as db:
        db.execute("DROP TRIGGER v3_no_delete")
        db.execute("DELETE FROM v3_events WHERE seq=(SELECT MAX(seq) FROM v3_events)")
    # The remaining hash chain is internally consistent after tail deletion;
    # only a separately retained (count, head) attests to completeness.
    assert j.verify_chain()[0] == 1
    with pytest.raises(ValueError, match="journal_does_not_match_external_manifest"):
        j.verify_chain(expected_count=anchor[0], expected_head=anchor[1])
    with pytest.raises(ValueError, match="external_manifest_requires_count_and_head"):
        j.verify_chain(expected_count=anchor[0])
