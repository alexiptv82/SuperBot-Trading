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
print("READONLY_AUDIT_FINISHED=YES")
