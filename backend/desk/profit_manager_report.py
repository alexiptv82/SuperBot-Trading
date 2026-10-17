"""Offline report generator for Profit Manager shadow snapshots.

Reads JSONL snapshots exported by an approved read-only source.
Does not connect to VPS, exchange, bots or APIs. No order capability.

Usage:
 python -m backend.desk.profit_manager_report input_snapshots.jsonl

Each line: trade_id, timestamp_ms, open_ms, side, entry, mark, qty,
allocated_margin; optional funding_paid_usdt, open_fee_usdt.
No inferred market history or fabricated fills.
"""
import json
import sys
from collections import Counter
from pathlib import Path

try:
    from .profit_manager_replay import ShadowReplay, Snapshot
except ImportError:
    from profit_manager_replay import ShadowReplay, Snapshot


def analyze_lines(lines):
    replay = ShadowReplay()
    counters = Counter()
    first_exits = []
    errors = []
    for line_no, raw in enumerate(lines, 1):
        if not raw.strip():
            continue
        counters["snapshots_seen"] += 1
        try:
            record = json.loads(raw)
            if not isinstance(record, dict):
                raise ValueError("Expected JSON object")
            snap = Snapshot(**record)
            result = replay.observe(snap)
            counters["snapshots_accepted"] += 1
            if result.action == "SHADOW_EXIT":
                if result.trade_id not in {x["trade_id"] for x in first_exits}:
                    first_exits.append({
                        "trade_id": result.trade_id,
                        "timestamp_ms": result.timestamp_ms,
                        "estimated_net_usdt": result.estimated_net_usdt,
                        "roi_net_pct": result.roi_net_pct,
                        "reason": result.reason,
                    })
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            errors.append({"line": line_no, "error": str(exc)})
            counters["snapshots_rejected"] += 1
    return {
        "mode": "offline_shadow_only",
        "snapshots_seen": counters["snapshots_seen"],
        "snapshots_accepted": counters["snapshots_accepted"],
        "snapshots_rejected": counters["snapshots_rejected"],
        "hypothetical_exits": first_exits,
        "errors": errors,
        "profit_improvement_verified": False,
        "note": "No baseline/fill reconciliation: hypothetical exits are NOT proof of profit improvement.",
    }


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        raise SystemExit("Usage: python -m backend.desk.profit_manager_report snapshots.jsonl")
    with Path(argv[0]).open("r", encoding="utf-8") as stream:
        print(json.dumps(analyze_lines(stream), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
