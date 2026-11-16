"""Offline regression tests: real Brain indicators on identical frozen market data."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from hashlib import sha256
import json
import unittest

from backend.v3.arena.compact_market import (
    CLASSIFICATION, build_compact_market,
)
from backend.v3.arena.frozen_market import FRAME_MS, FrozenMarketBatch, freeze_market_batch
from backend.v3.brain_market.params import load_default_params
from backend.v3.brain_market.view import min_bars

ASOF = 1795000000000


def _fixture():
    params = load_default_params()
    need = {"1m": 60}
    need.update({spec.name: min_bars(spec, params.indicators) for spec in params.timeframes})
    candles = {}
    for tf, step in FRAME_MS.items():
        n = need[tf]
        last = ASOF // step * step - step
        rows = []
        for i in range(n):
            stamp = last - (n - 1 - i) * step
            close = Decimal("100") + (Decimal(i % 17) / Decimal("10")) + (
                Decimal(i % 29) / Decimal("100"))
            rows.append([
                str(stamp), str(close), str(close + 2),
                str(close - 2), str(close), "100", "10000"
            ])
        candles[tf] = rows
    frozen = freeze_market_batch(
        {"BTCUSDT": candles}, need, asof_ms=ASOF,
        source_id="bitget.v2.synthetic-test"
    )
    return frozen, params


def _repack(frozen, change):
    data = json.loads(frozen.canonical_bytes)
    change(data)
    body = json.dumps(data, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")
    return FrozenMarketBatch(
        asof_ms=frozen.asof_ms, symbols=frozen.symbols,
        sha256_hex=sha256(body).hexdigest(), canonical_bytes=body
    )


class CompactBrainMarketTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frozen, cls.params = _fixture()
        cls.compact = build_compact_market(cls.frozen, cls.params)

    def test_all_three_providers_receive_identical_compact_market(self):
        payloads = [self.compact.for_provider(x) for x in
                    ("deepseek", "qwen", "minimax")]
        self.assertEqual(payloads[0], payloads[1])
        self.assertEqual(payloads[1], payloads[2])
        self.assertEqual(len(self.compact.sha256_hex), 64)

    def test_real_brain_market_view_uses_all_three_timeframes(self):
        doc = json.loads(self.compact.canonical_bytes)
        market = doc["markets"][0]["market"]
        self.assertEqual(market["base_tf"], "15m")
        self.assertNotEqual(market["regime"], "UNKNOWN")
        self.assertEqual([x["tf"] for x in market["timeframes"]],
                         ["15m", "1h", "4h"])
        self.assertTrue(all(x["status"] == "ok" for x in market["timeframes"]))
        self.assertIn("atr_pct_rank", market["timeframes"][0])
        self.assertIn("rsi", market["timeframes"][0])
        self.assertIn("adx", market["timeframes"][0])

    def test_raw_candles_not_sent_in_compact_payload(self):
        doc = json.loads(self.compact.canonical_bytes)
        self.assertEqual(doc["classification"], CLASSIFICATION)
        self.assertIs(doc["contains_raw_candles"], False)
        self.assertIs(doc["contains_trading_authorization"], False)
        self.assertNotIn("candles", doc)
        self.assertLess(len(self.compact.canonical_bytes),
                        len(self.frozen.canonical_bytes) // 10)

    def test_source_and_params_are_provenance_bound(self):
        doc = json.loads(self.compact.canonical_bytes)
        self.assertEqual(doc["source_snapshot_sha256"], self.frozen.sha256_hex)
        self.assertEqual(doc["params_sha256"], self.compact.params_sha256)
        self.assertEqual(doc["asof_ms"], ASOF)

    def test_no_unsigned_or_corrupted_payload(self):
        corrupt = replace(self.frozen, canonical_bytes=self.frozen.canonical_bytes + b" ")
        with self.assertRaisesRegex(ValueError, "SNAPSHOT_INTEGRITY_FAILURE"):
            build_compact_market(corrupt, self.params)
        corrupt_compact = replace(self.compact,
                                  canonical_bytes=self.compact.canonical_bytes + b" ")
        with self.assertRaisesRegex(ValueError, "COMPACT_INTEGRITY_FAILURE"):
            corrupt_compact.verify()

    def test_insufficient_atr_history_never_indicates_ready(self):
        broken = _repack(self.frozen,
                         lambda d: d["required"].__setitem__("15m", 80))
        with self.assertRaisesRegex(ValueError, "BRAIN_HISTORY_TOO_SHORT"):
            build_compact_market(broken, self.params)

    def test_partial_symbol_timeframes_fail_closed(self):
        broken = _repack(
            self.frozen, lambda d: d["candles"]["BTCUSDT"].pop("1m"))
        with self.assertRaisesRegex(ValueError, "FROZEN_TIMEFRAME_MISSING"):
            build_compact_market(broken, self.params)

    def test_invalid_quote_volume_never_builds_indicators(self):
        def patch(d):
            d["candles"]["BTCUSDT"]["1m"][-1][6] = "-100"
        broken = _repack(self.frozen, patch)
        with self.assertRaisesRegex(ValueError, "INVALID_OHLC"):
            build_compact_market(broken, self.params)

    def test_incompatible_market_config_fails_closed(self):
        broken = replace(self.params, base_timeframe="1h")
        with self.assertRaisesRegex(ValueError, "UNSUPPORTED_BRAIN_TIMEFRAMES"):
            build_compact_market(self.frozen, broken)

    def test_unknown_provider_or_injected_approval_rejected(self):
        with self.assertRaisesRegex(ValueError, "UNTRUSTED_ARENA_PROVIDER"):
            self.compact.for_provider("other")
        changed = replace(self.compact, classification="TRADE_APPROVED")
        with self.assertRaisesRegex(ValueError, "COMPACT_SCOPE_MISMATCH"):
            changed.verify()


if __name__ == "__main__":
    unittest.main()
