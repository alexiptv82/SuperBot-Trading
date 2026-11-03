"""Review indipendente Brain V3 F2 R1.9 — test negativi P0/P1.

Autore: Claude Sonnet 4.6 (coordinatore temporaneo, 2026-11-03)
Scopo: verifica che i 5 P0 blocker e le protezioni P1 siano presenti nel codice
       SENZA modificare il codice di Grok (F2/F3).
Branch: work/v3-f2-review-claude-20261103
"""
from __future__ import annotations

import hashlib
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from backend.v3.brain_f2.contracts import (
    BrainDecision, DecisionKind, MarketContext,
    OpenProposal, ProposalStatus,
)
from backend.v3.brain_f2.engine import BrainEngine, BrainPortfolioSnapshot


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _policy(minimum_equity: float = 500.0):
    p = MagicMock()
    p.minimum_equity = Decimal(str(minimum_equity))
    p.max_loss_fraction = Decimal("0.02")
    p.max_open_risk_fraction = Decimal("0.05")
    p.max_position_margin_fraction = Decimal("0.10")
    p.max_total_margin_fraction = Decimal("0.20")
    p.estimated_roundtrip_cost_bp = Decimal("4")
    p.liquidation_buffer_fraction = Decimal("0.01")
    return p


def _context(symbol: str = "BTCUSDT", price: float = 50000.0, ts: int = 1000) -> MarketContext:
    return MarketContext(
        symbol=symbol,
        price=Decimal(str(price)),
        timestamp_ms=ts,
        regime="TRENDING",
        source="test",
    )


def _market_params(fresh: bool = True, paused: bool = False, latched: bool = False) -> dict:
    return {
        "exchange_leverage_limit": 20,
        "quantity_step": Decimal("0.001"),
        "minimum_notional": Decimal("10"),
        "maintenance_fraction": Decimal("0.005"),
        "market_data_fresh": fresh,
        "paused": paused,
        "daily_loss_latched": latched,
    }


def _snapshot(equity: float = 1000.0) -> BrainPortfolioSnapshot:
    return BrainPortfolioSnapshot(
        equity=Decimal(str(equity)),
        available_cash=Decimal("800"),
        margin_used=Decimal("100"),
        existing_open_risk=Decimal("20"),
    )


def _make_policy_hash(policy) -> str:
    fields = (
        str(policy.max_loss_fraction), str(policy.max_open_risk_fraction),
        str(policy.max_position_margin_fraction), str(policy.max_total_margin_fraction),
        str(policy.minimum_equity), str(policy.estimated_roundtrip_cost_bp),
        str(policy.liquidation_buffer_fraction),
    )
    return hashlib.sha256("|".join(fields).encode()).hexdigest()[:16]


def _mandate(portfolio_id: str = "brain", run_id: str = "run-test-1", policy=None) -> dict:
    pol = policy or _policy()
    return {
        "approved": True,
        "version": "v1.0",
        "portfolio_id": portfolio_id,
        "run_id": run_id,
        "approved_by": "operator",
        "policy_hash": _make_policy_hash(pol),
    }


def _open_proposal(symbol: str = "BTCUSDT", price: float = 50000.0) -> OpenProposal:
    return OpenProposal(
        symbol=symbol,
        side=1,
        entry_price=Decimal(str(price)),
        stop_price=Decimal(str(price * 0.99)),
        leverage=5,
        rationale="deepseek:mock",
        confidence=0.9,
        originating_ai="deepseek:mock",
        context_hash="a" * 16,
    )


def _open_decision(symbol: str = "BTCUSDT", price: float = 50000.0, ts: int = 1000) -> BrainDecision:
    return BrainDecision(
        kind=DecisionKind.OPEN,
        proposal=_open_proposal(symbol, price),
        rationale="deepseek:mock",
        sources=["deepseek:mock"],
        occurred_at_ms=ts,
        status=ProposalStatus.PENDING_REVIEW,
    )


def _analyst_open(symbol: str = "BTCUSDT", price: float = 50000.0, ts: int = 1000):
    a = MagicMock()
    a.analyze.return_value = _open_decision(symbol, price, ts)
    return a


def _reviewer_pass():
    r = MagicMock()
    r.review.side_effect = lambda d, reason: d
    return r


def _real_quote_allowed():
    q = MagicMock()
    q.allowed = True
    return q


def _engine_with_open(
    policy=None,
    snapshot=None,
    run_id: str = "run-test-1",
    journal=None,
    verifier=None,
    mandate_override=None,
    portfolio_id: str = "brain",
) -> BrainEngine:
    pol = policy or _policy()
    m = mandate_override if mandate_override is not None else _mandate(run_id=run_id, policy=pol)
    # assicura policy_hash aggiornato se non è mandate_override
    if mandate_override is None:
        m["policy_hash"] = _make_policy_hash(pol)

    def _default_verifier(mandate: dict, rp) -> bool:
        return True

    return BrainEngine(
        analyst=_analyst_open(),
        reviewer=_reviewer_pass(),
        risk_policy=pol,
        portfolio_snapshot=snapshot if snapshot is not None else _snapshot(),
        market_params=_market_params(),
        journal=journal,
        portfolio_id=portfolio_id,
        run_id=run_id,
        policy_mandate=m,
        policy_verifier=verifier if verifier is not None else _default_verifier,
    )


# ---------------------------------------------------------------------------
# P0-1: risk_policy=None o portfolio_snapshot=None → mai OPEN/APPROVED
# ---------------------------------------------------------------------------

class TestP0RiskQuoterNone:
    def test_no_risk_policy_yields_no_trade(self):
        engine = _engine_with_open()
        engine.risk_policy = None
        d = engine.step(_context())
        assert d.kind == DecisionKind.NO_TRADE

    def test_no_risk_policy_risk_quote_is_none(self):
        engine = _engine_with_open()
        engine.risk_policy = None
        d = engine.step(_context())
        assert d.risk_quote is None

    def test_no_portfolio_snapshot_yields_no_trade(self):
        engine = _engine_with_open()
        engine.portfolio_snapshot = None
        d = engine.step(_context())
        assert d.kind == DecisionKind.NO_TRADE

    def test_approved_never_with_null_policy(self):
        engine = _engine_with_open()
        engine.risk_policy = None
        d = engine.step(_context())
        assert d.status != ProposalStatus.APPROVED


# ---------------------------------------------------------------------------
# P0-2: quote_paper_risk con firma sbagliata → NO_TRADE
# ---------------------------------------------------------------------------

class TestP0RiskQuoterSignatureMismatch:
    def test_wrong_callable_raises_no_trade(self):
        with patch("backend.v3.brain_f2.engine.quote_paper_risk", side_effect=TypeError("wrong args")):
            engine = _engine_with_open()
            d = engine.step(_context())
        assert d.kind == DecisionKind.NO_TRADE

    def test_wrong_callable_no_approved(self):
        with patch("backend.v3.brain_f2.engine.quote_paper_risk", side_effect=TypeError("wrong args")):
            engine = _engine_with_open()
            d = engine.step(_context())
        assert d.status != ProposalStatus.APPROVED

    def test_risk_quote_returning_none_no_approved(self):
        with patch("backend.v3.brain_f2.engine.quote_paper_risk", return_value=None):
            engine = _engine_with_open()
            d = engine.step(_context())
        assert d.kind == DecisionKind.NO_TRADE


# ---------------------------------------------------------------------------
# P0-3: journal=None → OPEN non diventa APPROVED
# ---------------------------------------------------------------------------

class TestP0JournalAppend:
    def test_open_without_journal_is_no_trade(self):
        with patch("backend.v3.brain_f2.engine.quote_paper_risk", return_value=_real_quote_allowed()):
            engine = _engine_with_open(journal=None)
            d = engine.step(_context())
        assert d.kind == DecisionKind.NO_TRADE
        assert d.rationale in ("missing_journal", "policy_not_authorized", "invalid_input", "risk_rejected")

    def test_no_trade_memory_stored_even_without_journal(self):
        with patch("backend.v3.brain_f2.engine.quote_paper_risk", return_value=_real_quote_allowed()):
            engine = _engine_with_open(journal=None)
            engine.step(_context())
        assert len(engine.memory) >= 1

    def test_open_approved_calls_journal_append(self):
        from backend.v3.events import EventJournal, StoredEvent as EventRecord
        journal = MagicMock(spec=EventJournal)
        captured = {}

        def fake_append(event):
            captured["event"] = event
            rec = MagicMock(spec=EventRecord)
            rec.event = event
            return rec

        def fake_list_run(portfolio_id, run_id):
            if captured:
                rec = MagicMock(spec=EventRecord)
                rec.event = captured["event"]
                return [rec]
            return []

        journal.append.side_effect = fake_append
        journal.list_run.side_effect = fake_list_run

        with patch("backend.v3.brain_f2.engine.quote_paper_risk", return_value=_real_quote_allowed()):
            engine = _engine_with_open(journal=journal)
            engine.step(_context())

        assert journal.append.called

    def test_journal_append_never_with_no_journal(self):
        """Senza journal, nessun append viene tentato (non esplode)."""
        engine = _engine_with_open(journal=None)
        # non deve lanciare eccezioni
        d = engine.step(_context())
        assert d.kind == DecisionKind.NO_TRADE


# ---------------------------------------------------------------------------
# P0-4: _reevaluate_positions è stub — non promuove a APPROVED
# ---------------------------------------------------------------------------

class TestP0ReevaluatePositions:
    def test_reevaluate_stub_returns_decision_unchanged(self):
        engine = _engine_with_open()
        d_in = BrainDecision(
            kind=DecisionKind.HOLD,
            rationale="ai_unavailable",
            sources=["engine:fail_closed"],
            occurred_at_ms=1000,
            status=ProposalStatus.REJECTED,
        )
        d_out = engine._reevaluate_positions(_context(), d_in)
        assert d_out is d_in  # stub: identità

    def test_reevaluate_never_produces_approved(self):
        engine = _engine_with_open()
        d_in = BrainDecision(
            kind=DecisionKind.NO_TRADE,
            rationale="ai_unavailable",
            sources=["engine:fail_closed"],
            occurred_at_ms=1000,
            status=ProposalStatus.REJECTED,
        )
        d_out = engine._reevaluate_positions(_context(), d_in)
        assert d_out.status != ProposalStatus.APPROVED


# ---------------------------------------------------------------------------
# P0-5: policy mandate + verifier obbligatori per OPEN/APPROVED
# ---------------------------------------------------------------------------

class TestP0IndependenceRealContract:
    def test_no_verifier_no_open_approved(self):
        with patch("backend.v3.brain_f2.engine.quote_paper_risk", return_value=_real_quote_allowed()):
            engine = _engine_with_open(verifier=None)
            engine.policy_verifier = None
            d = engine.step(_context())
        assert d.kind == DecisionKind.NO_TRADE

    def test_verifier_returning_false_no_open_approved(self):
        with patch("backend.v3.brain_f2.engine.quote_paper_risk", return_value=_real_quote_allowed()):
            engine = _engine_with_open(verifier=lambda m, p: False)
            d = engine.step(_context())
        assert d.kind == DecisionKind.NO_TRADE

    def test_verifier_returning_int_no_open_approved(self):
        """Verifier che restituisce 1 (non True strict) → rifiutato."""
        with patch("backend.v3.brain_f2.engine.quote_paper_risk", return_value=_real_quote_allowed()):
            engine = _engine_with_open(verifier=lambda m, p: 1)
            d = engine.step(_context())
        assert d.kind == DecisionKind.NO_TRADE

    def test_verifier_exception_no_open_approved(self):
        def _raise(m, p):
            raise RuntimeError("auth error")
        with patch("backend.v3.brain_f2.engine.quote_paper_risk", return_value=_real_quote_allowed()):
            engine = _engine_with_open(verifier=_raise)
            d = engine.step(_context())
        assert d.kind == DecisionKind.NO_TRADE

    def test_mandate_without_approved_field_no_open(self):
        m = _mandate()
        del m["approved"]
        with patch("backend.v3.brain_f2.engine.quote_paper_risk", return_value=_real_quote_allowed()):
            engine = _engine_with_open(mandate_override=m)
            d = engine.step(_context())
        assert d.kind == DecisionKind.NO_TRADE

    def test_mandate_wrong_portfolio_id_no_open(self):
        m = _mandate(portfolio_id="hawk")
        with patch("backend.v3.brain_f2.engine.quote_paper_risk", return_value=_real_quote_allowed()):
            engine = _engine_with_open(mandate_override=m)
            d = engine.step(_context())
        assert d.kind == DecisionKind.NO_TRADE

    def test_mandate_wrong_run_id_no_open(self):
        m = _mandate(run_id="run-WRONG")
        with patch("backend.v3.brain_f2.engine.quote_paper_risk", return_value=_real_quote_allowed()):
            engine = _engine_with_open(run_id="run-test-1", mandate_override=m)
            d = engine.step(_context())
        assert d.kind == DecisionKind.NO_TRADE


# ---------------------------------------------------------------------------
# P1: protezioni extra (floor, dati stantii, paused, latched, etc.)
# ---------------------------------------------------------------------------

class TestP1ExtraProtections:
    def test_equity_below_floor_no_trade(self):
        """Equity (400) < minimum_equity (500) → NO_TRADE."""
        engine = _engine_with_open(
            policy=_policy(minimum_equity=500.0),
            snapshot=_snapshot(equity=400.0),
        )
        d = engine.step(_context())
        assert d.kind == DecisionKind.NO_TRADE

    def test_stale_data_no_trade(self):
        engine = _engine_with_open()
        engine.market_params = _market_params(fresh=False)
        with patch("backend.v3.brain_f2.engine.quote_paper_risk", return_value=_real_quote_allowed()):
            d = engine.step(_context())
        assert d.kind == DecisionKind.NO_TRADE

    def test_paused_no_trade(self):
        engine = _engine_with_open()
        engine.market_params = _market_params(paused=True)
        with patch("backend.v3.brain_f2.engine.quote_paper_risk", return_value=_real_quote_allowed()):
            d = engine.step(_context())
        assert d.kind == DecisionKind.NO_TRADE

    def test_daily_loss_latched_no_trade(self):
        engine = _engine_with_open()
        engine.market_params = _market_params(latched=True)
        with patch("backend.v3.brain_f2.engine.quote_paper_risk", return_value=_real_quote_allowed()):
            d = engine.step(_context())
        assert d.kind == DecisionKind.NO_TRADE

    def test_invalid_portfolio_id_no_trade(self):
        engine = _engine_with_open(portfolio_id="hawk")
        d = engine.step(_context())
        assert d.kind == DecisionKind.NO_TRADE

    def test_empty_run_id_no_trade(self):
        engine = _engine_with_open(run_id="   ")
        d = engine.step(_context())
        assert d.kind == DecisionKind.NO_TRADE

    def test_executed_paper_never_returned(self):
        engine = _engine_with_open()
        d = engine.step(_context())
        assert d.status != ProposalStatus.EXECUTED_PAPER

    def test_close_and_modify_not_executable(self):
        """CLOSE e MODIFY_STOP vengono convertiti in NO_TRADE (gate R1)."""
        pol = _policy()
        for kind in (DecisionKind.CLOSE, DecisionKind.MODIFY_STOP):
            analyst = MagicMock()
            analyst.analyze.return_value = BrainDecision(
                kind=kind,
                rationale="ai_unavailable",
                sources=["deepseek:mock"],
                occurred_at_ms=1000,
                status=ProposalStatus.PENDING_REVIEW,
            )
            m = _mandate(policy=pol)
            engine = BrainEngine(
                analyst=analyst,
                reviewer=_reviewer_pass(),
                risk_policy=pol,
                portfolio_snapshot=_snapshot(),
                market_params=_market_params(),
                portfolio_id="brain",
                run_id="run-test-1",
                policy_mandate=m,
                policy_verifier=lambda mandate, rp: True,
            )
            d = engine.step(_context())
            assert d.kind == DecisionKind.NO_TRADE, f"kind={kind} → atteso NO_TRADE, got {d.kind}"
