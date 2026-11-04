"""Safety contracts and negative tests for Brain F2 R1.1.

No network, VPS, exchange, real wallet or secret access.
Temporary SQLite only.
"""
import os
import tempfile
from decimal import Decimal
from pathlib import Path

import pytest

from backend.v3.brain_f2.analyst import Analyst, MockDeepSeekAnalyst
from backend.v3.brain_f2.contracts import DecisionKind, MarketContext, OpenProposal, ProposalStatus, BrainDecision
from backend.v3.brain_f2.engine import BrainEngine, BrainPortfolioSnapshot, _policy_hash
from backend.v3.brain_f2.reviewer import MockClaudeReviewer
from backend.v3.events import Event, EventJournal, EventConflict
from backend.v3.risk import RiskPolicy, quote_paper_risk


def _make_journal():
    _tmpdir = tempfile.mkdtemp()
    journal = EventJournal(os.path.join(_tmpdir, "journal.db"))
    # Schema inizializzato: senza, un motore valido non riesce a persistere la
    # decisione e risponde NO_TRADE('journal_persist_failed') (init ripetuto = innocuo).
    journal.init_schema()
    return journal


def _market(regime="TRENDING", price="50000"):
    return MarketContext("BTCUSDT", Decimal(price), 1700000000000, regime)


def _policy(floor="450"):
    return RiskPolicy(
        max_loss_fraction=Decimal("0.02"),
        max_open_risk_fraction=Decimal("0.05"),
        max_position_margin_fraction=Decimal("0.1"),
        max_total_margin_fraction=Decimal("0.3"),
        minimum_equity=Decimal(floor),
        estimated_roundtrip_cost_bp=Decimal("16"),
        liquidation_buffer_fraction=Decimal("0.5"),
    )


def _snapshot(equity="1000"):
    return BrainPortfolioSnapshot(
        equity=Decimal(equity),
        available_cash=Decimal(equity),
        margin_used=Decimal("0"),
        existing_open_risk=Decimal("0"),
    )


def _market_params(fresh=True):
    return {
        "exchange_leverage_limit": 10,
        "quantity_step": Decimal("0.001"),
        "minimum_notional": Decimal("5"),
        "maintenance_fraction": Decimal("0.004"),
        "market_data_fresh": fresh, "paused": False, "daily_loss_latched": False,
    }


def _authorized(policy, run_id="test-run"):
    """Argomenti per un motore VALIDO: run_id + mandato con scope e hash coerenti.

    Hardening 04/11/2026: senza questi il motore risponde NO_TRADE('invalid_input')
    prima di arrivare al controllo che il test dichiara di verificare.
    """
    return dict(
        run_id=run_id,
        policy_verifier=lambda m, p: True,
        policy_mandate={"version": "safety-test", "approved_by": "operator",
                        "approved": True, "portfolio_id": "brain",
                        "run_id": run_id, "policy_hash": _policy_hash(policy)},
    )


def test_control_valid_engine_approves():
    """Controllo anti-test-vuoti: con input validi il motore DEVE approvare."""
    pol = _policy()
    engine = BrainEngine(
        MockDeepSeekAnalyst(), MockClaudeReviewer(always_approve=True),
        risk_policy=pol, portfolio_snapshot=_snapshot(),
        market_params=_market_params(), journal=_make_journal(), **_authorized(pol),
    )
    decision = engine.step(_market())
    assert (decision.kind, decision.status, decision.rationale) == \
        (DecisionKind.OPEN, ProposalStatus.APPROVED, "risk_quote_ok")


def test_no_risk_gate_must_prevent_open():
    """P0 contract: BrainEngine senza risk_policy non si costruisce."""
    with pytest.raises(ValueError, match="risk_policy is required"):
        BrainEngine(MockDeepSeekAnalyst(), MockClaudeReviewer(always_approve=True), run_id='test-run')


class UnavailableAnalyst(Analyst):
    def analyze(self, context, open_positions):
        raise RuntimeError("AI unavailable / 402")


def test_unavailable_ai_yields_no_trade():
    engine = BrainEngine(
        UnavailableAnalyst(), MockClaudeReviewer(always_approve=True),
        risk_policy=_policy(), portfolio_snapshot=_snapshot(),
        market_params=_market_params(), journal=_make_journal(),
        run_id='test-run',
    )
    decision = engine.step(_market())
    assert decision.kind == DecisionKind.NO_TRADE
    assert "ai_unavailable" in decision.rationale


def test_journal_sqlite_write_and_restart():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "brain.sqlite"
        journal = EventJournal(path)
        journal.init_schema()
        engine = BrainEngine(
            MockDeepSeekAnalyst(force_no_trade=True),
            MockClaudeReviewer(always_approve=True),
            risk_policy=_policy(), portfolio_snapshot=_snapshot(),
            market_params=_market_params(), journal=journal,
            run_id="brain-f2-offline",
        )
        decision = engine.step(_market())
        assert decision.kind == DecisionKind.NO_TRADE
        # Restart: new journal instance on same file
        journal2 = EventJournal(path)
        runs = journal2.list_run("brain", "brain-f2-offline")
        assert len(runs) == 1
        assert runs[0].event.portfolio_id == "brain"
        assert runs[0].event.occurred_at_ms == _market().timestamp_ms


def test_journal_idempotency_and_conflict():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "j.sqlite"
        journal = EventJournal(path)
        journal.init_schema()
        e1 = Event("id1", "brain", "run1", "brain_decision", 1700000000000, "test", {"a": 1})
        journal.append(e1)
        # Exact duplicate is idempotent
        journal.append(e1)
        assert len(journal.list_run("brain", "run1")) == 1
        # Conflicting content raises
        e2 = Event("id1", "brain", "run1", "brain_decision", 1700000000000, "test", {"a": 2})
        with pytest.raises(EventConflict):
            journal.append(e2)


def test_portfolio_isolation():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "iso.sqlite"
        journal = EventJournal(path)
        journal.init_schema()
        engine_b = BrainEngine(
            MockDeepSeekAnalyst(force_no_trade=True), MockClaudeReviewer(always_approve=True),
            risk_policy=_policy(), portfolio_snapshot=_snapshot(),
            market_params=_market_params(), journal=journal, run_id="brain-run",
        )
        engine_b.step(_market())
        assert len(journal.list_run("brain", "brain-run")) == 1
        engine_h = BrainEngine(
            MockDeepSeekAnalyst(force_no_trade=True), MockClaudeReviewer(always_approve=True),
            risk_policy=_policy(), portfolio_snapshot=_snapshot(),
            market_params=_market_params(), journal=journal, portfolio_id="hawk", run_id="hawk-run",
        )
        d = engine_h.step(_market())
        assert d.kind == DecisionKind.NO_TRADE
        assert len(journal.list_run("hawk", "hawk-run")) == 0


def test_stale_market_rejected():
    engine = BrainEngine(
        MockDeepSeekAnalyst(),
        MockClaudeReviewer(always_approve=True),
        risk_policy=_policy(),
        portfolio_snapshot=_snapshot(),
        market_params=_market_params(fresh=False),
        journal=_make_journal(),
        run_id="test-run",
    )
    decision = engine.step(_market())
    assert decision.kind == DecisionKind.NO_TRADE
    assert decision.rationale in ("risk_rejected", "market_gate")


def test_policy_floor_below_450_rejected():
    pol = _policy(floor="400")
    engine = BrainEngine(
        MockDeepSeekAnalyst(),
        MockClaudeReviewer(always_approve=True),
        risk_policy=pol,
        portfolio_snapshot=_snapshot(),
        market_params=_market_params(),
        journal=_make_journal(),
        **_authorized(pol),
    )
    decision = engine.step(_market())
    assert decision.kind == DecisionKind.NO_TRADE
    assert decision.rationale == "invalid_input"


def test_missing_market_params_rejected():
    pol = _policy()
    engine = BrainEngine(
        MockDeepSeekAnalyst(),
        MockClaudeReviewer(always_approve=True),
        risk_policy=pol,
        portfolio_snapshot=_snapshot(),
        market_params={},
        journal=_make_journal(),
        **_authorized(pol),
    )
    decision = engine.step(_market())
    assert decision.kind == DecisionKind.NO_TRADE
    assert decision.rationale == "invalid_input"


def test_nan_infinity_rejected():
    pol = _policy()
    engine = BrainEngine(
        MockDeepSeekAnalyst(),
        MockClaudeReviewer(always_approve=True),
        risk_policy=pol,
        portfolio_snapshot=BrainPortfolioSnapshot(Decimal("NaN"), Decimal("1000"), Decimal("0"), Decimal("0")),
        market_params=_market_params(),
        journal=_make_journal(),
        **_authorized(pol),
    )
    decision = engine.step(_market())
    assert decision.kind == DecisionKind.NO_TRADE
    assert decision.rationale == "invalid_input"


def test_close_and_modify_not_executable():
    class EmitClose(Analyst):
        def analyze(self, context, open_positions):
            from backend.v3.brain_f2.contracts import CloseProposal
            return BrainDecision(
                kind=DecisionKind.CLOSE,
                proposal=CloseProposal("pos1", "test", "deepseek", 0.9),
                rationale="close me",
                occurred_at_ms=context.timestamp_ms,
            )
    engine = BrainEngine(
        EmitClose(), MockClaudeReviewer(always_approve=True),
        risk_policy=_policy(), portfolio_snapshot=_snapshot(),
        market_params=_market_params(), journal=_make_journal(),
        run_id='test-run',
    )
    decision = engine.step(_market())
    assert decision.kind == DecisionKind.NO_TRADE
    assert decision.status != ProposalStatus.EXECUTED_PAPER
    assert "close_modify_not_executable" in decision.rationale


def test_falco_toro_signals_are_advisory_only():
    ctx = MarketContext(
        "BTCUSDT", Decimal("50000"), 1700000000000, "TRENDING",
        falco_signal={"side": -1},
        toro_signal={"side": 1},
    )
    def _decide(context):
        pol = _policy()
        return BrainEngine(
            MockDeepSeekAnalyst(),
            MockClaudeReviewer(always_approve=True),
            risk_policy=pol,
            portfolio_snapshot=_snapshot(),
            market_params=_market_params(),
            journal=_make_journal(),
            **_authorized(pol),
        ).step(context)

    with_signals = _decide(ctx)
    without_signals = _decide(_market())
    # Advisory-only: i segnali Falco/Toro non cambiano la decisione ne' il sizing
    assert with_signals.kind == without_signals.kind == DecisionKind.OPEN
    assert with_signals.status == without_signals.status == ProposalStatus.APPROVED
    assert with_signals.proposal.side == without_signals.proposal.side
    assert with_signals.risk_quote.quantity == without_signals.risk_quote.quantity
    assert with_signals.risk_quote.margin == without_signals.risk_quote.margin
    # Nessuna contaminazione: la decisione non incorpora dati di Falco/Toro
    assert "falco" not in (with_signals.rationale or "").lower()
    assert "toro" not in (with_signals.rationale or "").lower()
