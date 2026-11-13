#!/usr/bin/env python3
"""Toro V1 pre-registered STEP 0 — test only the GROSS entry edge.

Input: independently sourced CLOSED Bitget USDT-FUTURES 1H and 4H CSV.
No network, no orders, no access to a live portfolio or credentials.
Lookahead protection: entry at the next 1H open, never at signal close.
This is an unlevered gross/fee stress comparison, NOT a full portfolio backtest.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

from desk.toro_profit_hunter import Candle, entry_signal, HOUR, FOUR_HOURS


def load_csv(path: Path) -> tuple[list[Candle], str]:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = []
        for row in reader:
            rows.append(Candle(
                ts=int(row["ts"]), open=float(row["open"]),
                high=float(row["high"]), low=float(row["low"]),
                close=float(row["close"]), volume=float(row["volume"])
            ))
    if len(rows) != len({r.ts for r in rows}):
        raise ValueError(f"duplicates: {path}")
    rows.sort(key=lambda r: r.ts)
    return rows, digest


def check_complete(bars: list[Candle], interval: int) -> None:
    if not bars or any(not b.valid() or b.ts % interval for b in bars):
        raise ValueError("invalid_bars")
    if any(b.ts + interval != bars[i+1].ts for i, b in enumerate(bars[:-1])):
        raise ValueError("gaps_are_not_interpolated")


def backtest(hourly: list[Candle], fourh: list[Candle], symbol: str,
             *, windows: tuple[int, ...] = (4, 8, 12),
             seeds: int = 1000, cost_fraction: float = 0.0010) -> dict:
    check_complete(hourly, HOUR)
    check_complete(fourh, FOUR_HOURS)
    if hourly[-1].ts + HOUR > fourh[-1].ts + FOUR_HOURS*2:
        raise ValueError("4h_feed_stale")
    max_w = max(windows)
    raw_signals = []
    eligible = defaultdict(list)
    # Both signal and random control are indexed on the next hour's OPEN.
    # The control is limited to eligible periods after the 40-day warm-up.
    for j in range(1000, len(hourly)-max_w):
        decision_ts = hourly[j-1].ts + HOUR
        month = datetime.fromtimestamp(decision_ts/1000, timezone.utc).strftime("%Y-%m")
        candidate, why = entry_signal(symbol, hourly[:j], fourh, decision_ts)
        # The null shares the SAME non-down 4H eligibility as the real signals.
        # It is matched on symbol (this file), UTC month and eligible regime,
        # not sampled indiscriminately from violent downturns or warm-up gaps.
        if why not in {"strong_4h_downtrend", "missing_or_gapped_closed_history",
                       "4h_stale", "latest_1h_not_closed_at_decision"}:
            eligible[month].append(j)
        if candidate is not None:
            raw_signals.append((j, month))
    # A signal during an open trade cannot initiate another position on same symbol.
    signal_by_w = {}
    rng = random.Random(210713)
    for w in windows:
        chosen, next_allowed = [], 0
        for j, month in raw_signals:
            if j >= next_allowed:
                chosen.append((j, month))
                next_allowed = j + w
        gross = [(hourly[j+w-1].close / hourly[j].open)-1 for j, _ in chosen]
        net = [v-cost_fraction for v in gross]
        null_means = []
        matched = bool(chosen)
        for seed in range(seeds):
            baseline = []
            used = []
            for _, month in chosen:
                pool = eligible.get(month, ())
                possible = [j for j in pool if all(abs(j-k) >= w for k in used)]
                if not possible:
                    matched = False
                    break
                j = possible[rng.randrange(len(possible))]
                used.append(j)
                baseline.append(hourly[j+w-1].close/hourly[j].open-1-cost_fraction)
            if len(baseline) == len(chosen) and baseline:
                null_means.append(mean(baseline))
        avg = mean(net) if net else None
        null_out = (sum(x < avg for x in null_means)/len(null_means)
                    if avg is not None and null_means else None)
        signal_by_w[str(w)] = dict(signals=len(chosen), avg_gross=mean(gross) if gross else None,
                                  avg_net=avg, share_of_matched_random_beaten=null_out,
                                  random_reps=len(null_means), matched=matched,
                                  cost_fraction=cost_fraction)
    return {"symbol":symbol,"bars_1h":len(hourly),"bars_4h":len(fourh),
            "raw_signals":len(raw_signals),"windows":signal_by_w,
            "note":"Entry only, not orders maker, portfolio, stop, Profit Guardian, AI or LIVE"}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--symbol", required=True)
    p.add_argument("--hourly", type=Path, required=True)
    p.add_argument("--fourhourly", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--cost-bp", type=float, default=10)
    ns = p.parse_args()
    if not 0 <= ns.cost_bp <= 100:
        p.error("cost-bp must be in [0,100]")
    h, hash_h = load_csv(ns.hourly)
    f, hash_f = load_csv(ns.fourhourly)
    result = backtest(h, f, ns.symbol, cost_fraction=ns.cost_bp/10000)
    result["sources"] = {"hourly":str(ns.hourly),"sha256_hourly":hash_h,
                         "4h":str(ns.fourhourly),"sha256_4h":hash_f}
    # Atomic write after full evaluation; never modifies any trading database.
    tmp = ns.out.with_suffix(ns.out.suffix+".tmp")
    tmp.write_text(json.dumps(result, indent=2), encoding="utf-8")
    tmp.replace(ns.out)
    print(json.dumps({"symbol":ns.symbol,"windows":result["windows"],
                      "result":"RECORDED_ONLY_NOT_APPROVED"},ensure_ascii=False))


if __name__ == "__main__":
    main()
