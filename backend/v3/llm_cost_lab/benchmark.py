"""Confronto fra gli stessi input. L'accordo con la baseline non è correttezza."""
from __future__ import annotations

from collections import defaultdict
from typing import Mapping, Optional, Sequence


def _percentile(values: Sequence[int], pct: float) -> Optional[int]:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * pct
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    weight = rank - low
    return int(round(ordered[low] * (1 - weight) + ordered[high] * weight))


def summarize(records: Sequence[Mapping], outcomes: Optional[Sequence[Mapping]] = None) -> dict:
    by_model: dict[str, list] = defaultdict(list)
    for row in records:
        by_model[str(row.get("model_id"))].append(row)
    known = {}
    if outcomes:
        for item in outcomes:
            if item.get("known") is True and item.get("sample_id") and item.get("label") in {
                    "LONG", "SHORT", "NO_TRADE"}:
                known[item["sample_id"]] = item
    arms = []
    for model_id, rows in sorted(by_model.items()):
        latencies = [row["latency_ms"] for row in rows
                     if type(row.get("latency_ms")) is int and row.get("attempts") == 1]
        costs = [row["cost_micro_usd"] for row in rows if type(row.get("cost_micro_usd")) is int]
        measured = [row for row in rows if row.get("cost_origin") == "simulated_usage"]
        calls = sum(1 for row in rows if row.get("attempts") == 1)
        valid = sum(1 for row in rows if row.get("valid") is True)
        mean = (sum(latencies) / len(latencies)) if latencies else None
        per_thousand = None
        if costs and len(costs) == len(rows):
            per_thousand = int(round((sum(costs) / len(costs)) * 1000))
        quality = _quality(rows, known)
        arms.append({
            "model_id": model_id,
            "decisions": len(rows),
            "calls": calls,
            "valid_schema": valid,
            "valid_schema_rate": (valid / len(rows)) if rows else None,
            "timeouts": sum(1 for row in rows if row.get("failure") == "timeout"),
            "rate_limits": sum(1 for row in rows if row.get("failure") == "rate_limit"),
            "http_errors": sum(1 for row in rows if row.get("failure") in {"http_error", "connection", "transport"}),
            "malformed": sum(1 for row in rows if row.get("failure") in {"invalid_json", "invalid_schema", "malformed"}),
            "latency_mean_ms": mean,
            "latency_median_ms": _percentile(latencies, 0.50),
            "latency_p95_ms": _percentile(latencies, 0.95),
            "latency_basis": "simulated" if latencies else "not_measured",
            "cost_per_1000_micro_usd": per_thousand,
            "cost_basis": "simulated_usage" if measured and len(measured) == len(rows) else "incomplete",
            "daily_consumption": "not_measured",
            "quality_vs_outcomes": quality,
            "may_open_any": any(row.get("may_open") for row in rows),
        })
    return {
        "arms": arms,
        "agreement_with_baseline": _agreement(records),
        "agreement_is_correctness": False,
        "live_provider_measured": False,
    }


def _agreement(records: Sequence[Mapping]) -> dict:
    baseline = {}
    others = defaultdict(dict)
    for row in records:
        if row.get("valid") is not True:
            continue
        sample = row.get("sample_id")
        action = row.get("action")
        if row.get("model_id") == "deepseek-flash":
            baseline[sample] = action
        else:
            others[row.get("model_id")][sample] = action
    report = {}
    for model_id, actions in sorted(others.items()):
        shared = [sample for sample in actions if sample in baseline]
        same = sum(1 for sample in shared if actions[sample] == baseline[sample])
        report[model_id] = {
            "compared": len(shared),
            "same_action": same,
            "rate": (same / len(shared)) if shared else None,
            "means_correct": False,
        }
    return report


def _quality(rows: Sequence[Mapping], known: Mapping) -> dict:
    if not known:
        return {"status": "incomplete", "reason": "no_verified_outcomes"}
    judged = 0
    matched = 0
    avoided = 0
    unfavorable = 0
    for row in rows:
        outcome = known.get(row.get("sample_id"))
        if outcome is None or row.get("valid") is not True:
            continue
        judged += 1
        if row.get("action") == outcome["label"]:
            matched += 1
        if outcome.get("unfavorable") is True:
            unfavorable += 1
            if row.get("action") == "NO_TRADE":
                avoided += 1
    if judged == 0:
        return {"status": "incomplete", "reason": "no_overlapping_outcomes"}
    return {
        "status": "simulated_labels_only",
        "judged": judged,
        "matched_label": matched,
        "unfavorable": unfavorable,
        "avoided_unfavorable": avoided,
        "live_market_verified": False,
    }
