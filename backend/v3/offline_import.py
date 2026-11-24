"""Atomic, idempotent OFFLINE import of verified classic PAPER closes into V3.

Strictly a test-laboratory function, NOT a runtime endpoint or migration CLI.
Requires a caller-supplied workspace, a frozen SOURCE COPY outside that
workspace, and a NEW/previously initialized V3 journal in that workspace.
Never edits the classic snapshot. Does not import Brain, positions, cash,
learning events other than trade closes, or create V3 trading wallets.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import sqlite3

from .events import EventJournal, EventConflict, _validate, _digest, _GENESIS
from .legacy_accounting import audit_classic_books
from .legacy_archives import audit_classic_archives
from .legacy_multirun import plan_classic_multirun_events
from .legacy_audit import _MAX_JSONL, _MAX_STATE, _source

_SOURCE_FILES = ("state_v2.json", "trade_history.jsonl", "learning_log.jsonl")
_SCHEMA_VERSION = "v3.legacy-classic-import.v1"
_SELECT = """SELECT seq,event_id,portfolio_id,run_id,kind,occurred_at_ms,
                    source,payload_json,previous_hash,event_hash
             FROM v3_events ORDER BY seq"""


@dataclass(frozen=True)
class ImportReceipt:
    portfolio_id: str
    event_count: int
    inserted: int
    already_present: int
    source_digest: str
    batch_digest: str
    chain_head: str
    run_count: int
    journal_path: str


def _source_hashes(root: Path) -> dict[str, str]:
    """Hash every source required for a complete multirun audit."""
    files = {name: sha256(_source(root / name,
            _MAX_STATE if name == _SOURCE_FILES[0] else _MAX_JSONL)).hexdigest()
            for name in _SOURCE_FILES}
    archive = root / "archive"
    if archive.is_symlink():
        raise ValueError("archive_symlink_forbidden")
    if archive.is_dir():
        folders = sorted(archive.iterdir())
        if len(folders) > 256:
            raise ValueError("too_many_archive_runs")
        for folder in folders:
            if folder.is_symlink() or not folder.is_dir():
                raise ValueError("invalid_archive_entry")
            for name in ("state_v2.json", "trade_history.jsonl", "summary.json"):
                key = "archive/" + folder.name + "/" + name
                files[key] = sha256(_source(
                    folder / name,
                    _MAX_JSONL if name.endswith(".jsonl") else _MAX_STATE
                )).hexdigest()
    return files


def _hash(obj: object) -> str:
    return sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def _verify_inside_transaction(db: sqlite3.Connection) -> str:
    previous = _GENESIS
    for row in db.execute(_SELECT):
        _, eid, portfolio, run, kind, stamp, source, payload, prev, digest = row
        from .events import Event
        event = Event(eid, portfolio, run, kind, stamp, source, json.loads(payload))
        if (prev != previous or _validate(event) != payload
                or _digest(event, payload, previous) != digest):
            raise ValueError("v3_journal_chain_invalid")
        previous = digest
    return previous


def import_verified_classic_copy(
    *,
    workspace: str | Path,
    source_copy: str | Path,
    portfolio_id: str,
    journal_name: str = "v3-import.sqlite3",
) -> ImportReceipt:
    """Atomically import one classic's verified closed-trade history.

    workspace is a dedicated, EXISTING offline directory; no additional
    relative path/traversal allowed. Source copy must exist outside it.
    Repeat execution checks exact manifest AND exact events. On any
    conflict the transaction rolls back. Re-importing a changed source is
    always rejected, even when records look otherwise identical.
    """
    work = Path(workspace)
    source = Path(source_copy)
    if (not work.is_dir() or work.is_symlink() or
            not source.is_dir() or source.is_symlink()):
        raise ValueError("offline_workspace_or_source_invalid")
    if (not isinstance(journal_name, str)
            or not journal_name.endswith(".sqlite3")
            or journal_name in (".sqlite3", "..sqlite3")
            or journal_name.count("/") or "\\" in journal_name):
        raise ValueError("invalid_journal_name")
    work = work.resolve(strict=True)
    source = source.resolve(strict=True)
    if work == source or work in source.parents or source in work.parents:
        raise ValueError("workspace_and_source_must_be_separate")
    destination = work / journal_name
    if destination.is_symlink():
        raise ValueError("journal_symlink_forbidden")
    if portfolio_id not in ("hawk", "bull"):
        raise ValueError("brain_import_not_supported")

    before = _source_hashes(source)
    report, events = plan_classic_multirun_events(source, portfolio_id)
    books = audit_classic_books(source, portfolio_id)
    archives = audit_classic_archives(source, portfolio_id)
    after = _source_hashes(source)
    if before != after:
        raise ValueError("source_modified_during_audit")
    if (not archives.eligible or not report.eligible or not books.cash_formula_pass
            or not books.multirun_pass or books.issues
            or len(events) != report.history_closes
            or len(events) != report.learning_closes):
        raise ValueError("legacy_reconciliation_not_eligible")
    if not report.runs or len(events) == 0:
        raise ValueError("empty_legacy_import_not_supported")
    prepared = []
    keys = set()
    for ev in events:
        payload = _validate(ev)
        if ev.event_id in keys:
            raise EventConflict("duplicate_event_id_in_batch")
        keys.add(ev.event_id)
        prepared.append((ev, payload))
    source_digest = _hash({"schema": _SCHEMA_VERSION, "source": before})
    batch_digest = _hash([
        _digest(ev, payload, _GENESIS) for ev, payload in prepared
    ])
    run_count = len(report.runs)

    journal = EventJournal(destination)
    if not destination.exists():
        journal.init_schema()
    # Fail closed on any non-V3 destination. Creating a new file is
    # intentionally the only implicit filesystem write.
    with journal._connect() as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            head = _verify_inside_transaction(db)
            db.execute("""
                CREATE TABLE IF NOT EXISTS v3_import_manifest(
                    portfolio_id TEXT PRIMARY KEY,
                    version TEXT NOT NULL,
                    source_digest TEXT NOT NULL,
                    batch_digest TEXT NOT NULL,
                    event_count INTEGER NOT NULL,
                    run_count INTEGER NOT NULL
                )
            """)
            db.execute("""
                CREATE TRIGGER IF NOT EXISTS v3_no_manifest_update
                BEFORE UPDATE ON v3_import_manifest BEGIN
                  SELECT RAISE(ABORT,'v3_import_manifest_immutable');
                END
            """)
            db.execute("""
                CREATE TRIGGER IF NOT EXISTS v3_no_manifest_delete
                BEFORE DELETE ON v3_import_manifest BEGIN
                  SELECT RAISE(ABORT,'v3_import_manifest_immutable');
                END
            """)
            manifest = db.execute(
                """SELECT version,source_digest,batch_digest,event_count,run_count
                   FROM v3_import_manifest WHERE portfolio_id=?""",
                (portfolio_id,),
            ).fetchone()
            expected = (_SCHEMA_VERSION, source_digest, batch_digest,
                        len(prepared), run_count)
            if manifest is not None and tuple(manifest) != expected:
                raise EventConflict("import_manifest_mismatch")
            if manifest is None:
                # An imported event without a corresponding manifest indicates
                # a previous incomplete or manual write: never silently heal it.
                existing_batch_ids = [
                    ev.event_id for ev, _ in prepared
                    if db.execute("SELECT 1 FROM v3_events WHERE event_id=?",
                                  (ev.event_id,)).fetchone()
                ]
                if existing_batch_ids:
                    raise EventConflict("preexisting_event_without_manifest")
            inserted = 0
            for ev, payload in prepared:
                prior = db.execute(
                    """SELECT portfolio_id,run_id,kind,occurred_at_ms,
                              source,payload_json FROM v3_events WHERE event_id=?""",
                    (ev.event_id,),
                ).fetchone()
                expected_row = (ev.portfolio_id, ev.run_id, ev.kind,
                                ev.occurred_at_ms, ev.source, payload)
                if prior is not None:
                    if tuple(prior) != expected_row:
                        raise EventConflict("event_id_content_conflict")
                    continue
                if manifest is not None:
                    raise EventConflict("manifest_present_but_event_missing")
                h = _digest(ev, payload, head)
                db.execute(
                    """INSERT INTO v3_events
                       (event_id,portfolio_id,run_id,kind,occurred_at_ms,
                        source,payload_json,previous_hash,event_hash)
                       VALUES(?,?,?,?,?,?,?,?,?)""",
                    (ev.event_id, ev.portfolio_id, ev.run_id, ev.kind,
                     ev.occurred_at_ms, ev.source, payload, head, h),
                )
                head = h
                inserted += 1
            if manifest is None:
                db.execute(
                    """INSERT INTO v3_import_manifest
                       (portfolio_id,version,source_digest,batch_digest,
                        event_count,run_count) VALUES(?,?,?,?,?,?)""",
                    (portfolio_id, *expected),
                )
            db.execute("COMMIT")
        except BaseException:
            db.execute("ROLLBACK")
            raise

    verified_count, verified_head = journal.verify_chain()
    if verified_head != head or verified_count < len(prepared):
        raise ValueError("journal_post_commit_verification_failed")
    return ImportReceipt(
        portfolio_id=portfolio_id, event_count=len(prepared),
        inserted=inserted, already_present=len(prepared)-inserted,
        source_digest=source_digest, batch_digest=batch_digest,
        chain_head=head, run_count=run_count, journal_path=str(destination),
    )
