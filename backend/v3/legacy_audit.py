"""Read-only audit and dry-run mapping of legacy PAPER snapshots.

No filesystem writes, no imports into the V3 journal, no credentials or APIs.
Never assume that state, trade_history and learning_log are disjoint trade sets.
An unmatched, malformed, or missing source is an explicit BLOCKED audit.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping

from .events import Event

_MAX_STATE = 16 * 1024 * 1024
_MAX_JSONL_ROW = 2 * 1024 * 1024
_MAX_JSONL = 300 * 1024 * 1024


@dataclass(frozen=True)
class AuditReport:
    portfolio_id: str
    legacy_run_id: str
    eligible: bool
    state_closed: int
    history_closed: int
    learning_closed: int
    open_positions: int
    state_net: str
    history_net: str
    files_sha256: Mapping[str, str]
    issues: tuple[str, ...]

    def public_summary(self) -> dict[str, Any]:
        return asdict(self)


def _source(path: Path, limit: int) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ValueError("missing_or_symlink_source:" + path.name)
    if path.stat().st_size > limit:
        raise ValueError("source_over_limit:" + path.name)
    with path.open("rb") as handle:
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise ValueError("source_over_limit:" + path.name)
    return data


def _parse_doc(raw: bytes) -> Mapping[str, Any]:
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected_json_object")
    return value


def _parse_rows(raw: bytes) -> list[dict]:
    rows = []
    for i, line in enumerate(raw.splitlines(), 1):
        if not line.strip():
            continue
        if len(line) > _MAX_JSONL_ROW:
            raise ValueError("jsonl_row_too_large")
        obj = _parse_doc(line)
        rows.append(dict(obj))
    return rows


def _number(value: Any) -> Decimal:
    if value is None or isinstance(value, bool):
        raise ValueError("invalid_legacy_net")
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("invalid_legacy_net") from exc
    if not d.is_finite():
        raise ValueError("invalid_legacy_net")
    return d


def _closed(row: Mapping[str, Any]) -> tuple[int, Decimal]:
    if (not isinstance(row, dict)
            or type(row.get("id")) is not int or row["id"] < 1
            or not isinstance(row.get("symbol"), str)
            or not row["symbol"].strip()
            or type(row.get("close_ms")) is not int
            or row["close_ms"] <= 0):
        raise ValueError("invalid_legacy_close")
    return row["close_ms"], _number(row.get("net"))


def _canon(row: Mapping[str, Any]) -> str:
    return json.dumps(row, ensure_ascii=True, allow_nan=False,
                      sort_keys=True, separators=(",", ":"), default=str)


def _fingerprints(rows: list[dict]) -> Counter:
    return Counter(_canon(row) for row in rows)


def _net(rows: list[dict]) -> Decimal:
    return sum((_closed(row)[1] for row in rows), Decimal("0"))


def audit_classic_snapshot(
    directory: str | Path,
    portfolio_id: str,
    *,
    learning_path: str | Path | None = None,
) -> AuditReport:
    """Compare the CURRENT classic run with its own history and learning log.

    Archived runs must use their archived state_v2.json and trade_history.jsonl,
    and explicitly pass learning_path pointing to the shared ORIGINAL learning
    log if the archive omitted it. Never silently borrow another run's data.
    No cross-run matching by symbol or trade ID is permitted.
    """
    if portfolio_id not in ("hawk", "bull"):
        raise ValueError("unsupported_portfolio")
    root = Path(directory)
    if not root.is_dir() or root.is_symlink():
        raise ValueError("invalid_source_directory")

    files = ("state_v2.json", "trade_history.jsonl", "learning_log.jsonl")
    raw: dict[str, bytes] = {}
    digest: dict[str, str] = {}
    for filename in files:
        path = Path(learning_path) if filename == "learning_log.jsonl" and learning_path is not None else root / filename
        raw[filename] = _source(path, _MAX_STATE if filename == files[0] else _MAX_JSONL)
        digest[filename] = hashlib.sha256(raw[filename]).hexdigest()

    state = _parse_doc(raw["state_v2.json"])
    run = state.get("run_no")
    if type(run) is not int or run < 1:
        raise ValueError("invalid_legacy_run_no")
    main = state.get("main")
    if not isinstance(main, dict):
        raise ValueError("missing_legacy_main")
    state_closed = main.get("closed")
    positions = main.get("positions")
    if not isinstance(state_closed, list) or not isinstance(positions, dict):
        raise ValueError("invalid_legacy_account")
    if any(not isinstance(r, dict) for r in state_closed):
        raise ValueError("invalid_state_closed_rows")

    history = _parse_rows(raw["trade_history.jsonl"])
    learn = _parse_rows(raw["learning_log.jsonl"])
    # A reset can copy files to archive/; do not infer run IDs from filenames.
    # The current learning log may span many runs, unlike trade_history.
    learning_closes = [r for r in learn
                       if r.get("ev") == "close" and r.get("run_no") == run]
    issues: list[str] = []
    for row in state_closed + history:
        _closed(row)
    state_sum, history_sum = _net(state_closed), _net(history)
    if len(state_closed) != len(history):
        issues.append("CLOSED_COUNT_MISMATCH")
    if _fingerprints(state_closed) != _fingerprints(history):
        issues.append("CLOSED_ROW_MISMATCH")
    if state_sum != history_sum:
        issues.append("CLOSED_NET_MISMATCH")
    if len(_fingerprints(history)) != len(history):
        issues.append("DUPLICATE_HISTORY_ROW")
    # Learning writer may silently fail, so never invent missing lessons.
    if len(learning_closes) != len(history):
        issues.append("LEARNING_COVERAGE_GAP")
    for row in learn:
        if row.get("ev") == "close" and row.get("run_no") == run:
            if not isinstance(row.get("id"), int) or row.get("net") is None:
                issues.append("INVALID_LEARNING_CLOSE")
                break

    return AuditReport(
        portfolio_id, f"legacy-{portfolio_id}-{run}", not issues,
        len(state_closed), len(history), len(learning_closes),
        len(positions), str(state_sum), str(history_sum),
        digest, tuple(dict.fromkeys(issues)),
    )


def plan_classic_closed_events(
    directory: str | Path,
    portfolio_id: str,
    *,
    learning_path: str | Path | None = None,
) -> tuple[AuditReport, tuple[Event, ...]]:
    """Stage validated close events in memory ONLY; nothing is written.

    Event IDs use the source line number, not trade ID, because one trade
    may have several partial closes. A changed source line with the same ID
    will later be rejected as a conflict by the V3 event journal.
    """
    report = audit_classic_snapshot(directory, portfolio_id, learning_path=learning_path)
    if not report.eligible:
        return report, ()
    root = Path(directory)
    history = _parse_rows(_source(root / "trade_history.jsonl", _MAX_JSONL))
    prepared = []
    for idx, row in enumerate(history, 1):
        occurred_at_ms, _ = _closed(row)
        prepared.append(Event(
            event_id=f"legacy.{portfolio_id}.{report.legacy_run_id}.close.{idx}",
            portfolio_id=portfolio_id,
            run_id=report.legacy_run_id,
            kind="legacy_trade_closed",
            occurred_at_ms=occurred_at_ms,
            source="legacy_snapshot",
            payload={
                "provenance": "observed_paper_record_not_retraining",
                "source_line": idx,
                "source_row_sha256": hashlib.sha256(
                    _canon(row).encode("utf-8")).hexdigest(),
                "legacy_record": row,
            },
        ))
    return report, tuple(prepared)


def audit_brain_snapshot(db_path: str | Path) -> dict[str, Any]:
    """Brain Free V2 read-only inventory; do not yet infer P&L from events.

    This is deliberately an audit, not an importer; Brain Free uses a
    different ledger, partial closes and events schema that need a separate
    reconciliation contract.
    """
    path = Path(db_path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("invalid_brain_database")
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro",
                         uri=True, timeout=5) as db:
        db.execute("PRAGMA query_only=ON")
        integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise ValueError("brain_sqlite_integrity_error")
        state_row = db.execute("SELECT body FROM state WHERE id=1").fetchone()
        if not state_row:
            raise ValueError("brain_state_missing")
        state = json.loads(state_row[0])
        if state.get("mode") != "paper" or state.get("account_id") != "brain-free-paper":
            raise ValueError("foreign_brain_account")
        count = db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        trade_closed = db.execute(
            "SELECT COUNT(*) FROM events WHERE kind='trade_closed'"
        ).fetchone()[0]
        positions = state.get("positions")
        if not isinstance(positions, dict):
            raise ValueError("brain_positions_invalid")
    return {
        "portfolio": "brain",
        "provenance": "historical_paper_brain_free",
        "verified_sqlite": True,
        "events": count,
        "trade_closed_events": trade_closed,
        "open_positions": len(positions),
        "import_eligible": False,
        "requires": "brain_free_event_pnl_reconciliation_contract",
    }
