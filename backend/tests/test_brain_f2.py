"""Test offline isolati per Brain F2.

Non richiedono rete, AI reali, database o risk manager reale.
Usano i mock.
"""
import os
import tempfile
import pytest
from decimal import Decimal

from backend.v3.brain_f2.analyst import MockDeepSeekAnalyst
from backend.v3.brain_f2.contracts import DecisionKind, MarketContext
from backend.v3.brain_f2.engine import BrainEngine, BrainPortfolioSnapshot
from backend.v3.brain_f2.reviewer import MockClaudeReviewer
from backend.v3.events import EventJournal
from backend.v3.risk import RiskPolicy


def _make_journal():
    _tmpdir = tempfile.mkdtemp()
    return EventJournal(os.path.join(_tmpdir, "journal.db"))


def _dummy_policy():
    return RiskPolicy(
        max_loss_fraction=Decimal("0.02"),
        max_open_risk_fraction=Decimal("0.05"),
        max_position_margin_fraction=Decimal("0.1"),
        max_total_margin_fraction=Decimal("0.3"),
        minimum_equity=Decimal("450"),
        estimated_roundtrip_cost_bp=Decimal("16"),
        liquidation_buffer_fraction=Decimal("0.5"),
    )


def _dummy_snapshot():
    return BrainPortfolioSnapshot(
        equity=Decimal("1000"), available_cash=Decimal("1000"),
        margin_used=Decimal("0"), existing_open_risk=Decimal("0"),
    )


def _dummy_market_params():
    return {
        "exchange_leverage_limit": 10, "quantity_step": Decimal("0.001"),
        "minimum_notional": Decimal("5"), "maintenance_fraction": Decimal("0.004"),
        "market_data_fresh": True, "paused": False, "daily_loss_latched": False,
    }


def test_no_trade_is_valid_decision():
    analyst = MockDeepSeekAnalyst(force_no_trade=True)
    engine = BrainEngine(
        analyst, MockClaudeReviewer(),
        risk_policy=_dummy_policy(), portfolio_snapshot=_dummy_snapshot(),
        market_params=_dummy_market_params(), journal=_make_journal(),
        run_id='test-run',
    )
    ctx = MarketContext("BTCUSDT", Decimal("50000"), 1700000000000, "UNKNOWN")
    decision = engine.step(ctx)
    assert decision.kind == DecisionKind.NO_TRADE
    assert decision.rationale in ("deepseek:mock", "sanitized", "risk_quote_ok") or "deepseek" in decision.rationale.lower()


def test_no_automatic_fallback():
    """Se l'analista non è disponibile (mock force), non c'è strategia meccanica."""
    analyst = MockDeepSeekAnalyst(force_no_trade=True)
    engine = BrainEngine(
        analyst, MockClaudeReviewer(),
        risk_policy=_dummy_policy(), portfolio_snapshot=_dummy_snapshot(),
        market_params=_dummy_market_params(), journal=_make_journal(),
        run_id='test-run',
    )
    ctx = MarketContext("ETHUSDT", Decimal("3000"), 1700000001000, "TRENDING")
    decision = engine.step(ctx)
    assert decision.kind == DecisionKind.NO_TRADE
    assert decision.proposal is None


def test_selective_review_rejects_complex():
    analyst = MockDeepSeekAnalyst(force_no_trade=False)
    reviewer = MockClaudeReviewer(always_approve=False)
    engine = BrainEngine(
        analyst, reviewer,
        risk_policy=_dummy_policy(), portfolio_snapshot=_dummy_snapshot(),
        market_params=_dummy_market_params(), journal=_make_journal(),
        run_id='test-run',
    )
    ctx = MarketContext("BTCUSDT", Decimal("50000"), 1700000002000, "TRENDING")
    decision = engine.step(ctx, complexity_threshold=0.9)  # forza review
    # Mock analyst propone OPEN con conf 0.6 < 0.9 → review → NO_TRADE
    assert decision.kind == DecisionKind.NO_TRADE
    assert decision.rationale in ("claude:mock", "sanitized", "risk_rejected", "risk_quote_ok") or "claude" in decision.rationale.lower()


def test_memory_provenance():
    analyst = MockDeepSeekAnalyst()
    engine = BrainEngine(
        analyst, MockClaudeReviewer(),
        risk_policy=_dummy_policy(), portfolio_snapshot=_dummy_snapshot(),
        market_params=_dummy_market_params(), journal=_make_journal(),
        run_id='test-run',
    )
    ctx = MarketContext("SOLUSDT", Decimal("150"), 1700000003000, "RANGING")
    engine.step(ctx)
    assert len(engine.memory) == 1
    assert "deepseek:mock" in engine.memory[0].provenance
    assert engine.memory[0].decision.kind in (DecisionKind.HOLD, DecisionKind.NO_TRADE)


def test_independent_portfolio_observation():
    """Brain osserva Falco/Toro ma decide in modo indipendente."""
    analyst = MockDeepSeekAnalyst()
    engine = BrainEngine(
        analyst, MockClaudeReviewer(),
        risk_policy=_dummy_policy(), portfolio_snapshot=_dummy_snapshot(),
        market_params=_dummy_market_params(), journal=_make_journal(),
        run_id='test-run',
    )
    ctx = MarketContext(
        "BTCUSDT", Decimal("50000"), 1700000004000, "TRENDING",
        falco_signal={"side": "SHORT", "confidence": 0.8},
    )
    decision = engine.step(ctx)
    # Il mock non usa il segnale Falco per forzare; decisione propria
    assert decision.kind != DecisionKind.OPEN or decision.proposal.side == 1  # esempio
    assert "falco" not in str(decision.sources).lower()  # segnale non deve contaminare sources
