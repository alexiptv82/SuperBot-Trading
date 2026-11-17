#!/usr/bin/env python3
"""AI Arena read-only 8-vs-25 runner universe audit on the PRIVATE cache.

This audit cannot authorize the provisional 25-market research roster to
trade. It does not call AI APIs, update any config, run the bots or write files.
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
from backend.v3.arena.comparison_packet import build_common_packet
from backend.v3.arena.incremental_cache import load_research_cache
from backend.v3.arena.trial_universe_bridge import review_equal_universe
from backend.v3.brain_market.params import load_default_params
from backend.v3.runner.config import load_runner_config

PRIVATE_CACHE = Path("/var/lib/superbot-arena-research/arena-market-research-cache.json")
BASELINE = ROOT / "backend/v3/runner/runner_config_brain2000_paper.json"
SHA = re.compile(r"[a-f0-9]{64}\Z")


def audit(expected_sha: str):
    if not SHA.fullmatch(expected_sha):
        raise ValueError("EXPECTED_SHA_INVALID")
    frozen = load_research_cache(PRIVATE_CACHE)
    if frozen.sha256_hex != expected_sha:
        raise ValueError("RESEARCH_CACHE_SHA_CHANGED")
    source = build_common_packet(build_compact_market(frozen, load_default_params()))
    existing = load_runner_config(BASELINE.read_bytes())
    report = review_equal_universe(source, existing, now_ms=int(time.time()*1000))
    print("ARENA_UNIVERSE mode=READ_ONLY_RESEARCH_AUDIT")
    print("ARENA_UNIVERSE existing_config_symbols=" + str(len(report.legacy_brain_symbols)))
    print("ARENA_UNIVERSE existing_list=" + ",".join(report.legacy_brain_symbols))
    print("ARENA_UNIVERSE candidate_count=" + str(len(report.candidates)))
    print("ARENA_UNIVERSE metals=XAUUSDT,XAGUSDT")
    print("ARENA_UNIVERSE proposed_list=" + ",".join(report.candidates))
    print("ARENA_UNIVERSE common_packet_SHA256=" + report.source_packet_sha256)
    print("ARENA_UNIVERSE parity_across_3_models=" + str(
        len(set(x[1] for x in report.per_ai)) == 1).upper())
    print("ARENA_UNIVERSE readiness_issues=" + ",".join(report.issues))
    print("ARENA_UNIVERSE live_deepseek_config_changed=NO")
    print("ARENA_UNIVERSE paper_wallets_started=0 paid_AI_calls=0 orders=0 writes=0")
    print("ARENA_UNIVERSE candidate_authorized_for_trading=NO")
    print("ARENA_UNIVERSE RESULT=UNIVERSE_PREVIEW_ONLY_NOT_DEPLOYED")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "--audit":
        print("ARENA_UNIVERSE RESULT=USE_AUDIT_EXPECTED_CACHE_SHA")
        sys.exit(2)
    try:
        sys.exit(audit(sys.argv[2]))
    except (ValueError, OSError, KeyError, TypeError, ArithmeticError) as exc:
        reason = str(exc)
        if re.fullmatch(r"[A-Z0-9_]{3,70}", reason) is None:
            reason = "UNVERIFIED_RESEARCH_INPUT"
        print("ARENA_UNIVERSE RESULT=FAILED_" + reason)
        sys.exit(2)
