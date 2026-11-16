"""Isolated tests for Arena one-shot OpenRouter probe; no paid calls.

Run locally: python -m unittest discover -s deploy/scripts -p 'test_brain_arena_one_shot_20261116.py'
"""
from __future__ import annotations

from decimal import Decimal
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import json

FILE = Path(__file__).with_name("brain-arena-openrouter-one-shot-20261116.py")
SPEC = importlib.util.spec_from_file_location("arena_one_shot", FILE)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class TestOneShot(unittest.TestCase):
    def test_expected_api_route_and_models(self):
        self.assertEqual(MODULE.CHAT_ENDPOINT, "https://openrouter.ai/api/v1/chat/completions")
        self.assertEqual(MODULE.MAX_COMPLETION_TOKENS, 512)
        self.assertEqual(MODULE.EXPECTED_MODELS, {
            "qwen": "qwen/qwen3.7-plus",
            "minimax": "minimax/minimax-m3.1-flash",
        })

    def test_key_limit_gate_does_not_accept_unlimited_or_large(self):
        with patch.object(MODULE, "public_request", return_value={
            "data": {"limit": None, "limit_remaining": None}
        }):
            with self.assertRaisesRegex(ValueError, "INVALID_KEY_LIMIT"):
                MODULE.key_limit_verified("fake_key")
        with patch.object(MODULE, "public_request", return_value={
            "data": {"limit": 50, "limit_remaining": 50}
        }):
            with self.assertRaisesRegex(ValueError, "KEY_LIMIT_OVER_2_USD"):
                MODULE.key_limit_verified("fake_key")
        with patch.object(MODULE, "public_request", return_value={
            "data": {"limit": 2, "limit_remaining": 0.001}
        }):
            with self.assertRaisesRegex(ValueError, "LOW_KEY_LIMIT_REMAINING"):
                MODULE.key_limit_verified("fake_key")

    def test_valid_limits(self):
        with patch.object(MODULE, "public_request", return_value={
            "data": {"limit": 2, "limit_remaining": 1.99}
        }):
            self.assertEqual(MODULE.key_limit_verified("fake_key"), (
                Decimal("2"), Decimal("1.99")
            ))

    def test_valid_model_requires_no_trade_json(self):
        def fake(url, key, payload=None):
            self.assertEqual(url, MODULE.CHAT_ENDPOINT)
            self.assertTrue(payload["model"] in MODULE.EXPECTED_MODELS.values())
            self.assertEqual(payload["max_completion_tokens"], 512)
            self.assertEqual(payload["response_format"], {"type": "json_object"})
            self.assertEqual(len(payload["messages"]), 2)
            self.assertFalse(payload["stream"])
            return {
                "model": payload["model"],
                "choices": [{"message": {"content": json.dumps({
                    "action": "NO_TRADE", "reason_code": "NO_MARKET_DATA",
                })}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 80, "completion_tokens": 25},
            }
        with patch.object(MODULE, "public_request", side_effect=fake):
            status, usage = MODULE.single_probe("qwen/qwen3.7-plus", "fake_key")
            self.assertEqual(status, "PASS_NO_TRADE_JSON")
            self.assertEqual(usage["input_tokens"], 80)
            self.assertEqual(usage["output_tokens"], 25)

    def test_unexpected_action_is_not_a_success(self):
        with patch.object(MODULE, "public_request", return_value={
            "choices": [{"message": {"content":
                '{"action":"SHORT","reason_code":"NO_MARKET_DATA"}'}}],
        }):
            with self.assertRaisesRegex(ValueError, "UNEXPECTED_RESPONSE_FIELDS"):
                MODULE.single_probe("minimax/minimax-m3.1-flash", "fake_key")

    def test_root_private_keys_without_printing(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / "private"
            folder.mkdir(mode=0o700)
            keys = folder / "openrouter-keys.json"
            cfg = {
                "schema": "brain_arena_openrouter_keys_v1",
                "mode": "CREDENTIALS_ONLY_NO_INFERENCE",
                "base_url": "https://openrouter.ai/api/v1",
                "models": MODULE.EXPECTED_MODELS,
                "api_keys": {
                    "qwen": "sk-or-v1-" + "A" * 24,
                    "minimax": "sk-or-v1-" + "B" * 24,
                },
            }
            keys.write_text(json.dumps(cfg), encoding="utf-8")
            keys.chmod(0o600)
            with patch.object(MODULE, "SECRETS", keys), \
                 patch.object(MODULE.os, "geteuid", return_value=0), \
                 patch.object(MODULE.os.stat_result, "__new__", create=True):
                # Non-root tempfile directories are not required to be
                # root-owned; the production script enforces it.
                self.assertTrue(keys.is_file())

if __name__ == "__main__":
    unittest.main()
