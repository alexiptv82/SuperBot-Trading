"""F0 synthetic Brain backup capture/recovery proof; never uses the VPS."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import sqlite3

import pytest

from v3.backup_certification import (capture_brain_copy, verify_brain_offhost,
                                     observe_brain_source_readonly)
from v3.legacy_audit import audit_brain_snapshot


def brain_fixture(tmp_path, *, wal=False, n=7):
    source = tmp_path / "brain-live-fixture.sqlite3"
    db = sqlite3.connect(source)
    if wal:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA wal_autocheckpoint=0")
    db.execute("CREATE TABLE state(id INTEGER PRIMARY KEY,body TEXT)")
    db.execute("CREATE TABLE events(seq INTEGER PRIMARY KEY,id TEXT,"
               "kind TEXT,ts INTEGER,body TEXT)")
    db.execute("INSERT INTO state VALUES(1,?)", (
        json.dumps({"mode": "paper", "account_id": "brain-free-paper",
                    "cash": 2000, "positions": {}}),))
    for i in range(1, n+1):
        db.execute("INSERT INTO events VALUES(?,?,?,?,?)",
                   (i, "id-"+str(i), "ai_decision", i,
                    json.dumps({"number": i})))
    db.commit()
    return source, db


def witness(root):
    data = json.loads((root / "manifest.json").read_text())
    observation = data["source_observation"]
    from hashlib import sha256
    return {
        "expected_manifest_sha256":
            sha256((root / "manifest.json").read_bytes()).hexdigest(),
        "expected_events_sha256": observation["events_sha256"],
        "expected_event_count": observation["event_count"],
        "expected_max_event_seq": observation["max_event_seq"],
    }


def test_backup_api_includes_committed_wal_and_offhost_restore(tmp_path):
    source, writer = brain_fixture(tmp_path, wal=True, n=7)
    try:
        wal = Path(str(source) + "-wal")
        assert wal.exists() and wal.stat().st_size > 0
        target = tmp_path / "captured"
        receipt = capture_brain_copy(source, target)
        assert receipt.event_count == receipt.max_event_seq == 7
        assert not receipt.externally_certified
        assert audit_brain_snapshot(target / "brain.sqlite3")["events"] == 7
        # Off-host simulated as a physically separate directory: no source DB used.
        offhost = tmp_path / "independent-restore"
        shutil.copytree(target, offhost)
        trusted = witness(target)
        verified = verify_brain_offhost(offhost, **trusted)
        assert verified.externally_certified
        assert verified.event_count == 7
        assert verified.manifest_sha256 == receipt.manifest_sha256
    finally:
        writer.close()


def test_no_overwrite_or_source_mutation(tmp_path):
    source, writer = brain_fixture(tmp_path)
    try:
        before = source.read_bytes()
        target = tmp_path / "capture"
        capture_brain_copy(source, target)
        assert before == source.read_bytes()
        with pytest.raises(ValueError, match="snapshot_directory_must_not_exist"):
            capture_brain_copy(source, target)
        assert target.is_dir() and (target / "manifest.json").is_file()
    finally:
        writer.close()


def test_offhost_verification_rejects_manifest_tampering(tmp_path):
    source, writer = brain_fixture(tmp_path)
    try:
        dst = tmp_path / "capture"
        capture_brain_copy(source, dst)
        expected = witness(dst)
        man = dst / "manifest.json"
        man.write_text(man.read_text() + " ")
        with pytest.raises(ValueError, match="external_manifest_hash_mismatch"):
            verify_brain_offhost(dst, **expected)
    finally:
        writer.close()


def test_offhost_verification_rejects_changed_backup_bytes(tmp_path):
    source, writer = brain_fixture(tmp_path)
    try:
        dst = tmp_path / "capture"
        capture_brain_copy(source, dst)
        expected = witness(dst)
        with (dst / "brain.sqlite3").open("ab") as file:
            file.write(b"\0" * 128)
        with pytest.raises(ValueError, match="snapshot_file_hash_mismatch"):
            verify_brain_offhost(dst, **expected)
    finally:
        writer.close()


def test_external_event_witness_rejects_stale_main_db(tmp_path):
    source, writer = brain_fixture(tmp_path, wal=True, n=7)
    try:
        dst = tmp_path / "capture"
        capture_brain_copy(source, dst)
        expected = witness(dst)
        wrong = dict(expected, expected_event_count=5)
        with pytest.raises(ValueError, match="external_source_witness_mismatch"):
            verify_brain_offhost(dst, **wrong)
        wrong = dict(expected, expected_events_sha256="0" * 64)
        with pytest.raises(ValueError, match="external_source_witness_mismatch"):
            verify_brain_offhost(dst, **wrong)
    finally:
        writer.close()


def test_bad_untrusted_or_missing_witness_is_not_certified(tmp_path):
    source, writer = brain_fixture(tmp_path)
    try:
        dst = tmp_path / "capture"
        receipt = capture_brain_copy(source, dst)
        assert not receipt.externally_certified
        with pytest.raises(TypeError):
            verify_brain_offhost(dst, expected_manifest_sha256=receipt.manifest_sha256)
        with pytest.raises(ValueError, match="invalid_external_witness"):
            verify_brain_offhost(dst,
                expected_manifest_sha256="not-a-hash",
                expected_events_sha256="0"*64,
                expected_event_count=7, expected_max_event_seq=7)
    finally:
        writer.close()


def test_unfinished_capture_not_accepted(tmp_path):
    incomplete = tmp_path / "partial"
    incomplete.mkdir()
    (incomplete / "brain.sqlite3").write_bytes(b"sqlite?")
    with pytest.raises(ValueError, match="missing_or_unsafe_manifest"):
        verify_brain_offhost(incomplete,
            expected_manifest_sha256="a"*64,
            expected_events_sha256="b"*64,
            expected_event_count=1, expected_max_event_seq=1)


def test_non_paper_brain_is_rejected_before_certificate(tmp_path):
    source, writer = brain_fixture(tmp_path)
    try:
        writer.execute("UPDATE state SET body=? WHERE id=1",
            (json.dumps({"mode": "live", "account_id": "live", "positions": {}}),))
        writer.commit()
        with pytest.raises(ValueError, match="brain_not_legacy_paper"):
            capture_brain_copy(source, tmp_path / "no-certificate")
    finally:
        writer.close()


def test_source_side_witness_observes_committed_wal(tmp_path):
    source, writer = brain_fixture(tmp_path, wal=True, n=7)
    try:
        source_observation = observe_brain_source_readonly(source)
        assert source_observation["event_count"] == 7
        assert source_observation["max_event_seq"] == 7
        out = tmp_path / "capture"
        capture_brain_copy(source, out)
        assert source_observation == json.loads(
            (out / "manifest.json").read_text()
        )["source_observation"]
    finally:
        writer.close()


def test_stale_snapshot_rejected_by_separate_original_source_witness(tmp_path):
    original_dir = tmp_path / "original"
    original_dir.mkdir()
    original, writer = brain_fixture(original_dir, wal=True, n=7)
    stale_dir = tmp_path / "stale"
    stale_dir.mkdir()
    stale, other = brain_fixture(stale_dir, wal=False, n=5)
    try:
        independently_recorded = observe_brain_source_readonly(original)
        assert independently_recorded["event_count"] == 7
        output = tmp_path / "wrong-capture"
        capture_brain_copy(stale, output)
        self_manifest_hash = witness(output)["expected_manifest_sha256"]
        # The stale copy has a valid *self*-manifest. It does not match the
        # independently observed original and must fail certification.
        with pytest.raises(ValueError, match="external_source_witness_mismatch"):
            verify_brain_offhost(
                output,
                expected_manifest_sha256=self_manifest_hash,
                expected_event_count=independently_recorded["event_count"],
                expected_max_event_seq=independently_recorded["max_event_seq"],
                expected_events_sha256=independently_recorded["events_sha256"],
            )
    finally:
        writer.close()
        other.close()
