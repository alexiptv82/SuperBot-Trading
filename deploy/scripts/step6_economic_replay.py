#!/usr/bin/env python3
"""Offline paired exit-overlay research. No network, orders or source writes.

One DRAFT candidate: after a closed 15m bar reaches +1.5 price-R, sell half
at the next open; after activation, close the remainder at the next open
following a bar whose modelled remainder liquidation is non-positive.
The baseline exit is a terminal boundary, never extended beyond its lifetime.
This is not a portfolio simulation or an economic seasonality ablation.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
import statistics
import sys

BAR = 900_000
DAY = 86_400_000
FEE = 6 / 10_000
FUND = 1 / 10_000
CASES = ((2, 0), (4, 0), (8, 0), (2, 1), (8, 1))
SCOPE = "paired_clean_trade_exit_overlay_not_portfolio_or_seasonality_pnl"
MAX_BYTES = 16 * 1024 * 1024


class Invalid(ValueError):
    """Only fixed error codes from this class may reach public logs."""


def require(condition, code):
    if not condition:
        raise Invalid(code)


def number(x):
    return type(x) in (int, float) and math.isfinite(x)


def unique(pairs):
    out = {}
    for key, value in pairs:
        require(key not in out, "duplicate_json_key")
        out[key] = value
    return out


def decode(raw):
    def reject(_):
        raise Invalid("nonfinite_json")
    def real(value):
        result = float(value)
        require(math.isfinite(result), "nonfinite_json")
        return result
    try:
        return json.loads(raw, object_pairs_hook=unique, parse_constant=reject, parse_float=real)
    except (ValueError, UnicodeError, RecursionError):
        raise Invalid("invalid_json") from None


def rows(raw):
    require(bool(raw) and raw.endswith(b"\n"), "empty_or_truncated_jsonl")
    out = []
    for line in raw.splitlines():
        require(bool(line.strip()) and len(line) <= 65536, "invalid_jsonl_line")
        row = decode(line)
        require(isinstance(row, dict), "nonobject_jsonl")
        out.append(row)
    require(len(out) <= 200_000, "too_many_rows")
    return out


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def snapshot(path):
    # Reject final symlinks; workflow pins trusted, canonical mount directories.
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        require(os.fstat(stream.fileno()).st_size <= MAX_BYTES, "oversize_input")
        raw = stream.read(MAX_BYTES + 1)
    require(0 < len(raw) <= MAX_BYTES, "empty_or_oversize_input")
    return raw


def utc_ms(value):
    try:
        require(isinstance(value, str) and value.endswith("Z"), "invalid_utc_time")
        at = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        return int(at.timestamp() * 1000)
    except (ValueError, TypeError, OverflowError):
        raise Invalid("invalid_utc_time") from None


def validate_plan(plan, registered_ms):
    require(isinstance(plan, dict) and plan.get("schema") == 1, "invalid_plan")
    require(set(plan) == {"schema", "status", "candidate", "oos_start_utc", "baseline_version",
                          "reviewed_versions", "min_days", "min_trades", "min_changed"}, "unknown_plan_fields")
    require(plan.get("status") == "approved", "draft_plan_requires_review")
    require(plan.get("candidate") == "half_after_close_1.5R_then_nonpositive_remainder", "unreviewed_candidate")
    require(plan.get("min_days") == 42 and plan.get("min_trades") == 100
            and plan.get("min_changed") == 50, "unreviewed_sample_gates")
    start = utc_ms(plan.get("oos_start_utc"))
    require(type(registered_ms) is int and registered_ms > 0 and start > registered_ms,
            "oos_must_follow_plan_commit")
    versions = plan.get("reviewed_versions")
    require(isinstance(versions, list) and bool(versions) and
            all(isinstance(v, str) and re.fullmatch(r"[a-f0-9]{7,40}", v) for v in versions),
            "invalid_reviewed_versions")
    require(plan.get("baseline_version") in versions, "invalid_baseline_version")
    return start


def candle_index(raw, manifest):
    require(isinstance(manifest, dict) and manifest.get("schema") == 1
            and manifest.get("source") == "bitget_public_15m"
            and manifest.get("timestamp_semantics") == "open_ms"
            and manifest.get("interval_ms") == BAR, "invalid_market_manifest")
    require(digest(raw) == manifest.get("bars_sha256"), "market_hash_mismatch")
    asof = manifest.get("asof_ms")
    require(type(asof) is int and asof > 0, "invalid_market_asof")
    out = defaultdict(dict)
    for row in rows(raw):
        sym, at = row.get("symbol"), row.get("open_ms")
        require(row.get("schema") == 1 and isinstance(sym, str) and 0 < len(sym) <= 40,
                "invalid_candle_identity")
        require(type(at) is int and at > 0 and at % BAR == 0 and at + BAR <= asof,
                "unclosed_or_invalid_candle")
        prices = [row.get(k) for k in ("open", "high", "low", "close")]
        require(all(number(p) and p > 0 for p in prices), "invalid_candle_price")
        o, h, low, c = prices
        require(low <= min(o, c) <= max(o, c) <= h, "invalid_ohlc_order")
        require(at not in out[sym], "duplicate_candle")
        out[sym][at] = (at, o, h, low, c)
    return out, asof


def clean_trades(events, bot, asof, plan):
    groups = defaultdict(list)
    excluded = Counter()
    for row in events:
        require(row.get("schema") == 1, "unsupported_event_schema")
        if row.get("ev") not in ("open", "close", "split_fill"):
            continue
        require(row.get("portfolio") == bot, "mixed_portfolio")
        run, ident = row.get("run_no"), row.get("id")
        if type(run) is not int or run < 1 or type(ident) is not int or ident < 1:
            excluded["invalid_identity_events"] += 1
            continue
        groups[run, ident].append(row)
    trades = []
    for group in groups.values():
        opens = [r for r in group if r["ev"] == "open"]
        closes = [r for r in group if r["ev"] == "close"]
        reason = None
        if len(opens) != 1:
            reason = "missing_or_duplicate_open"
        elif not closes:
            reason = "not_closed"
        elif len(closes) != 1 or closes[0].get("partial", False) is not False:
            reason = "partials_or_duplicate_close"
        elif any(r["ev"] == "split_fill" for r in group) or opens[0].get("split_plan"):
            reason = "split_plan_or_fill"
        if reason:
            excluded[reason] += 1
            continue
        o, c = opens[0], closes[0]
        if (type(c.get("dca_count")) is not int or c["dca_count"] != 0
                or type(c.get("legs")) is not int or c["legs"] != 1 or c.get("why") == "liquidazione"):
            excluded["dca_multileg_or_liquidation"] += 1
            continue
        fields = ("margin", "leverage", "entry", "exit", "r_dist", "risk_plan_usd",
                  "net", "gross", "fees", "funding", "net_r")
        if any(not number(c.get(k)) for k in fields) or any(c[k] <= 0 for k in fields[:6]):
            excluded["missing_economics"] += 1
            continue
        opened, closed = c.get("open_ms"), c.get("close_ms")
        if (type(opened) is not int or type(closed) is not int or not 0 < opened < closed
                or o.get("ts") != opened or c.get("ts") != closed or type(c.get("side")) is not int
                or c["side"] not in (-1, 1) or o.get("side") != c["side"]
                or not isinstance(c.get("symbol"), str) or c["symbol"] != o.get("symbol")
                or (c.get("why") in ("stop loss", "take profit") and closed % BAR != 0)):
            excluded["identity_or_time_mismatch"] += 1
            continue
        if closed > asof:
            excluded["after_market_asof"] += 1
            continue
        version = o.get("code_version")
        if version not in plan["reviewed_versions"] or c.get("code_version") != version:
            excluded["unreviewed_or_cross_version"] += 1
            continue
        t = dict(c, opened=opened, closed=closed, version=version)
        t["qty"] = c["margin"] * c["leverage"] / c["entry"]
        t["risk"] = c["risk_plan_usd"]
        t["baseline_ref"] = c["exit"] / (1 - c["side"] * 2 / 10_000)
        gross = c["side"] * (c["exit"] - c["entry"]) * t["qty"]
        fees = t["qty"] * (c["entry"] + c["exit"]) * FEE
        funding = t["qty"] * c["entry"] * FUND * (closed - opened) / 28_800_000 if c["side"] == 1 else 0
        checks = ((gross, c["gross"]), (fees, c["fees"]), (funding, c["funding"]),
                  (gross - fees - funding, c["net"]))
        tolerances = {"entry": 1e-8 * c["entry"], "risk_plan_usd": .00011,
                      "r_dist": .000011, "leverage": 1e-9}
        if (any(abs(a - b) > .05 for a, b in checks)
                or abs(c["net_r"] - c["net"] / t["risk"]) > .00015
                # r_dist is rounded to five decimals in the close event. The
                # unrounded OPEN value is the independent planned-risk input.
                or any(not number(o.get(k)) or abs(o[k] - c[k]) > tol
                       for k, tol in tolerances.items())
                or not number(o.get("margin_first")) or abs(o["margin_first"] - c["margin"]) > .00011
                or (number(o.get("r_dist")) and
                    abs(c["margin"] * c["leverage"] * o["r_dist"] - t["risk"]) > .00011)):
            excluded["independent_cost_or_risk_reconciliation"] += 1
            continue
        t["r_dist"] = o["r_dist"]
        trades.append(t)
    return trades, dict(excluded)


def liquidation(t, ref, at, slip):
    fill = ref * (1 - t["side"] * slip / 10_000)
    gross = t["side"] * (fill - t["entry"]) * t["qty"]
    fees = t["qty"] * (t["entry"] + fill) * FEE
    funding = t["qty"] * t["entry"] * FUND * (at - t["opened"]) / 28_800_000 if t["side"] == 1 else 0
    return gross - fees - funding


def window(t, index):
    series = index.get(t["symbol"], {})
    start, last = t["opened"] // BAR * BAR, t["closed"] // BAR * BAR
    require((last - start) // BAR < 10_000, "trade_window_too_long")
    needed = range(start, last + BAR, BAR)
    if any(at not in series for at in needed):
        return None
    return [series[at] for at in needed]


def replay(t, bars, slip, delay):
    base = liquidation(t, t["baseline_ref"], t["closed"], slip)
    # No alternative fill in the baseline SL/TP bar; its intrabar order is unknown.
    limit = t["closed"] - BAR if t.get("why") in ("stop loss", "take profit") else t["closed"]
    partial = None
    for i, (at, _, _, _, close) in enumerate(bars):
        fill_i = i + 1 + delay
        if at < t["opened"] or fill_i >= len(bars):
            continue
        fill_at, fill_ref = bars[fill_i][0:2]
        if fill_at >= limit:
            break
        if partial is None:
            if t["side"] * (close - t["entry"]) / (t["entry"] * t["r_dist"]) >= 1.5:
                partial = (.5 * liquidation(t, fill_ref, fill_at, slip), fill_at)
        elif at >= partial[1] and liquidation(t, close, at + BAR, slip) <= 0:
            return base / t["risk"], (partial[0] + .5 * liquidation(t, fill_ref, fill_at, slip)) / t["risk"], True
    alt = base if partial is None else partial[0] + .5 * base
    return base / t["risk"], alt / t["risk"], partial is not None


def summarize(pairs):
    if not pairs:
        return {"n": 0, "changed": 0, "mean_baseline_R": None, "mean_candidate_R": None,
                "mean_delta_R": None, "episode_ci975_delta_R": None, "episodes": 0}
    pairs = sorted(pairs, key=lambda r: r["opened"])
    delta = [r["delta"] for r in pairs]
    # Merge same-day and overlapping positions into episodes (may yield one cluster).
    clusters, end = [], -1
    for row in pairs:
        begin = row["opened"] // DAY * DAY
        finish = ((row["closed"] // DAY) + 1) * DAY
        if begin >= end:
            clusters.append([])
        clusters[-1].append(row["delta"])
        end = max(end, finish)
    ci = None
    if len(clusters) >= 5:
        rng = random.Random(20261022)
        samples = []
        for _ in range(2000):
            values = [v for _ in clusters for v in rng.choice(clusters)]
            samples.append(statistics.mean(values))
        samples.sort()
        # 97.5% per bot: Bonferroni for the two predeclared primary comparisons.
        ci = [samples[24], samples[1974]]
    mid = (pairs[0]["opened"] + pairs[-1]["opened"]) / 2
    halves = [[r["delta"] for r in pairs if (r["opened"] <= mid) == first] for first in (True, False)]
    trimmed = sorted(delta)[:-3]
    return {"n": len(pairs), "changed": sum(r["changed"] for r in pairs),
            "entry_days": len({r["opened"] // DAY for r in pairs}),
            "mean_baseline_R": statistics.mean(r["base"] for r in pairs),
            "mean_candidate_R": statistics.mean(r["alt"] for r in pairs),
            "mean_delta_R": statistics.mean(delta), "episodes": len(clusters),
            "episode_ci975_delta_R": ci,
            "mean_delta_R_without_best_three": statistics.mean(trimmed) if trimmed else None,
            "chronological_half_mean_delta_R": [statistics.mean(h) if h else None for h in halves]}


def analyze(events_by_bot, index, asof, plan, registered_ms):
    start = validate_plan(plan, registered_ms)
    report = {"schema": 1, "scope": SCOPE, "automatic_promotion": False,
              "oos_start_utc": plan["oos_start_utc"], "registered_ms": registered_ms,
              "market_asof_ms": asof,
              "limitations": ["Clean closed trades only; exclusions can bias the sample.",
                              "Recorded entries and baseline exit boundary are held fixed; no reentries or equity simulation.",
                              "Candidate is a closed-bar signal with next-open fills, not a standing limit at +1.5R.",
                              "Costs reproduce the PAPER model, not observed live execution or actual funding.",
                              "Episode bootstrap is descriptive; market serial dependence remains possible.",
                              "Input hashes prove byte identity, not market-data authenticity or causal profitability."],
              "bots": {}}
    for bot in ("hawk", "bull"):
        trades, excluded = clean_trades(events_by_bot[bot], bot, asof, plan)
        sets = {"historical_exploratory": [], "prospective": []}
        for trade in trades:
            if trade["opened"] < start <= trade["closed"]:
                excluded["crosses_oos_boundary"] = excluded.get("crosses_oos_boundary", 0) + 1
                continue
            group = "prospective" if trade["opened"] >= start else "historical_exploratory"
            if group == "prospective" and trade["version"] != plan["baseline_version"]:
                excluded["oos_baseline_version_changed"] = excluded.get("oos_baseline_version_changed", 0) + 1
                continue
            bars = window(trade, index)
            if bars is None:
                excluded["missing_candle_coverage"] = excluded.get("missing_candle_coverage", 0) + 1
                excluded[group + "_missing_candle_coverage"] = excluded.get(group + "_missing_candle_coverage", 0) + 1
                continue
            sets[group].append((trade, bars))
        groups = {}
        for group, items in sets.items():
            cases = {}
            for slip, delay in CASES:
                pairs = []
                for trade, bars in items:
                    base, alt, changed = replay(trade, bars, slip, delay)
                    pairs.append({"opened": trade["opened"], "closed": trade["closed"],
                                  "base": base, "alt": alt, "delta": alt - base, "changed": changed})
                cases[f"slip{slip}bp_delay{delay}bar"] = summarize(pairs)
            groups[group] = cases
        primary = groups["prospective"]["slip2bp_delay0bar"]
        version_changed = any(number(row.get("ts")) and start <= row["ts"] <= asof
                              and row.get("ev") in ("open", "close")
                              and row.get("code_version") != plan["baseline_version"]
                              for row in events_by_bot[bot])
        enough = (asof - start >= plan["min_days"] * DAY and primary["n"] >= plan["min_trades"]
                  and primary["changed"] >= plan["min_changed"])
        supported = False
        coverage_missing = excluded.get("prospective_missing_candle_coverage", 0) > 0
        if enough and not version_changed and not coverage_missing:
            ci = primary["episode_ci975_delta_R"]
            halves = primary["chronological_half_mean_delta_R"]
            supported = (ci is not None and ci[0] > 0 and primary["mean_delta_R"] >= .10
                         and primary["mean_delta_R_without_best_three"] is not None
                         and primary["mean_delta_R_without_best_three"] > 0
                         and all(v is not None and v > 0 for v in halves)
                         and all(c["mean_delta_R"] is not None and c["mean_delta_R"] > 0
                                 for c in groups["prospective"].values()))
        report["bots"][bot] = {"excluded": excluded, "groups": groups,
                               "version_gate": "invalidated" if version_changed else "unchanged_in_recorded_events",
                               "coverage_gate": "missing_prospective_candles" if coverage_missing else "complete_for_selected_trades",
                               "sample_gate": "review_sample_reached" if enough else "pending_more_prospective_data",
                               "hypothesis_gate": ("invalidated_baseline_change" if version_changed else
                                                   "pending" if not enough or coverage_missing else
                                                   "supports_further_shadow_review" if supported else "not_supported"),
                               "decision": "no_bot_change_manual_review_required"}
    return report


def run(data_root, market_root, plan_path, registered_ms):
    for directory in (Path(data_root), Path(data_root)/"hawk", Path(data_root)/"bull", Path(market_root)):
        require(directory.resolve() == directory.absolute(), "symlink_input_directory")
    paths = {bot: Path(data_root) / bot / "learning_log.jsonl" for bot in ("hawk", "bull")}
    paths.update(candles=Path(market_root) / "candles.jsonl",
                 market_manifest=Path(market_root) / "manifest.json", plan=Path(plan_path))
    raw = {key: snapshot(path) for key, path in paths.items()}
    plan = decode(raw["plan"])
    validate_plan(plan, registered_ms)
    index, asof = candle_index(raw["candles"], decode(raw["market_manifest"]))
    require(asof <= int(dt.datetime.now(dt.timezone.utc).timestamp() * 1000), "future_market_asof")
    report = analyze({b: rows(raw[b]) for b in ("hawk", "bull")}, index, asof, plan, registered_ms)
    report["input_sha256"] = {key: digest(value) for key, value in raw.items()}
    report["script_sha256"] = digest(Path(__file__).read_bytes())
    for key, path in paths.items():
        require(snapshot(path) == raw[key], "input_changed_during_analysis")
    require(all(sum(v["groups"][g]["slip2bp_delay0bar"]["n"] for g in v["groups"]) > 0
                for v in report["bots"].values()), "no_paired_trades_for_bot")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--market-root", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--registered-ms", type=int, required=True)
    args = parser.parse_args()
    try:
        report = run(args.data_root, args.market_root, args.plan, args.registered_ms)
        print(json.dumps(report, allow_nan=False, sort_keys=True))
    except Invalid as exc:
        print("STEP6_BLOCKED=" + str(exc), file=sys.stderr)
        return 2
    except Exception:
        # No traceback, paths, symbols, source lines or arbitrary exception text.
        print("STEP6_BLOCKED=input_or_runtime_failure", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
