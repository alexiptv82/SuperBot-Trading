"""P2, lato esecutore: l'id della decisione arriva da brain_decision a paper_open a paper_close.

Catena completa con i produttori VERI (BrainEngine -> execute_paper -> close_paper),
senza eventi scritti a mano, tranne nei test sul payload corrotto. Controllo +
codici d'errore esatti + mutanti (vedi messaggio di commit).
"""
from __future__ import annotations

import os
import tempfile
from decimal import Decimal

import pytest

from backend.v3.brain_f2.analyst import MockDeepSeekAnalyst
from backend.v3.brain_f2.contracts import (
    BrainDecision, DecisionKind, MarketContext, OpenProposal, ProposalStatus,
)
from backend.v3.brain_f2.engine import BrainEngine, BrainPortfolioSnapshot, _policy_hash
from backend.v3.brain_f2.reviewer import MockClaudeReviewer
from backend.v3.events import Event, EventJournal
from backend.v3.executor.paper import ExecutionError, execute_paper
from backend.v3.executor.paper_close import close_paper
from backend.v3.risk import RiskPolicy, RiskQuote

RUN = "r-e2e-link"
T_OPEN = 1_700_000_001_000
T_CLOSE = 1_700_000_061_000


def _journal() -> EventJournal:
    j = EventJournal(os.path.join(tempfile.mkdtemp(), "journal.db"))
    j.init_schema()
    return j


def _engine(journal) -> BrainEngine:
    policy = RiskPolicy(Decimal(".02"), Decimal(".05"), Decimal(".1"),
                        Decimal(".3"), Decimal("450"), Decimal("16"), Decimal(".5"))
    snapshot = BrainPortfolioSnapshot(Decimal("1000"), Decimal("1000"), Decimal("0"), Decimal("0"))
    params = {"exchange_leverage_limit": 10, "quantity_step": Decimal(".001"),
              "minimum_notional": Decimal("5"), "maintenance_fraction": Decimal(".004"),
              "market_data_fresh": True, "paused": False, "daily_loss_latched": False}
    return BrainEngine(
        analyst=MockDeepSeekAnalyst(), reviewer=MockClaudeReviewer(always_approve=True),
        risk_policy=policy, portfolio_snapshot=snapshot, market_params=params,
        journal=journal, portfolio_id="brain", run_id=RUN,
        policy_verifier=lambda m, p: True,
        policy_mandate={"version": "e2e", "approved_by": "operator", "approved": True,
                        "portfolio_id": "brain", "run_id": RUN, "policy_hash": _policy_hash(policy)})


def _hand_decision(**over) -> BrainDecision:
    """Decisione OPEN/APPROVED costruita a mano (non passa dal motore)."""
    prop = OpenProposal(symbol="BTC/USDT:USDT", side=1, entry_price=Decimal("30000"),
                        stop_price=Decimal("29000"), leverage=5, rationale="deepseek:analysis",
                        confidence=0.75, originating_ai="deepseek", context_hash="abc123")
    quote = RiskQuote(allowed=True, reason="ok", quantity=Decimal("0.01"), notional=Decimal("300"),
                      margin=Decimal("60"), worst_case_loss_estimate=Decimal("30"),
                      risk_budget=Decimal("450"))
    kw = dict(kind=DecisionKind.OPEN, proposal=prop, risk_quote=quote,
              rationale="deepseek:analysis", sources=["deepseek:analysis"],
              occurred_at_ms=1_700_000_000_000, status=ProposalStatus.APPROVED)
    kw.update(over)
    return BrainDecision(**kw)


def _kind(journal, portfolio, kind):
    return [s.event for s in journal.list_run(portfolio, RUN) if s.event.kind == kind]


# ---------------------------------------------------------------------------
# catena completa con i produttori veri
# ---------------------------------------------------------------------------

class TestFullChain:
    def test_decision_id_flows_from_brain_to_open_to_close(self):
        j = _journal()
        d = _engine(j).step(MarketContext("BTCUSDT", Decimal("50000"), 1_700_000_000_000, "TRENDING"))
        assert (d.kind, d.status) == (DecisionKind.OPEN, ProposalStatus.APPROVED)  # controllo
        brain_id = d.journal_event_id
        assert brain_id

        receipt = execute_paper(d, portfolio_id="hawk", run_id=RUN, journal=j, now_ms=T_OPEN)
        opens = _kind(j, "hawk", "paper_open")
        assert len(opens) == 1 and opens[0].payload["decision_event_id"] == brain_id
        assert receipt.decision_event_id == brain_id
        assert d.status == ProposalStatus.EXECUTED_PAPER  # execute_paper non ha perso il legame
        assert d.journal_event_id == brain_id

        close_paper(portfolio_id="hawk", run_id=RUN, position_id=receipt.position_id,
                    exit_price=Decimal("51000"), reason="brain_close", fee_bps=6,
                    journal=j, now_ms=T_CLOSE)
        closes = _kind(j, "hawk", "paper_close")
        assert len(closes) == 1 and closes[0].payload["decision_event_id"] == brain_id

    def test_the_linked_event_exists_and_describes_the_same_trade(self):
        """Il legame non e' penzolante: l'id punta a un brain_decision reale, stesso simbolo."""
        j = _journal()
        d = _engine(j).step(MarketContext("BTCUSDT", Decimal("50000"), 1_700_000_000_000, "TRENDING"))
        r = execute_paper(d, portfolio_id="hawk", run_id=RUN, journal=j, now_ms=T_OPEN)
        brain_events = {e.event_id: e for e in _kind(j, "brain", "brain_decision")}
        target = brain_events[r.decision_event_id]
        assert target.payload["kind"] == "OPEN" and target.payload["status"] == "APPROVED"
        assert target.payload["symbol"] == r.symbol == "BTCUSDT"
        assert target.payload["regime"] == "TRENDING"

    def test_two_decisions_two_positions_keep_their_own_links(self):
        j = _journal()
        eng = _engine(j)
        d1 = eng.step(MarketContext("BTCUSDT", Decimal("50000"), 1_700_000_000_000, "TRENDING"))
        d2 = eng.step(MarketContext("BTCUSDT", Decimal("50100"), 1_700_000_060_000, "TRENDING"))
        r1 = execute_paper(d1, portfolio_id="hawk", run_id=RUN, journal=j, now_ms=T_OPEN)
        r2 = execute_paper(d2, portfolio_id="hawk", run_id=RUN, journal=j, now_ms=T_OPEN + 1)
        assert r1.decision_event_id != r2.decision_event_id
        assert (r1.decision_event_id, r2.decision_event_id) == (d1.journal_event_id, d2.journal_event_id)


# ---------------------------------------------------------------------------
# posizioni senza decisione collegata / id non valido
# ---------------------------------------------------------------------------

class TestUnlinkedAndInvalid:
    def test_control_hand_built_decision_opens(self):
        j = _journal()
        r = execute_paper(_hand_decision(), portfolio_id="hawk", run_id=RUN, journal=j, now_ms=T_OPEN)
        assert r.symbol == "BTC/USDT:USDT"

    def test_decision_without_id_is_stored_as_unlinked(self):
        j = _journal()
        r = execute_paper(_hand_decision(), portfolio_id="hawk", run_id=RUN, journal=j, now_ms=T_OPEN)
        assert r.decision_event_id == ""
        assert _kind(j, "hawk", "paper_open")[0].payload["decision_event_id"] == ""
        c = close_paper(portfolio_id="hawk", run_id=RUN, position_id=r.position_id,
                        exit_price=Decimal("31000"), reason="manual", fee_bps=6, journal=j, now_ms=T_CLOSE)
        assert _kind(j, "hawk", "paper_close")[0].payload["decision_event_id"] == ""
        assert c.reason == "manual"

    def test_wellformed_id_on_hand_built_decision_is_stored(self):
        j = _journal()
        r = execute_paper(_hand_decision(journal_event_id="brain-req-" + "a" * 32),
                          portfolio_id="hawk", run_id=RUN, journal=j, now_ms=T_OPEN)
        assert r.decision_event_id == "brain-req-" + "a" * 32

    @pytest.mark.parametrize("bad", ["", "has space", "x" * 129, "-lead", "a/b", 5, b"abc", ["x"], 1.5])
    def test_malformed_id_is_rejected_and_nothing_is_written(self, bad):
        j = _journal()
        with pytest.raises(ExecutionError, match="^invalid_decision_event_id$"):
            execute_paper(_hand_decision(journal_event_id=bad), portfolio_id="hawk", run_id=RUN,
                          journal=j, now_ms=T_OPEN)
        assert _kind(j, "hawk", "paper_open") == []

    def test_rejected_decision_is_not_marked_executed(self):
        j = _journal()
        d = _hand_decision(journal_event_id="has space")
        with pytest.raises(ExecutionError):
            execute_paper(d, portfolio_id="hawk", run_id=RUN, journal=j, now_ms=T_OPEN)
        assert d.status == ProposalStatus.APPROVED


# ---------------------------------------------------------------------------
# close_paper: il campo del paper_open deve essere una stringa breve
# ---------------------------------------------------------------------------

def _raw_open(journal, **override):
    payload = {"position_id": "rawpos", "symbol": "BTC/USDT:USDT", "side": 1,
               "fill_price": "30000", "quantity": "0.01", "margin_used": "60", "leverage": 5}
    payload.update(override)
    journal.append(Event("paper_open.rawpos", "hawk", RUN, "paper_open", T_OPEN,
                         "executor.paper", payload))


class TestClosePropagationAndCorruption:
    def _close(self, j):
        return close_paper(portfolio_id="hawk", run_id=RUN, position_id="rawpos",
                           exit_price=Decimal("31000"), reason="stop", fee_bps=6,
                           journal=j, now_ms=T_CLOSE)

    def test_control_old_open_without_the_field_still_closes_as_unlinked(self):
        j = _journal()
        _raw_open(j)
        self._close(j)
        assert _kind(j, "hawk", "paper_close")[0].payload["decision_event_id"] == ""

    def test_close_copies_the_open_value(self):
        j = _journal()
        _raw_open(j, decision_event_id="brain-req-" + "b" * 32)
        self._close(j)
        assert _kind(j, "hawk", "paper_close")[0].payload["decision_event_id"] == "brain-req-" + "b" * 32

    @pytest.mark.parametrize("bad", [5, None, ["x"], {"a": 1}, "x" * 129, True])
    def test_corrupt_decision_event_id_fails_closed(self, bad):
        j = _journal()
        _raw_open(j, decision_event_id=bad)
        with pytest.raises(ExecutionError, match="^corrupt_position_payload$"):
            self._close(j)
        assert _kind(j, "hawk", "paper_close") == []
