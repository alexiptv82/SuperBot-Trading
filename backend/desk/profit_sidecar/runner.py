"""Shadow cycle processing and the polling loop. Observation only.

Reads a bot's data directory read-only, never writes anything but its own journal directory and a
small status file there. One committed journal line per processed bot cycle carries the snapshots,
the Profit Manager evaluations, the actual outcomes and the restart cache together, so a crash can
never leave the cache ahead of or behind the events.
"""
from dataclasses import asdict
import json
import os
import sys
import time

from ..profit import ledger, policy_bull, policy_hawk
from ..profit.features import Features, extract
from ..profit.liquidable import evaluate
from ..profit.machine import State, step
from ..profit.reversal import assess
from . import roi_variants
from .accounting import closed_records, identity, snapshot
from .candles import INTERVAL_MS, fetch_bars
from .common import Freeze, sha
from .journal import Journal
from .reader import read_consistent

POLICIES = {"hawk": policy_hawk.research_policy, "bull": policy_bull.research_policy}
MAX_BAR_AGE_MS = 20 * 60 * 1000


def _invalid_features(snap, reason):
    return Features(0, snap["price"], 0, 0, 0, 50, False, False, "unknown",
                    snap["asof_ms"] - snap["open_ms"], 0, False, reason)


def _evaluate_position(portfolio, run_no, pos, snap, view, costs, prudent, cached, *, pm_policy, roi_policy, bars_for, code_version):
    side = pos["side"]
    machine_before = State(**cached["pm"]) if cached and cached.get("pm") else State()
    roi_before = roi_variants.RoiState(**cached["roi"]) if cached and cached.get("roi") else roi_variants.RoiState()
    try:
        bars = bars_for(pos["symbol"], snap["asof_ms"])
        peak_ms = min(max(machine_before.peak_ms, snap["open_ms"]), snap["asof_ms"])
        features = extract(bars, asof_ms=snap["asof_ms"], opened_ms=snap["open_ms"], peak_ms=peak_ms,
                           interval_ms=INTERVAL_MS, max_age_ms=MAX_BAR_AGE_MS)
    except Freeze as exc:
        features = _invalid_features(snap, str(exc))
    except ValueError:
        features = _invalid_features(snap, "bars_rejected")
    liquidation = evaluate(view, snap["price"], costs)
    prudent_liquidation = evaluate(view, snap["price"], prudent)
    reversal = assess(features, side)
    decision = step(machine_before, features=features, liquidation=liquidation, qty=snap["aggregate_leg"]["qty"],
                    reversal=reversal, policy=pm_policy)
    event = ledger.evaluation(portfolio=portfolio, run_no=run_no, position_key=snap["position_key"], ts_ms=snap["asof_ms"],
                              code_version=code_version, policy=pm_policy, before=machine_before, decision=decision,
                              features=features, liquidation=liquidation, reversal=reversal)
    credible = reversal.score >= pm_policy.reversal_threshold and len(set(reversal.families)) >= 2
    roi_after, roi_decision = roi_variants.step(roi_before, roi=liquidation.roi_pct, eval_ms=snap["asof_ms"],
                                                credible_reversal=credible, features_valid=features.valid, policy=roi_policy)
    if roi_decision.get("checkpoint"):
        roi_decision["market_at_checkpoint"] = {"regime": features.regime, "rsi": features.rsi, "ema_slope": features.ema_slope,
                                                "atr": features.atr, "families": list(reversal.families), "valid": features.valid}
    record = {"snapshot": snap, "pm_eval": event, "roi": roi_decision,
              "prudent_exit": {"net_usd": prudent_liquidation.net_usd, "roi_pct": prudent_liquidation.roi_pct},
              "liquidable_now": {"net_usd": liquidation.net_usd, "roi_pct": liquidation.roi_pct}}
    return record, {"pm": asdict(decision.state), "roi": asdict(roi_after)}


def process_cycle(journal, obs, *, portfolio, bars_for, code_version, pm_policy=None, roi_policy=None):
    """Journal one bot cycle. Returns True when a new line was committed, False when already there."""
    pm_policy = pm_policy or POLICIES[portfolio]()
    roi_policy = roi_policy or roi_variants.RoiPolicy()
    event_id = sha(["cycle", obs.cycle_key])
    if event_id in journal.ids:
        return False
    cache = journal.cache.get(portfolio) or {}
    if cache.get("run_key") != obs.run_key:      # a new run (reset): nothing carries over
        cache = {"run_key": obs.run_key, "closed_hashes": [], "positions": {}, "last_cycle": None, "last_cycle_end_ms": None}
    hashes, outcomes = closed_records(obs, cache["closed_hashes"])
    run_no = obs.state["run_no"]
    cycles = obs.heartbeat["cycles"]
    positions, new_cache_positions, freezes = [], {}, []
    for symbol, pos in obs.state["main"]["positions"].items():
        try:
            key = identity(obs.run_key, pos)
        except Freeze as exc:
            freezes.append({"symbol": str(symbol), "reason": str(exc)})
            continue
        cached = cache["positions"].get(key)
        try:
            snap, view, costs, prudent = snapshot(obs, pos, previous_cycle_end=cache.get("last_cycle_end_ms"))
            record, new_state = _evaluate_position(portfolio, run_no, pos, snap, view, costs, prudent, cached,
                                                   pm_policy=pm_policy, roi_policy=roi_policy, bars_for=bars_for, code_version=code_version)
            positions.append(record)
            new_cache_positions[key] = new_state
        except (Freeze, ValueError) as exc:
            freezes.append({"position_key": key, "symbol": str(symbol), "reason": str(exc) if isinstance(exc, Freeze) else "invalid_input"})
            if cached:
                new_cache_positions[key] = cached        # keep the last good state; never invent one
    last = cache.get("last_cycle")
    body = {"event_id": event_id, "ev": "cycle", "portfolio": portfolio, "run_key": obs.run_key, "run_no": run_no,
            "cycle_key": obs.cycle_key, "cycle": cycles, "asof_ms": obs.asof_ms,
            "cycles_skipped": 0 if last is None else max(0, cycles - last - 1),
            "bot_version": obs.heartbeat.get("version"), "sidecar_version": code_version, "state_hash": obs.state_hash,
            "mode": "ombra", "applied": False, "pm_config_hash": pm_policy.config_hash, "roi_config_hash": roi_policy.config_hash,
            "positions": positions, "outcomes": outcomes, "freezes": freezes,
            "cache": {"run_key": obs.run_key, "closed_hashes": hashes, "positions": new_cache_positions,
                      "last_cycle": cycles, "last_cycle_end_ms": obs.asof_ms}}
    return journal.append(body)


def _write_status(root, status):
    path = os.path.join(root, "status.json")
    tmp = path + ".tmp"
    with open(tmp, "w") as stream:
        json.dump(status, stream, sort_keys=True)
    os.replace(tmp, path)


def poll_once(source, journal, *, portfolio, now_ms, bars_for, code_version, memo):
    """One polling step for one bot. Never raises: every outcome ends in journal or status."""
    try:
        obs = read_consistent(source, portfolio, now_ms)
        done = process_cycle(journal, obs, portfolio=portfolio, bars_for=bars_for, code_version=code_version)
        reason = None
        if done:
            memo["last_success_ms"] = now_ms
    except Freeze as exc:
        reason = str(exc)
    except Exception as exc:                      # unexpected: report the class only, never data
        reason = "unexpected_" + type(exc).__name__
    # Transient reasons (cycle running, between cycles) are not journaled every minute: only changes.
    if reason is not None and reason != memo.get("last_freeze"):
        try:
            journal.append({"event_id": sha(["freeze", portfolio, reason, now_ms]), "ev": "freeze", "portfolio": portfolio,
                            "ts_ms": now_ms, "reason": reason})
        except Exception:
            print(f"[sidecar:{portfolio}] cannot journal freeze {reason}", file=sys.stderr, flush=True)
    memo["last_freeze"] = reason
    try:
        _write_status(journal.root, {"ts_ms": now_ms, "portfolio": portfolio, "last_success_ms": memo.get("last_success_ms"),
                                     "freeze": reason, "sequence": journal.sequence, "mode": "ombra"})
    except OSError:
        print(f"[sidecar:{portfolio}] cannot write status", file=sys.stderr, flush=True)
    return reason


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description="Profit Manager shadow observer (read-only on bot data).")
    parser.add_argument("--bot", action="append", required=True, choices=("hawk", "bull"))
    parser.add_argument("--data-root", required=True, help="parent of the hawk/ and bull/ data directories (mounted read-only)")
    parser.add_argument("--out-root", required=True, help="own output directory (writable)")
    parser.add_argument("--interval", type=int, default=60)
    parser.add_argument("--code-version", default=os.environ.get("SIDECAR_SHA", "unknown"))
    args = parser.parse_args(argv)
    journals = {bot: Journal(os.path.join(args.out_root, bot)) for bot in args.bot}
    memos = {bot: {} for bot in args.bot}
    try:
        while True:
            now_ms = int(time.time() * 1000)
            for bot in args.bot:
                poll_once(os.path.join(args.data_root, bot), journals[bot], portfolio=bot, now_ms=now_ms,
                          bars_for=lambda symbol, asof_ms: fetch_bars(symbol, asof_ms=asof_ms),
                          code_version=args.code_version, memo=memos[bot])
            time.sleep(max(15, args.interval))
    finally:
        for journal in journals.values():
            journal.close()


if __name__ == "__main__":
    main()
