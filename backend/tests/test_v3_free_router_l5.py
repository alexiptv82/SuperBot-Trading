"""Router LLM gratuito: HTTP finto, nessun provider reale."""
import json
import logging
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest

from backend.v3.brain_f2.analyst import Analyst
from backend.v3.brain_f2.contracts import BrainDecision, DecisionKind, MarketContext
from backend.v3.brain_f2.engine import BrainEngine, BrainPortfolioSnapshot, _policy_hash
from backend.v3.brain_f2.reviewer import MockClaudeReviewer
from backend.v3.brain_f3.providers import ProviderUnavailable
from backend.v3.brain_market.free_router_l5 import (
    FreeRouterL5Analyst, RouterCall, RouterFailure, brain_llm_provider,
    deepseek_fallback_enabled, http_post, validate_router_url,
)
from backend.v3.events import EventJournal
from backend.v3.risk import RiskPolicy

CTX = MarketContext("BTCUSDT", Decimal("100"), 1_700_000_000_000, "TREND_UP")
KEY = "local-test-key-not-a-secret"


class Template:
    max_tokens = 128

    def l5_packet(self, context, positions):
        return json.dumps({"symbol": context.symbol}, sort_keys=True), ["deepseek:analysis"]


class Fallback:
    def __init__(self, mode="open"):
        self.calls = 0
        self.mode = mode

    def analyze(self, context, positions):
        self.calls += 1
        if self.mode == "cap":
            raise ProviderUnavailable("budget_denied")
        if self.mode == "fail":
            raise ProviderUnavailable("provider_unavailable")
        return BrainDecision(kind=DecisionKind.OPEN, rationale="deepseek:analysis",
                             sources=["deepseek:analysis"], occurred_at_ms=context.timestamp_ms)


def _settings(**extra):
    base = {"url": "http://127.0.0.1:3001/v1", "key": KEY, "model": "auto:smart",
            "timeout_s": 5, "allow_remote": False}
    base.update(extra)
    return base


def _chat(content, status=200, headers=None):
    raw = json.dumps({
        "choices": [{"finish_reason": "stop", "message": {"content": content}}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 4},
    }).encode()
    return RouterCall(status, headers or {}, raw, 12)


def _analyst(poster, fallback=None, enabled=True, settings=None):
    return FreeRouterL5Analyst(
        template=Template(), fallback=fallback if fallback is not None else Fallback(),
        fallback_enabled=enabled, settings=settings or _settings(), poster=poster)


def test_valid_open_and_valid_no_trade_do_not_fall_back():
    fallback = Fallback()
    opened = _analyst(lambda *_: _chat(
        json.dumps({"kind": "OPEN", "side": 1, "entry_price": "100", "stop_price": "99",
                    "leverage": 2, "confidence": 0.7, "strategy_id": "S07",
                    "strategy_origin": "library"}),
        headers={"X-Routed-Via": "groq", "X-Fallback-Attempts": "0"}), fallback)
    decision = opened.analyze(CTX, [])
    assert decision.kind == DecisionKind.OPEN
    assert decision.proposal.side == 1 and decision.proposal.originating_ai == "free_router"
    assert decision.llm_route["source"] == "free_router"
    assert decision.llm_route["routed_via"] == "groq"
    assert decision.llm_route["fallback_attempts"] == 0
    assert decision.llm_route["prompt_tokens"] == 3
    assert fallback.calls == 0
    held = _analyst(lambda *_: _chat(json.dumps({"kind": "NO_TRADE"})), fallback)
    no_trade = held.analyze(CTX, [])
    assert no_trade.kind == DecisionKind.NO_TRADE
    assert no_trade.rationale == "free_router:analysis"
    assert no_trade.llm_route["source"] == "free_router"
    assert "router_failure" not in no_trade.llm_route
    assert fallback.calls == 0


def _raise(code):
    def post(*_a):
        raise RouterFailure(code)
    return post


@pytest.mark.parametrize("poster,code", [
    (_raise("free_router:timeout"), "free_router:timeout"),
    (_raise("free_router:connection"), "free_router:connection"),
    (_raise("free_router:missing_key"), "free_router:missing_key"),
    (_raise("free_router:url_rejected"), "free_router:url_rejected"),
    (lambda *_: RouterCall(429, {"x-routed-via": "groq"}, b"", 4), "free_router:http_429"),
    (lambda *_: RouterCall(503, {}, b"", 4), "free_router:http_5xx"),
    (lambda *_: RouterCall(200, {}, b"not-json", 4), "free_router:invalid_json"),
    (lambda *_: _chat(json.dumps({"kind": "OPEN", "side": 1})), "free_router:schema"),
])
def test_each_router_failure_falls_back_once(poster, code):
    fallback = Fallback()
    decision = _analyst(poster, fallback).analyze(CTX, [])
    assert fallback.calls == 1
    assert decision.llm_route["source"] == "deepseek_fallback"
    assert decision.llm_route["router_failure"] == code
    assert decision.llm_route["deepseek_cost_units"] == 0


def test_valid_no_trade_never_falls_back():
    fallback = Fallback()
    decision = _analyst(lambda *_: _chat(json.dumps({"kind": "NO_TRADE"})), fallback).analyze(CTX, [])
    assert decision.kind == DecisionKind.NO_TRADE and fallback.calls == 0


def test_disabled_fallback_is_no_trade_without_deepseek():
    fallback = Fallback()
    decision = _analyst(lambda *_: RouterCall(500, {}, b"", 1), fallback, enabled=False).analyze(CTX, [])
    assert decision.kind == DecisionKind.NO_TRADE
    assert decision.rationale == "free_router:http_5xx"
    assert fallback.calls == 0


def test_deepseek_failure_and_cap_are_no_trade():
    failed = _analyst(lambda *_: RouterCall(500, {}, b"", 1), Fallback("fail")).analyze(CTX, [])
    assert failed.kind == DecisionKind.NO_TRADE
    assert failed.rationale == "free_router:deepseek_failed"
    capped = _analyst(lambda *_: RouterCall(500, {}, b"", 1), Fallback("cap")).analyze(CTX, [])
    assert capped.rationale == "free_router:deepseek_cap"
    assert capped.llm_route["source"] == "deepseek_fallback"


def test_one_fallback_per_symbol_and_cycle():
    fallback = Fallback()
    analyst = _analyst(lambda *_: RouterCall(429, {}, b"", 1), fallback)
    first = analyst.analyze(CTX, [])
    second = analyst.analyze(CTX, [])
    assert fallback.calls == 1
    assert first.llm_route["source"] == "deepseek_fallback"
    assert second.rationale == "free_router:fallback_used"
    other = MarketContext("ETHUSDT", Decimal("100"), CTX.timestamp_ms, "TREND_UP")
    analyst.analyze(other, [])
    assert fallback.calls == 2


def test_default_provider_is_deepseek_and_fallback_defaults_only_for_router(monkeypatch):
    monkeypatch.delenv("BRAIN_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("DEEPSEEK_FALLBACK", raising=False)
    assert brain_llm_provider() == "deepseek"
    assert deepseek_fallback_enabled() is False
    monkeypatch.setenv("BRAIN_LLM_PROVIDER", "free_router")
    assert deepseek_fallback_enabled() is True
    monkeypatch.setenv("DEEPSEEK_FALLBACK", "false")
    assert deepseek_fallback_enabled() is False


def test_public_url_is_rejected_and_loopback_is_accepted():
    with pytest.raises(RouterFailure) as raised:
        validate_router_url("https://api.openai.com/v1")
    assert raised.value.code == "free_router:url_rejected"
    assert validate_router_url("http://127.0.0.1:3001/v1").startswith("http://127.0.0.1")
    assert validate_router_url("http://10.1.2.3:3001/v1").startswith("http://10.1.2.3")
    with pytest.raises(RouterFailure):
        http_post(_settings(url="http://1.2.3.4/v1", key=KEY), {"model": "auto:smart"})


def test_key_never_appears_in_logs(caplog):
    caplog.set_level(logging.INFO)
    decision = _analyst(lambda *_: RouterCall(500, {}, b"", 1), Fallback("fail"),
                        settings=_settings(key=KEY)).analyze(CTX, [])
    text = caplog.text + json.dumps(decision.llm_route)
    assert KEY not in text
    assert "127.0.0.1" not in text


def test_journal_records_fallback_source_reason_and_cost(tmp_path):
    journal = EventJournal(str(tmp_path / "j.sqlite"))
    journal.init_schema()
    route = {"source": "deepseek_fallback", "router_failure": "free_router:timeout",
             "deepseek_cost_units": 42, "routed_via": "https://secret.example/key"}

    class One(Analyst):
        def analyze(self, context, open_positions):
            return BrainDecision(kind=DecisionKind.NO_TRADE, rationale="free_router:timeout",
                                 sources=["free_router:analysis"], occurred_at_ms=context.timestamp_ms,
                                 llm_route=route)

    policy = RiskPolicy(Decimal(".02"), Decimal(".05"), Decimal(".1"), Decimal(".3"),
                        Decimal("450"), Decimal("16"), Decimal(".5"))
    engine = BrainEngine(
        One(), MockClaudeReviewer(always_approve=True), risk_policy=policy,
        portfolio_snapshot=BrainPortfolioSnapshot(Decimal("1000"), Decimal("1000"), Decimal("0"), Decimal("0")),
        market_params={"exchange_leverage_limit": 10, "quantity_step": Decimal("0.001"),
                       "minimum_notional": Decimal("5"), "maintenance_fraction": Decimal("0.004"),
                       "market_data_fresh": True, "paused": False, "daily_loss_latched": False},
        journal=journal, run_id="router-synthetic",
        policy_mandate={"version": "t", "approved": True, "approved_by": "operator",
                        "policy_hash": _policy_hash(policy)},
        policy_verifier=lambda *_a: True)
    decision = engine.step(CTX, 0.0)
    payload = journal.list_run("brain", "router-synthetic")[-1].event.payload
    assert decision.llm_route["source"] == "deepseek_fallback"
    assert payload["llm_route"]["router_failure"] == "free_router:timeout"
    assert payload["llm_route"]["deepseek_cost_units"] == 42
    assert "routed_via" not in payload["llm_route"]
    assert KEY not in json.dumps(payload)


def test_local_http_server_open_and_header():
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.dumps({
                "choices": [{"finish_reason": "stop", "message": {"content": json.dumps({
                    "kind": "NO_TRADE"})}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("X-Routed-Via", "cerebras")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_a):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/v1"
        call = http_post(_settings(url=url, key=KEY), {"model": "auto:smart", "messages": []})
        assert call.status == 200
        assert call.headers["x-routed-via"] == "cerebras"
        decision = _analyst(lambda *_: call, Fallback()).analyze(CTX, [])
        assert decision.kind == DecisionKind.NO_TRADE and decision.llm_route["routed_via"] == "cerebras"
    finally:
        server.shutdown()
