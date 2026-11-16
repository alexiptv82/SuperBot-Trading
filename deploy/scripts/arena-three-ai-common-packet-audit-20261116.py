#!/usr/bin/env python3
"""Read-only three-AI shared 25-market comparison-packet audit.

Reads and validates an expected private Arena research-cache SHA. Derives REAL
Brain market indicators then a short, byte-identical 25-market prompt for
DeepSeek, Qwen and MiniMax. No provider call, no secrets, no orders or writes.
Snapshot is HISTORICAL, never presented as a live signal.
"""
from __future__ import annotations

from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.v3.arena.compact_market import build_compact_market
from backend.v3.arena.comparison_packet import (
    build_common_packet, LANES, MAX_COMMON_INPUT_BYTES,
)
from backend.v3.arena.incremental_cache import load_research_cache
from backend.v3.brain_market.params import load_default_params

CACHE = Path("/var/lib/superbot-arena-research/arena-market-research-cache.json")
SHA = re.compile(r"[0-9a-f]{64}\Z")


def audit(expected_sha: str) -> int:
    if type(expected_sha) is not str or not SHA.fullmatch(expected_sha):
        raise ValueError("EXPECTED_SHA_REQUIRED")
    previous = load_research_cache(CACHE)
    if previous.sha256_hex != expected_sha:
        raise ValueError("CACHE_SHA_CHANGED")
    if len(previous.symbols) != 25:
        raise ValueError("INVALID_UNIVERSE")
    compact = build_compact_market(previous, load_default_params())
    packet = build_common_packet(compact)
    market_messages = [packet.identical_messages(p) for p in LANES]
    if not market_messages[0] == market_messages[1] == market_messages[2]:
        raise ValueError("UNFAIR_MODEL_MARKET_INPUT")
    now = int(time.time() * 1000)
    if now < previous.asof_ms:
        raise ValueError("CACHE_TIME_IN_FUTURE")
    print("ARENA_COMPARE mode=OFFLINE_ALL25_COMMON_INPUT_READ_ONLY")
    print("ARENA_COMPARE markets=" + str(len(packet.symbols)))
    print("ARENA_COMPARE metals=XAUUSDT,XAGUSDT")
    print("ARENA_COMPARE source_SHA256=" + previous.sha256_hex)
    print("ARENA_COMPARE compact_SHA256=" + compact.sha256_hex)
    print("ARENA_COMPARE model_input_SHA256=" + packet.packet_sha256)
    print("ARENA_COMPARE policy_SHA256=" + packet.policy_sha256)
    print("ARENA_COMPARE compact_bytes=" + str(len(compact.canonical_bytes)))
    print("ARENA_COMPARE model_input_bytes=" + str(len(packet.canonical_market_bytes)))
    print("ARENA_COMPARE provider_input_limit_bytes=" + str(MAX_COMMON_INPUT_BYTES))
    print("ARENA_COMPARE snapshot_age_seconds=" + str((now - previous.asof_ms) // 1000))
    print("ARENA_COMPARE freshness=HISTORICAL_ONLY_NO_LIVE_SIGNAL")
    for provider in LANES:
        print("ARENA_COMPARE " + provider.upper()
              + "_INPUT_SHA256=" + packet.packet_sha256)
    print("ARENA_COMPARE model_output_contract=NO_TRADE_OR_CANDIDATE_NOT_OPEN")
    print("ARENA_COMPARE paid_AI_calls=0 public_GETs=0 orders=0 files_written=0")
    print("ARENA_COMPARE services_changed=0")
    print("ARENA_COMPARE RESULT=THREE_MODEL_ALL25_COMMON_PACKET_VERIFIED_NO_DEPLOY")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "--audit":
        print("ARENA_COMPARE RESULT=USE_AUDIT_AND_EXPECTED_SHA256")
        sys.exit(2)
    try:
        sys.exit(audit(sys.argv[2]))
    except (ValueError, OSError, KeyError, TypeError,
            ArithmeticError, UnicodeError) as exc:
        reason = str(exc)
        if not re.fullmatch("[A-Z0-9_]+", reason):
            reason = "MARKET_OR_PROVENANCE_UNVERIFIED"
        print("ARENA_COMPARE RESULT=FAILED_" + reason)
        sys.exit(2)
