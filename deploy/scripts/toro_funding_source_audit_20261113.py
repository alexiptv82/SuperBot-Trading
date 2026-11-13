#!/usr/bin/env python3
"""READ-ONLY public funding SOURCE audit, NOT Toro trading or a strategy backtest.

A limited, frozen-asof availability check for BTC and the five preregistered
holdout symbols. It archives normalized public settled funding rates with SHA
and reports only coverage / timestamp intersection / sign agreement. It does
NOT calculate extreme-funding thresholds, a coincidence GO/NO-GO or returns.

Pre-registration (immutable parent):
429bdd7382ef03a4f1617ee6174ed35d7e44f7a2
docs/v3/TORO-FUNDING-LONG-PREREG-20261113.md
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SYMBOLS = ("BTCUSDT", "ADAUSDT", "AVAXUSDT", "BCHUSDT",
           "DOGEUSDT", "DOTUSDT")
N_DAYS = 90
DAY_MS = 86_400_000
BASE = Path("/opt/superbot-toro-research")
PIN = "429bdd7382ef03a4f1617ee6174ed35d7e44f7a2"


def api(url: str) -> object:
    last_error = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "SuperBot-Toro-Public-Data-Audit/1.0",
                              "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=22) as response:
                if response.status != 200:
                    raise ValueError(f"http_{response.status}")
                raw = response.read(1_500_000)
            return json.loads(raw)
        except (urllib.error.HTTPError, urllib.error.URLError,
                TimeoutError, OSError) as exc:
            last_error = exc
            time.sleep(0.75 * (attempt + 1))
    raise RuntimeError(f"public_http_failed:{type(last_error).__name__}:{last_error}")


def iso(t: int | None) -> str:
    if t is None:
        return "NONE"
    return datetime.fromtimestamp(t/1000, timezone.utc).isoformat()


def clean_rows(records: list[dict], timestamp_field: str) -> list[dict]:
    mapped: dict[int, float] = {}
    for obj in records:
        ts = int(obj[timestamp_field])
        rate = float(obj["fundingRate"])
        if not math.isfinite(rate) or not (0 < ts < 4_000_000_000_000):
            raise ValueError("nonfinite_or_invalid_public_funding")
        if ts in mapped and abs(mapped[ts] - rate) > 1e-12:
            raise ValueError("conflicting_funding_same_settlement")
        mapped[ts] = rate
    return [{"ts": ts, "rate": mapped[ts]} for ts in sorted(mapped)]


def bitget(symbol: str, cutoff_ms: int, now_ms: int) -> list[dict]:
    all_rows = []
    oldest_seen = None
    for page in range(1, 41):
        qs = urllib.parse.urlencode({
            "category": "USDT-FUTURES", "symbol": symbol,
            "limit": 100, "cursor": page
        })
        response = api("https://api.bitget.com/api/v3/market/history-fund-rate?" + qs)
        if not isinstance(response, dict) or response.get("code") != "00000":
            raise ValueError(f"bitget_response_error:{str(response)[:150]}")
        data = response.get("data")
        rows = data.get("resultList") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            raise ValueError("bitget_result_list_missing")
        if not rows:
            break
        batch = clean_rows(rows, "fundingRateTimestamp")
        if oldest_seen is not None and batch[0]["ts"] >= oldest_seen:
            raise ValueError("bitget_cursor_not_advancing")
        oldest_seen = batch[0]["ts"]
        all_rows.extend(batch)
        if batch[0]["ts"] <= cutoff_ms or len(rows) < 100:
            break
        time.sleep(0.10)
    else:
        raise ValueError("bitget_page_cap_exceeded")
    return clean_rows(
        [{"fundingRateTimestamp": r["ts"], "fundingRate": r["rate"]}
         for r in all_rows if cutoff_ms <= r["ts"] <= now_ms],
        "fundingRateTimestamp"
    )


def binance(symbol: str, cutoff_ms: int, now_ms: int) -> list[dict]:
    out = []
    start = cutoff_ms
    for page in range(1, 12):
        qs = urllib.parse.urlencode({
            "symbol": symbol, "startTime": start,
            "endTime": now_ms, "limit": 1000
        })
        rows = api("https://fapi.binance.com/fapi/v1/fundingRate?" + qs)
        if not isinstance(rows, list):
            raise ValueError(f"binance_response_error:{str(rows)[:150]}")
        if not rows:
            break
        cleaned = clean_rows(rows, "fundingTime")
        if cleaned[0]["ts"] < start or cleaned[-1]["ts"] > now_ms:
            raise ValueError("binance_funding_outside_query")
        if not cleaned or cleaned[-1]["ts"] < start:
            raise ValueError("binance_pagination_not_advancing")
        out.extend(cleaned)
        start = cleaned[-1]["ts"] + 1
        if len(rows) < 1000 or start > now_ms:
            break
        time.sleep(0.10)
    else:
        raise ValueError("binance_page_cap_exceeded")
    return clean_rows(
        [{"fundingTime": r["ts"], "fundingRate": r["rate"]} for r in out],
        "fundingTime"
    )


def save(path: Path, obj: dict) -> str:
    payload = (json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2)
               + "\n").encode("utf-8")
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    with tmp.open("xb") as fp:
        fp.write(payload)
        fp.flush()
        os.fsync(fp.fileno())
    os.replace(tmp, path)
    return hashlib.sha256(payload).hexdigest()


def main() -> int:
    now = int(time.time() * 1000)
    start = now - N_DAYS*DAY_MS
    out = BASE / ("funding-source-audit-" +
                  datetime.fromtimestamp(now/1000, timezone.utc).strftime(
                      "%Y%m%dT%H%M%SZ"))
    out.mkdir(parents=True, exist_ok=False)
    manifest = {
        "classification": "PUBLIC_DATA_QUALITY_ONLY_NOT_BACKTEST",
        "preregistration_commit": PIN,
        "recorded_utc": iso(now), "cutoff_utc": iso(start),
        "symbol_scope": SYMBOLS,
        "not_trading": True, "not_extreme_coincidence_gate": True,
        "funding_proxies_not_interchangeable": True,
        "symbols": {}, "errors": [],
    }
    print("TORO_FUNDING_AUDIT SOURCE_ONLY=1 STRATEGY_BACKTEST=0 "
          f"out={out}", flush=True)
    for symbol in SYMBOLS:
        try:
            a = bitget(symbol, start, now)
            b = binance(symbol, start, now)
            if not a or not b:
                raise ValueError("missing_one_venue")
            a_by = {r["ts"]: r["rate"] for r in a}
            b_by = {r["ts"]: r["rate"] for r in b}
            both = sorted(set(a_by) & set(b_by))
            agree = sum((a_by[t] < 0) == (b_by[t] < 0) for t in both)
            stats = {
                "bitget_records": len(a), "binance_records": len(b),
                "bitget_first": iso(a[0]["ts"]), "binance_first": iso(b[0]["ts"]),
                "bitget_last": iso(a[-1]["ts"]), "binance_last": iso(b[-1]["ts"]),
                "same_settlement_timestamps": len(both),
                "negative_vs_nonnegative_sign_agreement": (
                    round(agree / len(both), 5) if both else None),
                "coverage_note": "No GO: different funding schedules and extreme "
                                 "episodes have NOT been evaluated",
            }
            ha = save(out / f"{symbol}_bitget_settled.json", {
                "symbol": symbol, "venue": "BITGET", "asof_ms": now,
                "rows": a, "settled_only": True
            })
            hb = save(out / f"{symbol}_binance_settled.json", {
                "symbol": symbol, "venue": "BINANCE", "asof_ms": now,
                "rows": b, "settled_only": True
            })
            stats["sha256_bitget"] = ha
            stats["sha256_binance"] = hb
            manifest["symbols"][symbol] = stats
            print(f"TORO_FUNDING_AUDIT symbol={symbol} "
                  f"bitget={len(a)} binance={len(b)} "
                  f"exact_shared_times={len(both)} "
                  f"sign_agreement={stats['negative_vs_nonnegative_sign_agreement']} "
                  "extreme_gate=NOT_TESTED", flush=True)
        except Exception as exc:
            msg = f"{symbol}:{type(exc).__name__}:{str(exc)[:180]}"
            manifest["errors"].append(msg)
            print(f"TORO_FUNDING_AUDIT symbol={symbol} "
                  f"DATA_ERROR={type(exc).__name__} "
                  f"detail={str(exc)[:120]}", flush=True)
        save(out / "manifest.json", manifest)
    print(f"TORO_FUNDING_AUDIT RESULT={'PUBLIC_DATA_AVAILABLE' if not manifest['errors'] else 'INCOMPLETE'} "
          f"verified_symbols={len(manifest['symbols'])}/{len(SYMBOLS)} "
          f"errors={len(manifest['errors'])} "
          "PROXY_GATE=NOT_EVALUATED LIVE_TRADES=0 NO_BOT_CHANGES=1", flush=True)
    print(f"TORO_FUNDING_AUDIT MANIFEST={out / 'manifest.json'}", flush=True)
    return 0 if not manifest["errors"] else 2


if __name__ == "__main__":
    sys.exit(main())
