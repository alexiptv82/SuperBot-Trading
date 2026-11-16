#!/usr/bin/env python3
"""AI Arena: read-only full 25-market private-cache -> genuine Brain indicators.

Only reads the private research cache and the checked-in Brain params file.
No network, provider API calls, market orders, files written, or service changes.
Output is an audit of a HISTORICAL research snapshot, never a live signal.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.v3.arena.compact_market import build_compact_market
from backend.v3.arena.incremental_cache import load_research_cache
from backend.v3.brain_market.params import load_default_params

CACHE_FILE = Path(
    "/var/lib/superbot-arena-research/arena-market-research-cache.json"
)
METALS = {"XAUUSDT", "XAGUSDT"}
LANES = ("deepseek", "qwen", "minimax")
SHA64 = re.compile(r"[a-f0-9]{64}\Z")


def audit(expected_sha256: str) -> int:
    if not SHA64.fullmatch(expected_sha256):
        raise ValueError("INVALID_EXPECTED_DIGEST")
    print("ARENA_COMPACT_AUDIT mode=HISTORICAL_CACHE_READ_ONLY", flush=True)
    snapshot = load_research_cache(CACHE_FILE)
    if snapshot.sha256_hex != expected_sha256:
        raise ValueError("UNEXPECTED_CACHE_SHA256")
    if (len(snapshot.symbols) != 25
            or not METALS.issubset(snapshot.symbols)
            or snapshot.classification != "PROVISIONAL_NOT_TRADE_APPROVED"):
        raise ValueError("INVALID_CACHE_MARKET_UNIVERSE")
    age_seconds = (int(time.time() * 1000) - snapshot.asof_ms) // 1000
    if age_seconds < 0:
        raise ValueError("SNAPSHOT_TIMESTAMP_IN_FUTURE")
    print("ARENA_COMPACT_AUDIT cache_SHA256=" + snapshot.sha256_hex, flush=True)
    print("ARENA_COMPACT_AUDIT markets=" + str(len(snapshot.symbols)), flush=True)
    print("ARENA_COMPACT_AUDIT asof_utc="
          + datetime.fromtimestamp(snapshot.asof_ms / 1000, timezone.utc).isoformat(),
          flush=True)
    print("ARENA_COMPACT_AUDIT age_seconds=" + str(age_seconds), flush=True)
    print("ARENA_COMPACT_AUDIT freshness=HISTORICAL_ONLY_NOT_LIVE",
          flush=True)

    compact = build_compact_market(snapshot, load_default_params())
    compact.verify()
    payload = json.loads(compact.canonical_bytes)
    if (type(payload) is not dict
            or len(payload.get("markets", [])) != 25
            or payload.get("source_snapshot_sha256") != expected_sha256
            or payload.get("contains_raw_candles") is not False
            or payload.get("contains_trading_authorization") is not False
            or payload.get("classification") != "PROVISIONAL_NOT_TRADE_APPROVED"):
        raise ValueError("COMPACT_MARKET_SCOPE_FAILURE")
    regimes = {}
    for entry in payload["markets"]:
        label = entry["market"]["regime"]
        if any(tf.get("status") != "ok" for tf in entry["market"]["timeframes"]):
            raise ValueError("COMPACT_TIMEFRAME_NOT_READY")
        regimes[label] = regimes.get(label, 0) + 1
    if sum(regimes.values()) != 25:
        raise ValueError("REGIME_ACCOUNTING_MISMATCH")
    print("ARENA_COMPACT_AUDIT market_regimes=" + str(dict(sorted(regimes.items()))),
          flush=True)
    print("ARENA_COMPACT_AUDIT source_bytes=" + str(len(snapshot.canonical_bytes)))
    print("ARENA_COMPACT_AUDIT compact_bytes=" + str(len(compact.canonical_bytes)))
    print("ARENA_COMPACT_AUDIT params_SHA256=" + compact.params_sha256)
    print("ARENA_COMPACT_AUDIT shared_compact_SHA256=" + compact.sha256_hex)
    for lane in LANES:
        body, digest = compact.for_provider(lane)
        if body != compact.canonical_bytes or digest != compact.sha256_hex:
            raise ValueError("CROSS_PROVIDER_MARKET_DIFFERENCE")
        print("ARENA_COMPACT_AUDIT " + lane.upper() + "_SHA256=" + digest)
    print("ARENA_COMPACT_AUDIT classification=PROVISIONAL_NOT_TRADE_APPROVED")
    print("ARENA_COMPACT_AUDIT paid_AI_calls=0 public_GETs=0 orders=0")
    print("ARENA_COMPACT_AUDIT services_changed=0 files_written=0")
    print("ARENA_COMPACT_AUDIT RESULT=25_REAL_BRAIN_INDICATORS_VERIFIED_NO_DEPLOY")
    return 0


def main() -> int:
    if len(sys.argv) != 3 or sys.argv[1] != "--audit":
        print("ARENA_COMPACT_AUDIT RESULT=USE_AUDIT_AND_EXPECTED_SHA256")
        return 2
    try:
        return audit(sys.argv[2])
    except (ValueError, OSError, OverflowError, ArithmeticError,
            KeyError, TypeError) as exc:
        reason = str(exc)
        if not re.fullmatch(r"[A-Z0-9_]+", reason):
            reason = "DATA_OR_INDICATOR_INTEGRITY_FAILURE"
        print("ARENA_COMPACT_AUDIT RESULT=NOT_VERIFIED_" + reason, flush=True)
        return 2


if __name__ == "__main__":
    sys.exit(main())
