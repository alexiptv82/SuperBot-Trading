"""Backup a caldo e prova di ripristino della cartella dati del Brain Unico, su una run REALE del ciclo (sintetica)."""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from pathlib import Path

import pytest

from backend.tests.test_v3_runner_cycle import RUN, _events
from backend.v3.events import EventJournal
from backend.v3.runner import run_backup as RB
from backend.v3.runner.test_decision_trace import ScriptAnalyst, _run


def _run_dir():
    d = Path(tempfile.mkdtemp()) / "brain"
    d.mkdir()
    j = EventJournal(d / "journal.db")
    j.init_schema()
    _run(j, ScriptAnalyst())
    _run(j, ScriptAnalyst(kind="NO_TRADE"), symbols=("CCCUSDT",))
    (d / "daily_loss.json").write_text(json.dumps({"version": 2, "halt_latched": False}))
    (d / "mandate.json").write_text("{}")
    (d / ".exit_service.lock").write_text("")
    return d, j


def test_backup_and_restore_preserve_the_whole_memory():
    src, j = _run_dir()
    before = (src / "journal.db").read_bytes()
    out = Path(tempfile.mkdtemp())
    m = RB.backup(src, out / "b")
    assert m["journal_events"] == len(j.list_run("brain", RUN)) and len(m["journal_head"]) == 64
    assert set(m["files"]) == {"journal.db", "daily_loss.json", "mandate.json"}           # nessun lock
    assert (src / "journal.db").read_bytes() == before                                      # sorgente intatta
    r = RB.verify_restore(out / "b", out / "r")
    assert r["restored"] and r["journal_events"] == m["journal_events"]
    restored = EventJournal(out / "r" / "journal.db")
    assert [e.event_id for e in _events(restored, "brain_decision")] == [e.event_id for e in _events(j, "brain_decision")]


def test_hot_backup_while_the_journal_keeps_growing():
    src, j = _run_dir()
    out = Path(tempfile.mkdtemp())
    m1 = RB.backup(src, out / "b1")
    _run(j, ScriptAnalyst(kind="NO_TRADE"), symbols=("DDDUSDT",))                          # la run continua
    m2 = RB.backup(src, out / "b2")
    assert m2["journal_events"] > m1["journal_events"]
    assert RB.verify_restore(out / "b1", out / "r1")["journal_events"] == m1["journal_events"]


def test_a_tampered_backup_fails_the_restore():
    src, _ = _run_dir()
    out = Path(tempfile.mkdtemp())
    RB.backup(src, out / "b")
    with open(out / "b" / "daily_loss.json", "a") as fh:
        fh.write(" ")
    with pytest.raises(RB.BackupError, match="hash_mismatch"):
        RB.verify_restore(out / "b", out / "r")


def test_a_truncated_journal_with_a_rewritten_manifest_is_detected():
    src, _ = _run_dir()
    out = Path(tempfile.mkdtemp())
    m = RB.backup(src, out / "b")
    con = sqlite3.connect(out / "b" / "journal.db")
    con.execute("DROP TRIGGER v3_no_delete")
    con.execute("DELETE FROM v3_events WHERE seq=(SELECT MAX(seq) FROM v3_events)")
    con.commit()
    con.close()
    man = json.loads((out / "b" / RB.MANIFEST).read_text())
    man["files"]["journal.db"] = RB._sha(out / "b" / "journal.db")                       # impronta ricalcolata
    (out / "b" / RB.MANIFEST).write_text(json.dumps(man))
    with pytest.raises(RB.BackupError, match="journal_restore_mismatch"):                 # conteggio/testa non tornano
        RB.verify_restore(out / "b", out / "r")


def test_never_overwrite_and_never_inside_the_source():
    src, _ = _run_dir()
    out = Path(tempfile.mkdtemp())
    RB.backup(src, out / "b")
    with pytest.raises(RB.BackupError, match="destination_exists"):
        RB.backup(src, out / "b")
    with pytest.raises(RB.BackupError, match="destination_inside_source"):
        RB.backup(src, src / "bk")
    with pytest.raises(RB.BackupError, match="journal_missing"):
        RB.backup(out, out / "x")


def test_unlisted_files_in_a_backup_are_refused():
    src, _ = _run_dir()
    out = Path(tempfile.mkdtemp())
    RB.backup(src, out / "b")
    (out / "b" / "intruso.json").write_text("{}")
    with pytest.raises(RB.BackupError, match="unlisted_files_in_backup"):
        RB.verify_restore(out / "b", out / "r")


def test_cli_reports_go_and_no_go(capsys):
    src, _ = _run_dir()
    out = Path(tempfile.mkdtemp())
    assert RB.main(["--source", str(src), "--dest", str(out / "b"), "--restore-test", str(out / "r")]) == 0
    assert "RIPRISTINO VERIFICATO" in capsys.readouterr().out
    assert RB.main(["--source", str(src), "--dest", str(out / "b")]) == 1


@pytest.mark.skipif(not __import__("shutil").which("age"), reason="age non installato")
def test_encrypted_backup_round_trip_with_a_test_key():
    import subprocess
    src, _ = _run_dir()
    out = Path(tempfile.mkdtemp())
    RB.backup(src, out / "b")
    key = out / "test.key"                                              # chiave di PROVA, mai quella del proprietario
    subprocess.run(["age-keygen", "-o", str(key)], check=True, capture_output=True)
    pub = subprocess.run(["age-keygen", "-y", str(key)], check=True, capture_output=True, text=True).stdout
    (out / "recipient.txt").write_text(pub)
    sha = RB.encrypt(out / "b", out / "b.tar.age", out / "recipient.txt")
    assert len(sha) == 64 and b"journal" not in (out / "b.tar.age").read_bytes()[:4096]   # nessun nome in chiaro
    (out / "x").mkdir()
    dec = subprocess.run(["age", "-d", "-i", str(key), str(out / "b.tar.age")], check=True, capture_output=True).stdout
    subprocess.run(["tar", "-C", str(out / "x"), "-xf", "-"], input=dec, check=True)
    assert RB.verify_restore(out / "x" / "b", out / "r")["restored"]
    with pytest.raises(RB.BackupError, match="destination_exists"):
        RB.encrypt(out / "b", out / "b.tar.age", out / "recipient.txt")
