"""Offline model->BrainEngine boundary checks for independent Arena lanes.

Synthetic model JSON + synthetic market views only. No provider HTTP,
journal writes, paper executions, Bitget queries, or service changes. A
validated OPEN proposal is NOT a risk-approved or executed trade.
"""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
import json
from unittest import TestCase, main
from unittest.mock import patch

from backend.v3.arena.l5_analyst import ArenaL5Analyst
from backend.v3.arena.openrouter_transport import (
    MODELS, ARENA_JSON_OBJECT_FORMAT, ARENA_RESPONSE_FORMAT,
)
from backend.v3.brain_f2.contracts import (
    BrainDecision, DecisionKind, MarketContext, ProposalStatus,
)
from backend.v3.brain_f2.engine import BrainEngine
from backend.v3.brain_f3.providers import ProviderUnavailable, TransportResponse
from backend.v3.brain_market.params import load_default_params as load_market_params
from backend.v3.brain_view.params import load_default_params as load_view_params


TIME_MS = 1795000000000
CONTEXT = MarketContext(
    symbol="BTCUSDT", price=Decimal("100"),
    timestamp_ms=TIME_MS, regime="TREND_DOWN",
)
NO_TRADE = {
    "kind": "NO_TRADE", "side": 0, "entry_price": "0",
    "stop_price": "0", "leverage": 0, "confidence": 0,
    "strategy_id": "", "strategy_origin": "",
}


def open_json(side: int) -> dict:
    if side not in (-1, 1):
        raise ValueError("invalid_test_side")
    return {
        "kind": "OPEN", "side": side, "entry_price": "100",
        "stop_price": "99" if side == 1 else "101",
        "leverage": 20, "confidence": 0.8,
        "strategy_id": "", "strategy_origin": "",
    }


def analyst(provider: str, raw: dict, requests: list) -> ArenaL5Analyst:
    def model_transport(payload):
        requests.append(payload)
        return TransportResponse(status_code=200, body={
            "choices": [{
                "finish_reason": "stop",
                "message": {"content": json.dumps(raw)},
            }],
        })
    return ArenaL5Analyst(
        provider=provider,
        run_id="brain-" + provider + "-paper20261116",
        model=MODELS[provider], enabled=True,
        reasoning_mode="disabled" if provider == "qwen" else "omit",
        transport=model_transport, spending_gate=lambda name: name == provider,
        bars_source=lambda symbol: {},
        outcomes_source=lambda: (),
        view_params=load_view_params(),
        market_params=load_market_params(), menu=(),
    )


def propose(provider: str, raw: dict) -> tuple[BrainDecision, list]:
    calls = []
    a = analyst(provider, raw, calls)
    with (
        patch("backend.v3.brain_market.deepseek_l5.build_market_view",
              return_value={
                  "base_tf": "15m", "regime": "TREND_DOWN",
                  "timeframes": [{"tf": "15m", "status": "ok"}],
              }),
        patch("backend.v3.brain_market.deepseek_l5.build_scoreboard",
              return_value={"status": "insufficient"}),
    ):
        result = a.analyze(CONTEXT, [])
    return result, calls


def isolated_engine(provider: str) -> BrainEngine:
    # We only use _validate_decision. These non-executing injected objects
    # deliberately do not have the methods/permits needed for engine.step.
    return BrainEngine(
        analyst=object(), reviewer=object(),
        risk_policy=object(), portfolio_snapshot=object(), journal=object(),
        portfolio_id="brain", run_id=f"brain-{provider}-paper20261116",
        arena_provider=provider,
    )


class ArenaModelToBrainTests(TestCase):
    def test_same_market_evidence_and_independent_opposite_decisions(self):
        q, qc = propose("qwen", open_json(1))
        m, mc = propose("minimax", open_json(-1))
        self.assertEqual(q.kind, DecisionKind.OPEN)
        self.assertEqual(m.kind, DecisionKind.OPEN)
        self.assertEqual(q.proposal.side, 1)
        self.assertEqual(m.proposal.side, -1)
        self.assertEqual(q.proposal.originating_ai, "qwen")
        self.assertEqual(m.proposal.originating_ai, "minimax")
        self.assertEqual(q.proposal.context_hash, m.proposal.context_hash)
        self.assertEqual(qc[0]["messages"][1]["content"],
                         mc[0]["messages"][1]["content"])
        self.assertEqual(qc[0]["response_format"], ARENA_RESPONSE_FORMAT)
        self.assertEqual(mc[0]["response_format"], ARENA_JSON_OBJECT_FORMAT)
        self.assertEqual(len(qc), 1)
        self.assertEqual(len(mc), 1)
        self.assertIsNone(q.risk_quote)
        self.assertIsNone(m.risk_quote)
        self.assertIsNone(q.journal_event_id)
        self.assertIsNone(m.journal_event_id)

    def test_engine_accepts_proposal_as_draft_not_as_order(self):
        for provider, side in (("qwen", 1), ("minimax", -1)):
            with self.subTest(provider=provider):
                decision, _ = propose(provider, open_json(side))
                checked = isolated_engine(provider)._validate_decision(
                    decision, CONTEXT,
                )
                self.assertEqual(checked.kind, DecisionKind.OPEN)
                self.assertEqual(checked.status, ProposalStatus.DRAFT)
                self.assertEqual(checked.proposal.originating_ai, provider)
                self.assertEqual(checked.proposal.side, side)
                self.assertIsNone(checked.risk_quote)
                self.assertIsNone(checked.journal_event_id)

    def test_cross_provider_injection_rejected_at_brain_boundary(self):
        q, _ = propose("qwen", open_json(1))
        rejected = isolated_engine("minimax")._validate_decision(q, CONTEXT)
        self.assertEqual(rejected.kind, DecisionKind.NO_TRADE)
        self.assertEqual(rejected.status, ProposalStatus.REJECTED)

        m, _ = propose("minimax", open_json(-1))
        rejected = isolated_engine("qwen")._validate_decision(m, CONTEXT)
        self.assertEqual(rejected.kind, DecisionKind.NO_TRADE)
        self.assertEqual(rejected.status, ProposalStatus.REJECTED)

    def test_legacy_deepseek_run_not_permitted_to_take_arena_proposal(self):
        q, _ = propose("qwen", open_json(1))
        engine = BrainEngine(
            analyst=object(), reviewer=object(), risk_policy=object(),
            portfolio_snapshot=object(), journal=object(), portfolio_id="brain",
            run_id="brain-v3-paper20261111",
        )
        decision = engine._validate_decision(q, CONTEXT)
        self.assertEqual(decision.kind, DecisionKind.NO_TRADE)
        self.assertEqual(decision.status, ProposalStatus.REJECTED)

    def test_no_trade_from_each_model_stays_no_trade(self):
        for provider in MODELS:
            d, calls = propose(provider, NO_TRADE)
            self.assertEqual(d.kind, DecisionKind.NO_TRADE)
            checked = isolated_engine(provider)._validate_decision(d, CONTEXT)
            self.assertEqual(checked.kind, DecisionKind.NO_TRADE)
            self.assertIsNone(checked.proposal)
            self.assertIsNone(checked.risk_quote)
            self.assertEqual(len(calls), 1)

    def test_bad_json_fail_closed_without_automatic_retry(self):
        for provider in MODELS:
            for invalid in (
                {"kind": "OPEN", "side": -1},  # missing fields
                {**open_json(-1), "side": 0},
                {**open_json(-1), "leverage": True},
                {**open_json(-1), "confidence": 1.5},
                {**open_json(-1), "extra": "unexpected"},
                {**NO_TRADE, "side": 1},
            ):
                with self.subTest(provider=provider, invalid=invalid):
                    calls = []
                    a = analyst(provider, invalid, calls)
                    with (
                        patch("backend.v3.brain_market.deepseek_l5.build_market_view",
                              return_value={
                                  "base_tf": "15m", "regime": "TREND_DOWN",
                                  "timeframes": [{"tf":"15m","status":"ok"}],
                              }),
                        patch("backend.v3.brain_market.deepseek_l5.build_scoreboard",
                              return_value={}),
                    ):
                        with self.assertRaisesRegex(ProviderUnavailable,
                                                    "invalid_model_output"):
                            a.analyze(CONTEXT, [])
                    self.assertEqual(len(calls), 1)

    def test_wrong_market_regime_rejected_before_model_call(self):
        calls = []
        a = analyst("qwen", open_json(-1), calls)
        with patch("backend.v3.brain_market.deepseek_l5.build_market_view",
                   return_value={
                       "base_tf":"15m", "regime":"TREND_UP",
                       "timeframes":[{"tf":"15m", "status":"ok"}],
                   }):
            with self.assertRaisesRegex(ProviderUnavailable, "regime_mismatch"):
                a.analyze(CONTEXT, [])
        self.assertEqual(calls, [])

    def test_closed_candles_required_before_model_call(self):
        calls = []
        a = analyst("minimax", open_json(-1), calls)
        with patch("backend.v3.brain_market.deepseek_l5.build_market_view",
                   return_value={
                       "base_tf":"15m", "regime":"TREND_DOWN",
                       "timeframes":[{"tf":"15m", "status":"stale"}],
                   }):
            with self.assertRaisesRegex(ProviderUnavailable, "market_data_unavailable"):
                a.analyze(CONTEXT, [])
        self.assertEqual(calls, [])


if __name__ == "__main__":
    main()
