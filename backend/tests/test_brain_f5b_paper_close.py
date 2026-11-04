"""F5b — esecutore di chiusura PAPER: test offline.

Standard di qualita' (lezione del 4/11, PR #40): ogni test negativo asserisce il
codice di errore ESATTO, e test_control_* dimostra che con input validi la
chiusura riesce, cosi' un fallimento negli altri test e' attribuibile all'input
manipolato e non a un setup sbagliato. Le posizioni aperte arrivano dal
produttore vero (execute_paper), non da eventi scritti a mano, salvo nei test
sui payload corrotti.
"""
from __future__ import annotations

import os
import tempfile
from decimal import Decimal

import pytest

from backend.v3.brain_f2.contracts import (
    BrainDecision, DecisionKind, OpenProposal, ProposalStatus,
)
from backend.v3.events import Event, EventJournal
from backend.v3.executor.paper import ExecutionError, execute_paper
from backend.v3.executor.paper_close import CLOSE_REASONS, CloseReceipt, close_paper
from backend.v3.risk import RiskQuote

RUN = "run-close"
T_OPEN = 1_700_000_001_000
T_CLOSE = 1_700_000_061_000  # 60 s dopo


# ---------------------------------------------------------------------------
# helper
# ---------------------------------------------------------------------------

def _journal() -> EventJournal:
    j = EventJournal(os.path.join(tempfile.mkdtemp(), "journal.db"))
    j.init_schema()
    return j


def _decision(side: int = 1, entry: str = "30000", stop: str = "29000",
              qty: str = "0.01", margin: str = "60", leverage: int = 5) -> BrainDecision:
    proposal = OpenProposal(
        symbol="BTC/USDT:USDT", side=side, entry_price=Decimal(entry),
        stop_price=Decimal(stop), leverage=leverage, rationale="deepseek:analysis",
        confidence=0.75, originating_ai="deepseek", context_hash="abc123")
    quote = RiskQuote(
        allowed=True, reason="ok", quantity=Decimal(qty),
        notional=(Decimal(entry) * Decimal(qty)), margin=Decimal(margin),
        worst_case_loss_estimate=Decimal("30"), risk_budget=Decimal("450"))
    return BrainDecision(
        kind=DecisionKind.OPEN, proposal=proposal, risk_quote=quote,
        rationale="deepseek:analysis", sources=["deepseek:analysis"],
        occurred_at_ms=1_700_000_000_000, status=ProposalStatus.APPROVED)


def _open(journal: EventJournal, portfolio_id: str = "hawk", **kw):
    return execute_paper(_decision(**kw), portfolio_id=portfolio_id, run_id=RUN,
                         journal=journal, now_ms=T_OPEN)


def _close(journal: EventJournal, position_id: str, **over):
    args = dict(portfolio_id="hawk", run_id=RUN, position_id=position_id,
                exit_price=Decimal("31000"), reason="brain_close",
                fee_bps=Decimal("6"), journal=journal, now_ms=T_CLOSE)
    args.update(over)
    return close_paper(**args)


def _count(journal: EventJournal, portfolio_id: str = "hawk") -> int:
    return len(journal.list_run(portfolio_id, RUN))


def _raw_open(journal: EventJournal, position_id: str = "rawpos", **override):
    """paper_open scritto a mano: serve solo per payload corrotti / decision_event_id."""
    payload = {"position_id": position_id, "symbol": "BTC/USDT:USDT", "side": 1,
               "fill_price": "30000", "quantity": "0.01", "margin_used": "60",
               "leverage": 5}
    payload.update(override)
    journal.append(Event(f"paper_open.{position_id}", "hawk", RUN, "paper_open",
                         T_OPEN, "executor.paper", payload))
    return position_id


# ---------------------------------------------------------------------------
# controllo + aritmetica
# ---------------------------------------------------------------------------

class TestControlAndArithmetic:
    def test_control_valid_close_succeeds(self):
        j = _journal()
        pos = _open(j)
        r = _close(j, pos.position_id)
        assert isinstance(r, CloseReceipt)
        assert r.position_id == pos.position_id

    def test_long_profit_exact_numbers(self):
        # gross = (31000-30000)*0.01 = 10 ; fees = (300+310)*6/10000 = 0.366
        j = _journal()
        r = _close(j, _open(j).position_id, exit_price=Decimal("31000"))
        assert r.gross_pnl == Decimal("10.00000000")
        assert r.fees == Decimal("0.36600000")
        assert r.realized_pnl == Decimal("9.63400000")

    def test_long_loss_exact_numbers(self):
        # gross = (29000-30000)*0.01 = -10 ; fees = (300+290)*6/10000 = 0.354
        j = _journal()
        r = _close(j, _open(j).position_id, exit_price=Decimal("29000"))
        assert r.gross_pnl == Decimal("-10.00000000")
        assert r.realized_pnl == Decimal("-10.35400000")

    def test_short_profit_exact_numbers(self):
        j = _journal()
        pos = _open(j, side=-1, stop="31000")
        r = _close(j, pos.position_id, exit_price=Decimal("29000"))
        assert r.gross_pnl == Decimal("10.00000000")
        assert r.realized_pnl == Decimal("9.64600000")

    def test_short_loss_exact_numbers(self):
        j = _journal()
        pos = _open(j, side=-1, stop="31000")
        r = _close(j, pos.position_id, exit_price=Decimal("31000"))
        assert r.gross_pnl == Decimal("-10.00000000")
        assert r.realized_pnl == Decimal("-10.36600000")

    def test_zero_fee_realized_equals_gross(self):
        j = _journal()
        r = _close(j, _open(j).position_id, fee_bps=0)
        assert r.fees == Decimal("0E-8") or r.fees == 0
        assert r.realized_pnl == r.gross_pnl

    def test_fee_bps_accepts_int_and_decimal_equally(self):
        j1, j2 = _journal(), _journal()
        a = _close(j1, _open(j1).position_id, fee_bps=6)
        b = _close(j2, _open(j2).position_id, fee_bps=Decimal("6"))
        assert a.realized_pnl == b.realized_pnl

    def test_held_ms_is_close_minus_open(self):
        j = _journal()
        r = _close(j, _open(j).position_id)
        assert r.held_ms == T_CLOSE - T_OPEN == 60_000

    def test_close_at_same_instant_allowed(self):
        j = _journal()
        r = _close(j, _open(j).position_id, now_ms=T_OPEN)
        assert r.held_ms == 0


# ---------------------------------------------------------------------------
# journal
# ---------------------------------------------------------------------------

class TestJournalEvent:
    def test_event_written_with_contract_fields(self):
        j = _journal()
        pos = _open(j)
        r = _close(j, pos.position_id)
        stored = [s for s in j.list_run("hawk", RUN) if s.event.kind == "paper_close"]
        assert len(stored) == 1
        ev = stored[0].event
        assert ev.event_id == f"paper_close.{pos.position_id}" == r.journal_event_id
        assert ev.source == "executor.paper_close"
        assert ev.occurred_at_ms == T_CLOSE
        for key in ("position_id", "symbol", "side", "entry_price", "exit_price",
                    "quantity", "notional_entry", "notional_exit", "gross_pnl", "fees",
                    "realized_pnl", "margin_used", "leverage", "fee_bps", "reason",
                    "opened_at_ms", "held_ms", "loss_exceeds_margin", "decision_event_id"):
            assert key in ev.payload, key
        assert ev.payload["realized_pnl"] == str(r.realized_pnl)

    def test_hash_chain_still_valid_after_close(self):
        j = _journal()
        _close(j, _open(j).position_id)
        count, _ = j.verify_chain()
        assert count == 2

    @pytest.mark.parametrize("reason", sorted(CLOSE_REASONS))
    def test_every_allowed_reason_is_stored(self, reason):
        j = _journal()
        r = _close(j, _open(j).position_id, reason=reason)
        assert r.reason == reason
        ev = [s.event for s in j.list_run("hawk", RUN) if s.event.kind == "paper_close"][0]
        assert ev.payload["reason"] == reason

    def test_manual_is_distinguishable_from_brain_close(self):
        assert "manual" in CLOSE_REASONS and "brain_close" in CLOSE_REASONS

    def test_decision_event_id_copied_from_open_when_present(self):
        j = _journal()
        pos = _raw_open(j, decision_event_id="brain-req-abc")
        _close(j, pos)
        ev = [s.event for s in j.list_run("hawk", RUN) if s.event.kind == "paper_close"][0]
        assert ev.payload["decision_event_id"] == "brain-req-abc"

    def test_decision_event_id_empty_when_open_lacks_it(self):
        j = _journal()
        _close(j, _open(j).position_id)
        ev = [s.event for s in j.list_run("hawk", RUN) if s.event.kind == "paper_close"][0]
        assert ev.payload["decision_event_id"] == ""

    def test_loss_exceeds_margin_flag(self):
        # leva 5, margine 60: da 30000 a 20000 perde ~100 > 60 -> flag; il valore NON e' troncato
        j = _journal()
        r = _close(j, _open(j).position_id, exit_price=Decimal("20000"))
        ev = [s.event for s in j.list_run("hawk", RUN) if s.event.kind == "paper_close"][0]
        assert ev.payload["loss_exceeds_margin"] is True
        assert r.realized_pnl < Decimal("-60")

    def test_loss_within_margin_flag_false(self):
        j = _journal()
        _close(j, _open(j).position_id, exit_price=Decimal("29000"))
        ev = [s.event for s in j.list_run("hawk", RUN) if s.event.kind == "paper_close"][0]
        assert ev.payload["loss_exceeds_margin"] is False


# ---------------------------------------------------------------------------
# validazione degli argomenti: codice ESATTO e nessuna scrittura
# ---------------------------------------------------------------------------

def _expect(code: str, journal: EventJournal, position_id: str, **over):
    before = _count(journal)
    with pytest.raises(ExecutionError) as e:
        _close(journal, position_id, **over)
    assert str(e.value) == code
    assert _count(journal) == before, "una chiusura fallita non deve scrivere nel journal"


class TestArgumentValidation:
    @pytest.mark.parametrize("bad", ["", None, 5])
    def test_invalid_portfolio_id(self, bad):
        j = _journal()
        _expect("invalid_portfolio_id", j, _open(j).position_id, portfolio_id=bad)

    @pytest.mark.parametrize("bad", ["", None, 5])
    def test_invalid_run_id(self, bad):
        j = _journal()
        _expect("invalid_run_id", j, _open(j).position_id, run_id=bad)

    @pytest.mark.parametrize("bad", ["", None, 5])
    def test_invalid_position_id(self, bad):
        j = _journal()
        _open(j)
        _expect("invalid_position_id", j, bad)

    def test_invalid_journal_type(self):
        j = _journal()
        pid = _open(j).position_id
        with pytest.raises(ExecutionError, match="^invalid_journal_type$"):
            close_paper(portfolio_id="hawk", run_id=RUN, position_id=pid,
                        exit_price=Decimal("31000"), reason="stop", fee_bps=6,
                        journal=object(), now_ms=T_CLOSE)

    @pytest.mark.parametrize("bad", ["", "tp", "STOP", None, 3])
    def test_invalid_reason(self, bad):
        j = _journal()
        _expect("invalid_reason", j, _open(j).position_id, reason=bad)

    @pytest.mark.parametrize("bad", [0, -1, Decimal("-0.5"), "NaN", "Infinity", "abc", True, None])
    def test_invalid_exit_price(self, bad):
        j = _journal()
        _expect("invalid_exit_price", j, _open(j).position_id, exit_price=bad)

    @pytest.mark.parametrize("bad", [-1, Decimal("100.01"), 101, "NaN", "Infinity", "x", True, None])
    def test_invalid_fee_bps(self, bad):
        j = _journal()
        _expect("invalid_fee_bps", j, _open(j).position_id, fee_bps=bad)

    @pytest.mark.parametrize("bad", [0, -5, 1.5, True, "1700000000000"])
    def test_invalid_timestamp(self, bad):
        j = _journal()
        _expect("invalid_timestamp", j, _open(j).position_id, now_ms=bad)

    def test_fee_bps_upper_bound_is_inclusive(self):
        j = _journal()
        r = _close(j, _open(j).position_id, fee_bps=100)
        assert r.fees > 0


# ---------------------------------------------------------------------------
# stato della posizione
# ---------------------------------------------------------------------------

class TestPositionState:
    def test_unknown_position(self):
        j = _journal()
        _open(j)
        _expect("position_not_found", j, "doesnotexist")

    def test_wrong_portfolio(self):
        j = _journal()
        pid = _open(j, portfolio_id="hawk").position_id
        before = _count(j, "hawk")
        with pytest.raises(ExecutionError, match="^position_not_found$"):
            _close(j, pid, portfolio_id="bull")
        assert _count(j, "hawk") == before and _count(j, "bull") == 0

    def test_wrong_run(self):
        j = _journal()
        pid = _open(j).position_id
        with pytest.raises(ExecutionError, match="^position_not_found$"):
            _close(j, pid, run_id="another-run")

    def test_cannot_close_twice(self):
        j = _journal()
        pid = _open(j).position_id
        _close(j, pid)
        _expect("position_already_closed", j, pid, exit_price=Decimal("32000"))

    def test_second_close_does_not_change_realized_pnl(self):
        j = _journal()
        pid = _open(j).position_id
        first = _close(j, pid)
        with pytest.raises(ExecutionError):
            _close(j, pid, exit_price=Decimal("1"))
        ev = [s.event for s in j.list_run("hawk", RUN) if s.event.kind == "paper_close"]
        assert len(ev) == 1 and ev[0].payload["realized_pnl"] == str(first.realized_pnl)

    def test_close_before_open_rejected(self):
        j = _journal()
        pid = _open(j).position_id
        _expect("close_before_open", j, pid, now_ms=T_OPEN - 1)

    def test_two_positions_closed_independently(self):
        j = _journal()
        a, b = _open(j).position_id, _open(j).position_id
        ra = _close(j, a, exit_price=Decimal("31000"))
        rb = _close(j, b, exit_price=Decimal("29000"))
        assert ra.realized_pnl > 0 > rb.realized_pnl

    @pytest.mark.parametrize("override", [
        {"side": 0}, {"side": 2}, {"side": True}, {"side": "1"},
        {"fill_price": "abc"}, {"fill_price": "0"}, {"fill_price": "NaN"},
        {"quantity": "0"}, {"quantity": "-1"}, {"quantity": None},
        {"margin_used": "0"}, {"margin_used": "Infinity"},
        {"symbol": ""}, {"symbol": None},
    ])
    def test_corrupt_open_payload_fails_closed(self, override):
        j = _journal()
        pid = _raw_open(j, **override)
        _expect("corrupt_position_payload", j, pid)

    def test_control_raw_open_with_valid_payload_closes(self):
        """Controllo dei test sui payload corrotti: senza override la chiusura riesce."""
        j = _journal()
        r = _close(j, _raw_open(j))
        assert r.symbol == "BTC/USDT:USDT"


# ---------------------------------------------------------------------------
# guasti del journal
# ---------------------------------------------------------------------------

class _FailingWrite(EventJournal):
    def append(self, event):
        raise RuntimeError("disk full")


class _FailingRead(EventJournal):
    def list_run(self, portfolio_id, run_id):
        raise RuntimeError("db locked")


class TestJournalFailures:
    def test_write_failure_is_reported_and_nothing_written(self):
        base = _journal()
        pid = _open(base).position_id
        broken = _FailingWrite(base.filename)
        with pytest.raises(ExecutionError, match="^journal_write_failed$"):
            _close(broken, pid)
        assert _count(base) == 1  # solo il paper_open

    def test_read_failure_is_reported(self):
        base = _journal()
        pid = _open(base).position_id
        broken = _FailingRead(base.filename)
        with pytest.raises(ExecutionError, match="^journal_read_failed$"):
            _close(broken, pid)
        assert _count(base) == 1

    def test_error_message_has_no_balances_or_prices(self):
        j = _journal()
        pid = _open(j).position_id
        _close(j, pid)
        with pytest.raises(ExecutionError) as e:
            _close(j, pid, exit_price=Decimal("31234.5"))
        assert "31234" not in str(e.value) and "30000" not in str(e.value)
