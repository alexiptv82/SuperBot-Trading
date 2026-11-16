"""Offline tests: Qwen and MiniMax decisions reuse Brain L5 indicators, never orders."""
from __future__ import annotations

from decimal import Decimal
import json
from unittest import TestCase, main
from unittest.mock import patch

from backend.v3.arena.l5_analyst import ArenaL5Analyst
from backend.v3.arena.openrouter_transport import MODELS, ARENA_RESPONSE_FORMAT
from backend.v3.brain_f2.contracts import DecisionKind, MarketContext
from backend.v3.brain_f3.providers import ProviderUnavailable, TransportResponse
from backend.v3.brain_market.params import load_default_params as load_market_params
from backend.v3.brain_view.params import load_default_params as load_view_params


def neutral():
    return {
        "kind": "NO_TRADE", "side": 0, "entry_price": "0",
        "stop_price": "0", "leverage": 0, "confidence": 0,
        "strategy_id": "", "strategy_origin": "",
    }


def open_short():
    return {
        "kind": "OPEN", "side": -1, "entry_price": "100",
        "stop_price": "101", "leverage": 20, "confidence": 0.8,
        "strategy_id": "", "strategy_origin": "",
    }


def mk(provider, *, enabled=False, mode="omit", obj=None, captures=None):
    captures = [] if captures is None else captures
    def fake_transport(payload):
        captures.append(payload)
        return TransportResponse(status_code=200, body={"choices":[{
            "finish_reason": "stop",
            "message": {"content": json.dumps(neutral() if obj is None else obj)},
        }]})
    return ArenaL5Analyst(
        provider=provider,
        run_id=f"brain-{provider}-paper20261116", model=MODELS[provider],
        transport=fake_transport, enabled=enabled, reasoning_mode=mode,
        bars_source=lambda symbol: {}, outcomes_source=lambda: (),
        view_params=load_view_params(), market_params=load_market_params(),
        menu=(), spending_gate=lambda p: p == provider,
    )


CTX = MarketContext(
    symbol="BTCUSDT", price=Decimal("100"),
    timestamp_ms=1_795_000_000_000, regime="TREND_DOWN",
)


class ArenaL5AnalystTests(TestCase):
    def test_disabled_analyst_never_calls_transport(self):
        calls = []
        a = mk("qwen", captures=calls)
        with self.assertRaisesRegex(ProviderUnavailable, "provider_disabled"):
            a.analyze(CTX, [])
        self.assertEqual(calls, [])

    def test_invalid_model_run_or_provider_fails_before_transport(self):
        a = mk("qwen")
        args = dict(
            provider="minimax", run_id="brain-qwen-paper20261116",
            model=MODELS["minimax"], transport=a.transport,
            view_params=a.view_params, market_params=a.market_params,
            menu=(), outcomes_source=a.outcomes_source,
            bars_source=a.bars_source, spending_gate=a.spending_gate,
        )
        with self.assertRaisesRegex(ValueError, "arena_analyst_invalid_scope"):
            ArenaL5Analyst(**args)
        args["run_id"] = "brain-minimax-paper20261116"
        args["model"] = MODELS["qwen"]
        with self.assertRaises(ValueError):
            ArenaL5Analyst(**args)

    def test_provider_uses_identical_market_and_scoreboard_contract(self):
        for provider in ("qwen", "minimax"):
            with self.subTest(provider=provider):
                captured = []
                a = mk(provider, enabled=True, obj=neutral(), captures=captured)
                with patch("backend.v3.brain_market.deepseek_l5.build_market_view", return_value={
                    "timeframes": [{"tf": "15m", "status": "ok"}],
                    "base_tf": "15m", "regime": "TREND_DOWN",
                }), patch("backend.v3.brain_market.deepseek_l5.build_scoreboard", return_value={}):
                    result = a.analyze(CTX, [])
                self.assertEqual(result.kind, DecisionKind.NO_TRADE)
                self.assertEqual(result.rationale, provider + ":analysis")
                self.assertEqual(result.sources, [provider + ":analysis"])
                self.assertEqual(len(captured), 1)
                self.assertEqual(captured[0]["model"], MODELS[provider])
                self.assertEqual(captured[0]["response_format"], ARENA_RESPONSE_FORMAT)
                self.assertEqual(captured[0]["max_tokens"], 2048)
                self.assertIn('"market"', captured[0]["messages"][1]["content"])
                self.assertIn('"scoreboard"', captured[0]["messages"][1]["content"])
                self.assertIn('"strategies"', captured[0]["messages"][1]["content"])

    def test_both_models_can_suggest_open_but_never_execute(self):
        for provider in ("qwen", "minimax"):
            with self.subTest(provider=provider):
                a = mk(provider, enabled=True, obj=open_short())
                with patch("backend.v3.brain_market.deepseek_l5.build_market_view", return_value={
                    "timeframes": [{"tf": "15m", "status": "ok"}],
                    "base_tf": "15m", "regime": "TREND_DOWN",
                }), patch("backend.v3.brain_market.deepseek_l5.build_scoreboard", return_value={}):
                    result = a.analyze(CTX, [])
                self.assertEqual(result.kind, DecisionKind.OPEN)
                self.assertEqual(result.proposal.originating_ai, provider)
                self.assertEqual(result.proposal.side, -1)
                self.assertEqual(result.proposal.leverage, 20)
                self.assertIsNone(result.journal_event_id)
                self.assertIsNone(result.risk_quote)

    def test_bad_arena_model_json_cannot_become_approved_trade(self):
        a = mk("qwen")
        for obj in (
            {**neutral(), "side": -1},
            {**open_short(), "side": 0},
            {**open_short(), "leverage": 200},
            {**open_short(), "strategy_id": "S07"},
            {**open_short(), "confidence": float("nan")},
            {"kind": "OPEN", "side": -1},
        ):
            with self.subTest(obj=str(obj)[:100]):
                with self.assertRaises(ValueError):
                    a._decode_output(obj)

    def test_reasoning_disabled_only_with_explicit_diagnostic_mode(self):
        a = mk("qwen", mode="disabled")
        self.assertEqual(a._request_extras()["reasoning"], {"enabled": False})
        b = mk("qwen", mode="omit")
        self.assertNotIn("reasoning", b._request_extras())
        self.assertEqual(b._request_extras()["provider"], {"require_parameters": True})

    def test_invalid_token_size_rejected_before_calls(self):
        a = mk("minimax")
        with self.assertRaises(ValueError):
            ArenaL5Analyst(
                provider="minimax", run_id=a.arena_run_id,
                model=a.model, transport=a.transport, enabled=True,
                view_params=a.view_params, market_params=a.market_params,
                menu=(), outcomes_source=a.outcomes_source,
                bars_source=a.bars_source, spending_gate=a.spending_gate,
                max_tokens=200,
            )

    def test_legacy_no_trade_decode_stays_untouched(self):
        from backend.v3.brain_market.deepseek_l5 import DeepSeekL5Analyst
        a = mk("qwen")
        self.assertEqual(DeepSeekL5Analyst._identity(a), "deepseek")
        self.assertEqual(DeepSeekL5Analyst._response_format(a),
                         {"type":"json_object"})


if __name__ == "__main__":
    main()
