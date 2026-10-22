#!/usr/bin/env python3
"""Read-only evidence audit. Public output is a fixed aggregate allowlist only."""
import argparse
from collections import Counter, defaultdict
import datetime as dt
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import sys

START = 1792620000000  # 2026-10-21T22:00:00Z
END = START + 86400000
SCOPE = "profit_review_evidence_aggregate_only"
MAX_FILE = 32*1024*1024
MAX_TOTAL = 64*1024*1024


class Blocked(ValueError):
    pass


def need(ok, code):
    if not ok: raise Blocked(code)


def num(v):
    return type(v) in (int, float) and math.isfinite(v)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def decode(raw):
    def pairs(values):
        out = {}
        for k, v in values:
            need(k not in out, "duplicate_json_key")
            out[k] = v
        return out
    def reject(_): raise Blocked("nonfinite_json")
    def real(v):
        out = float(v); need(math.isfinite(out), "nonfinite_json"); return out
    try: return json.loads(raw, object_pairs_hook=pairs, parse_constant=reject, parse_float=real)
    except (ValueError, UnicodeError, RecursionError): raise Blocked("invalid_json") from None


def jsonl(raw):
    need(bool(raw) and raw.endswith(b"\n"), "truncated_jsonl")
    result = []
    for line in raw.splitlines():
        need(0 < len(line) <= 1024*1024, "invalid_jsonl_line")
        value = decode(line); need(isinstance(value, dict), "nonobject_event"); result.append(value)
    need(len(result) <= 300000, "too_many_rows")
    return result


def read(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        need(os.fstat(stream.fileno()).st_size <= MAX_FILE, "oversize_file")
        raw = stream.read(MAX_FILE+1)
    need(0 < len(raw) <= MAX_FILE, "empty_or_oversize_file")
    return raw


def bucket(roi):
    if not num(roi): return "unknown"
    return "negative" if roi < 0 else "0_to_25" if roi < 25 else "25_to_50" if roi < 50 else "50_to_100" if roi < 100 else "100_plus"


def hist(values, bins):
    counts = Counter()
    for v in values:
        label = "unknown"
        if num(v):
            label = next((name for limit, name in bins if v < limit), "highest")
        counts[label] += 1
    return dict(counts)


def identity(row, run=None):
    key = (row.get("run_no", run), row.get("id"), row.get("symbol"), row.get("open_ms", row.get("ts")))
    need(type(key[0]) is int and type(key[1]) is int and isinstance(key[2], str)
         and type(key[3]) is int, "invalid_position_identity")
    return key


def sidecar_bodies(raws):
    previous, seq, bodies = "0"*64, 0, []
    for raw in raws:
        for envelope in jsonl(raw):
            body = envelope.get("body"); need(isinstance(body, dict), "invalid_sidecar_envelope")
            seq += 1
            expected = sha(canonical([previous, seq, body]))
            need(envelope.get("sequence") == seq and envelope.get("previous") == previous
                 and envelope.get("hash") == expected, "sidecar_hash_chain_mismatch")
            previous = expected; bodies.append(body)
    return bodies


def current_roi(state, pos, now):
    main = state.get("main", {}); limits = main.get("limits", {})
    mark_at = state.get("last_prices_ms")
    if type(mark_at) is not int or not 0 <= now-mark_at <= 2700000:
        return None
    px = state.get("last_prices", {}).get(pos.get("symbol"))
    fields = [px, pos.get("entry"), pos.get("qty"), pos.get("fee_open"), pos.get("margin"),
              limits.get("fee_bp_side"), limits.get("slip_bp_side"), limits.get("funding_bp_8h_long")]
    if not all(num(v) for v in fields) or pos.get("side") not in (-1, 1): return None
    px, entry, qty, fee, reference, fee_bp, slip_bp, fund_bp = fields
    levels = pos.get("dca_levels", [])
    if not isinstance(levels, list) or any(not num(d.get("margin")) for d in levels): return None
    reference += sum(d["margin"] for d in levels)
    if reference <= 0 or entry <= 0 or qty <= 0 or type(pos.get("open_ms")) is not int: return None
    side = pos["side"]; fill = px*(1-side*slip_bp/10000)
    partials = [r for r in main.get("closed", []) if r.get("id") == pos.get("id")
                and r.get("symbol") == pos.get("symbol") and r.get("open_ms") == pos["open_ms"]
                and r.get("partial") is True]
    if any(not num(r.get("net")) for r in partials): return None
    realized = sum(r["net"] for r in partials)
    funding = qty*entry*fund_bp/10000*max(0, mark_at-pos["open_ms"])/28800000 if side == 1 else 0
    return 100*(realized + side*(fill-entry)*qty-fee-qty*fill*fee_bp/10000-funding)/reference


def seasonal_bonus(row):
    # Reconstruction is conditional on a reviewed historical version and pinned source.
    if row.get("code_version") not in {"5818aee","b4709d1","b6b9911","fa3e220","4aabeb8"}:
        return None, "unreviewed_version"
    source = Path(__file__).resolve().parents[2]/"backend/desk/seasonal.py"
    if sha(source.read_bytes()) != "47c12da1abbe51be0c826fc03b7609af40407e2e101911ded3444def5d6912c7":
        return None, "source_not_pinned"
    spec = importlib.util.spec_from_file_location("audit_seasonal",source)
    module = importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    sea=module.get_seasonal(row["symbol"],row["ts"])
    side=row.get("side")
    bonus=sea.long_bonus if side==1 else sea.short_bonus if side==-1 else None
    score=(row.get("features") or {}).get("sig_long" if side==1 else "sig_short")
    return bonus, "capped_increment_unknown" if score==100 and bonus else "reconstructed_not_directly_logged"


def audit_bot(events, state, heartbeat, bodies, now):
    end = min(END, now+1)
    need(heartbeat.get("exec_mode") == "paper", "paper_not_confirmed")
    need(heartbeat.get("cycle_running") is False and heartbeat.get("last_ok") is True, "cycle_not_consistent")
    need(type(heartbeat.get("ts")) in (int,float) and 0 <= now-heartbeat["ts"]*1000 <= 120000,
         "stale_heartbeat")
    need(all(r.get("schema") == 1 and r.get("portfolio") == heartbeat.get("portfolio") for r in events),
         "mixed_or_unknown_event_schema")
    calls = [r for r in events if r.get("ev") == "claude_call" and type(r.get("ts")) is int and START <= r["ts"] < end]
    opens = {}
    for r in events:
        if r.get("ev") == "open":
            key = identity(r); need(key not in opens, "duplicate_open"); opens[key] = r
    closes = defaultdict(list)
    for r in events:
        if r.get("ev") == "close":
            key = identity(r); closes[key].append(r)
    active = {k:r for k,r in opens.items() if k[3] < end and
              not any(c.get("partial") is not True and num(c.get("ts")) and c["ts"] < START for c in closes[k])}
    cohorts = Counter(); opening_counts = Counter(); scores = defaultdict(lambda:{"long":[], "short":[], "bonus":[], "bonus_state":[]})
    for key, row in opens.items():
        if not START <= key[3] < end: continue
        side = "long" if row.get("side") == 1 else "short" if row.get("side") == -1 else "unknown"
        source = row.get("source") if row.get("source") in ("rules", "claude") else "other"
        version = row.get("code_version")
        version = version if isinstance(version,str) and re.fullmatch(r"[a-f0-9]{7,40}",version) else "unknown"
        group = (side, source, version); opening_counts[group] += 1
        f = row.get("features") or {}
        scores[group]["long"].append(f.get("sig_long")); scores[group]["short"].append(f.get("sig_short"))
        # Existing logs lack numeric applied bonus. Do not silently invent it from a present-day table.
        bonus, status=seasonal_bonus(row)
        scores[group]["bonus"].append(bonus); scores[group]["bonus_state"].append(status)
    roi_positions, checkpoint_counts, roi_crossings = defaultdict(set), Counter(), defaultdict(list)
    for b in bodies:
        at = b.get("asof_ms")
        if b.get("ev") != "cycle" or type(at) is not int or not START <= at < end: continue
        need(b.get("applied") is False and b.get("mode") == "ombra", "sidecar_not_shadow")
        for p in b.get("positions", []):
            snap = p.get("snapshot", {}); key = identity(snap, b.get("run_no"))
            if key not in active: continue
            roi = p.get("roi", {}); value = roi.get("roi")
            if not num(value): value = p.get("liquidable_now", {}).get("roi_pct")
            roi_positions[bucket(value)].add(key)
            if num(value) and value >= 50: roi_crossings[key].append(at)
            label = roi.get("checkpoint")
            if label in ("CHIUDI_O_PARZIALE", "LASCIA_CORRERE", "DATI_NON_VALIDI"):
                checkpoint_counts[(label,bucket(value),str((at-START)//3600000))] += 1
    cap = heartbeat.get("daily_cap_usd"); budget = state.get("budget", {}); spent = budget.get("spent")
    current_budget_state = "unknown"
    if num(cap) and cap > 0 and num(spent):
        ratio = spent/cap
        current_budget_state = "below_90pct" if ratio < .90 else "90_to_95pct" if ratio < .95 else "95_to_100pct" if ratio <= 1 else "over_100pct"
    current = state.get("main", {}).get("positions", {})
    need(heartbeat.get("open_positions")==len(current),"state_heartbeat_position_mismatch")
    current_roi_counts = Counter(); verified_hold_lower_bound = 0
    call_times = {r["ts"] for r in calls if r.get("ok") is True}
    for p in current.values():
        current_roi_counts[bucket(current_roi(state,p,now))] += 1
        if p.get("last_review_ms") in call_times and p.get("last_review_ms",0) > p.get("open_ms",0):
            verified_hold_lower_bound += 1
    # Exact per-position historical actions/omissions are not logged by the current bot.
    # Publish distributions of call opportunities, not fabricated management decisions.
    for key in active:
        final = min([c["ts"] for c in closes[key] if c.get("partial") is not True and type(c.get("ts")) is int] or [end])
        opportunities = sum(r.get("ok") is True and key[3] <= r["ts"] < final for r in calls)
        cohorts["0" if opportunities == 0 else "1" if opportunities == 1 else "2_plus"] += 1
    score_bins = [(40,"under_40"),(60,"40_to_60"),(63,"60_to_63"),(70,"63_to_70"),(101,"70_to_100")]
    return {"positions_active_during_window":len(active),
        "opens": [{"side":k[0],"source":k[1],"version":k[2],"n":n,
                   "long_score_bands":hist(scores[k]["long"],score_bins),
                   "short_score_bands":hist(scores[k]["short"],score_bins),
                   "nominal_bonus_reconstruction":dict(Counter("unknown" if not num(v) else "0" if v==0 else "1_to_4" if v<5 else "5_to_9" if v<10 else "10_to_15" for v in scores[k]["bonus"])),
                   "bonus_evidence":dict(Counter(scores[k]["bonus_state"]))} for k,n in sorted(opening_counts.items())],
        "recorded_exit_events_actor_unknown":dict(Counter("partial" if c.get("partial") is True else "close" for k in active for c in closes[k] if type(c.get("ts")) is int and START <= c["ts"] < end)),
        "claude_calls":len(calls),"claude_calls_parsed":sum(r.get("ok") is True for r in calls),
        "call_opportunities_per_position_bands":dict(cohorts),
        "current_positions_with_timestamp_matched_hold_lower_bound":verified_hold_lower_bound,
        "exact_historical_management_actions":None,"exact_omitted_positions":None,
        "unidentifiable_reason":"successful_per_position_decisions_not_persisted",
        "sidecar_checkpoint_bands":[{"decision":k[0],"roi_band":k[1],"local_day_hour_offset":int(k[2]),"n":v}
                                    for k,v in sorted(checkpoint_counts.items())],
        "sidecar_distinct_positions_by_roi_band":{k:len(v) for k,v in roi_positions.items()},
        "positions_observed_at_or_above_50pct":len(roi_crossings),
        "positions_above_50_without_recorded_structured_claude_review":None,
        "no_review_caused_by_budget":None,"budget_block_start_ms":None,
        "causal_budget_reason":"historical_skip_and_per_position_review_log_missing",
        "last_recorded_claude_call_ms":max((r["ts"] for r in calls),default=None),
        "runtime_budget_band":current_budget_state,
        "current_above50_and_below_call_reserve_cooccurrence":(sum(v for k,v in current_roi_counts.items() if k in ("50_to_100","100_plus")) if num(cap) and num(spent) and spent >= cap-.04 else 0),
        "runtime_budget_day_matches_utc_today":budget.get("day")==dt.datetime.fromtimestamp(now/1000,dt.timezone.utc).strftime("%Y-%m-%d"),
        "runtime_mode":heartbeat.get("mode") if heartbeat.get("mode") in ("running","paused","halted") else "other",
        "runtime_calendar_allowed":((heartbeat.get("claude_schedule") or {}).get("allowed")
                                    if type((heartbeat.get("claude_schedule") or {}).get("allowed")) is bool else None),
        "runtime_observation_within_window":START <= now < END,
        "current_positions_roi_bands":dict(current_roi_counts),
        "roi_definition":"sidecar_lifecycle_net_over_initial_plus_DCA_reference_margin",
        "exit_events_do_not_identify_decider":"source_on_close_is_entry_source"}


def audit_ai(cycles, trades, now):
    end = min(END,now+1); rows = [r for r in cycles if type(r.get("ts_ms")) is int and START <= r["ts_ms"] < end]
    fills = Counter(); actions = Counter()
    for r in rows:
        for e in r.get("events",[]):
            if e.get("ev") == "fill": fills["long" if e.get("side")==1 else "short" if e.get("side")==-1 else "unknown"] += 1
            if e.get("ev") in ("exit","exit_parziale","stop_spostato"): actions[e["ev"]] += 1
    final = [r for r in trades if type(r.get("close_ms")) is int and START <= r["close_ms"] < end and r.get("partial") is not True]
    return {"cycles":len(rows),"called":sum((r.get("decision") or {}).get("called") is True for r in rows),
            "virtual_fills_by_side":dict(fills),"virtual_management_events":dict(actions),
            "closed_rows":len(final),"winning_closed_rows":sum(num(r.get("net")) and r["net"]>0 for r in final),
            "contribution_to_hawk_bull":"none_by_architecture","applied_to_bots":False}


def run(data_root,sidecar_root,ai_root,now):
    roots = [Path(p) for p in (data_root,sidecar_root,ai_root)]
    for p in roots: need(p.absolute()==p.resolve(),"noncanonical_root")
    paths = {}; missing = []
    for bot in ("hawk","bull"):
        folder=Path(data_root)/bot;need(folder.resolve()==folder.absolute(),"noncanonical_root")
        for name in ("learning_log.jsonl","heartbeat.json","state_v2.json"):
            paths[f"{bot}_{name}"] = Path(data_root)/bot/name
        folder = Path(sidecar_root)/bot; need(folder.resolve()==folder.absolute(),"noncanonical_root")
        parts = sorted(folder.glob("events-*.jsonl"))
        if not parts: missing.append(bot+"_sidecar")
        for i,p in enumerate(parts,1):
            need(p.name==f"events-{i:08d}.jsonl","sidecar_segment_gap"); paths[f"{bot}_sidecar_{i}"]=p
    ai_folder = Path(ai_root)/"ai"; need(ai_folder.resolve()==ai_folder.absolute(),"noncanonical_root")
    for kind in ("cycles","trades"):
        for day in ("2026-10-21","2026-10-22"):
            path=ai_folder/f"{kind}-{day}.jsonl"
            if path.exists() or path.is_symlink(): paths[f"ai_{kind}_{day}"]=path
            else: missing.append(f"ai_{kind}_{day}")
    raw = {}; total=0
    for k,p in paths.items():
        raw[k]=read(p);total+=len(raw[k]);need(total<=MAX_TOTAL,"oversize_snapshot")
    out = {"schema":1,"scope":SCOPE,"applied":False,"window_start_ms":START,"window_end_ms":END,
           "observed_until_ms":min(now,END),"missing_sources":missing,"bots":{}}
    for bot in ("hawk","bull"):
        state=decode(raw[f"{bot}_state_v2.json"]); hb=decode(raw[f"{bot}_heartbeat.json"])
        need(hb.get("portfolio")==bot,"mixed_portfolio")
        bodies=sidecar_bodies([v for k,v in raw.items() if k.startswith(bot+"_sidecar_")])
        out["bots"][bot]=audit_bot(jsonl(raw[f"{bot}_learning_log.jsonl"]),state,hb,bodies,now)
    out["ai_shadow"]=audit_ai([r for k,v in raw.items() if k.startswith("ai_cycles_") for r in jsonl(v)],
                               [r for k,v in raw.items() if k.startswith("ai_trades_") for r in jsonl(v)],now)
    out["input_sha256"]={k:sha(v) for k,v in raw.items()}
    for k,p in paths.items(): need(read(p)==raw[k],"input_changed_during_audit")
    # A rotation/new daily file can leave all old bytes unchanged: detect it too.
    for bot in ("hawk","bull"):
        expected={p.name for k,p in paths.items() if k.startswith(bot+"_sidecar_")}
        need({p.name for p in (Path(sidecar_root)/bot).glob("events-*.jsonl")}==expected,"input_manifest_changed")
    for kind in ("cycles","trades"):
        for day in ("2026-10-21","2026-10-22"):
            path=ai_folder/f"{kind}-{day}.jsonl"
            need((path.exists() or path.is_symlink()) == (f"ai_{kind}_{day}" in paths),"input_manifest_changed")
    return out


def main():
    p=argparse.ArgumentParser();p.add_argument("--data-root",required=True);p.add_argument("--sidecar-root",required=True);p.add_argument("--ai-root",required=True)
    args=p.parse_args()
    try:
        now=int(dt.datetime.now(dt.timezone.utc).timestamp()*1000)
        need(now>=START,"window_not_started")
        print(json.dumps(run(args.data_root,args.sidecar_root,args.ai_root,now),allow_nan=False,sort_keys=True))
    except Blocked as e: print("PROFIT_AUDIT_BLOCKED="+str(e),file=sys.stderr);return 2
    except Exception: print("PROFIT_AUDIT_BLOCKED=input_or_runtime_failure",file=sys.stderr);return 2
    return 0

if __name__=="__main__": raise SystemExit(main())
