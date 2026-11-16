"""Pure unit tests for identical immutable multi-model market snapshot."""
from __future__ import annotations
from dataclasses import replace
import json
import unittest
from backend.v3.arena.frozen_market import freeze_market_batch, FRAME_MS

ASOF = 1795000000000
REQ = {"1m": 60, "15m": 2893, "1h": 733, "4h": 193}


def fixtures(symbols=("BTCUSDT", "XAUUSDT")):
    # Last completed time is the exact close immediately preceding ASOF.
    frames = {}
    for tf, step in FRAME_MS.items():
        latest = ASOF // step * step - step
        # Include one forming candle; it must never be frozen.
        frames[tf] = [[str(latest - i*step), "100.00", "102", "98", "101", "5", "500"]
                      for i in range(REQ[tf])]
        frames[tf].append([str(latest+step), "100", "102", "98", "101", "5", "500"])
    return {s: {tf: [row[:] for row in rows] for tf, rows in frames.items()}
            for s in symbols}


class FrozenTests(unittest.TestCase):
    def test_three_models_receive_identical_bytes_and_hash(self):
        raw = fixtures()
        batch = freeze_market_batch(raw, REQ, asof_ms=ASOF, source_id="bitget.v2.20261116")
        values = [batch.for_provider(provider) for provider in ("deepseek","qwen","minimax")]
        self.assertEqual(values[0], values[1])
        self.assertEqual(values[1], values[2])
        self.assertEqual(len(values[0][1]), 64)
        doc = json.loads(values[0][0]); self.assertEqual(doc["classification"],"PROVISIONAL_NOT_TRADE_APPROVED")
        self.assertEqual(len(doc["candles"]["BTCUSDT"]["15m"]), 2893)
        self.assertEqual(len(doc["candles"]["BTCUSDT"]["1h"]), 733)
        self.assertEqual(len(doc["candles"]["BTCUSDT"]["4h"]), 193)
        # The forming candle was excluded.
        for tf, step in FRAME_MS.items():
            self.assertEqual(doc["candles"]["BTCUSDT"][tf][-1][0], ASOF//step*step-step)

    def test_order_deterministic(self):
        data=fixtures(); original=freeze_market_batch(data,REQ,asof_ms=ASOF,source_id="source.01")
        reverse=dict(reversed(list(data.items())))
        another=freeze_market_batch(reverse,REQ,asof_ms=ASOF,source_id="source.01")
        self.assertEqual(original.sha256_hex, another.sha256_hex)

    def test_never_accept_partial_history_from_preflight(self):
        data=fixtures(("BTCUSDT",)); data["BTCUSDT"]["15m"]=data["BTCUSDT"]["15m"][-79:]
        with self.assertRaisesRegex(ValueError,"INSUFFICIENT_FULL_BRAIN_HISTORY"):
            freeze_market_batch(data,REQ,asof_ms=ASOF,source_id="source.01")

    def test_missing_timeframe_rejected(self):
        data=fixtures(("BTCUSDT",));del data["BTCUSDT"]["4h"]
        with self.assertRaisesRegex(ValueError,"INCOMPLETE_SYMBOL_TIMEFRAMES"):
            freeze_market_batch(data,REQ,asof_ms=ASOF,source_id="source.01")

    def test_gaps_rejected(self):
        data=fixtures(("BTCUSDT",));del data["BTCUSDT"]["15m"][100]
        # Still enough bars? after deleting one, one forming bar never counted.
        with self.assertRaises(ValueError):
            freeze_market_batch(data,REQ,asof_ms=ASOF,source_id="source.01")

    def test_future_candle_rejected(self):
        data=fixtures(("BTCUSDT",));data["BTCUSDT"]["1h"][5][0]=str((ASOF//3_600_000+2)*3_600_000)
        with self.assertRaisesRegex(ValueError,"FUTURE_CANDLE"):
            freeze_market_batch(data,REQ,asof_ms=ASOF,source_id="source.01")

    def test_duplicate_rejected(self):
        data=fixtures(("BTCUSDT",)); data["BTCUSDT"]["4h"].append(data["BTCUSDT"]["4h"][5][:])
        with self.assertRaisesRegex(ValueError,"DUPLICATE_OR_MISALIGNED_CANDLE"):
            freeze_market_batch(data,REQ,asof_ms=ASOF,source_id="source.01")

    def test_invalid_prices_nan_and_volume_rejected(self):
        for col,bad in ((1,"NaN"),(2,"-1"),(3,"105"),(5,"-50"),(1,"inf")):
            with self.subTest(col=col,bad=bad):
                data=fixtures(("BTCUSDT",));data["BTCUSDT"]["1m"][5][col]=bad
                with self.assertRaises(ValueError):
                    freeze_market_batch(data,REQ,asof_ms=ASOF,source_id="source.01")

    def test_tampered_bytes_rejected(self):
        data=fixtures(("BTCUSDT",));batch=freeze_market_batch(data,REQ,asof_ms=ASOF,source_id="source.01")
        fake=replace(batch,canonical_bytes=batch.canonical_bytes+b" ")
        with self.assertRaisesRegex(ValueError,"SNAPSHOT_INTEGRITY_FAILURE"):
            fake.for_provider("qwen")
        with self.assertRaisesRegex(ValueError,"UNTRUSTED_ARENA_PROVIDER"):
            batch.for_provider("not-the-model")

    def test_unapproved_classification_cannot_be_overridden(self):
        data=fixtures(("BTCUSDT",));batch=freeze_market_batch(data,REQ,asof_ms=ASOF,source_id="source.01")
        fake=replace(batch,classification="TRADE_APPROVED")
        with self.assertRaisesRegex(ValueError,"SNAPSHOT_SCOPE_MISMATCH"):
            fake.verify()

    def test_stale_last_bar_rejected(self):
        data=fixtures(("BTCUSDT",))
        for row in data["BTCUSDT"]["15m"]: row[0]=str(int(row[0])-2*900_000)
        with self.assertRaisesRegex(ValueError,"STALE_SNAPSHOT_HISTORY"):
            freeze_market_batch(data,REQ,asof_ms=ASOF,source_id="source.01")

if __name__ == "__main__": unittest.main()
