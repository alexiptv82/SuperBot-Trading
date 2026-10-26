"""Bounded, replayable episodic memory derived only from Brain SQLite events.

Observational evidence, never a strategy/risk editor or another model call.
All writes are performed by Store in its existing state/event transaction.
"""
from collections import defaultdict
import copy
import hashlib
import json
import math
import re

VERSION = 1
POLICY = "brain-learning-v1"
DAY = 86400000
MAX_EPISODES = 500
BATCH = 1000
WINDOW = 90 * DAY
FRESH = 7 * DAY
MAX_CONTEXT_CHARS = 14000
MIN_SAMPLE = 12


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()[:20]


def entry_context(summary, model="unknown", references=()):
    """Whitelist factual entry features; never infer old regimes from today's data."""
    trends = summary.get("trend", {})
    daily, four = trends.get("1d"), trends.get("4h")
    regime = daily if daily == four and daily in ("up", "down") else (
        "mixed" if daily in ("up", "down", "flat") and four in ("up", "down", "flat") else "unknown")
    model = model if isinstance(model, str) and re.fullmatch(r"[A-Za-z0-9_.:/-]{1,100}", model) else "unknown"
    return {"policy": POLICY, "regime": regime, "model": model,
            "lesson_ids": [v for v in references if isinstance(v, str) and re.fullmatch(r"[a-f0-9]{20}", v)][:6]}


def context(value):
    value = value if isinstance(value, dict) else {}
    policy = value.get("policy")
    regime = value.get("regime")
    if policy != POLICY or regime not in ("up", "down", "mixed"):
        return {"policy": "legacy_unknown", "regime": "unknown", "model": "unknown", "lesson_ids": []}
    # Reuse the whitelist; do not relay AI reasoning/free text as memory instructions.
    return entry_context({"trend": {"1d": regime, "4h": regime}} if regime != "mixed" else
                         {"trend": {"1d": "up", "4h": "down"}}, value.get("model"), value.get("lesson_ids", []))


def empty():
    return {"version": VERSION, "cursor": 0, "records": 0, "invalid": 0,
            "duplicates": 0, "completed_total": 0, "pending": {}, "episodes": [], "caught_up": False}


def position_key(row):
    if (row.get("account") != "brain-paper" or not isinstance(row.get("id"), int) or
        isinstance(row.get("id"), bool) or row["id"] < 1 or row.get("side") not in (-1, 1) or
        isinstance(row.get("side"), bool) or not isinstance(row.get("symbol"), str) or
        not re.fullmatch(r"[A-Z0-9]{1,20}", row["symbol"]) or
        not finite(row.get("open_ms")) or row["open_ms"] < 0):
        raise ValueError("invalid_position_identity")
    return digest([row["account"], row["id"], row["open_ms"], row["symbol"], row["side"]])


def ingest(memory, row):
    key = position_key(row)
    if (not finite(row.get("close_ms")) or row["close_ms"] < row["open_ms"] or
        not finite(row.get("net")) or abs(row["net"]) > 1e12 or
        not isinstance(row.get("partial", False), bool)):
        raise ValueError("invalid_realization")
    if any(e["id"] == key for e in memory["episodes"]):
        memory["duplicates"] += 1
        return
    fingerprint = digest(row)
    part = memory["pending"].get(key)
    if part and fingerprint in part["fingerprints"]:
        memory["duplicates"] += 1
        return
    if not part:
        if len(memory["pending"]) >= 1000:
            raise ValueError("incomplete_episode_capacity")
        risk = row.get("risk_plan_usd")
        part = {"id": key, "symbol": row["symbol"], "side": row["side"], "open_ms": row["open_ms"],
                "net": 0., "risk": risk if finite(risk) and risk > 0 else None,
                "context": context(row.get("learning_context")), "fingerprints": [], "parts": 0,
                "mfe_r": None, "mae_r": None, "last_close_ms": row["open_ms"]}
    else:
        part = copy.deepcopy(part)
    if row["close_ms"] < part["last_close_ms"] or len(part["fingerprints"]) >= 100:
        raise ValueError("invalid_episode_order_or_capacity")
    part["net"] += row["net"]
    part["parts"] += 1
    part["last_close_ms"] = row["close_ms"]
    part["fingerprints"].append(fingerprint)
    for name in ("mfe_r", "mae_r"):
        value = row.get(name)
        if finite(value) and 0 <= value <= 10000:
            part[name] = max(part[name] or 0, value)
    memory["pending"][key] = part
    if not row.get("partial", False):
        part.pop("fingerprints")
        part["close_ms"] = row["close_ms"]
        part["net_r"] = part["net"] / part["risk"] if part["risk"] else None
        # Reasons are classified, never copied verbatim into a future prompt.
        why = row.get("why", "")
        part["exit"] = "ai_close" if isinstance(why, str) and why.startswith("brain:") else (
            "stop_loss" if why in ("SL", "stop_loss") else "take_profit" if why in ("TP", "take_profit") else "other")
        memory["pending"].pop(key)
        memory["episodes"].append(part)
        memory["episodes"].sort(key=lambda e: (e["close_ms"], e["id"]))
        memory["episodes"] = memory["episodes"][-MAX_EPISODES:]
        memory["completed_total"] += 1


def advance(db, saved):
    """Read incremental authoritative events. Caller owns the transaction.

    A corrupt/version-unknown cache is rebuilt, never the portfolio or history.
    Backfill is bounded; lessons stay unavailable until the cursor catches up.
    """
    memory = copy.deepcopy(saved) if isinstance(saved, dict) and saved.get("version") == VERSION else empty()
    if not all(k in memory for k in empty()):
        memory = empty()
    rows = db.execute("SELECT seq,body FROM events WHERE seq>? AND kind='trade' ORDER BY seq LIMIT ?",
                      (memory["cursor"], BATCH + 1)).fetchall()
    for seq, body in rows[:BATCH]:
        try:
            row = json.loads(body)
            ingest(memory, row)
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
            memory["invalid"] += 1
        memory["cursor"] = seq
        memory["records"] += 1
    memory["caught_up"] = len(rows) <= BATCH
    return memory


def metrics(rows):
    count = len(rows)
    wins = sum(e["net"] > 0 for e in rows)
    p = wins / count
    z = 1.96
    center = (p + z*z/(2*count)) / (1 + z*z/count)
    half = z * math.sqrt(p*(1-p)/count + z*z/(4*count*count)) / (1+z*z/count)
    return {"n": count, "wins": wins, "win_rate": round(p, 4),
            "win_rate_95pct": [round(center-half, 4), round(center+half, 4)],
            "mean_net_r": round(sum(e["net_r"] for e in rows)/count, 4),
            "net_paper_usd": round(sum(e["net"] for e in rows), 4)}


def build_view(memory, summaries, now_ms):
    """As-of view: completed episodes only, chronological holdout, no text mining.

    Minimums, windows and Wilson checks are experimental engineering defaults,
    not proof of predictive edge. Repeated holdouts are not an independent trial.
    """
    base = {"version": VERSION, "status": "insufficient_data", "as_of_ms": now_ms,
            "scope": "Brain PAPER only; observational evidence, not causal or guaranteed",
            "records_processed": memory.get("records", 0), "invalid_records": memory.get("invalid", 0),
            "completed_total": memory.get("completed_total", 0), "lessons": [], "cases": []}
    if not memory.get("caught_up"):
        base["status"] = "backfilling"
        return base
    rows = [e for e in memory["episodes"] if now_ms-WINDOW <= e["close_ms"] <= now_ms]
    base["window_completed"] = len(rows)
    base["window_days"] = WINDOW//DAY
    base["retention_cap"] = MAX_EPISODES
    base["incomplete_positions"] = len(memory["pending"])
    # Separate legacy/model/policy cohorts; never label their entry regime retroactively.
    groups = defaultdict(list)
    for e in rows:
        ctx = e["context"]
        if ctx["regime"] != "unknown" and finite(e["net_r"]) and abs(e["net_r"]) <= 10000:
            groups[(e["side"], ctx["regime"], ctx["policy"], ctx["model"])].append(e)
    relevant = {entry_context(s)["regime"] for s in summaries.values()} - {"unknown"}
    candidates = []
    for cohort, episodes in sorted(groups.items()):
        side, regime, policy, model = cohort
        if regime not in relevant or len(episodes) < MIN_SAMPLE or now_ms-episodes[-1]["close_ms"] > FRESH:
            continue
        split = len(episodes)*2//3
        train, holdout = episodes[:split], episodes[split:]
        # Purge positions overlapping the holdout: training outcomes must have
        # been known before the first evaluation entry (no temporal leakage).
        first_entry = min(e["open_ms"] for e in holdout)
        train = [e for e in train if e["close_ms"] < first_entry]
        if (len(train) < 8 or len(holdout) < 4 or
            len({e["close_ms"]//DAY for e in episodes}) < 3 or
            len({e["close_ms"]//DAY for e in holdout}) < 2):
            continue
        training, validation = metrics(train), metrics(holdout)
        harmful = training["mean_net_r"] < 0 and validation["mean_net_r"] < 0 and validation["win_rate_95pct"][1] < .5
        favorable = training["mean_net_r"] > 0 and validation["mean_net_r"] > 0 and validation["win_rate_95pct"][0] > .5
        if not (harmful or favorable):
            continue
        used = train + holdout
        identity = digest([cohort, [e["id"] for e in used]])
        candidates.append({"id": identity, "side": "LONG" if side == 1 else "SHORT", "regime": regime,
            "policy": policy, "model": model, "finding": "historical_weakness" if harmful else "historical_strength",
            "instruction": "Recheck current supporting AND contrary evidence; never force a direction or override risk limits.",
            "training": training, "later_validation": validation, "last_close_ms": episodes[-1]["close_ms"],
            "expires_ms": episodes[-1]["close_ms"]+FRESH,
            "evidence_ids": [e["id"] for e in used[-5:]],
            "limitations": "Small, correlated observational sample; repeated chronological holdout, no predictive certification."})
    base["lessons"] = sorted(candidates, key=lambda x: (-x["last_close_ms"], x["id"]))[:6]
    relevant_rows = [e for e in rows if e["context"]["regime"] in relevant]
    for e in relevant_rows[-3:]:
        base["cases"].append({k: e[k] for k in ("id", "symbol", "side", "close_ms", "net", "net_r", "exit", "parts", "mfe_r", "mae_r", "context")})
    if memory.get("invalid", 0):
        # Exclusions can bias a cohort. Fail neutral until the data is reviewed.
        base["lessons"] = []
        base["status"] = "data_quality_warning"
    else:
        base["status"] = "historical_evidence" if base["lessons"] else "insufficient_data"
    exposed = [e for e in rows if e["context"]["lesson_ids"] and finite(e["net_r"])]
    base["subsequent_exposed_outcomes"] = metrics(exposed) if exposed else None
    base["outcome_caveat"] = "Exposure means lesson supplied, not followed; outcomes are not a causal A/B test."
    # Include actual selection coverage, not a lifetime 50/50 target.
    base["direction_counts"] = {"long": sum(e["side"] == 1 for e in rows), "short": sum(e["side"] == -1 for e in rows)}
    if len(json.dumps(base, separators=(",", ":"))) > MAX_CONTEXT_CHARS:
        raise ValueError("learning_prompt_capacity")
    return base
