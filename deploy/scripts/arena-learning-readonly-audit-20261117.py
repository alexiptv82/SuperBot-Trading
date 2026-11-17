#!/usr/bin/env python3
"""Read-only journal integrity/learning-evidence audit of the EXISTING Brain.

This does not certify active AI learning, write SQLite, copy source files,
read API keys, trigger orders or configure a service. Run with the REAL journal
path/run ID confirmed on the VPS. Never guess either from the GitHub repo.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path
from backend.v3.events import EventJournal
from backend.v3.outcomes import extract_outcomes


def audit(journal_path: Path, run_id: str) -> dict:
    if (type(journal_path) is not Path or not journal_path.is_absolute()
            or journal_path.is_symlink() or not journal_path.is_file()
            or type(run_id) is not str or
            not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.:-]{1,127}", run_id)):
        raise ValueError("invalid_or_missing_journal_scope")
    journal = EventJournal(journal_path)
    count, head = journal.verify_chain()
    events = journal.list_run("brain", run_id)
    # Shared historical databases may include classic events, so count only
    # entries of this Brain run; unlike isolated new trial DBs, don't impose
    # count == len(run events).
    if len(events) > count:
        raise ValueError("brain_event_count_overflow")
    report = extract_outcomes(journal, "brain", run_id)
    journal.verify_chain(expected_count=count, expected_head=head)
    closed_count = sum(e.event.kind == "paper_close" for e in events)
    open_count = sum(e.event.kind == "paper_open" for e in events)
    decision_count = sum(e.event.kind == "brain_decision" for e in events)
    no_trade_count = sum(
        e.event.kind == "brain_decision" and
        e.event.payload.get("kind") == "NO_TRADE" for e in events
    )
    matched = sum(o.link_status == "linked" for o in report.outcomes)
    manual = sum(o.is_manual for o in report.outcomes)
    findings = {
        "run_id": run_id,
        "all_journal_events": count,
        "run_events": len(events),
        "chain_head_sha256": head,
        "brain_decisions": decision_count,
        "brain_no_trade_decisions": no_trade_count,
        "paper_opens": open_count,
        "paper_closes": closed_count,
        "outcomes_verified": len(report.outcomes),
        "outcomes_linked_to_decisions": matched,
        "outcomes_manual": manual,
        "open_positions_pending": len(report.open_position_ids),
        "outcomes_skipped": len(report.skipped),
        # A verified append-only journal is evidence retention, not proof
        # that the deployed LLM adapts its prompt/weights using this data.
        "model_learning_active": "NOT_PROVEN_BY_JOURNAL",
        "archive_backup_restore": "NOT_CHECKED",
    }
    if len(report.outcomes) != closed_count or report.skipped:
        findings["status"] = "REVIEW_REQUIRED_OUTCOME_GAPS"
    else:
        findings["status"] = "READONLY_JOURNAL_AND_OUTCOMES_CONSISTENT"
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--journal", required=True, help="absolute path to current Brain V3 PAPER journal.db")
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    try:
        result = audit(Path(args.journal), args.run_id)
    except Exception as error:
        print("ARENA_MEMORY_AUDIT RESULT=REFUSED_" + type(error).__name__.upper())
        return 2
    for key, value in result.items():
        print("ARENA_MEMORY_AUDIT " + key + "=" + str(value))
    return 0 if result["status"] == "READONLY_JOURNAL_AND_OUTCOMES_CONSISTENT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
