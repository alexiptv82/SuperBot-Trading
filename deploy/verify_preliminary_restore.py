#!/usr/bin/env python3
"""Verify an existing preliminary snapshot through an isolated copy. No source reads."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile

SNAPSHOT = Path("/opt/superbot-backups/singapore-preliminary-20261017T204807Z-szeo75jx")
BASE = Path("/opt/superbot-backups")

def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1048576), b""):
            h.update(chunk)
    return h.hexdigest()

def verify(root):
    manifest_path = root / "manifest.json"
    if manifest_path.is_symlink():
        raise ValueError("manifest symlink")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("kind") != "PRELIMINARY_ONLY_NOT_CUTOVER_READY":
        raise ValueError("unexpected snapshot kind")
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise ValueError("missing manifest entries")
    actual = {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file() and p.name != "manifest.json"}
    if actual != set(files):
        raise ValueError("file list mismatch")
    for relative, info in files.items():
        p = root / relative
        if p.is_symlink() or not p.is_file() or not p.resolve().is_relative_to(root.resolve()):
            raise ValueError("unsafe file")
        if p.stat().st_size != info["size"] or digest(p) != info["sha256"]:
            raise ValueError("checksum mismatch")
    for portfolio in ("hawk", "bull"):
        for name in ("state_v2.json", "trade_history.jsonl", "learning_log.jsonl"):
            p = root / portfolio / name
            if name.endswith(".jsonl"):
                with p.open(encoding="utf-8") as stream:
                    for line in stream:
                        if not line.strip():
                            raise ValueError("empty JSONL row")
                        json.loads(line)
            elif not isinstance(json.loads(p.read_text(encoding="utf-8")), dict):
                raise ValueError("state not object")
    db_path = root / "superbot.db"
    with sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True) as conn:
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("sqlite integrity")
    return len(files)

def main():
    if os.geteuid() != 0 or not SNAPSHOT.is_dir() or SNAPSHOT.is_symlink():
        raise ValueError("invalid host permissions or snapshot")
    if not BASE.is_dir() or BASE.is_symlink():
        raise ValueError("invalid backup base")
    if any(p.is_symlink() for p in SNAPSHOT.rglob("*")):
        raise ValueError("snapshot symlink")
    n = verify(SNAPSHOT)
    size = sum(p.stat().st_size for p in SNAPSHOT.rglob("*") if p.is_file())
    if shutil.disk_usage(BASE).free < max(512 * 1024 * 1024, size * 3):
        raise ValueError("insufficient free space")
    with tempfile.TemporaryDirectory(prefix="singapore-restore-test-", dir=BASE) as temp:
        destination = Path(temp) / "restored"
        shutil.copytree(SNAPSHOT, destination)
        restored_n = verify(destination)
        if restored_n != n:
            raise ValueError("restored file count mismatch")
        print("MANIFEST_SHA256_VERIFIED")
        print("ISOLATED_RESTORE_VERIFIED")
        print("FILES_VERIFIED:", n)
        print("NOTE: preliminary live backup, cross-file consistency not established")
    print("TEMP_RESTORE_CLEANED")

if __name__ == "__main__":
    main()
