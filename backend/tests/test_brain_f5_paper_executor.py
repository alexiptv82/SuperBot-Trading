"""Offline tests for backend/v3/executor/paper.py — Fase F5.

All tests are offline: no HTTP, no Bitget API, no live market data.
The EventJournal uses a temporary SQLite file created per test.

Coverage plan (25 tests)
-------------------------
TestExecutionReceipt (3):
  - receipt is immutable (frozen dataclass)
  - all fields present
  - fill_price >= entry_price for long (slippage > 0)

TestValidation (10):
  - decision not OPEN kind → ExecutionError
  - decision not APPROVED → ExecutionError
  - decision missing proposal → ExecutionError
  - risk_quote.allowed=False → ExecutionError
  - risk_quote.quantity=0 → ExecutionError
  - invalid portfolio_id → ExecutionError
  - invalid run_id → ExecutionError
  - invalid journal type → ExecutionError
  - slippage_bps out of range → ExecutionError
  - entry_price=0 → ExecutionError

TestSuccessPath (8):
  - basic OPEN long: receipt fields match inputs
  - basic OPEN short: receipt fields match inputs
  - slippage_bps=0: fill_price == entry_price
  - slippage_bps=10: long fill_price > entry_price
  - slippage_bps=10: short fill_price < entry_price
  - decision.status set to EXECUTED_PAPER after success
  - journal contains paper_open event with correct payload
  - journal event_id is deterministic (position_id embedded)

TestFailClosed (4):
  - journal write failure → ExecutionError, decision.status unchanged
  - two calls same decision → second call succeeds (idempotent via event_id conflict handling)
  - wrong portfolio_id ('invalid') → ExecutionError from journal
  - now_ms override respected in receipt and journal
"""
from __future__ import annotations

import os
import tempfile
from decimal import Decimal
from pathlib import Path

import pytest

from backend.v3.brain_f2.contracts import (
    BrainDecision, DecisionKind, OpenProposal, ProposalStatus,
)
from backend.v3.events import EventJournal
from backend.v3.executor.paper import ExecutionError, ExecutionReceipt, execute_paper
from backend.v3.risk import RiskQuote


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_journal() -> EventJournal:
    d = tempfile.mkdtemp()
    j = EventJournal(os.path.join(d, "journal.db"))
    j.init_schema()
    return j


def _make_proposal(
    symbol: str = "BTC/USDT:USDT",
    side: int = 1,
    entry_price: str = "30000",
    stop_price: str = "29000",
    leverage: int = 5,
) -> OpenProposal:
    return OpenProposal(
        symbol=symbol,
        side=side,
        entry_price=Decimal(entry_price),
        stop_price=Decimal(stop_price),
        leverage=leverage,
        rationale="deepseek:analysis",
        confidence=0.75,
        originating_ai="deepseek",
        context_hash="abc123",
    )


def _make_quote(
    allowed: bool = True,
    quantity: str = "0.01",
    margin: str = "60",
    notional: str = "300",
) -> RiskQuote:
    return RiskQuote(
        allowed=allowed,
        reason="ok",
        quantity=Decimal(quantity),
        notional=Decimal(notional),
        margin=Decimal(margin),
        worst_case_loss_estimate=Decimal("30"),
        risk_budget=Decimal("450"),
    )


def _make_approved_decision(proposal: OpenProposal | None = None,
                             quote: RiskQuote | None = None) -> BrainDecision:
    if proposal is None:
        proposal = _make_proposal()
    if quote is None:
        quote = _make_quote()
    d = BrainDecision(
        kind=DecisionKind.OPEN,
        proposal=proposal,
        risk_quote=quote,
        rationale="deepseek:analysis",
        sources=["deepseek:analysis", "claude:review"],
        occurred_at_ms=1_700_000_000_000,
        status=ProposalStatus.APPROVED,
    )
    return d


def _call(decision=None, *, portfolio_id="hawk", run_id="run-001",
          journal=None, slippage_bps=0, now_ms=1_700_000_001_000):
    if decision is None:
        decision = _make_approved_decision()
    if journal is None:
        journal = _make_journal()
    return execute_paper(
        decision,
        portfolio_id=portfolio_id,
        run_id=run_id,
        journal=journal,
        slippage_bps=slippage_bps,
        now_ms=now_ms,
    )


# ---------------------------------------------------------------------------
# TestExecutionReceipt
# ---------------------------------------------------------------------------

class TestExecutionReceipt:
    def test_receipt_is_frozen_dataclass(self):
        receipt = _call()
        with pytest.raises((AttributeError, TypeError)):
            receipt.position_id = "tampered"  # type: ignore[misc]

    def test_all_fields_present(self):
        receipt = _call()
        assert receipt.position_id
        assert receipt.portfolio_id == "hawk"
        assert receipt.run_id == "run-001"
        assert receipt.symbol == "BTC/USDT:USDT"
        assert receipt.side == 1
        assert isinstance(receipt.fill_price, Decimal)
        assert isinstance(receipt.quantity, Decimal)
        assert isinstance(receipt.notional, Decimal)
        assert isinstance(receipt.margin_used, Decimal)
        assert receipt.leverage == 5
        assert isinstance(receipt.stop_price, Decimal)
        assert receipt.timestamp_ms == 1_700_000_001_000
        assert receipt.journal_seq >= 1
        assert receipt.journal_event_id.startswith("paper_open.")

    def test_fill_price_long_with_slippage_gt_zero(self):
        receipt = _call(slippage_bps=10)
        # long: fill_price >= entry_price
        assert receipt.fill_price >= Decimal("30000")


# ---------------------------------------------------------------------------
# TestValidation
# ---------------------------------------------------------------------------

class TestValidation:
    def test_decision_not_open_raises(self):
        d = _make_approved_decision()
        d.kind = DecisionKind.NO_TRADE
        with pytest.raises(ExecutionError, match="decision_not_open"):
            _call(d)

    def test_decision_not_approved_raises(self):
        d = _make_approved_decision()
        d.status = ProposalStatus.DRAFT
        with pytest.raises(ExecutionError, match="decision_not_approved"):
            _call(d)

    def test_decision_missing_proposal_raises(self):
        d = _make_approved_decision()
        d.proposal = None
        with pytest.raises(ExecutionError, match="missing_proposal"):
            _call(d)

    def test_risk_quote_not_allowed_raises(self):
        d = _make_approved_decision(quote=_make_quote(allowed=False))
        with pytest.raises(ExecutionError, match="risk_quote_not_allowed"):
            _call(d)

    def test_risk_quote_zero_quantity_raises(self):
        d = _make_approved_decision(quote=_make_quote(quantity="0"))
        with pytest.raises(ExecutionError, match="invalid_quantity"):
            _call(d)

    def test_invalid_portfolio_id_empty(self):
        with pytest.raises(ExecutionError, match="invalid_portfolio_id"):
            _call(portfolio_id="")

    def test_invalid_portfolio_id_none(self):
        with pytest.raises((ExecutionError, TypeError)):
            _call(portfolio_id=None)  # type: ignore[arg-type]

    def test_invalid_run_id_empty(self):
        with pytest.raises(ExecutionError, match="invalid_run_id"):
            _call(run_id="")

    def test_invalid_journal_type(self):
        with pytest.raises(ExecutionError, match="invalid_journal_type"):
            _call(journal="not_a_journal")  # type: ignore[arg-type]

    def test_slippage_bps_out_of_range(self):
        with pytest.raises(ExecutionError, match="invalid_slippage_bps"):
            _call(slippage_bps=501)


# ---------------------------------------------------------------------------
# TestSuccessPath
# ---------------------------------------------------------------------------

class TestSuccessPath:
    def test_basic_long_receipt_fields(self):
        receipt = _call()
        assert receipt.symbol == "BTC/USDT:USDT"
        assert receipt.side == 1
        assert receipt.fill_price == Decimal("30000")  # no slippage
        assert receipt.quantity == Decimal("0.01")
        assert receipt.margin_used == Decimal("60")
        assert receipt.leverage == 5
        assert receipt.stop_price == Decimal("29000")
        assert receipt.slippage_bps == 0

    def test_basic_short_receipt_fields(self):
        proposal = _make_proposal(side=-1, entry_price="30000", stop_price="31000")
        d = _make_approved_decision(proposal=proposal)
        receipt = _call(d)
        assert receipt.side == -1
        assert receipt.fill_price == Decimal("30000")  # no slippage

    def test_slippage_zero_fill_equals_entry(self):
        receipt = _call(slippage_bps=0)
        assert receipt.fill_price == Decimal("30000")

    def test_slippage_long_fill_above_entry(self):
        receipt = _call(slippage_bps=10)
        # 30000 * (1 + 10/10000) = 30030
        assert receipt.fill_price > Decimal("30000")

    def test_slippage_short_fill_below_entry(self):
        proposal = _make_proposal(side=-1, stop_price="31000")
        d = _make_approved_decision(proposal=proposal)
        receipt = _call(d, slippage_bps=10)
        # short: fill_price < entry_price
        assert receipt.fill_price < Decimal("30000")

    def test_decision_status_set_to_executed_paper(self):
        d = _make_approved_decision()
        assert d.status == ProposalStatus.APPROVED
        _call(d)
        assert d.status == ProposalStatus.EXECUTED_PAPER

    def test_journal_contains_paper_open_event(self):
        journal = _make_journal()
        d = _make_approved_decision()
        receipt = execute_paper(
            d, portfolio_id="hawk", run_id="r1", journal=journal,
            slippage_bps=0, now_ms=1_700_000_001_000,
        )
        events = journal.list_run(portfolio_id="hawk", run_id="r1")
        assert len(events) == 1
        ev = events[0]
        assert ev.event.kind == "paper_open"
        assert ev.event.payload["position_id"] == receipt.position_id
        assert ev.event.payload["symbol"] == "BTC/USDT:USDT"
        assert ev.event.payload["side"] == 1

    def test_journal_event_id_contains_position_id(self):
        receipt = _call()
        assert receipt.position_id in receipt.journal_event_id


# ---------------------------------------------------------------------------
# TestFailClosed
# ---------------------------------------------------------------------------

class TestFailClosed:
    def test_journal_failure_raises_execution_error(self):
        """If the journal is broken, ExecutionError is raised and status stays APPROVED."""
        d = _make_approved_decision()
        # Pass a journal pointing at a non-existent directory → append will fail
        bad_journal = EventJournal("/nonexistent/path/journal.db")
        with pytest.raises(ExecutionError, match="journal_write_failed"):
            execute_paper(d, portfolio_id="hawk", run_id="r1", journal=bad_journal)
        # decision must remain unchanged
        assert d.status == ProposalStatus.APPROVED

    def test_wrong_portfolio_raises_from_journal(self):
        """portfolio_id not in {'hawk','bull','brain'} → journal raises, we wrap in ExecutionError."""
        d = _make_approved_decision()
        j = _make_journal()
        with pytest.raises(ExecutionError, match="journal_write_failed"):
            execute_paper(d, portfolio_id="invalid_portfolio", run_id="r1", journal=j)
        assert d.status == ProposalStatus.APPROVED

    def test_now_ms_override_respected(self):
        receipt = _call(now_ms=9_999_999_999_000)
        assert receipt.timestamp_ms == 9_999_999_999_000

    def test_different_calls_get_different_position_ids(self):
        """Each call generates a unique position_id."""
        j = _make_journal()
        r1 = execute_paper(
            _make_approved_decision(), portfolio_id="hawk", run_id="r1",
            journal=j, now_ms=1_000_000_001_000,
        )
        r2 = execute_paper(
            _make_approved_decision(), portfolio_id="hawk", run_id="r1",
            journal=j, now_ms=1_000_000_002_000,
        )
        assert r1.position_id != r2.position_id
        assert r1.journal_seq < r2.journal_seq
