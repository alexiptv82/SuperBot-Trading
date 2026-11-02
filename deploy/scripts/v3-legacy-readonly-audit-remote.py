"""Audit frozen post-shutdown snapshot only. Executed via python3 - (stdin).

No filesystem writes, no subprocesses, no network calls, no credential loading.
Input code for v3.events/v3.legacy_audit pre-loaded in memory by the runner.
Output intentionally excludes per-trade detail and USDT PnL.
"""
import hashlib
from pathlib import Path

from v3.legacy_audit import audit_classic_snapshot, audit_brain_snapshot

SNAP = Path("/opt/superbot-v3-backups/20261102T144010Z/restore-test")
if SNAP.is_symlink() or not SNAP.is_dir():
    raise SystemExit("AUDIT_BLOCKED:OFFLINE_BACKUP_MISSING")
print("V3_SNAPSHOT_AUDIT=READ_ONLY")
print("V3_SNAPSHOT_LOCATION=POST_STOP_RESTORED_COPY")

for port in ("hawk", "bull"):
    path = SNAP / "superbot-desk-data" / port
    try:
        report = audit_classic_snapshot(path, port)
    except Exception as exc:
        print(port.upper(), "BLOCKED", "error=", type(exc).__name__)
        continue
    print(
        port.upper(), "ELIGIBLE=", report.eligible,
        "STATE_CLOSES=", report.state_closed,
        "HISTORY_CLOSES=", report.history_closed,
        "LEARNING_CLOSES=", report.learning_closed,
        "OPEN_SAVED=", report.open_positions,
        "NET_MATCH=", report.state_net == report.history_net,
        "ISSUES=", ",".join(report.issues) if report.issues else "NONE",
    )

    # Diagnostic only: detect whether the current run is a strict subset of
    # a historical, multi-run JSONL. Do not modify the audit's BLOCKED gate.
    import json
    from collections import Counter
    from v3.legacy_audit import _canon
    account = json.loads((path / "state_v2.json").read_text())
    state_rows = account["main"]["closed"]
    history_rows = [json.loads(line) for line in
                    (path / "trade_history.jsonl").read_text().splitlines()
                    if line.strip()]
    a, b = Counter(_canon(r) for r in state_rows), Counter(_canon(r) for r in history_rows)
    full_current_subset = all(b[key] >= n for key, n in a.items())
    log_rows = [json.loads(line) for line in
                (path / "learning_log.jsonl").read_text().splitlines()
                if line.strip()]
    close_by_run = Counter(str(r.get("run_no", "MISSING")) for r in log_rows
                           if r.get("ev") == "close")
    print(port.upper(), "CURRENT_ROWS_PRESENT_IN_HISTORY=", full_current_subset,
          "LEARNING_CLOSE_RUN_COUNTS=", ";".join(
              f"{k}:{v}" for k, v in sorted(close_by_run.items())
          ))

    from v3.legacy_multirun import audit_classic_multirun
    multi = audit_classic_multirun(path, port)
    print(port.upper(), "MULTIRUN_ELIGIBLE=", multi.eligible,
          "TOTAL_RECONCILED=", sum(item[1] for item in multi.runs),
          "TOTAL_HISTORY=", multi.history_closes,
          "CURRENT_RUN_MATCH=", multi.current_net_matches
          and multi.state_current_closes == multi.current_history_closes,
          "RUNS=", ",".join(str(x[0]) for x in multi.runs),
          "MULTIRUN_ISSUES=", ",".join(multi.issues) if multi.issues else "NONE")

    if multi.eligible:
        from v3.legacy_multirun import plan_classic_multirun_events
        from v3.events import _validate
        prepared_report, proposed_events = plan_classic_multirun_events(path, port)
        for ev in proposed_events:
            _validate(ev)
        assert len(proposed_events) == multi.history_closes
        assert len({ev.event_id for ev in proposed_events}) == len(proposed_events)
        print(port.upper(), "MEMORY_ONLY_EVENT_PLAN_PASS=", len(proposed_events))

    if "LEARNING_FIELD_MISMATCH" in multi.issues:
        from v3.legacy_multirun import _key
        learning_map = {_key(item): item for item in log_rows
                        if item.get("ev") == "close"}
        discrepancy = Counter()
        for row in history_rows:
            found = learning_map.get(_key(row))
            if found:
                for key, value in row.items():
                    if key != "reason" and found.get(key, object()) != value:
                        discrepancy[key] += 1
        print(port.upper(), "DIFFERING_FIELD_NAMES_ONLY=",
              ";".join(f"{k}:{v}" for k, v in sorted(discrepancy.items())))

brain = SNAP / "superbot-brain-free" / "brain.sqlite3"
try:
    report = audit_brain_snapshot(brain)
    print("BRAIN", "SQLITE_OK=", report["verified_sqlite"],
          "EVENTS=", report["events"],
          "TRADE_CLOSED_EVENTS=", report["trade_closed_events"],
          "OPEN_SAVED=", report["open_positions"],
          "IMPORT_ELIGIBLE=", report["import_eligible"])
except Exception as exc:
    print("BRAIN BLOCKED", "error=", type(exc).__name__)
from v3.legacy_accounting import audit_classic_books, audit_brain_structure
for port in ("hawk", "bull"):
    try:
        result = audit_classic_books(SNAP / "superbot-desk-data" / port, port)
        print(
            "ACCOUNTING", port.upper(),
            "RUN=", result.run_id,
            "CLOSED=", result.closed_count,
            "OPEN=", result.open_count,
            "MULTIRUN_PASS=", result.multirun_pass,
            "BOOK_CASH_PASS=", result.cash_formula_pass,
            "BOOK_ISSUES=", ",".join(result.issues) if result.issues else "NONE",
        )
    except Exception as exc:
        print("ACCOUNTING", port.upper(), "BLOCKED=", type(exc).__name__)

try:
    structure = audit_brain_structure(brain)
    print("BRAIN_STRUCTURE PAPER=", structure.paper_valid,
          "EVENTS=", structure.total_events,
          "KINDS=", ";".join(k + ":" + str(v) for k,v in structure.kind_counts),
          "OPEN=", structure.open_positions,
          "IMPORT_ALLOWED=", structure.import_allowed)
    for kind, fields in structure.relevant_fields:
        print("BRAIN_EVENT_FIELDS", kind, ",".join(fields))
except Exception as exc:
    print("BRAIN_STRUCTURE BLOCKED=", type(exc).__name__)
print("READONLY_AUDIT_FINISHED=YES")
