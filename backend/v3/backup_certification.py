"""F0 laboratory-only SQLite backup certification for historical Brain PAPER.

Nothing in this module connects to a VPS, SSH, exchange or active trading bot.
Capture only from a stopped/offline source with appropriate OS permissions.
A consistent SQLite backup includes committed WAL content. A copy alone is
NOT proof that an earlier raw file omitted no WAL; trustworthy capture-time
evidence and an independently retained witness remain separate gates.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sqlite3

from .legacy_audit import open_frozen_sqlite

_VERSION = "superbot-v3-f0-brain-snapshot-v1"
_HEX256 = re.compile(r"[a-f0-9]{64}\Z")


@dataclass(frozen=True)
class BackupReceipt:
    snapshot_directory: str
    event_count: int
    max_event_seq: int
    manifest_sha256: str
    externally_certified: bool = False


def _hash_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for piece in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(piece)
    return digest.hexdigest()


def _inspect(db: sqlite3.Connection) -> dict:
    if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise ValueError("brain_integrity_failed")
    result = db.execute("SELECT body FROM state WHERE id=1").fetchone()
    if result is None or not isinstance(result[0], str):
        raise ValueError("brain_state_missing")
    state = json.loads(result[0])
    if (not isinstance(state, dict) or state.get("mode") != "paper"
            or state.get("account_id") != "brain-free-paper"
            or not isinstance(state.get("positions"), dict)):
        raise ValueError("brain_not_legacy_paper")
    stream = sha256()
    count = 0
    last_seq = 0
    for row in db.execute("SELECT seq,id,kind,ts,body FROM events ORDER BY seq"):
        seq, eid, kind, ts, body = row
        if (type(seq) is not int or seq <= last_seq
                or not isinstance(eid, str) or not eid
                or not isinstance(kind, str) or not kind
                or type(ts) is not int or not isinstance(body, str)):
            raise ValueError("invalid_brain_event_stream")
        encoded = json.dumps(row, ensure_ascii=True, allow_nan=False,
                             separators=(",", ":")).encode("utf-8")
        stream.update(len(encoded).to_bytes(8, "big"))
        stream.update(encoded)
        count += 1
        last_seq = seq
    return {
        "event_count": count,
        "max_event_seq": last_seq,
        "events_sha256": stream.hexdigest(),
        "state_sha256": sha256(result[0].encode("utf-8")).hexdigest(),
    }


def _check_source(source: Path, target: Path) -> None:
    if source.is_symlink() or not source.is_file():
        raise ValueError("source_db_missing_or_symlink")
    if target.exists() or target.is_symlink():
        raise ValueError("snapshot_directory_must_not_exist")
    if target.parent.is_symlink() or not target.parent.is_dir():
        raise ValueError("snapshot_parent_missing_or_symlink")
    if source.resolve() == target.resolve():
        raise ValueError("source_equals_destination")


def observe_brain_source_readonly(source_db: str | Path) -> dict:
    """Produce source-side witness fields without backing up or writing.

    Run separately while the original source is stopped; preserve the result
    outside the backup and independently of the destination copy. This uses
    normal read-only SQLite semantics so committed WAL entries are included.
    """
    source = Path(source_db)
    if source.is_symlink() or not source.is_file():
        raise ValueError("source_db_missing_or_symlink")
    with sqlite3.connect(source.resolve().as_uri() + "?mode=ro",
                         uri=True, timeout=10) as db:
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        observed = _inspect(db)
        db.execute("COMMIT")
        return observed


def capture_brain_copy(source_db: str | Path,
                       snapshot_directory: str | Path) -> BackupReceipt:
    """Create a new local consistent SQLite backup, with manifest-last marker.

    PRECONDITION: source is an already stopped/captured PAPER Brain database.
    Source opens via mode=ro (NOT immutable), so committed WAL changes are
    visible. No source-side checkpoint or cleanup is attempted. If anything
    fails, output remains untrusted without an independently verified manifest.
    """
    source = Path(source_db)
    target = Path(snapshot_directory)
    _check_source(source, target)
    target.mkdir(mode=0o700)  # exclusive; never replace an old backup
    db_copy = target / "brain.sqlite3"
    with sqlite3.connect(source.resolve().as_uri() + "?mode=ro",
                         uri=True, timeout=10) as src:
        src.execute("PRAGMA query_only=ON")
        src.execute("BEGIN")
        observed = _inspect(src)
        with sqlite3.connect(db_copy) as dest:
            src.backup(dest)
        src.execute("COMMIT")
        after = _inspect(src)
    # Detect changes between the beginning and end of capture.
    if observed != after:
        raise ValueError("source_changed_during_capture")
    with open_frozen_sqlite(db_copy) as copied:
        checked = _inspect(copied)
    if observed != checked:
        raise ValueError("sqlite_backup_snapshot_mismatch")
    # fsync the completed backup before publishing its manifest.
    with db_copy.open("rb") as file:
        os.fsync(file.fileno())
    db_hash = _hash_file(db_copy)
    manifest = {
        "schema": _VERSION,
        "capture_method": "sqlite3.Connection.backup_from_read_only_source",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source_observation": observed,
        "snapshot_observation": checked,
        "snapshot_db_sha256": db_hash,
        "no_offhost_attestation_implied": True,
    }
    manifest_bytes = (json.dumps(manifest, sort_keys=True,
                                 separators=(",", ":"), ensure_ascii=True)
                      + "\n").encode("utf-8")
    with (target / ".manifest.incomplete").open("xb") as stream:
        stream.write(manifest_bytes)
        stream.flush()
        os.fsync(stream.fileno())
    (target / ".manifest.incomplete").replace(target / "manifest.json")
    dirfd = os.open(target, os.O_RDONLY)
    try:
        os.fsync(dirfd)
    finally:
        os.close(dirfd)
    return BackupReceipt(str(target), observed["event_count"],
                         observed["max_event_seq"], sha256(manifest_bytes).hexdigest())


def verify_brain_offhost(snapshot_directory: str | Path, *,
                         expected_manifest_sha256: str,
                         expected_events_sha256: str,
                         expected_event_count: int,
                         expected_max_event_seq: int) -> BackupReceipt:
    """Verify an offline restored copy against separately preserved evidence.

    Four expected values MUST come from a trusted, independently retained
    capture-time witness. Matching this function does not itself attest
    that the witness was obtained from the correct original server.
    """
    root = Path(snapshot_directory)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("invalid_snapshot_directory")
    if (not isinstance(expected_manifest_sha256, str)
            or not _HEX256.fullmatch(expected_manifest_sha256)
            or not isinstance(expected_events_sha256, str)
            or not _HEX256.fullmatch(expected_events_sha256)
            or type(expected_event_count) is not int or expected_event_count < 1
            or type(expected_max_event_seq) is not int
            or expected_max_event_seq < expected_event_count):
        raise ValueError("invalid_external_witness")
    manifest_path = root / "manifest.json"
    dbpath = root / "brain.sqlite3"
    if (manifest_path.is_symlink() or not manifest_path.is_file()
            or manifest_path.stat().st_size > 64 * 1024):
        raise ValueError("missing_or_unsafe_manifest")
    raw = manifest_path.read_bytes()
    if sha256(raw).hexdigest() != expected_manifest_sha256:
        raise ValueError("external_manifest_hash_mismatch")
    manifest = json.loads(raw.decode("utf-8"))
    if (not isinstance(manifest, dict)
            or manifest.get("schema") != _VERSION
            or manifest.get("capture_method") != "sqlite3.Connection.backup_from_read_only_source"):
        raise ValueError("invalid_manifest_schema")
    with open_frozen_sqlite(dbpath) as restored:
        measurement = _inspect(restored)
    if _hash_file(dbpath) != manifest.get("snapshot_db_sha256"):
        raise ValueError("snapshot_file_hash_mismatch")
    if (measurement != manifest.get("source_observation")
            or measurement != manifest.get("snapshot_observation")):
        raise ValueError("snapshot_measurement_mismatch")
    if (measurement["events_sha256"] != expected_events_sha256
            or measurement["event_count"] != expected_event_count
            or measurement["max_event_seq"] != expected_max_event_seq):
        raise ValueError("external_source_witness_mismatch")
    return BackupReceipt(str(root), measurement["event_count"],
                         measurement["max_event_seq"], expected_manifest_sha256,
                         externally_certified=True)
