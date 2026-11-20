"""Script amministrativo di backup cifrato: collaudato DA NON-ROOT su una run sintetica reale del ciclo."""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sqlite3
import stat
import subprocess
import tempfile
from pathlib import Path

import pytest

from backend.v3.events import EventJournal, _digest, _from_row
from backend.v3.runner.test_decision_trace import ScriptAnalyst, _run

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "ops/brain-unico/backup/brain_run_backup_root.py"
spec = importlib.util.spec_from_file_location("brbr", SCRIPT)
BR = importlib.util.module_from_spec(spec)
spec.loader.exec_module(BR)
pytestmark = pytest.mark.skipif(not shutil.which("age"), reason="age non installato")


def _key(d: Path):
    k = d / "owner.key"
    subprocess.run(["age-keygen", "-o", str(k)], check=True, capture_output=True)
    pub = subprocess.run(["age-keygen", "-y", str(k)], check=True, capture_output=True, text=True).stdout
    (d / "recipient.txt").write_text("# chiave pubblica di prova\n" + pub)
    return k, d / "recipient.txt"


def _setup():
    base = Path(tempfile.mkdtemp())
    src = base / "run"
    src.mkdir()
    j = EventJournal(src / "journal.db")
    j.init_schema()
    _run(j, ScriptAnalyst())
    (src / "daily_loss.json").write_text('{"halt_latched": false}')
    (src / ".exit_service.lock").write_text("")
    out = base / "out"
    out.mkdir()
    key, rec = _key(base)
    return base, src, out, key, rec, j


def test_the_script_does_not_import_repository_code():
    import ast
    names = {n.module for n in ast.walk(ast.parse(SCRIPT.read_text())) if isinstance(n, ast.ImportFrom) and n.module}
    names |= {a.name for n in ast.walk(ast.parse(SCRIPT.read_text())) if isinstance(n, ast.Import) for a in n.names}
    assert not any(m.startswith("backend") or m.startswith("ops") for m in names)


def test_its_hash_rule_is_the_journal_rule():
    _, src, *_ = _setup()
    con = sqlite3.connect(src / "journal.db")
    prev = BR.GENESIS
    for row in con.execute("SELECT seq,event_id,portfolio_id,run_id,kind,occurred_at_ms,source,payload_json,"
                           "previous_hash,event_hash FROM v3_events ORDER BY seq"):
        assert BR.digest(prev, row) == _digest(_from_row(row).event, row[7], prev) == row[9]
        prev = row[9]


def test_backup_encrypts_verifies_cleans_up_and_leaves_the_source_intact():
    base, src, out, key, rec, j = _setup()
    before = {p.name: BR.sha256(p) for p in src.iterdir()}
    s = BR.backup(src, out, rec, "brain-run-test")
    assert {p.name: BR.sha256(p) for p in src.iterdir()} == before                  # sorgente intatta
    assert sorted(p.name for p in out.iterdir()) == ["brain-run-test.manifest.json", "brain-run-test.tar.age"]
    rows = sqlite3.connect(src / "journal.db").execute("SELECT COUNT(*) FROM v3_events").fetchone()[0]
    assert s["journal_events"] == rows > 0
    assert set(s["files"]) == {"journal.db", "daily_loss.json"}                       # nessun lock
    assert "encrypted_round_trip_ephemeral_key" in s["verified"]
    assert stat.S_IMODE(os.stat(out / "brain-run-test.tar.age").st_mode) & 0o077 == 0 # non leggibile da altri
    man = (out / "brain-run-test.manifest.json").read_text()
    assert "halt_latched" not in man and "payload" not in man                          # nessun contenuto
    # ripristino dal file cifrato con la chiave del proprietario (qui di prova)
    assert BR.verify(out / "brain-run-test.tar.age", out / "brain-run-test.manifest.json", key)["verified"]


def test_the_ephemeral_key_and_all_plain_copies_are_gone_even_on_failure(monkeypatch):
    base, src, out, key, rec, _ = _setup()
    real = BR.check_copy
    calls = []

    def boom(folder, manifest):
        calls.append(folder)
        if len(calls) == 2:
            raise BR.Fail("simulated")
        return real(folder, manifest)
    monkeypatch.setattr(BR, "check_copy", boom)
    with pytest.raises(BR.Fail):
        BR.backup(src, out, rec, "x")
    assert list(out.iterdir()) == []                                                    # niente chiaro, niente .age


def test_tampered_encrypted_file_or_wrong_key_fail_the_verification():
    base, src, out, key, rec, _ = _setup()
    BR.backup(src, out, rec, "b")
    (base / "o").mkdir()
    other, _ = _key(base / "o")
    with pytest.raises(BR.Fail, match="decryption_failed"):
        BR.verify(out / "b.tar.age", out / "b.manifest.json", other)
    with open(out / "b.tar.age", "ab") as fh:
        fh.write(b"x")
    with pytest.raises(BR.Fail, match="encrypted_file_changed"):
        BR.verify(out / "b.tar.age", out / "b.manifest.json", key)


def test_refusals():
    base, src, out, key, rec, _ = _setup()
    (base / "bad.txt").write_text("ssh-ed25519 AAAA chiave-sbagliata\n")
    with pytest.raises(BR.Fail, match="recipient_file_must_contain_only_age_public_keys"):
        BR.backup(src, out, base / "bad.txt", "b")
    with pytest.raises(BR.Fail, match="out_dir_inside_source"):
        BR.backup(src, src, rec, "b")
    BR.backup(src, out, rec, "b")
    with pytest.raises(BR.Fail, match="destination_exists"):
        BR.backup(src, out, rec, "b")
    con = sqlite3.connect(src / "journal.db")
    con.execute("DROP TRIGGER v3_no_update")
    con.execute("UPDATE v3_events SET source='x' WHERE seq=1")
    con.commit()
    con.close()
    with pytest.raises(BR.Fail, match="journal_hash_chain_invalid"):
        BR.backup(src, out, rec, "c")
    assert sorted(p.name for p in out.iterdir()) == ["b.manifest.json", "b.tar.age"]
