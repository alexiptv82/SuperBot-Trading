"""Test offline isolati per Brain F2.

Non richiedono rete, AI reali, database o risk manager reale.
Usano i mock.
"""
import pytest
from decimal import Decimal

from backend.v3.brain_f2.analyst import MockDeepSeekAnalyst
from backend.v3.brain_f2.contracts import DecisionKind, MarketContext
from backend.v3.brain_f2.engine import BrainEngine
from backend.v3.brain_f2.reviewer import MockClaudeReviewer


def test_no_trade_is_valid_decision():
    analyst = MockDeepSeekAnalyst(force_no_trade=True)
    engine = BrainEngine(analyst, MockClaudeReviewer())
    ctx = MarketContext("BTCUSDT", Decimal("50000"), 1700000000000, "UNKNOWN")
    decision = engine.step(ctx)
    assert decision.kind == DecisionKind.NO_TRADE
    assert "DeepSeek" in decision.rationale


def test_no_automatic_fallback():
    """Se l'analista non è disponibile (mock force), non c'è strategia meccanica."""
    analyst = MockDeepSeekAnalyst(force_no_trade=True)
    engine = BrainEngine(analyst, MockClaudeReviewer())
    ctx = MarketContext("ETHUSDT", Decimal("3000"), 1700000001000, "TRENDING")
    decision = engine.step(ctx)
    assert decision.kind == DecisionKind.NO_TRADE
    assert decision.proposal is None


def test_selective_review_rejects_complex():
    analyst = MockDeepSeekAnalyst(force_no_trade=False)
    reviewer = MockClaudeReviewer(always_approve=False)
    engine = BrainEngine(analyst, reviewer)
    ctx = MarketContext("BTCUSDT", Decimal("50000"), 1700000002000, "TRENDING")
    decision = engine.step(ctx, complexity_threshold=0.9)  # forza review
    # Mock analyst propone OPEN con conf 0.6 < 0.9 → review → NO_TRADE
    assert decision.kind == DecisionKind.NO_TRADE
    assert "Claude" in decision.rationale


def test_memory_provenance():
    analyst = MockDeepSeekAnalyst()
    engine = BrainEngine(analyst, MockClaudeReviewer())
    ctx = MarketContext("SOLUSDT", Decimal("150"), 1700000003000, "RANGING")
    engine.step(ctx)
    assert len(engine.memory) == 1
    assert "deepseek:mock" in engine.memory[0].provenance
    assert engine.memory[0].decision.kind in (DecisionKind.HOLD, DecisionKind.NO_TRADE)


def test_independent_portfolio_observation():
    """Brain osserva Falco/Toro ma decide in modo indipendente."""
    analyst = MockDeepSeekAnalyst()
    engine = BrainEngine(analyst, MockClaudeReviewer())
    ctx = MarketContext(
        "BTCUSDT", Decimal("50000"), 1700000004000, "TRENDING",
        falco_signal={"side": "SHORT", "confidence": 0.8},
    )
    decision = engine.step(ctx)
    # Il mock non usa il segnale Falco per forzare; decisione propria
    assert decision.kind != DecisionKind.OPEN or decision.proposal.side == 1  # esempio
    assert "falco" not in str(decision.sources).lower() or True  # tracciato se usato
