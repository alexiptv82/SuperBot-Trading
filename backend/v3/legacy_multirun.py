"""Reconcile cumulative classic trade history with per-run learning records.

All source input is a stopped, frozen PAPER backup. No SQLite writes, no
legacy modifications and no real trades are executed. Never silently infer a
run number from a trade ID or symbol.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal
import hashlib
from pathlib import Path
from typing import Any

from .events import Event
from .legacy_audit import (_MAX_JSONL, _MAX_STATE, _source, _parse_doc,
                            _parse_rows, _closed, _canon, _fingerprints, _net)


@dataclass(frozen=True)
class MultiRunReport:
    portfolio_id: str
    current_run: int
    eligible: bool
    history_closes: int
    learning_closes: int
    state_current_closes: int
    current_history_closes: int
    current_net_matches: bool
    open_positions: int
    runs: tuple[tuple[int, int, str], ...]  # (run_number, closed_count, net_USDT)
    issues: tuple[str, ...]


# These are produced by both engine._close()/partial_close() and log_event.
# Reason is not included because the logger historically truncates it.
_ID_FIELDS = ("id", "symbol", "side", "open_ms", "close_ms",
              "net", "partial", "fraction", "entry", "exit",
              "margin", "fees", "funding", "leverage")


def _key(row: dict) -> str:
    # Explicit absence sentinel distinguishes missing from null.
    return _canon({key: [key in row, row.get(key)] for key in _ID_FIELDS})


def _scan(
    directory: str | Path,
    portfolio_id: str,
    *,
    learning_path: str | Path | None = None,
):
    if portfolio_id not in ("hawk", "bull"):
        raise ValueError("unsupported_portfolio")
    root = Path(directory)
    if not root.is_dir() or root.is_symlink():
        raise ValueError("invalid_source_directory")
    state = _parse_doc(_source(root / "state_v2.json", _MAX_STATE))
    run = state.get("run_no")
    if type(run) is not int or run < 1:
        raise ValueError("invalid_legacy_run_no")
    account = state.get("main")
    if not isinstance(account, dict):
        raise ValueError("invalid_account")
    current = account.get("closed")
    positions = account.get("positions")
    if not isinstance(current, list) or not isinstance(positions, dict):
        raise ValueError("invalid_current_account")
    if any(not isinstance(x, dict) for x in current):
        raise ValueError("invalid_current_closed")
    history = _parse_rows(_source(root / "trade_history.jsonl", _MAX_JSONL))
    log_path = Path(learning_path) if learning_path is not None else root / "learning_log.jsonl"
    learning = _parse_rows(_source(log_path, _MAX_JSONL))
    learn_closes = [x for x in learning if x.get("ev") == "close"]
    for row in current + history:
        _closed(row)
    return run, current, positions, history, learn_closes


def _match(run, current, positions, history, learn_closes):
    issues = []
    by_key = defaultdict(list)
    for row in learn_closes:
        key = _key(row)
        by_key[key].append(row)
    assigned: list[tuple[int, dict]] = []
    for item in history:
        sig = _key(item)
        candidates = by_key.get(sig, [])
        if len(candidates) != 1:
            issues.append("UNMATCHED_OR_AMBIGUOUS_LEARNING_CLOSE")
            continue
        candidate = candidates.pop()
        run_no = candidate.get("run_no")
        if type(run_no) is not int or run_no < 1:
            issues.append("INVALID_LEARNING_RUN_NO")
            continue
        # Ensure match on ALL unmodified record fields, not only identity key.
        for field, value in item.items():
            if field != "reason" and (field not in candidate or candidate[field] != value):
                issues.append("LEARNING_FIELD_MISMATCH")
                break
        assigned.append((run_no, item))
    if any(remaining for remaining in by_key.values()):
        issues.append("UNMATCHED_LEARNING_CLOSE")
    if len(assigned) != len(history):
        issues.append("HISTORY_ASSIGNMENT_INCOMPLETE")
    current_history = [x for r, x in assigned if r == run]
    if _fingerprints(current_history) != _fingerprints(current):
        issues.append("CURRENT_RUN_STATE_HISTORY_MISMATCH")
    if len(_fingerprints(history)) != len(history):
        issues.append("DUPLICATE_HISTORY_ROW")
    current_net_matches = _net(current) == _net(current_history)
    if not current_net_matches:
        issues.append("CURRENT_RUN_NET_MISMATCH")
    groups: dict[int, list] = defaultdict(list)
    for r, row in assigned:
        groups[r].append(row)
    run_summaries = tuple((r, len(rows), str(_net(rows)))
                          for r, rows in sorted(groups.items()))
    return assigned, current_history, current_net_matches, run_summaries, tuple(dict.fromkeys(issues))


def audit_classic_multirun(directory, portfolio_id, *, learning_path=None):
    """Build a conservative read-only report for cumulative JSONL across runs."""
    run, current, positions, history, learn = _scan(
        directory, portfolio_id, learning_path=learning_path
    )
    assigned, current_history, net_match, run_summaries, issues = _match(
        run, current, positions, history, learn
    )
    report = MultiRunReport(
        portfolio_id, run, not issues, len(history), len(learn),
        len(current), len(current_history), net_match, len(positions),
        run_summaries, issues
    )
    return report


def plan_classic_multirun_events(directory, portfolio_id, *, learning_path=None):
    """Return memory-only events for EVERY verified historical run.

    Never import until all history rows map one-to-one to a run-specific
    learning record and current-run state matches its assigned subset.
    """
    run, current, positions, history, learn = _scan(
        directory, portfolio_id, learning_path=learning_path
    )
    assigned, current_history, net_match, summaries, issues = _match(
        run, current, positions, history, learn
    )
    report = MultiRunReport(
        portfolio_id, run, not issues, len(history), len(learn),
        len(current), len(current_history), net_match, len(positions),
        summaries, issues
    )
    if issues:
        return report, ()
    events = []
    for idx, (historical_run, item) in enumerate(assigned, 1):
        stamp, _ = _closed(item)
        events.append(Event(
            event_id=f"legacy.{portfolio_id}.{historical_run}.closed.{idx}",
            portfolio_id=portfolio_id,
            run_id=f"legacy-{portfolio_id}-{historical_run}",
            kind="legacy_trade_closed",
            occurred_at_ms=stamp,
            source="legacy_paper_history",
            payload={
                "provenance": "historical_paper_observed",
                "history_row": idx,
                "record_sha256": hashlib.sha256(
                    _canon(item).encode("utf-8")
                ).hexdigest(),
                "record": item,
            },
        ))
    return report, tuple(events)
