"""Politica d'ingresso e di gestione versionabile (24/11/2026): filtri LONG e costi, consulto selettivo, rischio
dimezzato senza Claude (preparato, spento), guardia sugli stop dell'AI (caso BTC reale), secondo ingresso.

Regola di base: i valori predefiniti riproducono ESATTAMENTE il comportamento precedente; ogni posizione usa la
politica della versione con cui e' nata."""
import json
from dataclasses import replace
from decimal import Decimal as D

import pytest

from backend.tests.test_brain_f7_outcomes import _hand
from backend.tests.test_v3_brain_unico_2000 import CFG, T0, _engine, _view, cfg
from backend.v3 import entry_policy as ep
from backend.v3 import strategy_versions as sv
from backend.v3.brain_f2.analyst import Analyst
from backend.v3.brain_f2.contracts import BrainDecision, DecisionKind, MarketContext, OpenProposal, ProposalStatus
from backend.v3.brain_f2.engine import _scale_in_cap
from backend.v3.events import EventJournal
from backend.v3.executor.paper import execute_paper
from backend.v3.runner.config import load_runner_config
from backend.v3.runner.consult import ClaudeView, CollaborativeAnalyst, arbitrate_entry, entry_triggers
from backend.v3.runner.position_review import ReviewProposal, groups_from_journal, validate

RUN = "r1"
V2 = {"long_trend_filter": True, "max_cost_fraction_r": "0.3", "consult_conf_tier_a": "0.6",
      "consult_conf_other": "0.7", "consult_on_expansion": False, "consult_limit_fallback": "veto",
      "stop_guard_atr_mult": "1", "stop_guard_cost_zone": True, "scale_in_min_gap_r": "0.25",
      "scale_in_min_stop_room_r": "0.3"}


def _prop(symbol="BTCUSDT", side=-1, conf=0.62, uncertain=False, reasons=(), stop="60800", entry="60200"):
    return OpenProposal(symbol, side, D(entry), D(stop), 20, "deepseek:analysis", conf, "deepseek", "a" * 32,
                        reasons=reasons, uncertain=uncertain)


def _market(t1h=(50, 1), t4h=(80, 1), atr1h="108"):
    def tf(name, g):
        return {"tf": name, "status": "ok", "ema_slow_gap_bp": g[0], "ema_cross": g[1], "atr_bp": atr1h}
    return {"timeframes": [tf("1h", t1h), tf("4h", t4h)] if t4h else [tf("1h", t1h)]}


def _base_with(policy=V2, version=None) -> bytes:
    data = json.loads(CFG.read_bytes())
    data["brain_unico"]["entry_policy"] = dict(policy)
    if version:
        data["brain_unico"]["strategy_version"] = version
    return json.dumps(data, indent=2).encode()


# ----------------------------------------------------------------------------- predefiniti = comportamento di prima
def test_defaults_reproduce_the_previous_behaviour():
    assert ep.policy_from_config(None) == ep.DEFAULT and cfg().unico.entry is ep.DEFAULT
    calm = {"open_risk_pct": "0"}
    for p, regime in [(_prop(conf=0.7), "TREND_UP"), (_prop(conf=0.6), "TREND_UP"), (_prop(conf=0.7), "EXPANSION"),
                      (_prop(reasons=("reversal_risk",), conf=0.8), "TREND_UP")]:
        assert entry_triggers(p, regime, calm, ep.DEFAULT) == entry_triggers(p, regime, calm)
    for status in ep.NOT_CONSULTED:
        assert arbitrate_entry(_prop(), ClaudeView(status), "TREND_DOWN", ep.DEFAULT).code == "claude_unavailable_critical"
    assert ep.entry_block(ep.DEFAULT, side=1, entry=D(100), stop=D("99.99"), market=None,
                          roundtrip_cost_bp=D(16)) is None
    assert ep.stop_guard(ep.DEFAULT, side=-1, entry=D(60201), initial_stop=D(60800), new_stop=D(60250),
                         price=D(59950), atr_1h_bp=None, roundtrip_cost_bp=D(16)) is None


def test_config_block_is_strict_and_loads():
    c = load_runner_config(_base_with(version="V2"))
    assert c.unico.entry.long_trend_filter is True and c.unico.base_version == "V2"
    for bad in ({**V2, "extra": 1}, {**V2, "consult_limit_fallback": "open"}, {**V2, "max_cost_fraction_r": "3"}):
        with pytest.raises(ValueError):
            load_runner_config(_base_with(bad))


# ----------------------------------------------------------------------------- 5. LONG solo con trend 1h e 4h
def test_long_needs_trend_on_1h_and_4h_and_short_is_untouched():
    pol = ep.policy_from_config(V2)
    ok = dict(entry=D(100), stop=D(98), roundtrip_cost_bp=D(16))
    assert ep.entry_block(pol, side=1, market=_market(), **ok) is None
    assert ep.entry_block(pol, side=1, market=_market(t4h=(-30, -1)), **ok) == "long_against_trend"
    assert ep.entry_block(pol, side=1, market=_market(t1h=(20, -1)), **ok) == "long_against_trend"   # misto
    assert ep.entry_block(pol, side=1, market=_market(t4h=None), **ok) == "long_trend_unknown"
    assert ep.entry_block(pol, side=-1, market=_market(t4h=(-30, -1)), **ok) is None
    assert ep.entry_block(replace(pol, long_trend_filter=False), side=1, market=_market(t4h=(-30, -1)), **ok) is None


# ----------------------------------------------------------------------------- 4. costi rispetto allo stop
def test_cost_filter_rejects_tiny_stops_and_never_widens_them():
    pol = ep.policy_from_config(V2)                          # costi al massimo 30 % di 1R
    assert ep.cost_fraction(D(100), D("99.5"), D(16)) == D("0.32")           # stop a 50 bp: 16/50
    assert ep.entry_block(pol, side=-1, entry=D(100), stop=D("100.5"), market=None, roundtrip_cost_bp=D(16)) \
        == "cost_too_high_for_stop"
    assert ep.entry_block(pol, side=-1, entry=D(100), stop=D("100.6"), market=None, roundtrip_cost_bp=D(16)) is None


# ----------------------------------------------------------------------------- 1. consulto selettivo e senza Claude
def test_selective_consult_thresholds_by_instrument():
    pol = ep.policy_from_config(V2)
    calm = {"open_risk_pct": "0"}
    assert entry_triggers(_prop("BTCUSDT", conf=0.62), "EXPANSION", calm, pol) == ()        # soglia 0,60, no EXPANSION
    assert entry_triggers(_prop("SOLUSDT", conf=0.62), "TREND_DOWN", calm, pol) == ("uncertainty",)   # soglia 0,70
    assert entry_triggers(_prop("BTCUSDT", conf=0.62, reasons=("reversal_risk",)), "TREND_DOWN", calm, pol) \
        == ("trend_change_or_conflict",)


def test_half_risk_only_when_enabled_and_only_when_claude_did_not_judge():
    pol = replace(ep.policy_from_config(V2), consult_limit_fallback="half_risk")
    assert arbitrate_entry(_prop(conf=0.62), ClaudeView("skipped_limit"), "TREND_DOWN", pol).code \
        == "claude_missing_half_risk"
    assert arbitrate_entry(_prop(conf=0.55), ClaudeView("skipped_limit"), "TREND_DOWN", pol).code \
        == "claude_unavailable_critical"                    # sotto soglia: nessuna apertura
    assert arbitrate_entry(_prop(conf=0.62, uncertain=True), ClaudeView("budget"), "TREND_DOWN", pol).code \
        == "claude_unavailable_critical"
    assert arbitrate_entry(_prop(conf=0.62), ClaudeView("ok", "CONTEST"), "TREND_DOWN", pol).code == "claude_contested"
    assert _scale_in_cap(None, replace(_prop(), risk_scale=0.5), D(2000), D("0.043")) == D("43.000")
    assert _scale_in_cap(D(30), replace(_prop(), risk_scale=0.5), D(2000), D("0.043")) == D(30)


class _Inner(Analyst):
    def __init__(self, prop):
        self.prop = prop

    def analyze(self, context, open_positions):
        return BrainDecision(kind=DecisionKind.OPEN, proposal=self.prop, occurred_at_ms=T0,
                             status=ProposalStatus.DRAFT, rationale="deepseek:analysis", sources=["deepseek:analysis"])


class _Busy:
    """Consulente al limite dei consulti del giro."""
    def start_cycle(self, k):
        pass

    def ask(self, *a, **k):
        return ClaudeView("skipped_limit")


def _collab(tmp_path, prop, pol, market):
    j = EventJournal(str(tmp_path / "journal.db"))
    j.init_schema()
    a = CollaborativeAnalyst(_Inner(prop), _Busy(), journal=j, run_id=RUN, market_view=lambda s, t: market,
                             portfolio_state=lambda: {"open_risk_pct": "0"}, policy=pol, roundtrip_cost_bp=D(16))
    return a, j


def test_analyst_filters_before_any_ai_spend_and_records_why(tmp_path):
    a, j = _collab(tmp_path, _prop("ETHUSDT", side=1, conf=0.8, stop="2900", entry="3000"), ep.policy_from_config(V2),
                   _market(t4h=(-40, -1)))
    d = a.analyze(MarketContext("ETHUSDT", D(3000), T0, "TREND_UP"), [])
    assert d.kind == DecisionKind.NO_TRADE
    rows = [r.event for r in j.list_run("brain", RUN)]
    assert [e.kind for e in rows] == ["entry_filter"] and rows[0].payload["code"] == "long_against_trend"


def test_analyst_half_risk_path_and_veto_by_default(tmp_path):
    prop = _prop("BTCUSDT", conf=0.58, reasons=("conflicting_signals",))
    pol = replace(ep.policy_from_config(V2), consult_limit_fallback="half_risk", consult_conf_tier_a=D("0.55"))
    a, _ = _collab(tmp_path, prop, pol, _market())
    d = a.analyze(MarketContext("BTCUSDT", D(60200), T0, "TREND_DOWN"), [])
    assert d.kind == DecisionKind.OPEN and d.proposal.risk_scale == 0.5
    (tmp_path / "x").mkdir()
    a2, _ = _collab(tmp_path / "x", prop, ep.policy_from_config(V2), _market())        # predefinito: veto
    assert a2.analyze(MarketContext("BTCUSDT", D(60200), T0, "TREND_DOWN"), []).kind == DecisionKind.NO_TRADE


def test_engine_halves_the_risk_and_records_it(tmp_path):
    eng = _engine(tmp_path, cfg().risk_policy)
    prop = OpenProposal("BTCUSDT", 1, D(100), D(98), 20, "deepseek:analysis", .8, "deepseek", "a" * 32)
    full = eng._apply_risk_gate(BrainDecision(kind=DecisionKind.OPEN, proposal=prop, occurred_at_ms=T0,
                                              status=ProposalStatus.DRAFT, rationale="x", sources=["risk:quote"]),
                                MarketContext("BTCUSDT", D(100), T0, "TREND_UP"))
    half = eng._apply_risk_gate(BrainDecision(kind=DecisionKind.OPEN, proposal=replace(prop, risk_scale=0.5),
                                              occurred_at_ms=T0, status=ProposalStatus.DRAFT, rationale="x",
                                              sources=["risk:quote"]),
                                MarketContext("BTCUSDT", D(100), T0, "TREND_UP"))
    assert half.risk_quote.quantity <= full.risk_quote.quantity / 2 + D("0.0001")
    j = EventJournal(str(tmp_path / "j2.db"))
    j.init_schema()
    execute_paper(half, portfolio_id="brain", run_id=RUN, journal=j, now_ms=T0)
    p = j.list_run("brain", RUN)[0].event.payload
    assert p["risk_scale"] == "0.5" and "scale_in_reserved" not in p


# ----------------------------------------------------------------------------- 3. guardia sugli stop (caso BTC)
def test_btc_stop_of_24_11_would_be_refused_and_sound_tightenings_pass():
    pol = ep.policy_from_config(V2)
    btc = dict(side=-1, entry=D("60201.16"), initial_stop=D(60800), price=D(59950), roundtrip_cost_bp=D(16))
    assert ep.stop_guard(pol, new_stop=D(60250), atr_1h_bp=D(108), **btc) == "stop_too_tight_for_volatility"
    assert ep.stop_guard(replace(pol, stop_guard_atr_mult=None), new_stop=D(60250), atr_1h_bp=D(108), **btc) \
        == "stop_in_cost_zone"
    assert ep.stop_guard(pol, new_stop=D(60650), atr_1h_bp=D(108), **btc) is None          # stretto ma lontano
    far = dict(btc, price=D(59200))                                                            # +1,7 R
    assert ep.stop_guard(pol, new_stop=D(60060), atr_1h_bp=D(108), **far) is None             # blocca un profitto
    assert ep.stop_guard(pol, new_stop=D(60650), atr_1h_bp=None, **btc) == "stop_volatility_unknown"


def test_validator_uses_the_policy_of_the_position_version():
    old = _view(side=-1, fill_price=D("60201.16"), initial_stop=D(60800), stop_now=D(60800), legs={"": "a"},
                take_profit_r={"": None})
    new = replace(old, policy=ep.policy_from_config(V2))
    stop = ReviewProposal("MODIFY_STOP", D(60250))
    assert validate(stop, old, D(59950), atr_1h_bp=D(108))[:2] == ("MODIFY_STOP", "stop_tightened")   # versione vecchia
    assert validate(stop, new, D(59950), atr_1h_bp=D(108))[:2] == ("HOLD", "stop_too_tight_for_volatility")
    assert validate(ReviewProposal("MODIFY_STOP", D(60900)), new, D(59950), atr_1h_bp=D(108))[1] == "stop_not_tighter"


# ----------------------------------------------------------------------------- 6. versioni: filtri e politiche AI
def test_versions_carry_entry_policy_and_old_positions_keep_theirs(tmp_path):
    base = _base_with(version="V2")
    j = EventJournal(str(tmp_path / "journal.db"))
    j.init_schema()
    reg = sv.read_registry(j, RUN, base)
    assert reg.active == "V2" and reg.next_name() == "V3"
    eff = sv.effective(base, reg)
    assert eff.snapshot()["entry_policy"]["stop_guard_atr_mult"] == "1"
    d = _hand(side=-1, entry="60200", stop="60800", qty="0.1", margin="200", lev=30, symbol="BTCUSDT", link="brain-req-a")
    execute_paper(d, portfolio_id="brain", run_id=RUN, journal=j, now_ms=T0, strategy=eff.snapshot())
    prop = sv.propose("Nota strategica: prova", reg, base, T0)   # le note non c'entrano: cambio via sovrapposizione
    over = sv.validate_overlay({"brain_unico.entry_policy.stop_guard_atr_mult": None,
                                "brain_unico.entry_policy.long_trend_filter": False})
    raw = sv.apply_overlay(base, over)
    assert load_runner_config(raw).unico.entry.stop_guard_atr_mult is None
    with pytest.raises(sv.StrategyError):
        sv.validate_overlay({"brain_unico.entry_policy.consult_limit_fallback": "always"})
    view = groups_from_journal(j, RUN)[0]
    assert view.policy.stop_guard_atr_mult == D(1)            # la posizione resta sulla V2 anche dopo un cambio
    assert prop.version == "V3"


def test_scale_in_rules_follow_the_position_version():
    from backend.v3.executor.paper_scale import add_price_ok
    args = dict(side=-1, avg_price=D(60200), initial_risk=D(600), stop=D(60800), price=D(60380))   # SHORT: 0,3 R piu in alto
    assert add_price_ok(**args) is True
    assert add_price_ok(**args, min_gap_r=D("0.5")) is False
    from backend.v3.runner.open_serial import _scale_in_rules
    assert _scale_in_rules({"strategy": {"version": "V3", "entry_policy": {**V2, "scale_in_min_gap_r": "0.5"}}}) \
        == {"min_gap_r": D("0.5"), "min_stop_room_r": D("0.3")}
    assert _scale_in_rules({}) == {"min_gap_r": D("0.25"), "min_stop_room_r": D("0.3")}
