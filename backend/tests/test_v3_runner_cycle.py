"""A2b - ciclo del Brain: test offline con produttori VERI (BrainEngine -> execute_paper -> journal).

Si finge solo cio' che sta fuori dal repo: le candele (``FakeStore``) e il modello (``ScriptAnalyst``).
Stesso standard degli altri moduli V3: caso valido che riesce, codici d'errore esatti, un test per ogni
garanzia dichiarata nel modulo.
"""
from __future__ import annotations

import dataclasses
import os
import tempfile
from decimal import Decimal

import pytest

from backend.v3.brain_f2.analyst import Analyst
from backend.v3.brain_f2.contracts import (
    BrainDecision, DecisionKind, MarketContext, OpenProposal, ProposalStatus,
)
from backend.v3.brain_f2.engine import _policy_hash
from backend.v3.brain_market.params import TimeframeSpec, load_default_params
from backend.v3.dashboard import build_summary
from backend.v3.events import EventJournal
from backend.v3.features.indicators import Bar
from backend.v3.risk import RiskPolicy
from backend.v3.runner.cycle import (
    CycleBars, CycleReport, MarketEntryAnalyst, NoReviewer, price_with_room, run_brain_cycle,
    snapshot_from_summary,
)

D = Decimal
RUN = "r-a2b"
G = (1_700_000_000_000 // 14_400_000) * 14_400_000        # allineato a 15 m, 1 h e 4 h
NOW = G + 20_000                                          # 20 s dopo la chiusura
POLICY = RiskPolicy(D(".02"), D(".05"), D(".1"), D(".3"), D("450"), D("16"), D(".5"))
RULES = {"exchange_leverage_limit": 10, "quantity_step": D(".001"),
         "minimum_notional": D("5"), "maintenance_fraction": D(".004")}
VIEW = dataclasses.replace(
    load_default_params(),
    timeframes=(TimeframeSpec("15m", 900_000, 20), TimeframeSpec("1h", 3_600_000, 20),
                TimeframeSpec("4h", 14_400_000, 20)))
STEP = {"15m": 900_000, "1h": 3_600_000, "4h": 14_400_000}


def _bars(tf: str, now_ms: int = NOW, n: int = 60) -> list[Bar]:
    step = STEP[tf]
    last = now_ms // step * step - step                    # ultima barra chiusa
    out, prev = [], D("100")
    for i in range(n):
        close = D("100") + D((i * 7) % 11) / 10 + D(i) / 20
        out.append(Bar(last - (n - 1 - i) * step, prev, max(prev, close) + D("0.2"),
                       min(prev, close) - D("0.2"), close, D("10") + D(i % 5)))
        prev = close
    return out


class FakeStore:
    def __init__(self, now_ms: int = NOW, fail: tuple[str, ...] = ()):
        self.now_ms, self.fail, self.calls = now_ms, fail, []

    def refresh(self, symbol, tf, now_ms):
        self.calls.append((symbol, tf, now_ms))
        if symbol in self.fail:
            raise RuntimeError("network")
        return _bars(tf, self.now_ms)


class ScriptAnalyst(Analyst):
    """Un modello finto: propone sempre OPEN (side/stop/entry/confidenza configurabili) e ricorda le chiamate."""

    def __init__(self, side=1, stop_factor=D("0.99"), entry_factor=D("1"), confidence=0.8, kind="OPEN",
                 raises=False):
        self.side, self.stop_factor, self.entry_factor = side, stop_factor, entry_factor
        self.confidence, self.kind, self.raises = confidence, kind, raises
        self.calls: list[tuple[str, list]] = []

    def analyze(self, context: MarketContext, open_positions: list) -> BrainDecision:
        self.calls.append((context.symbol, list(open_positions)))
        if self.raises:
            raise RuntimeError("model down")
        if self.kind == "NO_TRADE":
            return BrainDecision(kind=DecisionKind.NO_TRADE, rationale="deepseek:analysis",
                                 sources=["deepseek:analysis"], occurred_at_ms=context.timestamp_ms)
        p = OpenProposal(symbol=context.symbol, side=self.side, entry_price=context.price * self.entry_factor,
                         stop_price=context.price * self.stop_factor, leverage=3,
                         rationale="deepseek:analysis", confidence=self.confidence,
                         originating_ai="deepseek", context_hash="ab12", strategy_id="S25",
                         strategy_origin="library")
        return BrainDecision(kind=DecisionKind.OPEN, proposal=p, rationale="deepseek:analysis",
                             sources=["deepseek:analysis"], occurred_at_ms=context.timestamp_ms)


def _journal() -> EventJournal:
    j = EventJournal(os.path.join(tempfile.mkdtemp(), "journal.db"))
    j.init_schema()
    return j


def _mandate(approved=True, run=RUN):
    return {"version": "t1", "approved": approved, "approved_by": "operator", "portfolio_id": "brain",
            "run_id": run, "policy_hash": _policy_hash(POLICY)}


def _cycle(journal, analyst, *, symbols=("AAAUSDT", "BBBUSDT"), store=None, bars=None, now=NOW,
           mandate=..., rules=lambda s: RULES, slip=2, equity=D("1000"), price_source=None, rotate=0,
           wrap=True, policy=POLICY, run=RUN):
    holder = bars or CycleBars()
    return run_brain_cycle(
        now_ms=now, journal=journal, run_id=run, symbols=symbols, store=store or FakeStore(now),
        bars_holder=holder, analyst=MarketEntryAnalyst(analyst) if wrap else analyst, view_params=VIEW,
        risk_policy=policy, mandate=_mandate() if mandate is ... else mandate,
        policy_verifier=lambda m, p: True, market_rules=rules, initial_equity=equity, slippage_bps=slip,
        allowed_strategy_ids=("S25",), price_source=price_source, rotate=rotate)


def _events(j, kind):
    return [r.event for r in j.list_run("brain", RUN) if r.event.kind == kind]


# ---------------------------------------------------------------------------------------------------
# 1. Il caso valido: apre davvero, con i produttori veri
# ---------------------------------------------------------------------------------------------------

def test_opens_a_paper_position_for_each_symbol_and_links_the_decision():
    j, a = _journal(), ScriptAnalyst()
    rep = _cycle(j, a)
    assert isinstance(rep, CycleReport) and rep.now_ms == NOW
    assert [s for s, _ in rep.opened] == ["AAAUSDT", "BBBUSDT"] and rep.errors == () and rep.skipped_open == ()
    assert [d[:3] for d in rep.decisions] == [("AAAUSDT", "OPEN", "APPROVED"), ("BBBUSDT", "OPEN", "APPROVED")]
    opens, decs = _events(j, "paper_open"), _events(j, "brain_decision")
    assert len(opens) == 2 and len(decs) == 2
    last_close = _bars("15m")[-1].close
    for ev, sym in zip(opens, ("AAAUSDT", "BBBUSDT")):
        p = ev.payload
        assert p["symbol"] == sym and p["side"] == 1 and p["slippage_bps"] == 2
        assert D(p["fill_price"]) > last_close                                  # long: slippage avversa
        assert D(p["stop_price"]) == last_close * D("0.99")
        assert p["decision_event_id"].startswith("brain-req-") and ev.occurred_at_ms == NOW
        assert ev.portfolio_id == "brain" and ev.run_id == RUN
    assert {d.payload["strategy_id"] for d in decs} == {"S25"}                  # etichetta L1 nel journal
    assert {d.payload["strategy_origin"] for d in decs} == {"library"}
    assert [p.symbol for p in build_summary(j, "brain", RUN).open_positions] == ["AAAUSDT", "BBBUSDT"]


def test_short_fill_has_adverse_slippage_and_exact_stop():
    j = _journal()
    _cycle(j, ScriptAnalyst(side=-1, stop_factor=D("1.01")), symbols=("AAAUSDT",), slip=5)
    p = _events(j, "paper_open")[0].payload
    price = _bars("15m")[-1].close
    assert p["side"] == -1 and D(p["fill_price"]) < price and D(p["stop_price"]) == price * D("1.01")


def test_entry_is_forced_to_the_market_price_not_the_models():
    j = _journal()
    _cycle(j, ScriptAnalyst(entry_factor=D("1.005")), symbols=("AAAUSDT",), slip=0)     # il modello dice +0,5 %
    price = _bars("15m")[-1].close
    assert D(_events(j, "paper_open")[0].payload["fill_price"]) == price


def test_a_model_entry_more_than_one_percent_away_is_still_a_market_entry():
    j = _journal()
    rep = _cycle(j, ScriptAnalyst(entry_factor=D("1.05")), symbols=("AAAUSDT",), slip=0)
    assert rep.opened and D(_events(j, "paper_open")[0].payload["fill_price"]) == _bars("15m")[-1].close


def test_without_the_wrapper_a_far_entry_is_rejected_by_the_engine():
    j = _journal()
    rep = _cycle(j, ScriptAnalyst(entry_factor=D("1.05")), symbols=("AAAUSDT",), wrap=False)
    assert rep.opened == () and rep.decisions == (("AAAUSDT", "NO_TRADE", "REJECTED", "price_divergence"),)


# ---------------------------------------------------------------------------------------------------
# 2. Una posizione aperta ferma quel simbolo; le altre contano per i simboli successivi
# ---------------------------------------------------------------------------------------------------

def test_symbol_with_open_position_is_skipped_and_the_model_is_not_called():
    j = _journal()
    _cycle(j, ScriptAnalyst(), symbols=("AAAUSDT",))
    a2 = ScriptAnalyst()
    rep = _cycle(j, a2, symbols=("AAAUSDT", "BBBUSDT"), now=NOW + 900_000, store=FakeStore(NOW + 900_000))
    assert rep.skipped_open == ("AAAUSDT",) and [s for s, _ in a2.calls] == ["BBBUSDT"]
    assert [s for s, _ in rep.opened] == ["BBBUSDT"]


def test_a_position_opened_earlier_in_the_cycle_is_visible_to_the_next_symbol():
    j, a = _journal(), ScriptAnalyst()
    _cycle(j, a)
    assert a.calls[0] == ("AAAUSDT", [])
    assert a.calls[1] == ("BBBUSDT", [{"symbol": "AAAUSDT", "side": 1}])


def test_margin_of_the_first_position_limits_the_next_one():
    j = _journal()
    tight = RiskPolicy(D(".02"), D(".05"), D(".1"), D(".1"), D("450"), D("16"), D(".5"))   # margine totale 10 %
    rep = _cycle(j, ScriptAnalyst(), policy=tight, mandate={**_mandate(), "policy_hash": _policy_hash(tight)})
    assert [s for s, _ in rep.opened] == ["AAAUSDT"]
    assert rep.decisions[1] == ("BBBUSDT", "NO_TRADE", "RISK_REJECTED", "risk_rejected")


# ---------------------------------------------------------------------------------------------------
# 3. Fail-closed: errori isolati per simbolo, nessuna decisione senza dati buoni
# ---------------------------------------------------------------------------------------------------

def test_feed_error_on_one_symbol_does_not_stop_the_others():
    j, a = _journal(), ScriptAnalyst()
    rep = _cycle(j, a, store=FakeStore(fail=("AAAUSDT",)))
    assert rep.errors == (("AAAUSDT", "feed_error"),) and [s for s, _ in rep.opened] == ["BBBUSDT"]
    assert [s for s, _ in a.calls] == ["BBBUSDT"]


def test_stale_candles_mean_no_decision_no_model_call_no_journal_event():
    j, a = _journal(), ScriptAnalyst()
    late = NOW + 900_000                                     # i dati sono di un giro prima
    rep = _cycle(j, a, symbols=("AAAUSDT",), now=late, store=FakeStore(NOW))
    assert rep.errors == (("AAAUSDT", "data_unavailable"),) and rep.decisions == () and a.calls == []
    assert _events(j, "brain_decision") == [] and _events(j, "paper_open") == []


def test_view_error_when_candles_are_in_the_future():
    j, a = _journal(), ScriptAnalyst()
    rep = _cycle(j, a, symbols=("AAAUSDT",), now=NOW - 3_600_000, store=FakeStore(NOW))
    assert rep.errors == (("AAAUSDT", "view_error"),) and a.calls == []


@pytest.mark.parametrize("rules", [lambda s: None, lambda s: {"quantity_step": D(".001")},
                                   lambda s: [("quantity_step", 1)], lambda s: "x"])
def test_missing_or_incomplete_market_rules_skip_the_symbol(rules):
    j, a = _journal(), ScriptAnalyst()
    rep = _cycle(j, a, symbols=("AAAUSDT",), rules=rules)
    assert rep.errors == (("AAAUSDT", "no_market_rules"),) and a.calls == [] and rep.opened == ()


def test_a_crashing_rules_provider_is_isolated_to_its_symbol():
    def rules(sym):
        if sym == "AAAUSDT":
            raise KeyError(sym)
        return RULES
    rep = _cycle(_journal(), ScriptAnalyst(), rules=rules)
    assert rep.errors == (("AAAUSDT", "cycle_error"),) and [s for s, _ in rep.opened] == ["BBBUSDT"]


def test_model_failure_is_journaled_as_no_trade_and_opens_nothing():
    j = _journal()
    rep = _cycle(j, ScriptAnalyst(raises=True), symbols=("AAAUSDT",))
    assert rep.decisions == (("AAAUSDT", "NO_TRADE", "REJECTED", "ai_unavailable"),) and rep.opened == ()
    assert len(_events(j, "brain_decision")) == 1 and _events(j, "paper_open") == []


def test_no_trade_from_the_model_is_journaled_and_opens_nothing():
    j = _journal()
    rep = _cycle(j, ScriptAnalyst(kind="NO_TRADE"), symbols=("AAAUSDT",))
    assert rep.decisions[0][:2] == ("AAAUSDT", "NO_TRADE") and rep.opened == ()
    assert len(_events(j, "brain_decision")) == 1


@pytest.mark.parametrize("mandate", [_mandate(approved=False), None, {**_mandate(), "approved_by": ""},
                                     {**_mandate(), "run_id": "altro"}, {**_mandate(), "policy_hash": "0" * 16}])
def test_without_a_valid_approved_mandate_nothing_opens(mandate):
    j = _journal()
    rep = _cycle(j, ScriptAnalyst(), symbols=("AAAUSDT",), mandate=mandate)
    assert rep.opened == () and rep.decisions == (("AAAUSDT", "NO_TRADE", "REJECTED", "policy_not_authorized"),)
    assert _events(j, "paper_open") == []


def test_stop_on_the_wrong_side_is_refused_by_the_risk_gate():
    j = _journal()
    rep = _cycle(j, ScriptAnalyst(side=1, stop_factor=D("1.01")), symbols=("AAAUSDT",))
    assert rep.opened == () and rep.decisions[0][:3] == ("AAAUSDT", "NO_TRADE", "RISK_REJECTED")


def test_equity_below_the_floor_blocks_every_opening():
    rep = _cycle(_journal(), ScriptAnalyst(), symbols=("AAAUSDT",), equity=D("449"))
    assert rep.opened == () and rep.decisions[0][2] == "RISK_REJECTED"


def test_low_confidence_is_not_sent_to_a_reviewer():
    j = _journal()
    rep = _cycle(j, ScriptAnalyst(confidence=0.05), symbols=("AAAUSDT",))
    assert rep.opened and rep.decisions[0][2] == "APPROVED"          # nessuna revisione chiesta


def test_no_reviewer_refuses_if_it_is_ever_asked():
    with pytest.raises(RuntimeError, match="review_not_available"):
        NoReviewer().review(BrainDecision(kind=DecisionKind.NO_TRADE), "x")


def test_execution_error_is_reported_and_other_symbols_continue(monkeypatch):
    import backend.v3.runner.cycle as cyc
    from backend.v3.executor.paper import ExecutionError
    real = cyc.execute_paper

    def flaky(decision, **kw):
        if decision.proposal.symbol == "AAAUSDT":
            raise ExecutionError("journal_write_failed")
        return real(decision, **kw)
    monkeypatch.setattr(cyc, "execute_paper", flaky)
    j = _journal()
    rep = _cycle(j, ScriptAnalyst())
    assert rep.errors == (("AAAUSDT", "journal_write_failed"),) and [s for s, _ in rep.opened] == ["BBBUSDT"]
    assert [e.payload["symbol"] for e in _events(j, "paper_open")] == ["BBBUSDT"]


@pytest.mark.parametrize("kind,status", [(DecisionKind.OPEN, ProposalStatus.REJECTED),
                                         (DecisionKind.OPEN, ProposalStatus.RISK_REJECTED),
                                         (DecisionKind.OPEN, ProposalStatus.DRAFT),
                                         (DecisionKind.HOLD, ProposalStatus.APPROVED)])
def test_only_an_open_approved_decision_is_ever_executed(monkeypatch, kind, status):
    import backend.v3.runner.cycle as cyc

    class StubEngine:
        def __init__(self, **kw):
            self.open_positions = []

        def step(self, context, threshold):
            return BrainDecision(kind=kind, status=status, rationale="sanitized", sources=[],
                                 occurred_at_ms=context.timestamp_ms)

    def boom(*a, **kw):
        raise AssertionError("execute_paper must not be called")
    monkeypatch.setattr(cyc, "BrainEngine", StubEngine)
    monkeypatch.setattr(cyc, "execute_paper", boom)
    rep = _cycle(_journal(), ScriptAnalyst(), symbols=("AAAUSDT",))
    assert rep.opened == () and rep.errors == () and rep.decisions[0][:3] == ("AAAUSDT", kind.value, status.value)


def test_market_entry_analyst_leaves_non_open_decisions_alone():
    ctx = MarketContext("AAAUSDT", D("100"), NOW, "UNCERTAIN")
    prop = OpenProposal(symbol="AAAUSDT", side=1, entry_price=D("100.4"), stop_price=D("99"), leverage=2,
                        rationale="deepseek:analysis", confidence=0.5, originating_ai="deepseek", context_hash="ab")

    class Hold(Analyst):
        def analyze(self, context, open_positions):
            return BrainDecision(kind=DecisionKind.HOLD, proposal=prop, rationale="deepseek:analysis",
                                 sources=[], occurred_at_ms=context.timestamp_ms)
    assert MarketEntryAnalyst(Hold()).analyze(ctx, []).proposal.entry_price == D("100.4")


# ---------------------------------------------------------------------------------------------------
# 4. Prezzo, rotazione, argomenti
# ---------------------------------------------------------------------------------------------------

def test_price_source_overrides_the_base_close_for_context_and_fill():
    j = _journal()
    seen = []

    def src(sym, now):
        seen.append((sym, now))
        return D("100.5")
    a = ScriptAnalyst()
    _cycle(j, a, symbols=("AAAUSDT",), slip=0, price_source=src)
    assert seen == [("AAAUSDT", NOW)]
    p = _events(j, "paper_open")[0].payload
    assert D(p["fill_price"]) == D("100.5") and D(p["stop_price"]) == D("100.5") * D("0.99")


@pytest.mark.parametrize("src", [lambda s, n: (_ for _ in ()).throw(RuntimeError("x")), lambda s, n: None,
                                 lambda s, n: 100.5, lambda s, n: D("0"), lambda s, n: D("-1"),
                                 lambda s, n: D("NaN"), lambda s, n: D("Infinity")])
def test_a_bad_price_source_skips_the_symbol(src):
    a = ScriptAnalyst()
    rep = _cycle(_journal(), a, symbols=("AAAUSDT",), price_source=src)
    assert rep.errors == (("AAAUSDT", "price_error"),) and a.calls == [] and rep.opened == ()


def test_rotation_changes_the_order_but_not_the_set():
    syms = ("AAAUSDT", "BBBUSDT", "CCCUSDT")
    orders = []
    for rot in (0, 1, 2, 3, 4):
        a = ScriptAnalyst(kind="NO_TRADE")
        _cycle(_journal(), a, symbols=syms, rotate=rot)
        orders.append([s for s, _ in a.calls])
    assert orders == [["AAAUSDT", "BBBUSDT", "CCCUSDT"], ["BBBUSDT", "CCCUSDT", "AAAUSDT"],
                      ["CCCUSDT", "AAAUSDT", "BBBUSDT"], ["AAAUSDT", "BBBUSDT", "CCCUSDT"],
                      ["BBBUSDT", "CCCUSDT", "AAAUSDT"]]


def test_empty_symbol_list_is_a_quiet_cycle():
    rep = _cycle(_journal(), ScriptAnalyst(), symbols=())
    assert rep == CycleReport(NOW, (), (), (), ())


@pytest.mark.parametrize("now", [0, -1, 1.5, "1", True, None])
def test_invalid_now_is_rejected(now):
    with pytest.raises(ValueError, match="invalid_now"):
        _cycle(_journal(), ScriptAnalyst(), now=now)


@pytest.mark.parametrize("rot", [-1, 1.0, "1", True, None])
def test_invalid_rotate_is_rejected(rot):
    with pytest.raises(ValueError, match="invalid_rotate"):
        _cycle(_journal(), ScriptAnalyst(), rotate=rot)


def test_cycle_bars_holder_is_cleared_each_cycle_and_keeps_copies():
    holder = CycleBars()
    holder.set("X", {"15m": [1]})
    src = {"15m": [1, 2]}
    holder.set("Y", src)
    src["15m"].append(3)
    assert holder("Y") == {"15m": [1, 2]} and holder("X") == {"15m": [1]}
    _cycle(_journal(), ScriptAnalyst(kind="NO_TRADE"), symbols=("AAAUSDT",), bars=holder)
    with pytest.raises(KeyError):
        holder("X")                                          # un giro nuovo parte pulito
    assert set(holder("AAAUSDT")) == {"15m", "1h", "4h"}


# ---------------------------------------------------------------------------------------------------
# 5. MarketEntryAnalyst e istantanea del portafoglio
# ---------------------------------------------------------------------------------------------------

def test_market_entry_analyst_only_touches_open_entries():
    ctx = MarketContext("AAAUSDT", D("100"), NOW, "UNCERTAIN")
    wrapped = MarketEntryAnalyst(ScriptAnalyst(entry_factor=D("1.004"), stop_factor=D("0.97"), confidence=0.61))
    d = wrapped.analyze(ctx, [])
    pr = d.proposal
    assert pr.entry_price == D("100") and pr.stop_price == D("97.00") and pr.confidence == 0.61
    assert pr.side == 1 and pr.leverage == 3 and pr.strategy_id == "S25" and pr.context_hash == "ab12"
    nt = MarketEntryAnalyst(ScriptAnalyst(kind="NO_TRADE")).analyze(ctx, [])
    assert nt.kind == DecisionKind.NO_TRADE and nt.proposal is None


def test_market_entry_analyst_requires_an_analyst():
    with pytest.raises(ValueError, match="invalid_analyst"):
        MarketEntryAnalyst(object())


def test_snapshot_from_summary_uses_realized_pnl_margin_and_open_risk():
    j = _journal()
    _cycle(j, ScriptAnalyst(), symbols=("AAAUSDT",), slip=0)
    s = build_summary(j, "brain", RUN)
    pos = s.open_positions[0]
    snap = snapshot_from_summary(s, D("1000"))
    assert snap.equity == D("1000") and snap.margin_used == pos.margin_used
    assert snap.available_cash == D("1000") - pos.margin_used
    assert snap.existing_open_risk == abs(pos.fill_price - pos.stop_price) * pos.quantity
    big = dataclasses.replace(s, realized_pnl=D("-50"), margin_in_use=D("2000"))
    snap2 = snapshot_from_summary(big, D("1000"))
    assert snap2.equity == D("950") and snap2.available_cash == D("0")       # mai negativa
    empty = dataclasses.replace(s, open_positions=(), margin_in_use=D("0"), realized_pnl=D("12.5"))
    snap3 = snapshot_from_summary(empty, D("1000"))
    assert (snap3.equity, snap3.available_cash, snap3.margin_used, snap3.existing_open_risk) == (
        D("1012.5"), D("1012.5"), D("0"), D("0"))


# ---------------------------------------------------------------------------------------------------
# 6. Precisione del prezzo: la slippage non deve sparire (execute_paper arrotonda alla precisione del prezzo)
# ---------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("price,expected_exp", [("100", -8), ("100.5", -8), ("0.18234", -8), ("97123.4", -8),
                                                ("0.123456789012", -12), ("1.00000000", -8)])
def test_price_with_room_keeps_the_value_and_at_least_eight_places(price, expected_exp):
    out = price_with_room(D(price))
    assert out == D(price) and out.as_tuple().exponent == expected_exp


@pytest.mark.parametrize("price,long_fill,short_fill", [
    ("100", "100.02000000", "99.98000000"),
    ("0.18234", "0.18237646", "0.18230353"),         # a 5 decimali la slippage di 2 bp si perderebbe sul long
    ("97123.4", "97142.82468000", "97103.97532000"),
])
def test_slippage_is_applied_at_full_precision_whatever_the_price_decimals(price, long_fill, short_fill):
    for side, stop_factor, expected in ((1, D("0.99"), long_fill), (-1, D("1.01"), short_fill)):
        j = _journal()
        rep = _cycle(j, ScriptAnalyst(side=side, stop_factor=stop_factor), symbols=("AAAUSDT",), slip=2,
                     price_source=lambda s, n, p=price: D(p))
        assert rep.opened, rep
        assert D(_events(j, "paper_open")[0].payload["fill_price"]) == D(expected)
