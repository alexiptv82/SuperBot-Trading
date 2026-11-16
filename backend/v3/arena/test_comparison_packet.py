"""Offline strict regression: 25-market same-input three-AI research packet."""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
import unittest

from backend.v3.arena.compact_market import build_compact_market
from backend.v3.arena.comparison_packet import (
    build_common_packet, parse_research_choice, CLASSIFICATION, LANES,
)
from backend.v3.arena.frozen_market import freeze_market_batch
from backend.v3.arena.test_compact_market import _fixture


def _shared_fixture():
    one, params = _fixture()
    doc = json.loads(one.canonical_bytes)
    markets = ("BTCUSDT",) + tuple(
        "ASSET" + str(i) + "USDT" for i in range(1, 23)
    ) + ("XAUUSDT", "XAGUSDT")
    assert len(markets) == 25
    candles = {symbol: doc["candles"]["BTCUSDT"] for symbol in markets}
    snapshot = freeze_market_batch(
        candles, doc["required"], asof_ms=one.asof_ms,
        source_id="bitget.v2.synthetic-common-25",
    )
    compact = build_compact_market(snapshot, params)
    return compact, build_common_packet(compact)


class CommonPacketTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compact, cls.packet = _shared_fixture()

    def test_all_models_receive_exactly_identical_messages(self):
        messages = [self.packet.identical_messages(p) for p in LANES]
        self.assertEqual(messages[0], messages[1])
        self.assertEqual(messages[1], messages[2])
        self.assertEqual(len(self.packet.symbols), 25)

    def test_lossless_indicator_fields_for_each_market_and_tf(self):
        raw = json.loads(self.compact.canonical_bytes)
        packet = json.loads(self.packet.canonical_market_bytes)
        names = packet["columns"]
        for original, packed in zip(raw["markets"], packet["rows"]):
            self.assertEqual(original["symbol"], packed[0])
            self.assertEqual(original["market"]["regime"], packed[1])
            for src_tf, compacted in zip(original["market"]["timeframes"], packed[2]):
                self.assertEqual(
                    {key: compacted[idx] for idx, key in enumerate(names)},
                    {key: src_tf[key] for key in names},
                )

    def test_payload_fits_transport_limit_and_has_no_raw_candles(self):
        self.assertLessEqual(len(self.packet.canonical_market_bytes), 24000)
        self.assertLess(len(self.packet.canonical_market_bytes), 25000)
        msg = self.packet.identical_messages("minimax")
        self.assertLessEqual(len(msg[1]["content"]), 25000)
        self.assertNotIn('"candles"', msg[1]["content"])
        self.assertIn("RESEARCH_ONLY_NOT_TRADE_APPROVED", msg[1]["content"])

    def test_packet_source_digest_and_policy_pinned(self):
        doc = json.loads(self.packet.canonical_market_bytes)
        self.assertEqual(doc["input_compact_sha256"], self.compact.sha256_hex)
        self.assertEqual(self.packet.packet_sha256, sha256(self.packet.canonical_market_bytes).hexdigest())
        self.assertEqual(self.packet.classification, CLASSIFICATION)

    def test_tampered_common_packet_rejected(self):
        broken = replace(
            self.packet,
            canonical_market_bytes=self.packet.canonical_market_bytes + b" ",
        )
        with self.assertRaisesRegex(ValueError, "ARENA_COMMON_PACKET_INTEGRITY"):
            broken.verify()
        with self.assertRaisesRegex(ValueError, "ARENA_COMMON_PROVIDER_UNKNOWN"):
            self.packet.identical_messages("untrusted")

    def test_valid_candidate_is_never_an_order(self):
        result = parse_research_choice(
            self.packet, {
                "action": "CANDIDATE", "symbol": "BTCUSDT",
                "side": "SHORT", "confidence": 0.72,
                "reason_code": "MTF_DOWNTREND",
            },
        )
        self.assertEqual(result.action, "CANDIDATE")
        self.assertEqual(result.classification, CLASSIFICATION)
        self.assertFalse(hasattr(result, "leverage"))
        self.assertFalse(hasattr(result, "order_id"))

    def test_valid_no_trade(self):
        result = parse_research_choice(self.packet, {
            "action": "NO_TRADE", "symbol": "", "side": "NONE",
            "confidence": 0, "reason_code": "NO_CLEAR_EDGE",
        })
        self.assertEqual(result.action, "NO_TRADE")

    def test_invalid_unlisted_symbol_blocked(self):
        with self.assertRaisesRegex(ValueError, "ARENA_CHOICE_INVALID_CANDIDATE"):
            parse_research_choice(self.packet, {
                "action": "CANDIDATE", "symbol": "FAKEUSDT",
                "side": "LONG", "confidence": 0.8,
                "reason_code": "DIRECTIONAL_SETUP",
            })

    def test_extra_order_fields_refused(self):
        with self.assertRaisesRegex(ValueError, "ARENA_CHOICE_INVALID_FIELDS"):
            parse_research_choice(self.packet, {
                "action": "CANDIDATE", "symbol": "BTCUSDT",
                "side": "SHORT", "confidence": 0.8,
                "reason_code": "DIRECTIONAL_SETUP",
                "leverage": 50, "order": "BUY",
            })

    def test_no_trade_cannot_carry_direction(self):
        with self.assertRaisesRegex(ValueError, "ARENA_CHOICE_MALFORMED_NO_TRADE"):
            parse_research_choice(self.packet, {
                "action": "NO_TRADE", "symbol": "BTCUSDT",
                "side": "SHORT", "confidence": 0,
                "reason_code": "NO_CLEAR_EDGE",
            })

    def test_unbounded_or_invalid_confidence_rejected(self):
        for value in [float("nan"), float("inf"), -1, 1.01]:
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "ARENA_CHOICE_INVALID_CONFIDENCE"):
                    parse_research_choice(self.packet, {
                        "action": "CANDIDATE", "symbol": "BTCUSDT",
                        "side": "SHORT", "confidence": value,
                        "reason_code": "DIRECTIONAL_SETUP",
                    })

    def test_unknown_action_and_freeform_reason_rejected(self):
        for action, reason, err in [
            ("OPEN", "DIRECTIONAL_SETUP", "ARENA_CHOICE_ACTION_NOT_ALLOWED"),
            ("CANDIDATE", "send-order-now", "ARENA_CHOICE_INVALID_FIELDS"),
        ]:
            with self.subTest(action=action):
                with self.assertRaisesRegex(ValueError, err):
                    parse_research_choice(self.packet, {
                        "action": action, "symbol": "BTCUSDT",
                        "side": "SHORT", "confidence": 0.8,
                        "reason_code": reason,
                    })


if __name__ == "__main__":
    unittest.main()
