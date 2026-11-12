"""Stdlib-only offline tests of RC84 private PAPER snapshot SQLite validation.

Run with: python3 -I deploy/scripts/test_rc84_sqlite_snapshot_isolation.py
No VPS service, position, backup directory, API or key is accessed.
"""
from __future__ import annotations
import hashlib
import importlib.util
from pathlib import Path
import sqlite3
import tempfile
import unittest

SCRIPT = Path(__file__).with_name("rc84-freeze-verify-paper-snapshot-20261112.py")
spec = importlib.util.spec_from_file_location("rc84_snapshot", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def fingerprint(root):
    result = {}
    for file in sorted(root.rglob("*")):
        if file.is_file():
            result[str(file.relative_to(root))] = hashlib.sha256(file.read_bytes()).hexdigest()
    return result


class SqliteSnapshotIsolationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.snapshot = Path(self.tmp.name) / "snapshot"
        brain = self.snapshot / "brain-v3-paper20261111"
        brain.mkdir(parents=True)
        self.connections = []
        for name in ("journal.db", "budget.db"):
            db = brain / name
            conn = sqlite3.connect(db)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("CREATE TABLE example (id INTEGER PRIMARY KEY, value TEXT)")
            conn.execute("INSERT INTO example(value) VALUES ('test')")
            conn.commit()
            # Keep a database connection open so WAL/SHM sidecars remain
            # in the fixture, reproducing the problematic RC84 copy layout.
            self.connections.append(conn)
        self.addCleanup(lambda: [conn.close() for conn in self.connections])

    def test_integrity_preserves_every_byte_and_sidecar(self):
        before = fingerprint(self.snapshot)
        self.assertIn("brain-v3-paper20261111/journal.db-wal", before)
        self.assertIn("brain-v3-paper20261111/budget.db-wal", before)
        module.verify_sqlite_copies(self.snapshot)
        self.assertEqual(before, fingerprint(self.snapshot))
        self.assertEqual([], list(Path(self.tmp.name).glob(".rc84-sqlite-verify-*")))
        # A second verification is deterministic and still does not touch
        # the source snapshot's DB/WAL/SHM.
        module.verify_sqlite_copies(self.snapshot)
        self.assertEqual(before, fingerprint(self.snapshot))

    def test_corrupted_database_rejected_without_changing_snapshot(self):
        # Close the WAL clients, then intentionally corrupt only TEST DATA.
        for conn in self.connections:
            conn.close()
        self.connections.clear()
        bad = self.snapshot / "brain-v3-paper20261111/budget.db"
        bad.write_bytes(b"NOT A SQLITE DATABASE " * 16)
        before = fingerprint(self.snapshot)
        with self.assertRaises(sqlite3.DatabaseError):
            module.verify_sqlite_copies(self.snapshot)
        self.assertEqual(before, fingerprint(self.snapshot))
        self.assertEqual([], list(Path(self.tmp.name).glob(".rc84-sqlite-verify-*")))

    def test_missing_database_fail_closed(self):
        for conn in self.connections:
            conn.close()
        self.connections.clear()
        (self.snapshot / "brain-v3-paper20261111/budget.db").unlink()
        before = fingerprint(self.snapshot)
        with self.assertRaisesRegex(RuntimeError, "essential_brain_database_missing"):
            module.verify_sqlite_copies(self.snapshot)
        self.assertEqual(before, fingerprint(self.snapshot))


if __name__ == "__main__":
    unittest.main(verbosity=2)
