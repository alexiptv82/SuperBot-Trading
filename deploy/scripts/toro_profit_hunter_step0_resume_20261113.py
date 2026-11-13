#!/usr/bin/env python3
"""Toro Step0 restart-safe replay, 2026-11-13 frozen Bitget window.

READ-ONLY on trading code/data. Reuse historical public CSV as recorded in
step0-20261113T153437Z; never overwrite an existing dataset. Only fetch files
that are absent, save one independent report per symbol atomically, and
resume from verified per-symbol reports after a crash.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from backend.v3.lab_tools.fetch_candles import fetch_rows, write_csv
from deploy.scripts.toro_profit_hunter_step0 import backtest, load_csv
from desk.toro_profit_hunter import HOUR, FOUR_HOURS

OUT = Path("/opt/superbot-toro-research/step0-20261113T153437Z")
SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
PIN = "18ac3971c76269341c61b041394fbdb10f8bdb97"
FETCH_PIN = "ab7e0b7d991b8f4bd714fccfec23b09a936e6717"
FROZEN = datetime(2026, 11, 13, 15, 34, 37, tzinfo=timezone.utc)
END = (int(FROZEN.timestamp() * 1000) // FOUR_HOURS) * FOUR_HOURS
START = END - 365 * 24 * HOUR
SEEDS = 1000
COST_FRACTION = 0.0010


def say(**fields: object) -> None:
    print("TORO_RESUME " + " ".join(f"{k}={v}" for k, v in fields.items()),
          flush=True)


def save_atomic(path: Path, obj: dict) -> None:
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    with tmp.open("w", encoding="utf8") as fp:
        json.dump(obj, fp, sort_keys=True, indent=2, ensure_ascii=False)
        fp.write("\n")
        fp.flush()
        os.fsync(fp.fileno())
    os.replace(tmp, path)


def read_good_cache(sym: str, interval: int) -> tuple[list, dict]:
    name = f"{sym}_{interval//60_000}m.csv"
    file = OUT / name
    if file.exists():
        if not file.is_file() or file.is_symlink():
            raise RuntimeError(f"cache_not_regular:{name}")
        origin = "REUSE"
    else:
        # Fail closed if previously fetched BTC/ETH/SOL/BNB files have disappeared.
        # Don't silently rerun all public API fetches.
        if sym != "XRPUSDT":
            raise RuntimeError(f"previously_downloaded_cache_missing:{name}")
        say(event="FETCH_MISSING", symbol=sym, timeframe=f"{interval//60_000}m")
        rows = fetch_rows(sym, START, END, candle_ms=interval,
                          window_bars=200, max_requests=300)
        if not rows:
            raise RuntimeError(f"no_public_bars:{name}")
        # Save first to a temp file and rename atomically.
        temp = OUT / (name + ".part")
        write_csv(temp, rows)
        os.replace(temp, file)
        origin = "FETCHED"
    bars, digest = load_csv(file)
    if not bars or any(not b.valid() or b.ts % interval for b in bars):
        raise RuntimeError(f"invalid_data:{name}")
    if any(a.ts >= b.ts for a,b in zip(bars,bars[1:])):
        raise RuntimeError(f"unordered_or_duplicate:{name}")
    if bars[0].ts < START or bars[-1].ts >= END:
        raise RuntimeError(f"outside_original_frozen_window:{name}")
    expected = (END-START)//interval
    coverage = len(bars)/expected
    valid_history = bars[0].ts <= START+7*24*HOUR and coverage >= 0.85
    fresh_at_original_end = bars[-1].ts >= END-2*interval
    gaps = sum(b.ts-a.ts > interval for a,b in zip(bars,bars[1:]))
    meta = {
        "path": str(file), "sha256": digest, "source": origin,
        "rows": len(bars), "expected": expected, "coverage": round(coverage,6),
        "start_ms": bars[0].ts, "end_ms": bars[-1].ts, "gaps": gaps,
        "valid_history": valid_history, "fresh_asof_original": fresh_at_original_end
    }
    say(event="DATA", symbol=sym, tf=f"{interval//60_000}m",
        source=origin, rows=len(bars), expected=expected,
        gaps=gaps, coverage_ok=int(valid_history),
        fresh=int(fresh_at_original_end))
    if not valid_history or not fresh_at_original_end:
        raise RuntimeError(f"insufficient_or_stale_data:{name}")
    return bars, meta


def main() -> int:
    if not OUT.is_dir() or OUT.is_symlink():
        say(result="BLOCK", reason="original_run_directory_missing")
        return 2
    if (OUT / "report_step0.json").exists():
        say(result="BLOCK", reason="original_report_already_exists_review_it")
        return 2
    start = time.monotonic()
    manifest = {
        "stage": "STEP0 ENTRY_ONLY NOT FULL PAPER", "frozen_asof_ms": END,
        "start_ms": START, "symbol_order": SYMBOLS, "source_pin": PIN,
        "fetch_pin": FETCH_PIN, "seed": SEEDS, "cost_fraction": COST_FRACTION,
        "unit_tests_previous": "19/19 PASS in Termius 16:34 CET",
        "raw_data": {}, "results": {}, "failures": [],
        "paper_orders": 0, "service_changes": 0,
    }
    save_atomic(OUT / "resume_status.json", manifest)
    say(event="BEGIN", frozen_asof_ms=END,
        output_dir=OUT, original_data_only=1, exit_unit_changes=0)
    for sym in SYMBOLS:
        try:
            one, m1 = read_good_cache(sym, HOUR)
            four, m4 = read_good_cache(sym, FOUR_HOURS)
            manifest["raw_data"][sym] = {"1h": m1, "4h": m4}
            save_atomic(OUT / "resume_status.json", manifest)

            perfile = OUT / f"step0_{sym}_result.json"
            fingerprints = {"1h": m1["sha256"], "4h": m4["sha256"]}
            if perfile.is_file():
                old = json.loads(perfile.read_text(encoding="utf-8"))
                if (old.get("source_pin") != PIN or
                    old.get("data_sha256") != fingerprints or
                    old.get("seed") != SEEDS or
                    old.get("cost_fraction") != COST_FRACTION or
                    old.get("frozen_asof_ms") != END):
                    raise RuntimeError(f"unverifiable_previous_result:{sym}")
                report = old["report"]
                say(event="REUSE_VERIFIED_RESULT", symbol=sym)
            else:
                say(event="REPLAY_BEGIN", symbol=sym, bars_1h=len(one),
                    bars_4h=len(four), cpu_nice=15)
                begin = time.monotonic()
                report = backtest(one, four, sym, seeds=SEEDS,
                                  cost_fraction=COST_FRACTION)
                save_atomic(perfile,{
                    "symbol":sym, "source_pin":PIN, "seed":SEEDS,
                    "cost_fraction":COST_FRACTION,
                    "data_sha256":fingerprints, "frozen_asof_ms":END,
                    "report":report
                })
                say(event="REPLAY_DONE", symbol=sym,
                    elapsed_s=round(time.monotonic()-begin,1),
                    signals=report["raw_signals"])
            manifest["results"][sym] = report
            save_atomic(OUT / "resume_status.json", manifest)
            for w,r in report["windows"].items():
                say(event="WINDOW", symbol=sym, hours=w, signals=r["signals"],
                    avg_net=("NA" if r["avg_net"] is None else round(r["avg_net"],6)),
                    random_beaten=("NA" if r["share_of_matched_random_beaten"] is None
                                   else round(r["share_of_matched_random_beaten"],4)))
        except Exception as exc:
            reason=f"{sym}:{type(exc).__name__}:{str(exc)[:200]}"
            manifest["failures"].append(reason)
            save_atomic(OUT / "resume_status.json", manifest)
            say(event="FAILURE", symbol=sym, type=type(exc).__name__,
                detail=str(exc)[:100].replace(" ","_"))
            # Continue so we can collect the other 4 symbols' independent reports.
    manifest["elapsed_s"] = round(time.monotonic()-start,2)
    manifest["complete"] = len(manifest["results"]) == len(SYMBOLS) and not manifest["failures"]
    save_atomic(OUT / "resume_status.json",manifest)
    if manifest["complete"]:
        save_atomic(OUT / "report_step0.json", manifest)
        say(result="DATA_READY_FOR_HUMAN_REVIEW", evaluated=len(manifest["results"]),
            report=OUT/"report_step0.json", approved=0)
        return 0
    say(result="INCOMPLETE_NOT_EVALUABLE", evaluated=len(manifest["results"]),
        failures=len(manifest["failures"]), partial=OUT/"resume_status.json")
    return 2


if __name__ == "__main__":
    sys.exit(main())
