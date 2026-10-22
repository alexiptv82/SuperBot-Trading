#!/usr/bin/env python3
"""R netto per regime BTC 24h e lato sui trade effettivamente chiusi (sola lettura).

Usa solo dati d'ingresso registrati nell'evento open e chiusure del learning_log.jsonl.
Il regime e' un proxy BTC noto all'ingresso: down < -1%, up > +1%, flat altrimenti.
Somma net_r delle chiusure parziali/finali per (bot, run_no, id); conta solo trade con
una apertura univoca e una chiusura finale. Non stampa simboli, id, prezzi o PnL in $.

Uso: python regime_trade_analysis.py --data-root /data --bots hawk,bull [--json]
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import random
import statistics
import sys
from collections import Counter, defaultdict
from typing import Any

BOOT_N = 4000
BOOT_SEED = 20261022
MIN_DAYS_FOR_CI = 5
THRESHOLD = 0.01


class DuplicateKey(ValueError):
    pass


def _unique_object(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise DuplicateKey(key)
        out[key] = value
    return out


def _reject_constant(value):
    raise ValueError(f"invalid JSON constant: {value}")


def finite_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def read_snapshot(path: str) -> tuple[bytes, str]:
    with open(path, "rb") as f:
        data = f.read()
    return data, hashlib.sha256(data).hexdigest()


def parse_snapshot(data: bytes) -> tuple[list[dict], dict]:
    """Strictly parse one byte snapshot; reject blank, malformed, or unterminated rows."""
    if data and not data.endswith(b"\n"):
        raise ValueError("registro senza newline finale: possibile append troncato")
    events = []
    counts = Counter()
    for number, raw in enumerate(data.splitlines(), 1):
        if not raw.strip():
            counts["blank_lines"] += 1
            raise ValueError(f"riga vuota alla posizione {number}")
        try:
            row = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object,
                             parse_constant=_reject_constant)
        except (UnicodeDecodeError, json.JSONDecodeError, DuplicateKey, ValueError) as exc:
            counts["invalid_json"] += 1
            raise ValueError(f"riga JSON non valida alla posizione {number}") from exc
        if not isinstance(row, dict):
            counts["non_object_rows"] += 1
            raise ValueError(f"riga non-oggetto alla posizione {number}")
        counts["rows"] += 1
        counts[f"event:{row.get('ev', 'missing')}"] += 1
        events.append(row)
    return events, dict(counts)


def classify_regime(roc):
    if not finite_number(roc):
        return None
    roc = float(roc)
    if roc < -THRESHOLD:
        return "down"
    if roc > THRESHOLD:
        return "up"
    return "flat"


def _trade_key(bot: str, row: dict):
    run_no, trade_id = row.get("run_no"), row.get("id")
    if run_no is None or trade_id is None:
        return None
    try:
        hash(run_no)
        hash(trade_id)
    except TypeError:
        return None
    return bot, run_no, trade_id


def build_trades(events: list[dict], bot: str) -> tuple[list[dict], dict]:
    opens = defaultdict(list)
    closes = defaultdict(list)
    excluded = Counter()
    other_events = Counter()
    for row in events:
        ev = row.get("ev")
        if ev not in ("open", "close"):
            other_events[str(ev)] += 1
            continue
        key = _trade_key(bot, row)
        if key is None:
            excluded[f"{ev}_missing_identity"] += 1
            continue
        (opens if ev == "open" else closes)[key].append(row)

    trades = []
    all_keys = set(opens) | set(closes)
    for key in all_keys:
        op = opens.get(key, [])
        cs = closes.get(key, [])
        if len(op) != 1:
            excluded["missing_or_duplicate_open"] += 1
            continue
        if not cs:
            excluded["not_closed"] += 1
            continue
        finals = [c for c in cs if not c.get("partial", False)]
        if len(finals) != 1:
            excluded["no_unique_final_close"] += 1
            continue
        o = op[0]
        close_times = [c.get("ts", c.get("close_ms")) for c in cs]
        open_ts = o.get("ts")
        side = o.get("side")
        feats = o.get("features") if isinstance(o.get("features"), dict) else {}
        roc = feats.get("btc_roc24h")
        if not finite_number(open_ts) or float(open_ts) <= 0:
            excluded["missing_open_time"] += 1
            continue
        if side not in (-1, 1):
            excluded["invalid_side"] += 1
            continue
        regime = classify_regime(roc)
        if regime is None:
            excluded["missing_entry_btc_roc24h"] += 1
            continue
        if any(not finite_number(c.get("net_r")) for c in cs):
            excluded["missing_or_invalid_net_r"] += 1
            continue
        if any(not finite_number(t) for t in close_times):
            excluded["missing_close_time"] += 1
            continue
        if any(float(t) < float(open_ts) for t in close_times):
            excluded["close_precedes_open"] += 1
            continue
        day = dt.datetime.fromtimestamp(float(open_ts) / 1000, tz=dt.timezone.utc).date().isoformat()
        trades.append({"r": sum(float(c["net_r"]) for c in cs),
                       "side": "long" if side == 1 else "short",
                       "regime": regime, "day": day,
                       "partials": sum(bool(c.get("partial", False)) for c in cs)})
    excluded["other_event_types"] = sum(other_events.values())
    excluded["other_event_kinds"] = len(other_events)
    return trades, dict(excluded)


def _cluster_bootstrap(values_by_day: dict[str, list[float]], seed: int = BOOT_SEED):
    days = sorted(values_by_day)
    if len(days) < MIN_DAYS_FOR_CI:
        return None
    rng = random.Random(seed)
    samples = []
    for _ in range(BOOT_N):
        chosen = [rng.choice(days) for _ in days]
        vals = [x for day in chosen for x in values_by_day[day]]
        if vals:
            samples.append(statistics.mean(vals))
    samples.sort()
    return [samples[int(0.025 * (len(samples) - 1))],
            samples[int(0.975 * (len(samples) - 1))]]


def summarize(trades: list[dict]) -> dict:
    if not trades:
        return {"n": 0, "days": 0, "mean_net_R": None, "win_rate": None, "cluster_bootstrap95": None}
    vals = [t["r"] for t in trades]
    by_day = defaultdict(list)
    for t in trades:
        by_day[t["day"]].append(t["r"])
    ci = _cluster_bootstrap(by_day)
    return {"n": len(vals), "days": len(by_day), "mean_net_R": round(statistics.mean(vals), 5),
            "win_rate": round(sum(v > 0 for v in vals) / len(vals), 5),
            "cluster_bootstrap95": [round(x, 5) for x in ci] if ci else None,
            "ci_note": "bootstrap per giorno UTC d'ingresso; esplorativo" if ci else f"IC omesso: meno di {MIN_DAYS_FOR_CI} giorni"}


def analyze(events_by_bot: dict[str, list[dict]], hashes: dict[str, str]) -> dict:
    report = {"kind": "executed_trade_r_by_entry_btc_regime_and_side",
              "method": "actual closed trades; sum additive close.net_r by bot/run/id; regime from open.features.btc_roc24h; down<-1%, up>+1%, flat otherwise; cluster bootstrap by UTC entry date; descriptive, not causal",
              "sources_sha256": hashes, "bots": {}, "groups": {}}
    all_trades = []
    for bot, events in events_by_bot.items():
        trades, excluded = build_trades(events, bot)
        report["bots"][bot] = {"eligible_closed_trades": len(trades), "exclusions": excluded,
                               "overall": summarize(trades)}
        all_trades.extend((bot, t) for t in trades)
        for regime in ("down", "flat", "up"):
            for side in ("long", "short"):
                rows = [t for t in trades if t["regime"] == regime and t["side"] == side]
                if rows:
                    report["groups"][f"{bot}/{regime}/{side}"] = summarize(rows)
    report["market_proxy_note"] = "btc_roc24h misurato all'apertura; non e' la mediana dei 26 simboli. Risultati per singolo trade; bootstrap per giorno non corregge pienamente trade sovrapposti tra giorni."
    return report


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", default="/data")
    ap.add_argument("--bots", default="hawk,bull")
    ap.add_argument("--json", dest="json_out", action="store_true")
    args = ap.parse_args(argv)
    events_by_bot, hashes, parse_summary = {}, {}, {}
    try:
        for bot in (b.strip().lower() for b in args.bots.split(",") if b.strip()):
            path = os.path.join(args.data_root, bot, "learning_log.jsonl")
            data, digest = read_snapshot(path)
            events, counts = parse_snapshot(data)
            events_by_bot[bot] = events
            hashes[bot] = digest
            parse_summary[bot] = counts
        report = analyze(events_by_bot, hashes)
        report["parse_summary"] = parse_summary
    except (OSError, ValueError) as exc:
        print(json.dumps({"kind": "executed_trade_r_by_entry_btc_regime_and_side", "error": str(exc),
                          "partial_output_suppressed": True}), flush=True)
        return 2
    if args.json_out:
        print(json.dumps(report, sort_keys=True), flush=True)
    else:
        print("R NETTO PER REGIME BTC AL MOMENTO DELL'INGRESSO E LATO — trade effettivamente chiusi", flush=True)
        for bot, data in report["bots"].items():
            s = data["overall"]
            print(f"{bot.upper()}: n={s['n']} giorni={s['days']} R medio={s['mean_net_R']} win={s['win_rate']} IC_cluster={s['cluster_bootstrap95']} esclusioni={data['exclusions']}", flush=True)
        for key, s in report["groups"].items():
            print(f"{key}: n={s['n']} giorni={s['days']} R medio={s['mean_net_R']} win={s['win_rate']} IC_cluster={s['cluster_bootstrap95']} ({s['ci_note']})", flush=True)
        print(report["market_proxy_note"], flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
