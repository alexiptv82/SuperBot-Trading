"""No-network tests of the three-provider one-shot research boundary."""
from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import unittest

from backend.v3.arena.test_comparison_packet import _shared_fixture


def module():
    root = Path(__file__).resolve().parents[3]
    script = root / "deploy/scripts/arena-three-ai-research-oneshot-20261116.py"
    spec = spec_from_file_location("arena_research_one_shot_offline", script)
    instance = module_from_spec(spec)
    spec.loader.exec_module(instance)
    return instance


class ThreeAIResearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = module()
        _, cls.packet = _shared_fixture()

    def test_three_models_shared_market(self):
        bodies = [self.m._body(n, self.packet) for n in self.m.ORDER]
        self.assertEqual(len(bodies), 3)
        self.assertEqual(bodies[0]["messages"], bodies[1]["messages"])
        self.assertEqual(bodies[1]["messages"], bodies[2]["messages"])
        self.assertEqual(len(bodies[0]["messages"]), 2)

    def test_budget_gate_passes_private_limited_key(self):
        self.assertEqual(
            self.m._budget_gate({"data": {"limit": 2, "limit_remaining": 1.25}})[1],
            self.m.Decimal("1.25"),
        )

    def test_budget_gate_rejects_50_dollar_key(self):
        with self.assertRaisesRegex(ValueError, "KEY_BUDGET_DENIED"):
            self.m._budget_gate({"data": {"limit": 50, "limit_remaining": 10}})

    def test_budget_gate_rejects_low_credit(self):
        with self.assertRaisesRegex(ValueError, "KEY_BUDGET_DENIED"):
            self.m._budget_gate({"data": {"limit": 2, "limit_remaining": 0.01}})

    def test_budget_gate_rejects_missing_details(self):
        with self.assertRaisesRegex(ValueError, "KEY_BUDGET_UNVERIFIED"):
            self.m._budget_gate({})

    def test_choice_parser_accepts_same_no_trade_schema_for_all(self):
        for lane in self.m.ORDER:
            body = {"choices": [{
                "finish_reason": "stop",
                "message": {"content": (
                    '{"action":"NO_TRADE","symbol":"","side":"NONE",'
                    '"confidence":0,"reason_code":"NO_CLEAR_EDGE"}'
                )},
            }], "usage": {"prompt_tokens": 1234, "completion_tokens": 18}}
            result = self.m._read_choice(lane, self.packet, body)
            self.assertEqual(result["action"], "NO_TRADE")
            self.assertEqual(result["symbol"], "")

    def test_choice_parser_accepts_single_valid_candidate(self):
        body = {"choices": [{
            "finish_reason": "stop",
            "message": {"content": (
                '{"action":"CANDIDATE","symbol":"BTCUSDT","side":"SHORT",'
                '"confidence":0.7,"reason_code":"TREND_CONFIRMATION"}'
            )},
        }]}
        result = self.m._read_choice("qwen", self.packet, body)
        self.assertEqual(result["side"], "SHORT")
        self.assertEqual(result["confidence"], "0.7")

    def test_incomplete_model_response_rejected(self):
        bad = {"choices": [{
            "finish_reason": "length",
            "message": {"content": (
                '{"action":"CANDIDATE","symbol":"BTCUSDT","side":"SHORT",'
                '"confidence":0.7,"reason_code":"TREND_CONFIRMATION"}'
            )},
        }]}
        with self.assertRaisesRegex(ValueError, "MODEL_NOT_COMPLETED"):
            self.m._read_choice("deepseek", self.packet, bad)

    def test_order_like_response_blocked(self):
        bad = {"choices": [{"finish_reason": "stop", "message": {"content": (
            '{"action":"OPEN","symbol":"BTCUSDT","side":"SHORT",'
            '"confidence":0.7,"reason_code":"TREND_CONFIRMATION"}'
        )}}]}
        with self.assertRaisesRegex(ValueError, "ARENA_CHOICE_ACTION_NOT_ALLOWED"):
            self.m._read_choice("minimax", self.packet, bad)

    def test_paid_calls_not_triggered_by_selftest(self):
        self.assertEqual(self.m.selftest(), 0)

    def test_model_specific_formats_only(self):
        b = {lane: self.m._body(lane, self.packet) for lane in self.m.ORDER}
        self.assertEqual(b["qwen"]["response_format"]["type"], "json_schema")
        self.assertEqual(b["minimax"]["response_format"], {"type": "json_object"})
        self.assertEqual(b["deepseek"]["response_format"], {"type": "json_object"})
        self.assertEqual(
            {z["model"] for z in b.values()},
            set(self.m.MODEL_IDS.values()),
        )


if __name__ == "__main__":
    unittest.main()
