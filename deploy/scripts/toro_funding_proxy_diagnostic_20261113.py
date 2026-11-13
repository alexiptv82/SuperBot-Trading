#!/usr/bin/env python3
"""Toro funding cross-venue comparability DIAGNOSTIC (NOT trading/backtest).

Only reads the 12 public settled-funding JSON files from the source audit:
funding-source-audit-20261113T184346Z. Verifies SHA against manifest,
normalizes differing settlement schedules to common UTC-hour validity, and
reports empirical 10th-percentile extreme-negative funding event agreement.

IMPORTANT: percentile estimated using the ENTIRE recorded 90d interval is a
RETROSPECTIVE data-quality diagnostic only. It must NEVER be used to produce
causal historical signals or to claim a predictive funding strategy. A pass
on this subset (BTC + five named holdouts) is NOT a full-universe GO.
Immutable preregistration: 429bdd7382ef03a4f1617ee6174ed35d7e44f7a2.
"""
from __future__ import annotations

import bisect
import hashlib
import json
import math
import random
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

HOUR_MS = 3_600_000
DAY_MS = 86_400_000
MAX_SETTLED_AGE_MS = 8 * HOUR_MS
ROOT = Path("/opt/superbot-toro-research/funding-source-audit-20261113T184346Z")
EXPECTED = ("BTCUSDT", "ADAUSDT", "AVAXUSDT", "BCHUSDT", "DOGEUSDT", "DOTUSDT")
PREREG = "429bdd7382ef03a4f1617ee6174ed35d7e44f7a2"
SHARE_ALL = 0.70
SHARE_PER_SYMBOL = 0.60
MIN_EVENTS_PER_SYMBOL = 10
MIN_COVERAGE = 0.90


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_verified(root: Path, symbol: str, venue: str, digest: str) -> list[dict]:
    path = root / f"{symbol}_{venue}_settled.json"
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"file_missing_or_link:{path.name}")
    if sha256(path) != digest:
        raise ValueError(f"sha256_does_not_match_manifest:{path.name}")
    document = json.loads(path.read_text(encoding="utf8"))
    if document.get("symbol") != symbol or document.get("venue") != venue.upper():
        raise ValueError(f"wrong_symbol_or_venue:{path.name}")
    rows = document["rows"]
    if not rows:
        raise ValueError(f"empty_history:{path.name}")
    prev = -1
    for item in rows:
        t, v = item.get("ts"), item.get("rate")
        if not isinstance(t, int) or t <= prev or not isinstance(v, (int,float)) or not math.isfinite(v):
            raise ValueError(f"invalid_or_nonmonotonic_series:{path.name}")
        prev = t
    return rows


def percentile_10(vals: list[float]) -> float:
    """Linear-interpolated empirical p10, with <= ties included, FIXED for diagnostic."""
    ordered = sorted(vals)
    position = (len(ordered) - 1) * 0.1
    i = int(position)
    weight = position - i
    return ordered[i] * (1.0 - weight) + ordered[min(i + 1, len(ordered) - 1)] * weight


def intervals(rows: list[dict]) -> tuple[list[int], list[bool], float]:
    threshold = percentile_10([r["rate"] for r in rows])
    return ([r["ts"] for r in rows],
            [r["rate"] < 0 and r["rate"] <= threshold for r in rows],
            threshold)


def latest_at(ts: list[int], extreme: list[bool], when: int) -> tuple[bool, bool, int | None]:
    i = bisect.bisect_right(ts, when) - 1
    if i < 0 or when-ts[i] >= MAX_SETTLED_AGE_MS:
        return False, False, None
    return True, extreme[i], ts[i]


def coverage_and_events(b: list[dict], g: list[dict], asof_ms: int) -> dict:
    bts, bext, bt = intervals(b)
    gts, gext, gt = intervals(g)

    # Common 1h grid. The last settlement from each venue must be no older
    # than 8h at that hour; a missing settlement becomes coverage failure.
    begin = max(bts[0], gts[0])
    begin = ((begin + HOUR_MS-1)//HOUR_MS) * HOUR_MS
    end = (asof_ms//HOUR_MS)*HOUR_MS
    hours = list(range(begin,end + 1,HOUR_MS))
    comparable = {}
    both_hours = 0
    for hour in hours:
        ok_b, ex_b, tb = latest_at(bts, bext, hour)
        ok_g, ex_g, tg = latest_at(gts, gext, hour)
        if ok_b and ok_g:
            both_hours += 1
            comparable[hour] = {"binance_extreme":ex_b, "bitget_extreme":ex_g,
                                "binance_settled_ms":tb, "bitget_settled_ms":tg}
    coverage = both_hours / len(hours) if hours else 0.0

    event_rows = []
    # Each Binance settlement event counted ONCE, never repeated 8 times per
    # hourly observation. A match requires time-overlap between the event's
    # settled-rate validity interval and a Bitget extreme-rate interval.
    # Diagnostic match may occur after Binance settlement; NO prediction claim.
    for index,(ts, is_extreme) in enumerate(zip(bts,bext)):
        if not is_extreme or ts > asof_ms:
            continue
        next_b = bts[index+1] if index+1 < len(bts) else asof_ms+HOUR_MS
        valid_until = min(ts+MAX_SETTLED_AGE_MS,next_b,asof_ms+HOUR_MS)
        begin_hour = ((ts+HOUR_MS-1)//HOUR_MS)*HOUR_MS
        hours_current = [h for h in range(begin_hour,valid_until,HOUR_MS)]
        common = [h for h in hours_current if h in comparable and
                  comparable[h]["binance_settled_ms"] == ts]
        matches = [h for h in common if comparable[h]["bitget_extreme"]]
        event_rows.append({
            "settlement_ms":ts,
            "utc_day":datetime.fromtimestamp(ts/1000,timezone.utc).strftime("%Y-%m-%d"),
            "comparable_hours":len(common),
            "matching_hours":len(matches),
            "matched":bool(matches),
            "first_match_hour_ms":min(matches) if matches else None,
        })
    count = len(event_rows)
    matched = sum(int(r["matched"]) for r in event_rows)
    observed_count = sum(r["comparable_hours"] > 0 for r in event_rows)
    precision = matched/count if count else None
    bootstrap = []
    day_events=defaultdict(list)
    for e in event_rows:
        day_events[e["utc_day"]].append(e)
    days=list(day_events)
    random_generator = random.Random(971113)
    for _ in range(500):
        if not days:
            break
        sample_days = [days[random_generator.randrange(len(days))]
                       for _ in days]
        n = sum(len(day_events[d]) for d in sample_days)
        m = sum(sum(int(e["matched"]) for e in day_events[d])
                for d in sample_days)
        if n:
            bootstrap.append(m/n)
    bootstrap.sort()
    bootstrap_ci = ([bootstrap[int(0.025*(len(bootstrap)-1))],
                     bootstrap[int(0.975*(len(bootstrap)-1))]]
                    if bootstrap else None)

    return {
        "bitget_rows":len(g), "binance_rows":len(b),
        "threshold_bitget_p10":gt,
        "threshold_binance_p10":bt,
        "candidate_hours":len(hours), "comparable_hours":both_hours,
        "coverage":coverage,
        "distinct_extreme_negative_binance_settlements":count,
        "binance_events_with_comparable_hours":observed_count,
        "matched_binance_events":matched,
        "conditional_precision":precision,
        "day_block_bootstrap_95pct":bootstrap_ci,
        "events":event_rows,
        "meets_sample":count>=MIN_EVENTS_PER_SYMBOL,
        "meets_coverage":coverage>=MIN_COVERAGE,
        "meets_local_precision":precision is not None and precision>=SHARE_PER_SYMBOL,
    }


def run(root: Path) -> dict:
    manifest_path = root/"manifest.json"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise ValueError("missing_original_manifest")
    manifest = json.loads(manifest_path.read_text(encoding="utf8"))
    if manifest.get("preregistration_commit") != PREREG:
        raise ValueError("preregistration_not_matched")
    if manifest.get("errors") or set(manifest.get("symbols",{})) != set(EXPECTED):
        raise ValueError("source_audit_incomplete")
    now_ms = int(datetime.fromisoformat(manifest["recorded_utc"]).timestamp()*1000)
    results = {}
    for symbol in EXPECTED:
        info = manifest["symbols"][symbol]
        g = load_verified(root,symbol,"bitget",info["sha256_bitget"])
        b = load_verified(root,symbol,"binance",info["sha256_binance"])
        result=coverage_and_events(b,g,now_ms)
        results[symbol]=result
        p=result["conditional_precision"]
        fmt_p="NA" if p is None else f"{p:.4f}"
        print(f"TORO_PROXY_DIAG symbol={symbol} "
              f"binance_negative_extreme_events={result['distinct_extreme_negative_binance_settlements']} "
              f"matches={result['matched_binance_events']} "
              f"coincident_fraction={fmt_p} coverage_hours={result['coverage']:.4f} "
              f"min_events_ok={int(result['meets_sample'])} "
              f"coverage_ok={int(result['meets_coverage'])} "
              f"per_symbol_60pct_ok={int(result['meets_local_precision'])}",
              flush=True)
    total_count = sum(x["distinct_extreme_negative_binance_settlements"] for x in results.values())
    total_match = sum(x["matched_binance_events"] for x in results.values())
    pooled = total_match/total_count if total_count else None
    pass_panel = (pooled is not None and pooled >= SHARE_ALL and
                  all(x["meets_sample"] and x["meets_coverage"] and
                      x["meets_local_precision"] for x in results.values()))
    return {
        "classification":"RETROSPECTIVE_PROXY_DATA_DIAGNOSTIC_NOT_BACKTEST",
        "original_manifest_sha256":sha256(manifest_path),
        "prereg_commit":PREREG,
        "source_dir":str(root),
        "symbols":results,
        "pooled_event_count":total_count,
        "pooled_matched_count":total_match,
        "pooled_precision":pooled,
        "nominal_thresholds":{"pooled_min":SHARE_ALL,
                              "per_symbol_min":SHARE_PER_SYMBOL,
                              "min_binance_extreme_events_per_symbol":MIN_EVENTS_PER_SYMBOL,
                              "minimum_comparable_hour_coverage":MIN_COVERAGE},
        "panel_diagnostic_pass":pass_panel,
        "historical_15_asset_universe_verified":False,
        "signal_90_day_causal_percentile_verified":False,
        "strategy_pass0_run":False,
        "strategy_go":False,
        "caveat":"Retrospective 90d percentile uses future in early timestamps; "
                 "valid only as source agreement diagnosis. No trading signal "
                 "or returns. A panel pass is NOT approval of historical proxy."
    }


def main() -> int:
    if len(sys.argv)>2 or (len(sys.argv)==2 and sys.argv[1]!="--self-test"):
        print("usage: script.py [--self-test]",file=sys.stderr)
        return 2
    if len(sys.argv)==2:
        t0=1700000000000
        b=[{"ts":t0+i*8*HOUR_MS,"rate":-0.0004 if i in (1,3,5,7) else .0001}
           for i in range(13)]
        g=[{"ts":t0+i*8*HOUR_MS+HOUR_MS,"rate":-0.0004 if i in (1,3,5,7) else .0001}
           for i in range(13)]
        result=coverage_and_events(b,g,t0+13*8*HOUR_MS)
        assert result["distinct_extreme_negative_binance_settlements"]>0
        assert result["matched_binance_events"]>0
        assert result["coverage"]>.85
        assert latest_at([t0],[True],t0+8*HOUR_MS)[0] is False
        assert percentile_10([1,2,3,4,5,6,7,8,9,10]) == 1.9
        print("TORO_PROXY_DIAG SYNTHETIC_TEST=PASS NO_NETWORK=1",flush=True)
        return 0
    root=ROOT
    if not root.is_dir() or root.is_symlink():
        print("TORO_PROXY_DIAG BLOCK=source_directory_missing_or_symlink",flush=True)
        return 2
    result=run(root)
    report=root/"proxy_diagnostic_20261113.json"
    if report.exists():
        print(f"TORO_PROXY_DIAG REPORT_ALREADY_EXISTS={report} DO_NOT_OVERWRITE=1")
        return 2
    payload=(json.dumps(result,indent=2,sort_keys=True,ensure_ascii=False)+"\n").encode()
    # No overwrite; prior original funding files remain untouched.
    with report.open("xb") as out:
        out.write(payload)
        out.flush()
        import os
        os.fsync(out.fileno())
    total=result["pooled_precision"]
    print(f"TORO_PROXY_DIAG PANEL_RESULT={'DIAGNOSTIC_THRESHOLDS_MET' if result['panel_diagnostic_pass'] else 'DIAGNOSTIC_THRESHOLDS_NOT_MET'} "
          f"pooled_extreme_events={result['pooled_event_count']} "
          f"pooled_precision={'NA' if total is None else round(total,4)} "
          "STRATEGY_BACKTEST=0 FULL_UNIVERSE_GO=0",
          flush=True)
    print(f"TORO_PROXY_DIAG REPORT={report}",flush=True)
    return 0


if __name__=="__main__":
    sys.exit(main())
