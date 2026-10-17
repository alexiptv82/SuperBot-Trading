#!/usr/bin/env python3
"""Validate an OFFLINE restored SuperBot snapshot. Never access a running source."""
import argparse
import hashlib
import json
import sqlite3
from pathlib import Path


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def validate_json(path):
    with path.open("r", encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError("expected JSON object")


def validate_jsonl(path):
    count = 0
    with path.open("r", encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                raise ValueError(f"blank line at {number}")
            json.loads(line)
            count += 1
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path, help="isolated RESTORED snapshot directory")
    args = parser.parse_args()
    root = args.snapshot.resolve(strict=True)
    if not root.is_dir():
        parser.error("snapshot must be a directory")
    failures = []
    print("OFFLINE RESTORE VALIDATION (no file contents printed)")
    for portfolio in ("hawk", "bull"):
        folder = root / portfolio
        if not folder.is_dir():
            failures.append(f"{portfolio}: missing directory")
            continue
        for filename in ("state_v2.json", "trade_history.jsonl", "learning_log.jsonl"):
            path = folder / filename
            if not path.is_file() or path.is_symlink():
                failures.append(f"{portfolio}/{filename}: missing or symlink")
                continue
            try:
                if filename.endswith(".jsonl"):
                    rows = validate_jsonl(path)
                    print(f"{portfolio}/{filename}: {rows} rows, {path.stat().st_size} bytes, sha256={digest(path)}")
                else:
                    validate_json(path)
                    print(f"{portfolio}/{filename}: valid JSON, {path.stat().st_size} bytes, sha256={digest(path)}")
            except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
                failures.append(f"{portfolio}/{filename}: {type(exc).__name__}")
    database = root / "superbot.db"
    if database.exists():
        try:
            if database.is_symlink():
                raise ValueError("symlink not allowed")
            uri = database.as_uri() + "?mode=ro"
            with sqlite3.connect(uri, uri=True) as connection:
                result = connection.execute("PRAGMA integrity_check").fetchone()[0]
                if result != "ok":
                    raise ValueError("integrity check failed")
            print(f"superbot.db: integrity ok, {database.stat().st_size} bytes, sha256={digest(database)}")
        except (sqlite3.Error, OSError, ValueError) as exc:
            failures.append(f"superbot.db: {type(exc).__name__}")
    else:
        failures.append("superbot.db: missing")
    if failures:
        for failure in failures:
            print("FAIL:", failure)
        raise SystemExit(1)
    print("STRUCTURAL_CHECKS_OK; cross-file consistency and cutover state still require separate verification")


if __name__ == "__main__":
    main()
