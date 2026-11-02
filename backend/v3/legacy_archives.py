"""Strict, read-only verification of archived classic PAPER run summaries.

Intended as a separate gate before any import from legacy backups. The active
run's trade_history.jsonl can be cumulative; archived trade_history and state
must instead reflect the run being archived. Missing archives are BLOCKING,
never filled with inferred closes.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from .legacy_audit import (_MAX_JSONL, _MAX_STATE, _source, _parse_doc,
                            _parse_rows, _fingerprints, _net, _number)
from .legacy_multirun import _scan, _match


@dataclass(frozen=True)
class ArchiveAudit:
    eligible: bool
    expected_runs: tuple[int, ...]
    verified_runs: tuple[int, ...]
    issues: tuple[str, ...]


def audit_classic_archives(directory: str | Path, portfolio_id: str) -> ArchiveAudit:
    """Compare every historic run to its immutable archive files and summary.

    Do not assume that the source archive/ is complete merely because
    learning_log and history agree with one another.
    """
    root = Path(directory)
    run, current, positions, history, learning = _scan(root, portfolio_id)
    assigned, _, _, _, assignment_issues = _match(
        run, current, positions, history, learning, portfolio_id
    )
    issues = list(assignment_issues)
    by_run: dict[int, list[dict]] = {}
    for r, row in assigned:
        by_run.setdefault(r, []).append(row)
    expected = set(r for r in by_run if r < run)
    archive_dir = root / "archive"
    verified: set[int] = set()
    if expected and (not archive_dir.is_dir() or archive_dir.is_symlink()):
        issues.append("ARCHIVE_DIRECTORY_MISSING")
        return ArchiveAudit(False, tuple(sorted(expected)), (), tuple(dict.fromkeys(issues)))
    if archive_dir.is_dir():
        for folder in sorted(archive_dir.iterdir()):
            if folder.is_symlink() or not folder.is_dir():
                issues.append("INVALID_ARCHIVE_ENTRY")
                continue
            try:
                summary = _parse_doc(_source(folder / "summary.json", _MAX_STATE))
                state = _parse_doc(_source(folder / "state_v2.json", _MAX_STATE))
                closed = state["main"]["closed"]
                opens = state["main"]["positions"]
                if not isinstance(closed, list) or not isinstance(opens, dict):
                    raise ValueError("invalid_archive_account")
                hist = _parse_rows(_source(folder / "trade_history.jsonl", _MAX_JSONL))
                r = summary.get("run_no")
                if type(r) is not int or r >= run or r < 1:
                    raise ValueError("invalid_archive_run")
                if r in verified:
                    raise ValueError("duplicate_archive_run")
                if state.get("run_no") != r:
                    raise ValueError("archive_run_mismatch")
                if summary.get("portfolio") != portfolio_id:
                    raise ValueError("archive_portfolio_mismatch")
                if opens:
                    raise ValueError("archived_run_has_open_positions")
                if (_fingerprints(hist) != _fingerprints(closed)
                        or _fingerprints(hist) != _fingerprints(by_run.get(r, []))):
                    raise ValueError("archive_trade_history_mismatch")
                if type(summary.get("trades")) is not int or summary["trades"] != len(hist):
                    raise ValueError("archive_trade_count_mismatch")
                net = _net(hist)
                start = _number(summary.get("start_equity"))
                reported_net = _number(summary.get("net_total"))
                end = _number(summary.get("end_equity"))
                reported_pnl = _number(summary.get("pnl"))
                tolerance = max(Decimal("0.01"), Decimal("0.00005") * len(hist))
                if any(abs(a-b) > tolerance for a,b in (
                    (net, reported_net), (end, start + net),
                    (reported_pnl, net)
                )):
                    raise ValueError("archive_cash_mismatch")
                verified.add(r)
            except (KeyError, ValueError, TypeError, IndexError) as exc:
                # Issue type only in reports; do not expose account data.
                issues.append("ARCHIVE_SUMMARY_MISMATCH:" + type(exc).__name__)
    if verified != expected:
        issues.append("ARCHIVE_RUN_COVERAGE_MISMATCH")
    return ArchiveAudit(
        eligible=not issues,
        expected_runs=tuple(sorted(expected)),
        verified_runs=tuple(sorted(verified)),
        issues=tuple(dict.fromkeys(issues)),
    )
