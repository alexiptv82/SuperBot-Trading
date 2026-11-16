#!/usr/bin/env python3
"""AI Arena offline recovery plan for the EXISTING private 25-market cache.

Reads a pinned cache digest and computes prospective public candle windows.
No network, paid AI calls, file writes, runner changes, orders, or services.
"""
from __future__ import annotations

from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.v3.arena.incremental_cache import load_research_cache
from backend.v3.arena.recovery_gap import recovery_plan, MAX_GAP_MS, MAX_PUBLIC_GETS

CACHE = Path("/var/lib/superbot-arena-research/arena-market-research-cache.json")
SHA = re.compile(r"[a-f0-9]{64}\Z")


def main() -> int:
    if len(sys.argv) != 3 or sys.argv[1] != "--plan" or not SHA.fullmatch(sys.argv[2]):
        print("ARENA_RECOVERY RESULT=USE_PLAN_EXPECTED_SHA256")
        return 2
    try:
        previous = load_research_cache(CACHE)
        if previous.sha256_hex != sys.argv[2]:
            raise ValueError("CACHE_DIGEST_CHANGED")
        if len(previous.symbols) != 25:
            raise ValueError("ARENA_EXPECTED_25_MARKETS")
        target_asof_ms = int(time.time() * 1000)
        planned = recovery_plan(previous, target_asof_ms)
        count_by_frame: dict[str, int] = {}
        for page in planned.pages:
            count_by_frame[page.frame] = count_by_frame.get(page.frame, 0) + 1
        rebase_by_frame: dict[str, int] = {}
        for _symbol, frame in planned.rebased:
            rebase_by_frame[frame] = rebase_by_frame.get(frame, 0) + 1
        print("ARENA_RECOVERY mode=READ_ONLY_PLAN", flush=True)
        print("ARENA_RECOVERY initial_SHA256=" + previous.sha256_hex, flush=True)
        print("ARENA_RECOVERY markets=" + str(len(previous.symbols)))
        print("ARENA_RECOVERY elapsed_minutes="
              + str((target_asof_ms - previous.asof_ms) // 60_000))
        print("ARENA_RECOVERY planned_public_GETs=" + str(len(planned.pages)))
        print("ARENA_RECOVERY planned_GETs_by_frame=" + str(count_by_frame))
        print("ARENA_RECOVERY REBASE_COUNT_by_frame=" + str(rebase_by_frame))
        print("ARENA_RECOVERY rebase_means_intermittent_bars_not_retained=YES")
        print("ARENA_RECOVERY max_elapsed_hours=" + str(MAX_GAP_MS // 3_600_000))
        print("ARENA_RECOVERY max_public_GETs=" + str(MAX_PUBLIC_GETS))
        print("ARENA_RECOVERY public_GETs=0 paid_AI_calls=0 orders=0 files_written=0")
        print("ARENA_RECOVERY RESULT=RECOVERY_PLAN_ONLY_NOT_EXECUTED")
        return 0
    except (ValueError, OSError, TypeError, OverflowError) as exc:
        reason = str(exc)
        if not re.fullmatch(r"[A-Z0-9_]+", reason):
            reason = "UNVERIFIED_CACHE_OR_TIME"
        print("ARENA_RECOVERY RESULT=NOT_PLANNED_" + reason, flush=True)
        return 2


if __name__ == "__main__":
    sys.exit(main())
