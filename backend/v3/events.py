"""Append-only V3 PAPER event journal.

This is an isolated foundation: not connected to any existing wallet or API.
Every event is namespaced by portfolio and run, and has an auditable hash chain.
SQLite triggers deter accidental UPDATE/DELETE; they are not a security boundary
against privileged file owners and do not replace external immutable backups.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Mapping

_ALLOWED_PORTFOLIOS = frozenset(("hawk", "bull", "brain"))
_TOKEN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}$")
_GENESIS = "0" * 64


@dataclass(frozen=True)
class Event:
    event_id: str
    portfolio_id: str
    run_id: str
    kind: str
    occurred_at_ms: int
    source: str
    payload: Mapping[str, Any]


@dataclass(frozen=True)
class StoredEvent:
    seq: int
    event: Event
    previous_hash: str
    event_hash: str


def _validate(event: Event) -> str:
    if event.portfolio_id not in _ALLOWED_PORTFOLIOS:
        raise ValueError("unknown_portfolio")
    for token in (event.event_id, event.run_id, event.kind, event.source):
        if not isinstance(token, str) or not _TOKEN.fullmatch(token):
            raise ValueError("invalid_event_identity")
    if type(event.occurred_at_ms) is not int or event.occurred_at_ms <= 0:
        raise ValueError("invalid_event_time")
    if not isinstance(event.payload, Mapping):
        raise ValueError("invalid_event_payload")
    text = json.dumps(
        event.payload, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False,
    )
    if len(text) > 65536:
        raise ValueError("payload_too_large")
    return text


def _digest(event: Event, payload_json: str, previous_hash: str) -> str:
    fields = [previous_hash, event.event_id, event.portfolio_id,
              event.run_id, event.kind, str(event.occurred_at_ms),
              event.source, payload_json]
    return hashlib.sha256(json.dumps(
        fields, separators=(",", ":"), ensure_ascii=True,
    ).encode("utf-8")).hexdigest()


def _from_row(row: tuple) -> StoredEvent:
    seq, eid, portfolio, run, kind, stamp, source, payload, prev, digest = row
    return StoredEvent(
        seq,
        Event(eid, portfolio, run, kind, stamp, source, json.loads(payload)),
        prev, digest,
    )


class EventConflict(ValueError):
    """The same event_id is being reused for different content."""


class EventJournal:
    """One writer at a time via SQLite BEGIN IMMEDIATE, multiple read-only readers.

    Call init_schema() explicitly before appending. This avoids implicit changes
    when a new, non-writer module merely imports or creates the journal wrapper.
    """

    def __init__(self, filename: str | Path):
        self.filename = Path(filename)

    def _connect(self, *, read_only: bool = False) -> sqlite3.Connection:
        if read_only:
            uri = "file:" + str(self.filename.resolve()) + "?mode=ro"
            db = sqlite3.connect(uri, uri=True, timeout=10)
            db.execute("PRAGMA query_only=ON")
        else:
            db = sqlite3.connect(self.filename, timeout=10, isolation_level=None)
        return db

    def init_schema(self) -> None:
        if not self.filename.parent.is_dir():
            raise FileNotFoundError("journal_parent_missing")
        with self._connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS v3_events(
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                portfolio_id TEXT NOT NULL CHECK (
                    portfolio_id IN ('hawk','bull','brain')),
                run_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                occurred_at_ms INTEGER NOT NULL,
                source TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                previous_hash TEXT NOT NULL,
                event_hash TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS ix_v3_portfolio_run
                ON v3_events(portfolio_id,run_id,seq);
            CREATE TRIGGER IF NOT EXISTS v3_no_update
                BEFORE UPDATE ON v3_events BEGIN
                    SELECT RAISE(ABORT, 'v3_events_immutable');
                END;
            CREATE TRIGGER IF NOT EXISTS v3_no_delete
                BEFORE DELETE ON v3_events BEGIN
                    SELECT RAISE(ABORT, 'v3_events_immutable');
                END;
            """)
            db.execute("PRAGMA user_version=0")

    def append(self, event: Event) -> StoredEvent:
        payload_json = _validate(event)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                existing = db.execute(
                    """SELECT seq,event_id,portfolio_id,run_id,kind,
                              occurred_at_ms,source,payload_json,previous_hash,event_hash
                       FROM v3_events WHERE event_id=?""", (event.event_id,)
                ).fetchone()
                if existing is not None:
                    record = _from_row(existing)
                    exact = (record.event.portfolio_id == event.portfolio_id
                             and record.event.run_id == event.run_id
                             and record.event.kind == event.kind
                             and record.event.occurred_at_ms == event.occurred_at_ms
                             and record.event.source == event.source
                             and existing[7] == payload_json)
                    if not exact:
                        raise EventConflict("event_id_conflict")
                    db.execute("COMMIT")
                    return record

                prior = db.execute(
                    "SELECT event_hash FROM v3_events ORDER BY seq DESC LIMIT 1"
                ).fetchone()
                prev_hash = prior[0] if prior else _GENESIS
                digest = _digest(event, payload_json, prev_hash)
                cur = db.execute(
                    """INSERT INTO v3_events
                       (event_id,portfolio_id,run_id,kind,occurred_at_ms,
                        source,payload_json,previous_hash,event_hash)
                       VALUES(?,?,?,?,?,?,?,?,?)""",
                    (event.event_id, event.portfolio_id, event.run_id,
                     event.kind, event.occurred_at_ms, event.source,
                     payload_json, prev_hash, digest),
                )
                db.execute("COMMIT")
                return StoredEvent(cur.lastrowid, event, prev_hash, digest)
            except BaseException:
                db.execute("ROLLBACK")
                raise

    def list_run(self, portfolio_id: str, run_id: str) -> list[StoredEvent]:
        if portfolio_id not in _ALLOWED_PORTFOLIOS or not _TOKEN.fullmatch(run_id):
            raise ValueError("invalid_run")
        with self._connect(read_only=True) as db:
            return [_from_row(row) for row in db.execute(
                """SELECT seq,event_id,portfolio_id,run_id,kind,
                          occurred_at_ms,source,payload_json,previous_hash,event_hash
                   FROM v3_events WHERE portfolio_id=? AND run_id=?
                   ORDER BY seq""", (portfolio_id, run_id)
            ).fetchall()]

    def verify_chain(self, expected_count: int | None = None,
                     expected_head: str | None = None) -> tuple[int, str]:
        """Verify chain; detect tail truncation only when an external anchor is given."""
        if (expected_count is None) != (expected_head is None):
            raise ValueError("external_manifest_requires_count_and_head")
        with self._connect(read_only=True) as db:
            prev = _GENESIS
            count = 0
            for row in db.execute(
                """SELECT seq,event_id,portfolio_id,run_id,kind,
                          occurred_at_ms,source,payload_json,previous_hash,event_hash
                   FROM v3_events ORDER BY seq"""
            ):
                record = _from_row(row)
                if row[8] != prev or row[9] != _digest(record.event, row[7], prev):
                    raise ValueError("journal_hash_chain_invalid")
                prev = row[9]
                count += 1
            if expected_count is not None and (count != expected_count or prev != expected_head):
                raise ValueError("journal_does_not_match_external_manifest")
            return count, prev
