"""F7 / P3 — TradeOutcome e l'estrattore sul journal: test offline.

Standard (lezione del 4/11): un test di controllo che riesce con input validi,
codici d'errore/stati ESATTI, e mutanti che fanno fallire ogni controllo. Le
posizioni arrivano dai produttori VERI (BrainEngine -> execute_paper ->
close_paper); gli eventi scritti a mano servono solo per record corrotti o
incoerenti, che i produttori veri non scriverebbero.
"""
from __future__ import annotations

import dataclasses
import json
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
from backend.v3.executor.paper import execute_paper
from backend.v3.executor.paper_close import close_paper
from backend.v3.outcomes import (
    LINK_STATUSES, SCHEMA_VERSION, OutcomeError, TradeOutcome, extract_outcomes,
)
from backend.v3.risk import RiskPolicy, RiskQuote

RUN = "r-p3"
TS_DEC = 1_700_000_000_000
T_OPEN = 1_700_000_001_000
T_CLOSE = 1_700_000_061_000
D = Decimal


def _journal() -> EventJournal:
    j = EventJournal(os.path.join(tempfile.mkdtemp(), "journal.db"))
    j.init_schema()
    return j


def _engine(journal, run=RUN) -> BrainEngine:
    policy = RiskPolicy(D(".02"), D(".05"), D(".1"), D(".3"), D("450"), D("16"), D(".5"))
    snapshot = BrainPortfolioSnapshot(D("1000"), D("1000"), D("0"), D("0"))
    params = {"exchange_leverage_limit": 10, "quantity_step": D(".001"),
              "minimum_notional": D("5"), "maintenance_fraction": D(".004"),
              "market_data_fresh": True, "paused": False, "daily_loss_latched": False}
    return BrainEngine(
        analyst=MockDeepSeekAnalyst(), reviewer=MockClaudeReviewer(always_approve=True),
        risk_policy=policy, portfolio_snapshot=snapshot, market_params=params,
        journal=journal, portfolio_id="brain", run_id=run,
        policy_verifier=lambda m, p: True,
        policy_mandate={"version": "p3", "approved_by": "operator", "approved": True,
                        "portfolio_id": "brain", "run_id": run, "policy_hash": _policy_hash(policy)})


def _brain(journal, *, ts=TS_DEC, regime="TRENDING", symbol="BTCUSDT", run=RUN) -> BrainDecision:
    return _engine(journal, run).step(MarketContext(symbol, D("50000"), ts, regime))


def _hand(*, side=1, entry="30000", stop="29000", qty="0.01", margin="60", lev=5,
          symbol="BTC/USDT:USDT", link=None) -> BrainDecision:
    prop = OpenProposal(symbol=symbol, side=side, entry_price=D(entry), stop_price=D(stop),
                        leverage=lev, rationale="deepseek:analysis", confidence=0.75,
                        originating_ai="deepseek", context_hash="h")
    quote = RiskQuote(allowed=True, reason="ok", quantity=D(qty), notional=D(entry) * D(qty),
                      margin=D(margin), worst_case_loss_estimate=D("30"), risk_budget=D("450"))
    return BrainDecision(kind=DecisionKind.OPEN, proposal=prop, risk_quote=quote,
                         rationale="deepseek:analysis", sources=["deepseek:analysis"],
                         occurred_at_ms=TS_DEC, status=ProposalStatus.APPROVED,
                         journal_event_id=link)


def _open(j, decision=None, *, portfolio="hawk", run=RUN, now=T_OPEN):
    return execute_paper(decision or _hand(), portfolio_id=portfolio, run_id=run,
                         journal=j, now_ms=now).position_id


def _close(j, pid, price="31000", *, reason="brain_close", fee=6, portfolio="hawk",
           run=RUN, now=T_CLOSE):
    return close_paper(portfolio_id=portfolio, run_id=run, position_id=pid, exit_price=D(price),
                       reason=reason, fee_bps=fee, journal=j, now_ms=now)


def _report(j, portfolio="hawk", run=RUN, **kw):
    return extract_outcomes(j, portfolio, run, **kw)


def _one(j, **kw) -> TradeOutcome:
    rep = _report(j, **kw)
    assert len(rep.outcomes) == 1 and rep.skipped == (), rep
    return rep.outcomes[0]


# eventi scritti a mano, coerenti con: long 30000 -> 31000, qty 0.01, fee 6 bp
def _raw_open(over=None, pid="rawpos"):
    p = {"position_id": pid, "symbol": "BTC/USDT:USDT", "side": 1, "fill_price": "30000",
         "quantity": "0.01", "notional": "300.00000000", "margin_used": "60", "leverage": 5,
         "stop_price": "29000", "slippage_bps": 0, "originating_ai": "deepseek",
         "context_hash": "h", "rationale": "r", "decision_event_id": ""}
    p.update(over or {})
    return p


def _raw_close(over=None, pid="rawpos"):
    p = {"position_id": pid, "symbol": "BTC/USDT:USDT", "side": 1, "entry_price": "30000",
         "exit_price": "31000", "quantity": "0.01", "notional_entry": "300.00000000",
         "notional_exit": "310.00000000", "gross_pnl": "10.00000000", "fees": "0.36600000",
         "realized_pnl": "9.63400000", "margin_used": "60", "leverage": 5, "fee_bps": "6",
         "reason": "brain_close", "opened_at_ms": T_OPEN, "held_ms": T_CLOSE - T_OPEN,
         "loss_exceeds_margin": False, "decision_event_id": ""}
    p.update(over or {})
    return p


def _raw_pair(j, open_over=None, close_over=None, pid="rawpos", *, with_open=True, with_close=True):
    if with_open:
        j.append(Event(f"paper_open.{pid}", "hawk", RUN, "paper_open", T_OPEN,
                       "executor.paper", _raw_open(open_over, pid)))
    if with_close:
        j.append(Event(f"paper_close.{pid}", "hawk", RUN, "paper_close", T_CLOSE,
                       "executor.paper_close", _raw_close(close_over, pid)))
    return pid


# ---------------------------------------------------------------------------
# controllo + numeri esatti
# ---------------------------------------------------------------------------

class TestControlAndNumbers:
    def test_control_full_chain_with_real_producers(self):
        j = _journal()
        d = _brain(j)
        assert (d.kind, d.status) == (DecisionKind.OPEN, ProposalStatus.APPROVED)  # controllo
        pid = _open(j, d)
        _close(j, pid, "51000", reason="brain_close")
        o = _one(j)
        assert o.position_id == pid and o.symbol == "BTCUSDT" and o.side == 1
        assert o.decision_event_id == d.journal_event_id
        assert (o.link_status, o.decision_regime) == ("linked", "TRENDING")
        assert o.schema_version == SCHEMA_VERSION == 1
        assert o.exit_reason == "brain_close" and o.is_win and not o.is_manual

    def test_long_exact_numbers(self):
        j = _journal()
        _close(j, _open(j))
        o = _one(j)
        assert (o.gross_pnl, o.fees, o.realized_pnl) == (D("10"), D("0.366"), D("9.634"))
        assert o.notional_entry == D("300")
        assert (o.gross_bp, o.costs_bp, o.net_bp) == (D("333.3333"), D("12.2"), D("321.1333"))
        assert o.stop_distance_bp == D("333.3333")
        assert o.r_multiple == D("0.9634")
        assert (o.hold_ms, o.opened_at_ms, o.closed_at_ms) == (60_000, T_OPEN, T_CLOSE)
        assert (o.entry_price, o.exit_price, o.quantity) == (D("30000"), D("31000"), D("0.01"))
        assert (o.margin_used, o.leverage, o.originating_ai) == (D("60"), 5, "deepseek")

    def test_short_exact_numbers(self):
        j = _journal()
        _close(j, _open(j, _hand(side=-1, stop="31000")), "29000")
        o = _one(j)
        assert o.side == -1
        assert (o.gross_pnl, o.fees, o.realized_pnl) == (D("10"), D("0.354"), D("9.646"))
        assert (o.gross_bp, o.costs_bp, o.net_bp) == (D("333.3333"), D("11.8"), D("321.5333"))
        assert o.r_multiple == D("0.9646") and o.stop_distance_bp == D("333.3333")

    def test_losing_trade_exact_numbers(self):
        j = _journal()
        _close(j, _open(j), "29500", reason="stop")
        o = _one(j)
        assert o.realized_pnl == D("-5.357") and not o.is_win
        assert (o.gross_bp, o.costs_bp, o.net_bp) == (D("-166.6667"), D("11.9"), D("-178.5667"))
        assert o.r_multiple == D("-0.5357") and o.exit_reason == "stop"

    def test_net_is_gross_minus_costs_within_rounding(self):
        j = _journal()
        _close(j, _open(j), "30777")
        o = _one(j)
        assert abs(o.net_bp - (o.gross_bp - o.costs_bp)) <= D("0.0001")

    def test_fees_eating_a_tiny_gross_profit_is_a_loss(self):
        """is_win guarda il netto: lordo positivo ma commissioni piu' alte => non e' una vittoria."""
        j = _journal()
        _close(j, _open(j), "30001")
        o = _one(j)
        assert o.gross_pnl > 0 > o.realized_pnl
        assert o.is_win is False and o.net_bp < 0

    def test_loss_exceeding_margin_is_propagated(self):
        j = _journal()
        _close(j, _open(j, _hand(margin="1")), "20000", reason="liquidation")
        o = _one(j)
        assert o.loss_exceeds_margin is True and o.exit_reason == "liquidation"

    def test_to_dict_is_json_safe_and_complete(self):
        j = _journal()
        _close(j, _open(j))
        o = _one(j)
        d = o.to_dict()
        assert set(d) == {f.name for f in dataclasses.fields(TradeOutcome)}
        assert d["net_bp"] == "321.1333" and d["realized_pnl"] == "9.63400000"
        assert d["stop_distance_bp"] == "333.3333" and d["exit_reason"] == "brain_close"
        assert json.loads(json.dumps(d)) == d
        assert all(not isinstance(v, Decimal) for v in d.values())

    def test_outcome_is_immutable(self):
        j = _journal()
        _close(j, _open(j))
        o = _one(j)
        with pytest.raises(dataclasses.FrozenInstanceError):
            o.net_bp = D("1")  # type: ignore[misc]

    def test_stop_on_the_wrong_side_gives_no_r_but_keeps_the_outcome(self):
        j = _journal()
        _raw_pair(j, {"stop_price": "31000"})
        o = _one(j)
        assert o.stop_distance_bp is None and o.r_multiple is None
        assert o.net_bp == D("321.1333")


# ---------------------------------------------------------------------------
# cosa non e' (ancora) un esito
# ---------------------------------------------------------------------------

class TestWhatIsNotAnOutcome:
    def test_open_position_is_listed_not_counted(self):
        j = _journal()
        a, b = _open(j), _open(j, now=T_OPEN + 1)
        _close(j, a)
        rep = _report(j)
        assert [o.position_id for o in rep.outcomes] == [a]
        assert rep.open_position_ids == (b,) and rep.skipped == ()

    def test_empty_journal_gives_empty_report(self):
        rep = _report(_journal())
        assert (rep.outcomes, rep.open_position_ids, rep.skipped) == ((), (), ())

    def test_outcomes_follow_the_order_of_closing(self):
        j = _journal()
        a, b = _open(j), _open(j, now=T_OPEN + 1)
        _close(j, b, now=T_CLOSE)
        _close(j, a, now=T_CLOSE + 5)
        assert [o.position_id for o in _report(j).outcomes] == [b, a]

    def test_manual_and_brain_close_stay_distinct_populations(self):
        j = _journal()
        a, b = _open(j), _open(j, now=T_OPEN + 1)
        _close(j, a, reason="manual")
        _close(j, b, reason="brain_close")
        by = {o.position_id: o for o in _report(j).outcomes}
        assert by[a].is_manual and by[a].exit_reason == "manual"
        assert not by[b].is_manual and by[b].exit_reason == "brain_close"
        assert by[a].is_win and by[b].is_win  # manuale in profitto = vittoria, come deciso


# ---------------------------------------------------------------------------
# legame con la decisione
# ---------------------------------------------------------------------------

class TestLinkStatus:
    def _status(self, j) -> str:
        return _one(j).link_status

    def test_unlinked_when_no_decision_id(self):
        j = _journal()
        _close(j, _open(j))
        o = _one(j)
        assert (o.link_status, o.decision_event_id, o.decision_regime) == ("unlinked", "", "")

    def test_dangling_when_the_decision_does_not_exist(self):
        j = _journal()
        _close(j, _open(j, _hand(link="brain-req-" + "a" * 32)))
        o = _one(j)
        assert (o.link_status, o.decision_regime) == ("dangling", "")

    def test_wrong_decision_when_the_event_is_not_an_approved_open(self):
        j = _journal()
        audit = _brain(j, regime="UNKNOWN", ts=TS_DEC)     # NO_TRADE: audit senza id
        assert audit.kind == DecisionKind.NO_TRADE and audit.journal_event_id is None
        nt_id = [s.event.event_id for s in j.list_run("brain", RUN)][0]
        _close(j, _open(j, _hand(link=nt_id)))
        o = _one(j)
        assert (o.link_status, o.decision_regime) == ("wrong_decision", "UNKNOWN")

    def test_symbol_mismatch(self):
        j = _journal()
        d = _brain(j)                                      # decisione su BTCUSDT
        _close(j, _open(j, _hand(link=d.journal_event_id, symbol="ETH/USDT:USDT")))
        o = _one(j)
        assert (o.link_status, o.decision_regime) == ("symbol_mismatch", "TRENDING")

    def test_decision_after_open(self):
        j = _journal()
        d = _brain(j, ts=T_OPEN + 5_000)                   # la decisione e' DOPO l'apertura
        _close(j, _open(j, _hand(link=d.journal_event_id, symbol="BTCUSDT")))
        assert self._status(j) == "decision_after_open"

    def test_decision_at_the_same_millisecond_is_linked(self):
        j = _journal()
        d = _brain(j, ts=T_OPEN)
        _close(j, _open(j, _hand(link=d.journal_event_id, symbol="BTCUSDT")))
        assert self._status(j) == "linked"

    def test_brain_run_id_selects_where_decisions_live(self):
        j = _journal()
        d = _brain(j, run="r-brain")
        pid = _open(j, d, run="r-pos")
        _close(j, pid, run="r-pos")
        assert _report(j, run="r-pos").outcomes[0].link_status == "dangling"   # cerca nel run sbagliato
        assert _report(j, run="r-pos", brain_run_id="r-brain").outcomes[0].link_status == "linked"

    def test_link_counts_and_linked_outcomes(self):
        j = _journal()
        d = _brain(j)
        a = _open(j, d)
        b = _open(j, _hand(), now=T_OPEN + 1)
        c = _open(j, _hand(link="brain-req-" + "b" * 32), now=T_OPEN + 2)
        for pid in (a, b, c):
            _close(j, pid)
        rep = _report(j)
        counts = rep.link_counts()
        assert set(counts) == set(LINK_STATUSES)
        assert (counts["linked"], counts["unlinked"], counts["dangling"]) == (1, 1, 1)
        assert sum(counts.values()) == 3
        assert [o.position_id for o in rep.linked_outcomes] == [a]


# ---------------------------------------------------------------------------
# record inutilizzabili: mai persi in silenzio
# ---------------------------------------------------------------------------

class TestSkippedRecords:
    def test_control_raw_pair_is_a_valid_outcome(self):
        j = _journal()
        _raw_pair(j)
        assert _one(j).net_bp == D("321.1333")

    @pytest.mark.parametrize("over", [
        {"side": 0}, {"side": "1"}, {"side": 1.0}, {"fill_price": "abc"}, {"fill_price": "0"},
        {"quantity": "0"}, {"stop_price": None}, {"margin_used": "NaN"}, {"leverage": 0},
        {"leverage": True}, {"symbol": ""}, {"decision_event_id": "has space"},
        {"originating_ai": 5}, {"fill_price": "1_000"},
    ])
    def test_corrupt_open(self, over):
        j = _journal()
        _raw_pair(j, over)
        rep = _report(j)
        assert rep.outcomes == () and [(s.position_id, s.code) for s in rep.skipped] == [
            ("rawpos", "corrupt_open")]

    @pytest.mark.parametrize("over", [
        {"reason": "nope"}, {"loss_exceeds_margin": "no"}, {"fees": "x"}, {"side": 0},
        {"decision_event_id": 5}, {"held_ms": -1}, {"exit_price": None}, {"fee_bps": "Infinity"},
        {"opened_at_ms": "x"},
    ])
    def test_corrupt_close(self, over):
        j = _journal()
        _raw_pair(j, None, over)
        rep = _report(j)
        assert rep.outcomes == () and [(s.position_id, s.code) for s in rep.skipped] == [
            ("rawpos", "corrupt_close")]

    @pytest.mark.parametrize("over", [
        {"symbol": "ETH/USDT:USDT"}, {"side": -1}, {"entry_price": "30001"}, {"quantity": "0.02"},
        {"margin_used": "61"}, {"leverage": 6}, {"opened_at_ms": T_OPEN + 1},
        {"held_ms": 1}, {"decision_event_id": "brain-req-" + "c" * 32},
    ])
    def test_close_open_mismatch(self, over):
        j = _journal()
        _raw_pair(j, None, over)
        assert [(s.position_id, s.code) for s in _report(j).skipped] == [
            ("rawpos", "close_open_mismatch")]
        assert _report(j).outcomes == ()

    @pytest.mark.parametrize("over", [
        {"realized_pnl": "100.00000000"}, {"gross_pnl": "11.00000000"}, {"fees": "0.10000000"},
        {"notional_entry": "301.00000000"}, {"notional_exit": "300.00000000"},
        {"exit_price": "32000"}, {"fee_bps": "7"}, {"loss_exceeds_margin": True},
    ])
    def test_inconsistent_close_is_not_trusted(self, over):
        """Numeri del close che non tornano con prezzi, quantita' e costi dichiarati."""
        j = _journal()
        _raw_pair(j, None, over)
        assert [(s.position_id, s.code) for s in _report(j).skipped] == [
            ("rawpos", "inconsistent_close")]
        assert _report(j).outcomes == ()

    def test_extreme_numbers_do_not_crash_the_extractor(self):
        j = _journal()
        _raw_pair(j, {"fill_price": "1E+999999"}, {"entry_price": "1E+999999"})
        rep = _report(j)
        assert [(s.position_id, s.code) for s in rep.skipped] == [("rawpos", "numeric_out_of_range")]

    def test_close_without_open(self):
        j = _journal()
        _raw_pair(j, with_open=False)
        rep = _report(j)
        assert [(s.position_id, s.code) for s in rep.skipped] == [("rawpos", "close_without_open")]
        assert rep.outcomes == () and rep.open_position_ids == ()

    def test_second_close_for_the_same_position_is_reported(self):
        j = _journal()
        _raw_pair(j)
        j.append(Event("paper_close.rawpos.dup", "hawk", RUN, "paper_close", T_CLOSE + 1,
                       "executor.paper_close", _raw_close()))
        rep = _report(j)
        assert [(s.position_id, s.code) for s in rep.skipped] == [("rawpos", "multiple_closes")]
        assert rep.outcomes == ()

    def test_second_open_for_the_same_position_is_reported(self):
        j = _journal()
        _raw_pair(j)
        j.append(Event("paper_open.rawpos.dup", "hawk", RUN, "paper_open", T_OPEN + 1,
                       "executor.paper", _raw_open()))
        rep = _report(j)
        assert [(s.position_id, s.code) for s in rep.skipped] == [("rawpos", "duplicate_open")]
        assert len(rep.outcomes) == 1  # il primo apre/chiude regolarmente

    def test_event_id_that_disagrees_with_position_id_is_corrupt(self):
        j = _journal()
        j.append(Event("paper_open.other", "hawk", RUN, "paper_open", T_OPEN,
                       "executor.paper", _raw_open()))
        j.append(Event("paper_close.rawpos", "hawk", RUN, "paper_close", T_CLOSE,
                       "executor.paper_close", _raw_close()))
        assert [(s.position_id, s.code) for s in _report(j).skipped] == [("rawpos", "corrupt_open")]

    def test_position_id_of_the_wrong_type(self):
        j = _journal()
        j.append(Event("paper_open.x", "hawk", RUN, "paper_open", T_OPEN, "executor.paper",
                       _raw_open({"position_id": 5})))
        assert [(s.position_id, s.code) for s in _report(j).skipped] == [("?", "corrupt_open")]

    def test_one_bad_position_does_not_hide_the_good_ones(self):
        j = _journal()
        good = _open(j)
        _close(j, good)
        _raw_pair(j, {"side": 0}, pid="badpos")
        rep = _report(j)
        assert [o.position_id for o in rep.outcomes] == [good]
        assert [(s.position_id, s.code) for s in rep.skipped] == [("badpos", "corrupt_open")]


# ---------------------------------------------------------------------------
# purezza, isolamento e argomenti
# ---------------------------------------------------------------------------

class TestPurityAndScope:
    def test_extraction_writes_nothing_and_is_deterministic(self):
        j = _journal()
        d = _brain(j)
        _close(j, _open(j, d))
        before = j.verify_chain()
        r1, r2 = _report(j), _report(j)
        assert j.verify_chain() == before
        assert r1 == r2 and r1.outcomes[0].to_dict() == r2.outcomes[0].to_dict()

    def test_other_portfolio_and_other_run_are_not_mixed(self):
        j = _journal()
        _close(j, _open(j, portfolio="bull"), portfolio="bull")
        _close(j, _open(j, run="r-other"), run="r-other")
        assert _report(j, "hawk", RUN).outcomes == ()
        assert len(_report(j, "bull", RUN).outcomes) == 1
        assert len(_report(j, "hawk", "r-other").outcomes) == 1

    def test_outcome_carries_its_own_scope(self):
        j = _journal()
        _close(j, _open(j, portfolio="bull"), portfolio="bull")
        o = _one(j, portfolio="bull")
        assert (o.portfolio_id, o.run_id) == ("bull", RUN)

    @pytest.mark.parametrize("args,code", [
        (dict(portfolio_id="", run_id=RUN), "invalid_portfolio_id"),
        (dict(portfolio_id=None, run_id=RUN), "invalid_portfolio_id"),
        (dict(portfolio_id="hawk", run_id=""), "invalid_run_id"),
        (dict(portfolio_id="hawk", run_id=None), "invalid_run_id"),
        (dict(portfolio_id="hawk", run_id=RUN, brain_run_id=""), "invalid_brain_run_id"),
        (dict(portfolio_id="hawk", run_id=RUN, brain_run_id=7), "invalid_brain_run_id"),
        (dict(portfolio_id="nobody", run_id=RUN), "invalid_scope"),
        (dict(portfolio_id="hawk", run_id="bad id!"), "invalid_scope"),
        (dict(portfolio_id="hawk", run_id=RUN, brain_run_id="bad id!"), "invalid_scope"),
    ])
    def test_invalid_arguments(self, args, code):
        with pytest.raises(OutcomeError, match=f"^{code}$"):
            extract_outcomes(_journal(), **args)

    def test_invalid_journal_type(self):
        with pytest.raises(OutcomeError, match="^invalid_journal_type$"):
            extract_outcomes(object(), "hawk", RUN)  # type: ignore[arg-type]

    def test_journal_read_failure_is_reported(self):
        class _Broken(EventJournal):
            def list_run(self, portfolio_id, run_id):
                raise RuntimeError("db locked")

        base = _journal()
        with pytest.raises(OutcomeError, match="^journal_read_failed$"):
            extract_outcomes(_Broken(base.filename), "hawk", RUN)
