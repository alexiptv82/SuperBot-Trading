"""Traccia delle chiamate: misura senza contenuti. Nessuna rete."""
from __future__ import annotations

import json

import pytest

from backend.v3.arena.inference_trace import TracedTransport
from backend.v3.brain_f3.providers import ProviderUnavailable, TransportResponse

PAYLOAD = {"model": "deepseek-flash", "max_tokens": 6000, "thinking": {"type": "enabled"},
           "reasoning_effort": "high", "messages": [{"role": "user", "content": "SEGRETO-PROMPT"}]}


def test_records_reasoning_params_tokens_latency_without_content(tmp_path):
    clock = iter([10.0, 12.5])
    body = {"choices": [{"finish_reason": "stop", "message": {"content": "RISPOSTA-PRIVATA"}}],
            "usage": {"prompt_tokens": 3000, "completion_tokens": 900,
                      "completion_tokens_details": {"reasoning_tokens": 700}, "cost": 0.0012}}
    t = TracedTransport(lambda p: TransportResponse(200, body), tmp_path / "t.jsonl", provider="deepseek",
                        monotonic=lambda: next(clock), wall_ms=lambda: 1)
    t(PAYLOAD)
    raw = (tmp_path / "t.jsonl").read_text()
    rec = json.loads(raw)
    assert rec["reasoning_params_sent"] == {"thinking": {"type": "enabled"}, "reasoning_effort": "high"}
    assert (rec["prompt_tokens"], rec["completion_tokens"], rec["reasoning_tokens"]) == (3000, 900, 700)
    assert rec["latency_ms"] == 2500 and rec["finish_reason"] == "stop" and rec["provider_reported_cost"] == "0.0012"
    assert "SEGRETO" not in raw and "PRIVATA" not in raw


def test_errors_are_traced_and_still_raised_and_trace_failure_never_blocks(tmp_path):
    def boom(_p):
        raise ProviderUnavailable("provider_disabled")
    t = TracedTransport(boom, tmp_path / "t.jsonl", provider="qwen")
    with pytest.raises(ProviderUnavailable):
        t(PAYLOAD)
    rec = json.loads((tmp_path / "t.jsonl").read_text())
    assert rec["outcome"] == "error" and rec["error_code"] == "provider_disabled"
    ok = TracedTransport(lambda p: TransportResponse(200, {}), tmp_path / "missing" / "t.jsonl", provider="qwen")
    assert ok(PAYLOAD).status_code == 200 and ok.write_failures == 1
