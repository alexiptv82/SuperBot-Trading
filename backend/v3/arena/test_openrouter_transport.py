"""Offline-only tests for isolated OpenRouter Brain Arena provider transport."""
from __future__ import annotations

from unittest import TestCase, main
from unittest.mock import patch
from pathlib import Path
import json
import tempfile

from backend.v3.arena.openrouter_transport import (
    MODELS, _read_key, _verify_key_budget, openrouter_transport,
)
from backend.v3.brain_f3.providers import ProviderUnavailable, TransportResponse


def sample_payload(model: str) -> dict:
    return {
        "model": model, "stream": False, "max_tokens": 256,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": "Return JSON only."},
            {"role": "user", "content": '{"symbol":"BTCUSDT","regime":"UNKNOWN"}'},
        ],
    }


class TestArenaOpenRouterTransport(TestCase):
    def test_disabled_by_default_does_not_read_keys_or_call_api(self):
        calls = []
        factory = openrouter_transport(
            "qwen",
            request=lambda *a: calls.append(a),
            key_reader=lambda name: calls.append(("KEY", name)),
        )
        with patch.dict("os.environ", {"DESK_MODE": "paper"}):
            with self.assertRaisesRegex(ProviderUnavailable, "provider_disabled"):
                factory(sample_payload(MODELS["qwen"]))
        self.assertEqual(calls, [])

    def test_reject_non_paper_before_network(self):
        calls = []
        transport = openrouter_transport(
            "minimax", allow_inference=True,
            request=lambda *a: calls.append(a),
            key_reader=lambda name: calls.append(("KEY", name)),
            spending_gate=lambda provider: True,
        )
        with patch.dict("os.environ", {"DESK_MODE": "live"}):
            with self.assertRaisesRegex(ProviderUnavailable, "provider_disabled"):
                transport(sample_payload(MODELS["minimax"]))
        self.assertEqual(calls, [])

    def test_provider_mismatch_and_unsafe_payload_fail_before_key(self):
        calls = []
        transport = openrouter_transport(
            "minimax", allow_inference=True,
            request=lambda *a: calls.append(a),
            key_reader=lambda name: calls.append(name),
            spending_gate=lambda provider: True,
        )
        with patch.dict("os.environ", {"DESK_MODE": "paper"}):
            with self.assertRaisesRegex(ProviderUnavailable, "invalid_model_payload"):
                transport(sample_payload(MODELS["qwen"]))
            bad = sample_payload(MODELS["minimax"])
            bad["tools"] = [{"type":"function", "function":{"name":"send_order"}}]
            with self.assertRaisesRegex(ProviderUnavailable, "invalid_model_payload"):
                transport(bad)
            bad = sample_payload(MODELS["minimax"])
            bad["max_tokens"] = 100_000
            with self.assertRaisesRegex(ProviderUnavailable, "invalid_model_payload"):
                transport(bad)
        self.assertEqual(calls, [])


    def test_missing_or_denied_budget_gate_never_reads_key(self):
        for gate in (None, lambda provider: False):
            calls = []
            provider = openrouter_transport(
                "qwen", allow_inference=True, spending_gate=gate,
                request=lambda *args: calls.append(args),
                key_reader=lambda p: calls.append(("secret", p)),
            )
            with patch.dict("os.environ", {"DESK_MODE": "paper"}):
                with self.assertRaisesRegex(ProviderUnavailable, "budget_denied"):
                    provider(sample_payload(MODELS["qwen"]))
            self.assertEqual(calls, [])

    def test_invalid_or_unlimited_budget_fails_closed(self):
        for data in (
            {}, {"data": {"limit": None, "limit_remaining": None}},
            {"data": {"limit": 50, "limit_remaining": 20}},
            {"data": {"limit": 2, "limit_remaining": 0.001}},
            {"data": {"limit": 2, "limit_remaining": "NaN"}},
            {"data": {"limit": 2, "limit_remaining": 2, "is_management_key": True}},
        ):
            with self.subTest(data=data):
                with self.assertRaises(ProviderUnavailable):
                    _verify_key_budget(data)

    def test_only_selected_key_used_and_no_retry(self):
        traces = []
        def request(path, key, payload):
            traces.append((path, key, payload))
            if path == "/key":
                return {"data": {"limit": 2, "limit_remaining": 1.95}}
            return {"model": MODELS["qwen"], "choices": [
                {"finish_reason":"stop", "message":{"content":'{"kind":"NO_TRADE"}'}}
            ]}
        def read_key(name):
            traces.append(("selected", name, None))
            return "qwen-private-synthetic"
        provider = openrouter_transport(
            "qwen", allow_inference=True,
            request=request, key_reader=read_key,
            spending_gate=lambda name: name == "qwen",
        )
        with patch.dict("os.environ", {"DESK_MODE": "paper"}):
            response = provider(sample_payload(MODELS["qwen"]))
        self.assertIsInstance(response, TransportResponse)
        self.assertEqual(response.body["model"], MODELS["qwen"])
        self.assertEqual([p[0] for p in traces], ["selected", "/key", "/chat/completions"])
        self.assertEqual(traces[0][1], "qwen")
        self.assertTrue(all("minimax" not in str(x) for x in traces))

    def test_failed_provider_call_has_no_fallback_to_other_model(self):
        paths = []
        def broken(path, key, payload):
            paths.append(path)
            if path == "/key":
                return {"data": {"limit": 2, "limit_remaining": 1.9}}
            raise RuntimeError("internal-should-not-leak-private-details")
        provider = openrouter_transport(
            "qwen", allow_inference=True, request=broken,
            key_reader=lambda _: "synthetic-qwen-key",
            spending_gate=lambda provider: provider == "qwen",
        )
        with patch.dict("os.environ", {"DESK_MODE": "paper"}):
            with self.assertRaisesRegex(ProviderUnavailable, "^provider_unavailable$"):
                provider(sample_payload(MODELS["qwen"]))
        self.assertEqual(paths, ["/key", "/chat/completions"])

    def test_key_reader_rejects_invalid_parent_or_mode(self):
        # No root-only file is created by this unit test.
        with patch("backend.v3.arena.openrouter_transport.os.geteuid", return_value=1000):
            with self.assertRaisesRegex(ProviderUnavailable, "provider_disabled"):
                _read_key("qwen")


if __name__ == "__main__":
    main()
