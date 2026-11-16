"""Offline tests for fail-closed incremental research cache. No network/API."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import os
import unittest

from backend.v3.arena.frozen_market import FRAME_MS, freeze_market_batch
from backend.v3.arena.incremental_cache import (
    delta_plan, merge_delta, save_research_cache, load_research_cache,
    MAX_ELAPSED_MS,
)

# Five minutes before a 4h boundary, so +10m tests all four TFs.
ASOF = (1795000000000 // FRAME_MS["4h"]) * FRAME_MS["4h"] - 300_000
TARGET = ASOF + 600_000
REQUIRED = {"1m": 60, "15m": 40, "1h": 25, "4h": 20}
SYMBOLS = ("BTCUSDT", "XAUUSDT")


def candle(t: int, value: str = "101") -> list:
    return [str(t), "100", "102", "99", value, "5", "500"]


def fixture():
    data = {}
    for symbol in SYMBOLS:
        by_frame = {}
        for frame, step in FRAME_MS.items():
            last = ASOF // step * step - step
            by_frame[frame] = [
                candle(last - (REQUIRED[frame] - 1 - index) * step)
                for index in range(REQUIRED[frame])
            ]
        data[symbol] = by_frame
    return freeze_market_batch(
        data, REQUIRED, asof_ms=ASOF,
        source_id="bitget.v2.history-candles.cache-test",
    )


def deltas(batch, target=TARGET):
    plan = delta_plan(batch, target)
    return {
        symbol: {
            frame: [candle(t) for t in range(start, end + step, step)]
            for frame, (start, end) in frames.items()
            for step in (FRAME_MS[frame],)
        }
        for symbol, frames in plan.items()
    }


class IncrementalCacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = fixture()

    def test_plan_all_four_frames_cross_boundary(self):
        plan = delta_plan(self.base, TARGET)
        self.assertEqual(set(plan), set(SYMBOLS))
        for frames in plan.values():
            self.assertEqual(set(frames), set(FRAME_MS))
            self.assertEqual(
                (frames["1m"][1] - frames["1m"][0]) // 60_000 + 1, 10)
            for frame, (first, last) in frames.items():
                self.assertGreaterEqual(last, first)

    def test_merge_only_missing_candles_and_replay_deterministic(self):
        new_rows = deltas(self.base)
        one = merge_delta(self.base, TARGET, new_rows)
        two = merge_delta(self.base, TARGET, new_rows)
        self.assertEqual(one.sha256_hex, two.sha256_hex)
        self.assertNotEqual(one.sha256_hex, self.base.sha256_hex)
        self.assertEqual(one.symbols, self.base.symbols)
        doc = json.loads(one.canonical_bytes)
        for symbol in SYMBOLS:
            for frame, step in FRAME_MS.items():
                rows = doc["candles"][symbol][frame]
                self.assertEqual(len(rows), REQUIRED[frame])
                self.assertEqual(rows[-1][0], TARGET // step * step - step)
        self.assertEqual(self.base.asof_ms, ASOF)

    def test_no_new_closed_candle_reuses_original_without_change(self):
        within_same_minute = ASOF + 15_000
        self.assertEqual(delta_plan(self.base, within_same_minute), {})
        result = merge_delta(self.base, within_same_minute, {})
        self.assertEqual(result.asof_ms, within_same_minute)

    def test_missing_symbol_rejected(self):
        missing = deltas(self.base)
        missing.pop(SYMBOLS[0])
        with self.assertRaisesRegex(ValueError, "CACHE_INCOMPLETE_DELTA_MARKETS"):
            merge_delta(self.base, TARGET, missing)

    def test_missing_frame_rejected(self):
        missing = deltas(self.base)
        missing["BTCUSDT"].pop("4h")
        with self.assertRaisesRegex(ValueError, "CACHE_INCOMPLETE_DELTA_FRAMES"):
            merge_delta(self.base, TARGET, missing)

    def test_missing_one_minute_rejected(self):
        broken = deltas(self.base)
        broken["BTCUSDT"]["1m"].pop(0)
        with self.assertRaisesRegex(ValueError, "CACHE_MISSING_EXTRA_OR_DUPLICATE_BARS"):
            merge_delta(self.base, TARGET, broken)

    def test_duplicate_timestamp_rejected(self):
        broken = deltas(self.base)
        broken["BTCUSDT"]["1m"].append(broken["BTCUSDT"]["1m"][0][:])
        with self.assertRaisesRegex(ValueError, "CACHE_MISSING_EXTRA_OR_DUPLICATE_BARS"):
            merge_delta(self.base, TARGET, broken)

    def test_new_forming_candle_rejected(self):
        broken = deltas(self.base)
        broken["BTCUSDT"]["15m"].append(candle(TARGET))
        with self.assertRaisesRegex(ValueError, "CACHE_MISSING_EXTRA_OR_DUPLICATE_BARS"):
            merge_delta(self.base, TARGET, broken)

    def test_ohlc_invalid_rejected(self):
        broken = deltas(self.base)
        broken["XAUUSDT"]["1m"][-1][2] = "0"
        with self.assertRaisesRegex(ValueError, "INVALID_OHLC"):
            merge_delta(self.base, TARGET, broken)

    def test_time_limit_and_replay_blocked(self):
        with self.assertRaisesRegex(ValueError, "CACHE_NONMONOTONIC_TIME"):
            delta_plan(self.base, ASOF)
        with self.assertRaisesRegex(ValueError, "CACHE_NONMONOTONIC_TIME"):
            delta_plan(self.base, ASOF - 60_000)
        with self.assertRaisesRegex(ValueError, "CACHE_TOO_OLD_REBOOTSTRAP_REQUIRED"):
            delta_plan(self.base, ASOF + MAX_ELAPSED_MS + 1)

    def test_tampering_of_source_rejected(self):
        forged = replace(
            self.base, canonical_bytes=self.base.canonical_bytes + b" "
        )
        with self.assertRaisesRegex(ValueError, "SNAPSHOT_INTEGRITY_FAILURE"):
            delta_plan(forged, TARGET)

    def test_atomic_disk_round_trip_and_reboot(self):
        merged = merge_delta(self.base, TARGET, deltas(self.base))
        with TemporaryDirectory(prefix="superbot-arena-research-", dir="/tmp") as d:
            path = Path(d) / "arena-market-research-cache.json"
            save_research_cache(self.base, path)
            first = load_research_cache(path)
            self.assertEqual(first.sha256_hex, self.base.sha256_hex)
            save_research_cache(merged, path)
            after_restart = load_research_cache(path)
            self.assertEqual(after_restart.sha256_hex, merged.sha256_hex)
            self.assertEqual(after_restart.canonical_bytes, merged.canonical_bytes)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_corrupted_file_rejected_and_previous_cache_unchanged_on_error(self):
        with TemporaryDirectory(prefix="superbot-arena-research-", dir="/tmp") as d:
            path = Path(d) / "arena-market-research-cache.json"
            save_research_cache(self.base, path)
            original_bytes = path.read_bytes()
            broken = replace(self.base, canonical_bytes=b"untrusted")
            with self.assertRaisesRegex(ValueError, "SNAPSHOT_INTEGRITY_FAILURE"):
                save_research_cache(broken, path)
            self.assertEqual(original_bytes, path.read_bytes())
            record = json.loads(original_bytes)
            record["payload_b64"] = "*invalidbase64"
            path.write_text(json.dumps(record), encoding="ascii")
            with self.assertRaisesRegex(ValueError, "CACHE_CORRUPT_OR_UNVERIFIED"):
                load_research_cache(path)

    def test_symlink_and_outside_research_path_rejected(self):
        with TemporaryDirectory(prefix="superbot-arena-research-", dir="/tmp") as d:
            path = Path(d) / "arena-market-research-cache.json"
            outside = Path(d) / "outside.json"
            outside.write_text("untouched")
            path.symlink_to(outside)
            with self.assertRaisesRegex(ValueError, "CACHE_SYMLINK_REJECTED"):
                save_research_cache(self.base, path)
            with self.assertRaisesRegex(ValueError, "CACHE_SYMLINK_REJECTED"):
                load_research_cache(path)
            self.assertEqual(outside.read_text(), "untouched")
        with TemporaryDirectory(prefix="general-temp-", dir="/tmp") as d:
            path = Path(d) / "arena-market-research-cache.json"
            with self.assertRaisesRegex(ValueError, "CACHE_PATH_OUTSIDE_RESEARCH_ROOT"):
                save_research_cache(self.base, path)


if __name__ == "__main__":
    unittest.main()
