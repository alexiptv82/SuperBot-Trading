"""Blocking safety contracts for Brain F2. Expected failures document absent gates.

No network, VPS, exchange, database or secret access. These tests are
xfail(strict=True) until Grok implements each invariant. An unexpected pass
will fail CI, forcing the maintainer to remove the marker and explicitly
acknowledge the newly implemented safeguard.
"""
from decimal import Decimal

import pytest

from backend.v3.brain_f2.analyst import Analyst, MockDeepSeekAnalyst
from backend.v3.brain_f2.contracts import DecisionKind, MarketContext
from backend.v3.brain_f2.engine import BrainEngine
from backend.v3.brain_f2.reviewer import MockClaudeReviewer


def _market():
    return MarketContext("BTCUSDT", Decimal("50000"), 1700000000000, "TRENDING")


@pytest.mark.xfail(strict=True, reason="P0: no risk quoter must fail closed")
def test_no_risk_gate_must_prevent_open():
    engine = BrainEngine(MockDeepSeekAnalyst(), MockClaudeReviewer(always_approve=True))
    decision = engine.step(_market())
    assert decision.kind == DecisionKind.NO_TRADE
    assert decision.risk_quote is None


class UnavailableAnalyst(Analyst):
    def analyze(self, context, open_positions):
        raise RuntimeError("AI unavailable / 402")


@pytest.mark.xfail(strict=True, reason="P0: unavailable AI must result in NO_TRADE not crash/trade")
def test_unavailable_ai_yields_no_trade():
    engine = BrainEngine(UnavailableAnalyst(), MockClaudeReviewer())
    decision = engine.step(_market())
    assert decision.kind == DecisionKind.NO_TRADE
    assert not decision.proposal


@pytest.mark.xfail(strict=True, reason="P0: journal callback is currently a placeholder")
def test_journal_callback_invoked_for_decision():
    writes = []
    engine = BrainEngine(MockDeepSeekAnalyst(force_no_trade=True),
                         MockClaudeReviewer(), journal_append=writes.append)
    decision = engine.step(_market())
    assert decision.kind == DecisionKind.NO_TRADE
    assert len(writes) == 1
    event = writes[0]
    assert event.portfolio_id == "brain"
    assert event.occurred_at_ms == _market().timestamp_ms
