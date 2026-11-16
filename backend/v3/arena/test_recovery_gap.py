"""No-network regression for bounded Arena historical gap recovery."""
from __future__ import annotations

from dataclasses import replace
import unittest

from backend.v3.arena.frozen_market import FRAME_MS, freeze_market_batch
from backend.v3.arena.recovery_gap import (
    MAX_GAP_MS, MAX_PUBLIC_GETS, PAGE_BARS, recovery_plan, recover_gap,
)

FOUR_HOURS = FRAME_MS["4h"]
ASOF = (1795000000000 // FOUR_HOURS) * FOUR_HOURS - 5 * 60_000
SMALL_TARGET = ASOF + 10 * 60_000
GAP_TARGET = ASOF + 90 * 60_000
MAX_TARGET = ASOF + MAX_GAP_MS
REQUIRED = {"1m": 60, "15m": 300, "1h": 100, "4h": 50}


def candle(t, close="101"):
    return [str(t), "100", "102", "98", close, "10", "1000"]


def fixture(markets=("BTCUSDT", "XAUUSDT")):
    frame_map = {}
    for symbol in markets:
        frame_map[symbol] = {}
        for frame, step in FRAME_MS.items():
            last = ASOF // step * step - step
            frame_map[symbol][frame] = [
                candle(last - (REQUIRED[frame] - 1 - index) * step)
                for index in range(REQUIRED[frame])
            ]
    return freeze_market_batch(
        frame_map, REQUIRED, asof_ms=ASOF, source_id="bitget.v2.research-gap-test",
    )


class PublicSource:
    def __init__(self):
        self.calls = []

    def __call__(self, symbol, frame, first, last):
        self.calls.append((symbol, frame, first, last))
        step = FRAME_MS[frame]
        # Bitget can include one rounded bar on each edge; in range exact.
        return [
            candle(t) for t in range(last + step, first - 2 * step, -step)
        ]


class RecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.initial = fixture()

    def test_short_gap_keeps_all_timeframes_contiguous(self):
        get = PublicSource()
        result, plan = recover_gap(self.initial, SMALL_TARGET, get)
        self.assertEqual(plan.rebased, ())
        self.assertEqual(result.asof_ms, SMALL_TARGET)
        self.assertEqual(len(get.calls), len(plan.pages))
        self.assertEqual(result.symbols, self.initial.symbols)

    def test_ninety_minute_gap_rebases_only_one_minute(self):
        get = PublicSource()
        result, plan = recover_gap(self.initial, GAP_TARGET, get)
        self.assertEqual(set(plan.rebased),
                         {(sym, "1m") for sym in self.initial.symbols})
        self.assertEqual(result.classification, "PROVISIONAL_NOT_TRADE_APPROVED")
        self.assertNotEqual(result.sha256_hex, self.initial.sha256_hex)
        self.assertEqual(self.initial.asof_ms, ASOF)
        self.assertEqual(result.for_provider("deepseek"), result.for_provider("qwen"))
        self.assertEqual(result.for_provider("qwen"), result.for_provider("minimax"))

    def test_max_72h_window_uses_paged_15m_and_fixed_budget(self):
        markets = ("BTCUSDT",) + tuple(f"A{i}USDT" for i in range(1, 23)) + (
            "XAUUSDT", "XAGUSDT",
        )
        original = fixture(markets)
        plan = recovery_plan(original, MAX_TARGET)
        self.assertEqual(len(plan.pages), 125)
        self.assertLessEqual(len(plan.pages), MAX_PUBLIC_GETS)
        self.assertEqual(len(plan.rebased), 25)
        for symbol in original.symbols:
            fifteen = [p for p in plan.pages if p.symbol == symbol
                       and p.frame == "15m"]
            self.assertEqual(len(fifteen), 2)
            self.assertEqual(sum(p.expected_rows for p in fifteen), 288)
        for p in plan.pages:
            self.assertLessEqual(p.expected_rows, PAGE_BARS)
        updated, verified = recover_gap(original, MAX_TARGET, PublicSource())
        self.assertEqual(verified, plan)
        self.assertEqual(len(updated.symbols), 25)

    def test_no_missing_candles_are_silently_accepted(self):
        def missing(symbol, frame, first, last):
            rows = PublicSource()(symbol, frame, first, last)
            if symbol == "BTCUSDT" and frame == "1m":
                return rows[:1] + rows[2:]
            return rows
        with self.assertRaisesRegex(ValueError, "RECOVERY_CANDLES_INCOMPLETE"):
            recover_gap(self.initial, GAP_TARGET, missing)

    def test_duplicate_timestamp_never_accepted(self):
        def duplicated(symbol, frame, first, last):
            rows = PublicSource()(symbol, frame, first, last)
            if symbol == "BTCUSDT" and frame == "1m":
                rows.append(rows[1][:])
            return rows
        with self.assertRaisesRegex(ValueError, "RECOVERY_DUPLICATE_CANDLE"):
            recover_gap(self.initial, GAP_TARGET, duplicated)

    def test_price_anomaly_rejected_before_merge(self):
        def bad_price(symbol, frame, first, last):
            rows = PublicSource()(symbol, frame, first, last)
            if symbol == "BTCUSDT" and frame == "1m":
                rows[1][2] = "0"
            return rows
        with self.assertRaisesRegex(ValueError, "INVALID_OHLC"):
            recover_gap(self.initial, GAP_TARGET, bad_price)

    def test_provider_unavailable_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "RECOVERY_PROVIDER_PAGE_INVALID"):
            recover_gap(self.initial, GAP_TARGET, lambda *_: None)

    def test_malformed_timestamp_rejected(self):
        def malformed(symbol, frame, first, last):
            rows = PublicSource()(symbol, frame, first, last)
            rows[1][0] = "not-a-time"
            return rows
        with self.assertRaisesRegex(ValueError, "RECOVERY_PROVIDER_TIMESTAMP_INVALID"):
            recover_gap(self.initial, GAP_TARGET, malformed)

    def test_downtime_just_above_max_rejected(self):
        with self.assertRaisesRegex(ValueError, "RECOVERY_TOO_OLD_MANUAL_REVIEW"):
            recovery_plan(self.initial, MAX_TARGET + 1)

    def test_no_time_travel_or_reusing_same_asof(self):
        for target in (ASOF, ASOF - 60_000):
            with self.assertRaisesRegex(ValueError, "RECOVERY_NONMONOTONIC_TIME"):
                recovery_plan(self.initial, target)

    def test_corrupted_base_sha_rejected(self):
        bad = replace(self.initial,
                      canonical_bytes=self.initial.canonical_bytes + b" ")
        with self.assertRaisesRegex(ValueError, "SNAPSHOT_INTEGRITY_FAILURE"):
            recovery_plan(bad, GAP_TARGET)

    def test_no_network_without_supplied_getter(self):
        with self.assertRaisesRegex(ValueError, "RECOVERY_GETTER_MISSING"):
            recover_gap(self.initial, GAP_TARGET, None)

    def test_a_failing_later_asset_does_not_modify_source(self):
        original_sha = self.initial.sha256_hex
        def late_failure(symbol, frame, first, last):
            if symbol == self.initial.symbols[-1] and frame == "4h":
                return []
            return PublicSource()(symbol, frame, first, last)
        with self.assertRaisesRegex(ValueError, "RECOVERY_CANDLES_INCOMPLETE"):
            recover_gap(self.initial, GAP_TARGET, late_failure)
        self.assertEqual(self.initial.sha256_hex, original_sha)
        self.initial.verify()


if __name__ == "__main__":
    unittest.main()
