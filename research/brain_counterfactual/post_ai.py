"""Read-only evidence accounting for Brain post-AI execution gaps.

The journal records approvals and fills but NOT durable per-decision guard
denial codes. heartbeat.json keeps only the last error, is overwritten every
tick and is NOT a historical audit log. Never infer missing causes.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import json
from pathlib import Path
import re

_CODES = frozenset({
    "risk_changed_after_ai", "risk_rejected_after_ai", "brain_paused",
    "market_price_moved", "market_unavailable", "exit_service_unhealthy",
    "open_lease_busy", "already_open", "decision_stale",
})


def audit(rows: list[dict], heartbeat: dict | None = None) -> dict:
    approved, executed, unresolved, risk_rejected = Counter(), Counter(), Counter(), Counter()
    for row in rows:
        sym = row["symbol"]
        if row["status"] == "RISK_REJECTED":
            risk_rejected[sym] += 1
        if row["kind"] == "OPEN" and row["status"] == "APPROVED":
            approved[sym] += 1
            if row["opening"] is not None:
                executed[sym] += 1
            else:
                unresolved[sym] += 1
    symbols = sorted(set(approved) | set(risk_rejected))
    newest = []
    heartbeat_has_history = False
    if heartbeat is not None:
        if type(heartbeat) is not dict:
            raise ValueError("heartbeat_invalid")
        text = heartbeat.get("last_error")
        if text is not None and type(text) is not str:
            raise ValueError("heartbeat_invalid")
        # Only an ephemeral hint. No join to decision event IDs is possible.
        newest = sorted({x for x in _CODES if text and re.search(r"(?<![a-z_])" + re.escape(x) + r"(?![a-z_])", text)})
    return {
        "schema": "brain_post_ai_gap_audit_v1",
        "run_scope": "only_brain_decisions_in_selected_run",
        "approved_total": sum(approved.values()),
        "executed_with_verified_decision_link": sum(executed.values()),
        "approved_unexecuted_reason_unknown": sum(unresolved.values()),
        "risk_rejected_before_approval": sum(risk_rejected.values()),
        "by_symbol": {
            s: {
                "approved": approved[s], "executed": executed[s],
                "unexecuted_unknown_cause": unresolved[s],
                "risk_rejected": risk_rejected[s],
            } for s in symbols
        },
        "last_heartbeat_error_codes_observed": newest,
        "last_heartbeat_is_complete_history": heartbeat_has_history,
        "post_ai_rejection_reason_per_decision_known": False,
        "warning": (
            "Do NOT classify every approved-unexecuted as a post-AI denial. "
            "Only current heartbeat errors can be observed optionally; "
            "they cannot be assigned to a decision without a durable event ID. "
            "The real risk guard must never be disabled to force fills."
        ),
        "mutations": 0,
    }


def report_file(ledger_jsonl: Path, heartbeat_json: Path | None = None) -> dict:
    with ledger_jsonl.open(encoding="utf-8") as f:
        records = [json.loads(line) for line in f if line.strip()]
    hb = None
    if heartbeat_json is not None:
        hb = json.loads(heartbeat_json.read_text(encoding="utf-8"))
    return audit(records, hb)


def main(argv: list[str] | None = None) -> None:
    import argparse
    ap = argparse.ArgumentParser(description="Evidence-only Brain PAPER guard audit")
    ap.add_argument("--ledger", required=True, type=Path)
    ap.add_argument("--heartbeat-snapshot", type=Path, default=None)
    args = ap.parse_args(argv)
    print(json.dumps(report_file(args.ledger, args.heartbeat_snapshot),
                     indent=2, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
