#!/usr/bin/env python3
"""Run ON THE SOURCE HOST by an authorized operator. Creates a non-destructive preliminary snapshot.
Never stops/restarts containers, touches HI-TV, transfers secrets, or claims multi-file consistency.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys

SOURCES = {
    "hawk": Path("/opt/superbot-desk-data/hawk"),
    "bull": Path("/opt/superbot-desk-data/bull"),
}
DATABASE = Path("/opt/superbot/data/superbot.db")
BASE = Path("/opt/superbot-backups")
REQUIRED = ("state_v2.json", "trade_history.jsonl", "learning_log.jsonl")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def validate_json(path: Path) -> None:
    with path.open(encoding="utf-8") as f:
        if not isinstance(json.load(f), dict):
            raise ValueError("state not a JSON object")


def validate_jsonl(path: Path) -> None:
    with path.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                raise ValueError("blank JSONL line")
            json.loads(line)


def main() -> int:
    if os.geteuid() != 0:
        print("STOP: run as root on the old VPS, not on Singapore")
        return 2
    for name, src in SOURCES.items():
        if not src.is_dir() or src.is_symlink():
            print(f"STOP: {name} source missing or symlink")
            return 2
        if any(not (src / f).is_file() for f in REQUIRED):
            print(f"STOP: {name} missing required file")
            return 2
    if not DATABASE.is_file() or DATABASE.is_symlink():
        print("STOP: source SQLite database missing or symlink")
        return 2
    if any(p.is_symlink() for d in SOURCES.values() for p in d.rglob("*")):
        print("STOP: source contains symlinks; manual review required")
        return 2
    total = sum(p.stat().st_size for d in SOURCES.values() for p in d.rglob("*") if p.is_file())
    total += DATABASE.stat().st_size
    if total > 500 * 1024 * 1024:
        print("STOP: data unexpectedly large")
        return 2
    BASE.mkdir(mode=0o700, parents=True, exist_ok=True)
    if shutil.disk_usage(BASE).free < max(512 * 1024 * 1024, total * 4):
        print("STOP: insufficient disk headroom")
        return 2
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = BASE / ("singapore-preliminary-" + stamp + "-" + str(os.getpid()))
    target.mkdir(mode=0o700)
    try:
        for name, src in SOURCES.items():
            shutil.copytree(src, target / name, symlinks=False)
        # SQLite online backup API rather than copying a live database file.
        src_uri = DATABASE.as_uri() + "?mode=ro"
        with sqlite3.connect(src_uri, uri=True, timeout=30) as source:
            with sqlite3.connect(target / "superbot.db") as destination:
                source.backup(destination)
        manifest = {}
        for name in SOURCES:
            for filename in REQUIRED:
                p = target / name / filename
                if filename.endswith(".jsonl"):
                    validate_jsonl(p)
                else:
                    validate_json(p)
        with sqlite3.connect((target / "superbot.db").as_uri() + "?mode=ro", uri=True) as db:
            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("SQLite integrity_check failed")
        for path in sorted(target.rglob("*")):
            if path.is_file():
                manifest[str(path.relative_to(target))] = {"size": path.stat().st_size, "sha256": sha256(path)}
        (target / "manifest.json").write_text(json.dumps({
            "kind": "PRELIMINARY_ONLY_NOT_CUTOVER_READY",
            "created_utc": stamp,
            "files": manifest,
        }, indent=2), encoding="utf-8")
        os.chmod(target / "manifest.json", 0o600)
        print("PRELIMINARY_BACKUP_VALIDATED")
        print("Snapshot:", target)
        print("Files checked:", len(manifest))
        print("NOTE: JSON/JSONL were copied live; cross-file consistency NOT guaranteed")
        return 0
    except Exception as exc:
        print("BACKUP_VALIDATION_FAILED:", type(exc).__name__)
        print("Incomplete snapshot retained for investigation:", target)
        return 1


if __name__ == "__main__":
    sys.exit(main())
