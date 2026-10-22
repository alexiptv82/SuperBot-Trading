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
PROTOCOL = {
    "candidate": "half_after_close_1.5R_then_nonpositive_remainder",
    "enrollment_days": 42, "maturation_days": 14,
    "min_trades": 100, "min_changed": 50,
    "min_episodes": 30, "min_changed_episodes": 25,
    "bootstrap_replicates": 10000, "bootstrap_seeds": [20261022, 20261023],
    "bootstrap_endpoint_tolerance_R": .02,
    "quantile_method": "inverse_empirical_cdf",
    "primary_family": "two_pooled_bot_means_bonferroni",
    "directional_inference": "descriptive_only",
    "min_mean_delta_R": .10,
    "reference_C": {"name": "closed_bar_price_R_trailing", "arm_R": 1.5,
                    "distance_R": 1.0, "quantity_fraction": 1.0,
                    "inference": "descriptive_only", "duration_strata": "baseline_holding_time"},
}


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
        require(isinstance(value, str) and
                re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value), "invalid_utc_time")
        at = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        return int(at.timestamp() * 1000)
    except (ValueError, TypeError, OverflowError):
        raise Invalid("invalid_utc_time") from None


def validate_plan(plan, registered_ms, allow_draft=False):
    require(isinstance(plan, dict) and type(plan.get("schema")) is int
            and plan["schema"] == 2, "invalid_plan")
    require(set(plan) == set(PROTOCOL) | {"schema", "status", "oos_start_utc", "baseline_version",
                                         "reviewed_versions", "baseline_config_sha256"}, "unknown_plan_fields")
    require(all(type(plan.get(k)) is type(v) and plan[k] == v for k, v in PROTOCOL.items()),
            "unreviewed_protocol")
    versions = plan.get("reviewed_versions")
    require(isinstance(versions, list) and bool(versions) and
            all(isinstance(v, str) and re.fullmatch(r"[a-f0-9]{7,40}", v) for v in versions) and
            len(set(versions)) == len(versions),
            "invalid_reviewed_versions")
    require(plan.get("baseline_version") in versions, "invalid_baseline_version")
    configs = plan.get("baseline_config_sha256")
    require(isinstance(configs, dict) and set(configs) == {"hawk", "bull"}, "invalid_baseline_config")
    if plan.get("status") == "draft":
        require(allow_draft, "draft_plan_requires_review")
        require(plan.get("oos_start_utc") is None and all(v is None for v in configs.values()),
                "draft_must_have_no_registration")
        return None
    require(plan.get("status") == "approved", "invalid_plan_status")
    require(all(isinstance(v, str) and re.fullmatch(r"[a-f0-9]{64}", v) for v in configs.values()),
            "unconfirmed_baseline_config")
    start = utc_ms(plan.get("oos_start_utc"))
    require(type(registered_ms) is int and registered_ms > 0 and start > registered_ms
            and start % DAY == 0, "oos_must_follow_plan_commit")
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
        features = o.get("features")
        btc = features.get("btc_roc24h") if isinstance(features, dict) else None
        t["entry_btc_regime"] = ("unknown" if not number(btc) else
                                  "down" if btc < -1 else "up" if btc > 1 else "flat")
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


def replay_C(t, bars, slip, delay):
    """Full-quantity mechanical reference: closed-bar 1R trailing after +1.5R.

    Uses the OLD floor for each signal, then updates its peak/floor for later
    evaluations. Fill is the next open (+ delay), bounded by the baseline.
    No standing intrabar stop and no partial; these constants are in the plan.
    """
    base = liquidation(t, t["baseline_ref"], t["closed"], slip) / t["risk"]
    limit = t["closed"]-BAR if t.get("why") in ("stop loss", "take profit") else t["closed"]
    peak, floor = None, None
    for i,(at,_,_,_,close) in enumerate(bars):
        fill_i=i+1+delay
        if at<t["opened"] or fill_i>=len(bars):continue
        fill_at,fill_ref=bars[fill_i][:2]
        if fill_at>=limit:break
        value=t["side"]*(close-t["entry"])/(t["entry"]*t["r_dist"])
        if floor is not None and value<=floor:
            return base,liquidation(t,fill_ref,fill_at,slip)/t["risk"],True
        peak=value if peak is None else max(peak,value)
        if peak>=1.5:
            floor=peak-1.0 if floor is None else max(floor,peak-1.0)
    return base,base,False


def distribution(values):
    ordered=sorted(values)
    return {"n":len(values),"mean":statistics.mean(values) if values else None,
            "median":statistics.median(values) if values else None,
            "q05":empirical_quantile(ordered,.05) if values else None,
            "q25":empirical_quantile(ordered,.25) if values else None,
            "q75":empirical_quantile(ordered,.75) if values else None,
            "q95":empirical_quantile(ordered,.95) if values else None,
            "min":min(values) if values else None,"max":max(values) if values else None,
            "positive":sum(v>0 for v in values),"negative":sum(v<0 for v in values),
            "zero":sum(v==0 for v in values)}


def summarize_C(rows):
    def duration(row):
        hours=(row["closed"]-row["opened"])/3600000
        return "under_1h" if hours<1 else "1_to_6h" if hours<6 else "6_to_24h" if hours<24 else "24h_plus"
    return {"inference":"descriptive_only_no_CI_no_gate", "n":len(rows),
            "exits_before_baseline":sum(r["changed"] for r in rows),
            "delta_R_C_minus_baseline":distribution([r["delta"] for r in rows]),
            "by_direction_and_baseline_duration":{
                side:{band:distribution([r["delta"] for r in rows if r["side"]==value and duration(r)==band])
                      for band in ("under_1h","1_to_6h","6_to_24h","24h_plus")}
                for side,value in (("long",1),("short",-1))}}


def episodes(pairs):
    """Whole UTC-day-expanded overlap components, never split by direction."""
    clusters, end = [], -1
    for row in sorted(pairs, key=lambda r: r["opened"]):
        begin = row["opened"] // DAY * DAY
        finish = (row["closed"] // DAY + 1) * DAY
        if begin >= end:
            clusters.append([])
        clusters[-1].append(row)
        end = max(end, finish)
    return clusters


def empirical_quantile(sorted_values, p):
    require(bool(sorted_values) and 0 < p < 1, "invalid_quantile")
    return sorted_values[math.ceil(len(sorted_values) * p) - 1]


def bootstrap_ci(clusters, replicates, seed):
    # Re-estimate the trade-weighted paired mean from whole resampled episodes.
    totals = [(sum(r["delta"] for r in c), len(c)) for c in clusters]
    rng = random.Random(seed)
    samples = []
    for _ in range(replicates):
        total, n = 0., 0
        for _ in totals:
            value, count = rng.choice(totals)
            total += value
            n += count
        samples.append(total / n)
    samples.sort()
    return [empirical_quantile(samples, p) for p in (.0125, .9875)]


def performance(values):
    positive = [v for v in values if v > 0]
    negative = [v for v in values if v < 0]
    return {"mean_R": statistics.mean(values) if values else None,
            "win_rate": len(positive) / len(values) if values else None,
            "mean_win_R": statistics.mean(positive) if positive else None,
            "mean_loss_R": statistics.mean(negative) if negative else None,
            "profit_factor_R": sum(positive) / -sum(negative) if negative else None,
            "profit_factor_denominator_zero": not bool(negative)}


def descriptive(pairs, clusters):
    members = {id(r) for r in pairs}
    return {"n": len(pairs), "changed": sum(r["changed"] for r in pairs),
            "entry_days": len({r["opened"] // DAY for r in pairs}),
            "episodes": sum(any(id(r) in members for r in c) for c in clusters),
            "changed_episodes": sum(any(id(r) in members and r["changed"] for r in c) for c in clusters),
            "mean_baseline_R": statistics.mean(r["base"] for r in pairs) if pairs else None,
            "mean_candidate_R": statistics.mean(r["alt"] for r in pairs) if pairs else None,
            "mean_delta_R": statistics.mean(r["delta"] for r in pairs) if pairs else None,
            "baseline": performance([r["base"] for r in pairs]),
            "candidate": performance([r["alt"] for r in pairs]),
            "mean_holding_hours": statistics.mean((r["closed"]-r["opened"])/3600000 for r in pairs) if pairs else None,
            "mean_leverage": statistics.mean(r["leverage"] for r in pairs) if pairs else None,
            "mean_stop_fraction": statistics.mean(r["r_dist"] for r in pairs) if pairs else None,
            "mean_baseline_cost_R": statistics.mean(r["cost_R"] for r in pairs) if pairs else None}


def summarize(pairs, plan=None, split_ms=None, inference=True):
    config = PROTOCOL if plan is None else plan
    clusters = episodes(pairs)
    result = descriptive(pairs, clusters)
    ci, repeat = None, None
    enough_clusters = len(clusters) >= config["min_episodes"]
    if inference and enough_clusters:
        ci, repeat = [bootstrap_ci(clusters, config["bootstrap_replicates"], seed)
                      for seed in config["bootstrap_seeds"]]
    shift = max(abs(a-b) for a, b in zip(ci, repeat)) if ci is not None else None
    total, n = sum(r["delta"] for r in pairs), len(pairs)
    leave_one_out = [(total-sum(r["delta"] for r in c))/(n-len(c))
                     for c in clusters if len(c) < n]
    midpoint = split_ms if split_ms is not None else (
        (min(r["opened"] for r in pairs)+max(r["opened"] for r in pairs))/2 if pairs else 0)
    halves = [[r["delta"] for r in pairs if (r["opened"] < midpoint) == first]
              for first in (True, False)]
    trimmed = sorted(r["delta"] for r in pairs)[:-3]
    result.update(episode_ci975_delta_R=ci, bootstrap_repeat_ci975_delta_R=repeat,
                  bootstrap_endpoint_max_shift_R=shift,
                  bootstrap_stable=(shift <= config["bootstrap_endpoint_tolerance_R"] if shift is not None else None),
                  min_leave_one_episode_out_mean_delta_R=min(leave_one_out) if leave_one_out else None,
                  mean_delta_R_without_best_three=statistics.mean(trimmed) if trimmed else None,
                  chronological_half_mean_delta_R=[statistics.mean(h) if h else None for h in halves],
                  inference="two_primary_bot_comparisons" if inference else "descriptive_only")
    result["by_direction"] = {
        label: descriptive([r for r in pairs if r["side"] == side], clusters)
        for label, side in (("long", 1), ("short", -1))}
    result["by_direction_and_entry_btc_regime"] = {
        label: {regime: descriptive([r for r in pairs if r["side"] == side
                                    and r.get("entry_btc_regime", "unknown") == regime], clusters)
                for regime in ("down", "flat", "up", "unknown")}
        for label, side in (("long", 1), ("short", -1))}
    return result


def version_gate(events, start, cutoff, baseline):
    # All timestamped event kinds, including non-trade observations. Logs cannot
    # prove a deployment/configuration did not change during a quiet interval.
    if any(type(r.get("ts")) is not int for r in events):
        return "invalidated_event_timeline"
    observed = [r for r in events if start <= r["ts"] <= cutoff]
    if any(r.get("code_version") != baseline for r in observed):
        return "invalidated_baseline_change"
    return "unchanged_in_recorded_events"


def continuity_gate(evidence, bot, start, cutoff, plan):
    """Validate an externally reviewed ledger attestation, not its authenticity."""
    if evidence is None:
        return "missing_runtime_ledger"
    require(isinstance(evidence, dict) and set(evidence) == {"schema", "source", "bots"}
            and evidence["schema"] == 1 and evidence["source"] == "reviewed_deployment_config_ledger"
            and isinstance(evidence["bots"], dict) and set(evidence["bots"]) == {"hawk", "bull"},
            "invalid_runtime_ledger")
    records = evidence["bots"][bot]
    require(isinstance(records, list), "invalid_runtime_ledger")
    cursor = start
    previous_end = -1
    for record in records:
        require(isinstance(record, dict) and set(record) ==
                {"from_ms", "to_ms", "code_version", "config_sha256", "paper", "source_sha256"},
                "invalid_runtime_ledger")
        begin, end = record["from_ms"], record["to_ms"]
        require(type(begin) is int and type(end) is int and 0 < begin < end
                and isinstance(record["source_sha256"], str)
                and re.fullmatch(r"[a-f0-9]{64}", record["source_sha256"]), "invalid_runtime_ledger")
        require(begin >= previous_end, "unordered_or_overlapping_runtime_ledger")
        previous_end = end
        if end <= start or begin >= cutoff:
            continue
        if begin > cursor:
            return "incomplete_runtime_ledger"
        if (record["code_version"] != plan["baseline_version"] or record["paper"] is not True
                or record["config_sha256"] != plan["baseline_config_sha256"][bot]):
            return "invalidated_runtime_change"
        cursor = max(cursor, end)
    return "attested_continuity_manual_review_required" if cursor >= cutoff else "incomplete_runtime_ledger"


def cohort_diagnostics(events, start, end, cutoff):
    counts = {side: Counter() for side in ("long", "short", "unknown")}
    groups = defaultdict(list)
    for row in events:
        if row.get("ev") in ("open", "close", "split_fill"):
            groups[row.get("run_no"), row.get("id")].append(row)
    unfinished = 0
    for group in groups.values():
        for opened in (r for r in group if r.get("ev") == "open"):
            at = opened.get("ts")
            if type(at) is not int:
                continue
            side = {1: "long", -1: "short"}.get(opened.get("side"), "unknown")
            if at < start:
                ended_before = any(r.get("ev") == "close" and r.get("partial", False) is False
                                   and type(r.get("ts")) is int and r["ts"] < start for r in group)
                if not ended_before:
                    counts[side]["opened_before_oos_not_finally_closed_before_start"] += 1
                continue
            if at >= end:
                counts[side]["opened_after_enrollment_end"] += 1
                continue
            counts[side]["opened_events"] += 1
            closes = [r for r in group if r.get("ev") == "close" and r.get("partial", False) is False
                      and type(r.get("ts")) is int and at < r["ts"] <= cutoff]
            if len(closes) != 1:
                counts[side]["not_uniquely_closed_by_cutoff"] += 1
                unfinished += 1
    return {k: dict(v) for k, v in counts.items()}, unfinished


def exclusion_audit(events, bot, cutoff, plan, start, end):
    groups = defaultdict(list)
    for row in events:
        if row.get("ev") in ("open", "close", "split_fill"):
            # Invalid identities are already counted globally by clean_trades.
            if type(row.get("run_no")) is int and type(row.get("id")) is int:
                groups[row["run_no"], row["id"]].append(row)
    audit = {cohort: {side: Counter() for side in ("long", "short", "unknown")}
             for cohort in ("historical_exploratory", "prospective", "after_enrollment", "unattributable")}
    for group in groups.values():
        opens = [r for r in group if r.get("ev") == "open"]
        cohort, side = "unattributable", "unknown"
        if len(opens) == 1 and type(opens[0].get("ts")) is int:
            at = opens[0]["ts"]
            cohort = "historical_exploratory" if at < start else "prospective" if at < end else "after_enrollment"
            side = {1: "long", -1: "short"}.get(opens[0].get("side"), "unknown")
        _, reasons = clean_trades(group, bot, cutoff, plan)
        audit[cohort][side].update(reasons)
        if cohort == "historical_exploratory" and any(
                r.get("ev") == "close" and type(r.get("ts")) is int and r["ts"] >= start for r in group):
            audit[cohort][side]["crosses_oos_boundary"] += 1
    return {cohort: {side: dict(counts) for side, counts in sides.items()} for cohort, sides in audit.items()}


def analyze(events_by_bot, index, asof, plan, registered_ms, runtime_evidence=None):
    start = validate_plan(plan, registered_ms)
    end = start + plan["enrollment_days"] * DAY
    final = end + plan["maturation_days"] * DAY
    cutoff = min(asof, final)
    is_final = asof >= final
    # Later snapshots cannot change the frozen cohort's candle horizon.
    available_index = {symbol: {at: bar for at, bar in series.items() if at+BAR <= cutoff}
                       for symbol, series in index.items()}
    report = {"schema": 2, "scope": SCOPE, "automatic_promotion": False,
              "oos_start_utc": plan["oos_start_utc"], "registered_ms": registered_ms,
              "market_asof_ms": asof, "enrollment_end_ms": end, "final_evaluation_ms": final,
              "evaluation_phase": "fixed_final" if is_final else "accrual_effects_withheld",
              "primary_family": plan["primary_family"], "directional_inference": "descriptive_only",
              "reference_C_protocol":plan["reference_C"],
              "limitations": ["Clean closed trades only; exclusions can bias the sample.",
                  "Recorded entries and baseline exit boundary are fixed; no reentries or equity simulation.",
                  "Closed-bar signal with next-open fills, not a standing limit or margin liquidation.",
                  "Costs reproduce PAPER, not actual execution or actual funding.",
                  "Episode percentile bootstrap is approximate; residual market dependence remains.",
                  "Runtime continuity is an external ledger attestation requiring manual provenance review.",
                  "Hashes prove byte identity, not authenticity or causal profitability.",
                  "No extension or new hypothesis after viewing the fixed final outcomes."], "bots": {}}
    for bot in ("hawk", "bull"):
        events = events_by_bot[bot]
        require(all(r.get("schema") == 1 and r.get("portfolio") == bot for r in events), "mixed_or_invalid_events")
        # Never use closes after the fixed final deadline to rescue a cohort.
        selected = [r for r in events if type(r.get("ts")) is int and r["ts"] <= cutoff]
        trades, excluded = clean_trades(selected, bot, cutoff, plan)
        diagnostics, unfinished = cohort_diagnostics(selected, start, end, cutoff)
        direction_exclusions = exclusion_audit(selected, bot, cutoff, plan, start, end)
        sets = {"historical_exploratory": [], "prospective": []}
        for trade in trades:
            if trade["opened"] < start <= trade["closed"]:
                excluded["crosses_oos_boundary"] = excluded.get("crosses_oos_boundary", 0) + 1
                continue
            if trade["opened"] >= end:
                excluded["after_enrollment_end"] = excluded.get("after_enrollment_end", 0) + 1
                continue
            group = "prospective" if trade["opened"] >= start else "historical_exploratory"
            if group == "prospective" and not is_final:
                continue  # Counts only: do not inspect candidate activation or effects yet.
            candles = window(trade, available_index)
            if candles is None:
                key = group + "_missing_candle_coverage"
                excluded[key] = excluded.get(key, 0) + 1
                side = "long" if trade["side"] == 1 else "short"
                counts = direction_exclusions[group][side]
                counts["missing_candle_coverage"] = counts.get("missing_candle_coverage", 0) + 1
                continue
            sets[group].append((trade, candles))
        groups = {}
        for group, items in sets.items():
            if group == "prospective" and not is_final:
                groups[group] = {"effects_withheld": True}
                continue
            cases = {}
            for slip, delay in CASES:
                pairs = []
                reference_rows = []
                for trade, candles in items:
                    base, alt, changed = replay(trade, candles, slip, delay)
                    cbase,cvalue,cchanged=replay_C(trade,candles,slip,delay)
                    require(abs(cbase-base)<1e-9,"reference_baseline_mismatch")
                    reference_rows.append({"opened":trade["opened"],"closed":trade["closed"],
                                           "side":trade["side"],"delta":cvalue-cbase,"changed":cchanged})
                    fill = trade["baseline_ref"] * (1-trade["side"]*slip/10000)
                    gross = trade["side"]*(fill-trade["entry"])*trade["qty"]
                    pairs.append({"opened": trade["opened"], "closed": trade["closed"],
                                  "base": base, "alt": alt, "delta": alt-base, "changed": changed,
                                  "side": trade["side"], "leverage": trade["leverage"],
                                  "r_dist": trade["r_dist"], "cost_R": gross/trade["risk"]-base,
                                  "entry_btc_regime": trade["entry_btc_regime"]})
                cases[f"slip{slip}bp_delay{delay}bar"] = summarize(
                    pairs, plan, start+(end-start)/2 if group == "prospective" else None,
                    inference=group == "prospective" and (slip, delay) == (2, 0))
                cases[f"slip{slip}bp_delay{delay}bar"]["reference_C"]=summarize_C(reference_rows)
            groups[group] = cases
        version = version_gate(events, start, cutoff, plan["baseline_version"])
        continuity = continuity_gate(runtime_evidence, bot, start, cutoff, plan) if cutoff > start else "not_started"
        coverage_missing = excluded.get("prospective_missing_candle_coverage", 0) > 0
        primary = groups["prospective"].get("slip2bp_delay0bar")
        enough = (primary is not None and primary["n"] >= plan["min_trades"]
                  and primary["changed"] >= plan["min_changed"]
                  and primary["episodes"] >= plan["min_episodes"]
                  and primary["changed_episodes"] >= plan["min_changed_episodes"])
        gate = "pending_fixed_final"
        if version.startswith("invalidated") or continuity == "invalidated_runtime_change":
            gate = "invalidated_baseline_change"
        elif is_final:
            if not enough or unfinished or coverage_missing:
                gate = "inconclusive_sample_or_coverage"
            elif continuity != "attested_continuity_manual_review_required":
                gate = "inconclusive_runtime_evidence"
            elif primary["bootstrap_stable"] is not True:
                gate = "inconclusive_bootstrap_precision"
            else:
                ci = primary["episode_ci975_delta_R"]
                supported = (ci is not None and ci[0] > 0
                    and primary["mean_delta_R"] >= plan["min_mean_delta_R"]
                    and primary["min_leave_one_episode_out_mean_delta_R"] is not None
                    and primary["min_leave_one_episode_out_mean_delta_R"] > 0
                    and primary["mean_delta_R_without_best_three"] is not None
                    and primary["mean_delta_R_without_best_three"] > 0
                    and all(v is not None and v > 0 for v in primary["chronological_half_mean_delta_R"])
                    and all(c["mean_delta_R"] is not None and c["mean_delta_R"] > 0
                            for c in groups["prospective"].values()))
                gate = "supports_further_shadow_review" if supported else "not_supported"
        report["bots"][bot] = {"excluded": excluded, "excluded_by_cohort_and_direction": direction_exclusions,
            "cohort_by_direction": diagnostics, "groups": groups, "version_gate": version,
            "runtime_continuity_gate": continuity,
            "coverage_gate": "missing_prospective_candles" if coverage_missing else "not_missing_in_selected_final_sample",
            "sample_gate": "fixed_sample_reached" if enough else "inconclusive_at_final" if is_final else "accruing",
            "hypothesis_gate": gate, "decision": "no_bot_change_manual_review_required"}
    return report


def run(data_root, market_root, plan_path, registered_ms):
    for directory in (Path(data_root), Path(data_root)/"hawk", Path(data_root)/"bull", Path(market_root)):
        require(directory.resolve() == directory.absolute(), "symlink_input_directory")
    paths = {bot: Path(data_root) / bot / "learning_log.jsonl" for bot in ("hawk", "bull")}
    paths.update(candles=Path(market_root) / "candles.jsonl",
                 market_manifest=Path(market_root) / "manifest.json", plan=Path(plan_path))
    ledger = Path(market_root) / "runtime-ledger.json"
    if ledger.exists() or ledger.is_symlink():
        paths["runtime_ledger"] = ledger
    raw = {key: snapshot(path) for key, path in paths.items()}
    plan = decode(raw["plan"])
    validate_plan(plan, registered_ms)
    index, asof = candle_index(raw["candles"], decode(raw["market_manifest"]))
    require(asof <= int(dt.datetime.now(dt.timezone.utc).timestamp() * 1000), "future_market_asof")
    report = analyze({b: rows(raw[b]) for b in ("hawk", "bull")}, index, asof, plan, registered_ms,
                     decode(raw["runtime_ledger"]) if "runtime_ledger" in raw else None)
    report["input_sha256"] = {key: digest(value) for key, value in raw.items()}
    report["script_sha256"] = digest(Path(__file__).read_bytes())
    for key, path in paths.items():
        require(snapshot(path) == raw[key], "input_changed_during_analysis")
    require(all(any(c.get("opened_events", 0) for c in v["cohort_by_direction"].values())
                or v["groups"]["historical_exploratory"]["slip2bp_delay0bar"]["n"]
                for v in report["bots"].values()), "no_observations_for_bot")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root")
    parser.add_argument("--market-root")
    parser.add_argument("--plan", required=True)
    parser.add_argument("--registered-ms", type=int, required=True)
    parser.add_argument("--check-plan", action="store_true", help="Validate approval before SSH; read only the plan.")
    args = parser.parse_args()
    try:
        if args.check_plan:
            validate_plan(decode(snapshot(args.plan)), args.registered_ms)
            print("STEP6_PLAN=APPROVED")
            return 0
        require(bool(args.data_root) and bool(args.market_root), "missing_input_roots")
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
