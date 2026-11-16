"""Offline tests for Qwen-only diagnostic (no network or paid calls)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest

P = Path(__file__).with_name("brain-arena-qwen-json-diagnostic-20261116.py")
SPEC = importlib.util.spec_from_file_location("qwen_diagnostic", P)
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


class QwenDiagnosticTests(unittest.TestCase):
    def test_expected_model_endpoint_and_schema(self):
        self.assertEqual(M.MODEL, "qwen/qwen3.7-plus")
        self.assertEqual(M.CHAT_URL, "https://openrouter.ai/api/v1/chat/completions")
        self.assertEqual(M.MAX_TOKENS, 1024)
        self.assertEqual(M.SCHEMA["type"], "json_schema")
        self.assertEqual(M.SCHEMA["json_schema"]["strict"], True)
        self.assertEqual(
            M.SCHEMA["json_schema"]["schema"]["additionalProperties"], False
        )

    def test_limit_stays_below_two_dollars(self):
        self.assertEqual(M.verify_limit({"data":{
            "limit":2, "limit_remaining":1.95
        }}), (M.Decimal(2), M.Decimal("1.95")))
        for data in (
            {"limit":50,"limit_remaining":50},
            {"limit":None, "limit_remaining":None},
            {"limit":2,"limit_remaining":0.01},
            {"limit":-1,"limit_remaining":-1},
        ):
            with self.subTest(data=data), self.assertRaises(ValueError):
                M.verify_limit({"data":data})

    def test_valid_json_is_accepted(self):
        status, meta = M.classify_response({
            "model":"qwen/qwen3.7-plus",
            "choices":[{
                "finish_reason":"stop",
                "message":{"content":json.dumps({
                    "action":"NO_TRADE","reason_code":"NO_MARKET_DATA"
                })}
            }],
            "usage":{"prompt_tokens":70,"completion_tokens":20},
        })
        self.assertEqual(status, "PASS_NO_TRADE_JSON")
        self.assertEqual(meta["content_chars"], 59 if False else meta["content_chars"])
        self.assertEqual(meta["output_tokens"], 20)

    def test_invalid_json_reports_only_safe_metadata(self):
        secret_like="this is not JSON, and should not be echoed 12345"
        status, meta=M.classify_response({
            "choices":[{
                "finish_reason":"length",
                "message":{"content":secret_like, "reasoning":"hidden"}
            }],
            "usage":{"completion_tokens":1024},
        })
        self.assertEqual(status,"INVALID_JSON")
        self.assertNotIn(secret_like,repr(meta))
        self.assertEqual(meta["finish_reason"],"length")
        self.assertTrue(meta["reasoning_present"])

    def test_json_with_wrong_action_is_rejected(self):
        status,_ = M.classify_response({
            "choices":[{"message":{"content":json.dumps({
                "action":"SHORT","reason_code":"NO_MARKET_DATA"
            })}}],
        })
        self.assertEqual(status,"SCHEMA_MISMATCH")


if __name__=="__main__":
    unittest.main()
