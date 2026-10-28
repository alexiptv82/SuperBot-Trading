"""PAPER-only arbitration and lifecycle cashflow regression. No network."""
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
import json
import pytest
from desk import classic_opportunities as policy, cli
from desk.engine import PaperAccount, Limits

T = 1_800_000_000_000


def entry(symbol="BTC", action="open_long", **kw):
    return dict(symbol=symbol, action=action, confidence=85, leverage=25,
                margin_usd=150, stop_loss_pct=.004, take_profit_pct=.008,
                reason="synthetic valid opportunity", **kw)


@pytest.mark.parametrize("reply", [[], [{"symbol": "BTC", "action": "hold"}]])
def test_empty_or_flat_hold_never_disables_technical_candidates(reply):
    rules = [entry(), entry("ETH")]
    out, audit = policy.combine(rules, reply, set())
    assert [d["symbol"] for d in out] == ["BTC", "ETH"]
    assert all(d["_decision_source"] == "rules" for d in out)
    assert audit["rule_proposals"] == 2


def test_veto_is_per_symbol_and_review_veto_cannot_be_reopened_by_rules():
    rules = [entry(), entry("ETH")]
    out, _ = policy.combine(rules, [{"symbol": "BTC", "action": "skip"}], set())
    assert [d["symbol"] for d in out] == ["ETH"]
    out, _ = policy.combine(rules, [], set(), vetoes=["BTC"])
    assert [d["symbol"] for d in out] == ["ETH"]


def test_ai_entry_owns_symbol_even_if_undersized_no_risk_upscaling():
    ai = entry(); ai["margin_usd"] = 60
    out, _ = policy.combine([entry()], [ai], set())
    assert len(out) == 1 and out[0]["margin_usd"] == 60
    assert out[0]["_decision_source"] == "deepseek"
    a = PaperAccount(cli._make_hawk_config().limits)
    p, why = a.open("BTC", 1, 60, 25, 100, 99, 102, T, {})
    assert p is None and "minimo" in why and a.cash == 1000


def test_existing_position_hold_overrides_only_its_rule_close():
    rules = [{"symbol": "BTC", "action": "close"}, entry("ETH")]
    out, _ = policy.combine(rules, [{"symbol": "BTC", "action": "hold"}], {"BTC"})
    assert {d["symbol"]: d["action"] for d in out} == {"BTC": "hold", "ETH": "open_long"}


def account(side=1, margin=100, leverage=20):
    a = PaperAccount(Limits())
    p, why = a.open("BTC", side, margin, leverage, 100, 100-side, 100+side*10,
                    T, {}, trade_type="scalp")
    assert p, why
    a.limits = cli._make_hawk_config().limits
    return a, p


def manage(a, state, price, now=T+1000, action="hold", own=85, opposite=10, **kw):
    side = a.positions["BTC"].side
    r = SimpleNamespace(long_score=own if side==1 else opposite,
                        short_score=own if side==-1 else opposite)
    decision = dict(symbol="BTC", action=action, _decision_source="deepseek", **kw)
    return policy.manage(a, {"BTC": price}, {"BTC": r}, [decision], state, now, cli.tier_entry_score)


@pytest.mark.parametrize("side", [1, -1])
def test_net_profit_lock_matches_independent_engine_cashflow(side):
    a, p = account(side)
    state = {}
    out, events = manage(a, state, 100+side*2)
    event = next(e for e in events if e["ev"] == "profit_lock")
    assert p.side*(p.sl-(100-side)) > 0
    copy = PaperAccount.from_dict(deepcopy(a.to_dict()))
    rec = copy.close("BTC", p.sl, T+1000)
    assert rec["net"] == pytest.approx(event["net_lock_estimate"], abs=.0001)
    assert out[0]["action"] == "hold"
    stop = p.sl
    manage(a, state, 100+side*1.8)
    assert p.sl == stop  # a lower peak must never loosen the stop


def test_lock_accounts_for_partials_and_never_uses_candle_extreme_as_net_peak():
    a, p = account()
    p.px_hi = 10000
    state = {}
    _, events = manage(a, state, 100.1)
    assert not events
    partial = a.partial_close("BTC", 102, T+500, .35)
    out, events = manage(a, state, 102)
    event = next(e for e in events if e["ev"] == "profit_lock")
    clone = PaperAccount.from_dict(deepcopy(a.to_dict()))
    final = clone.close("BTC", p.sl, T+1000)
    assert partial["net"] + final["net"] == pytest.approx(event["net_lock_estimate"], abs=.0002)


def test_indecisive_adviser_and_weakening_setup_take_positive_net():
    a, p = account()
    out, _ = manage(a, {}, 102, own=55)
    assert out[0]["action"] == "close"
    assert "salva profitto" in out[0]["close_why"]


def test_time_budget_closes_even_when_net_is_negative():
    a, _ = account()
    out, _ = manage(a, {}, 99.8, now=T+policy.DAY_MS)
    assert out[0]["action"] == "close"
    assert "tempo massimo" in out[0]["reason"]


def test_one_justified_extension_survives_restart_but_never_exceeds_48h():
    a, _ = account()
    state = {}
    out, events = manage(a, state, 100.5, now=T+policy.DAY_MS,
                         hold_extension_hours=24, reason="Trend forte e confermato con netto ancora positivo")
    assert out[0]["action"] == "hold" and any(e["ev"] == "scalp_extension" for e in events)
    restarted = json.loads(json.dumps(state))
    out, _ = manage(a, restarted, 100.5, now=T+2*policy.DAY_MS,
                    hold_extension_hours=24, reason="Una seconda estensione non deve essere concessa")
    assert out[0]["action"] == "close"


@pytest.mark.parametrize("kwargs", [
    dict(hold_extension_hours=24, reason="short"),
    dict(hold_extension_hours=25, reason="Motivazione lunga ma durata oltre il consentito"),
    dict(hold_extension_hours=float("nan"), reason="Motivazione lunga ma valore non valido"),
    dict(hold_extension_hours=24, reason="Motivazione presente ma setup debole", own=40),
])
def test_invalid_extension_never_keeps_expired_position(kwargs):
    a, _ = account()
    out, _ = manage(a, {}, 100.5, now=T+policy.DAY_MS, **kwargs)
    assert out[0]["action"] == "close"


def test_legacy_small_position_remains_manageable_and_missing_quote_never_invents_close():
    a, p = account(margin=50, leverage=10)
    out, _ = manage(a, {}, 100.1)
    assert out[0]["action"] == "hold" and p.margin == 50 and p.leverage == 10
    decisions, events = policy.manage(a, {}, {}, [], {}, T+3*policy.DAY_MS, cli.tier_entry_score)
    assert decisions == [] and events == [] and "BTC" in a.positions


@pytest.mark.parametrize("reply,expected", [( [], {"BTC", "ETH"}),
    ([{"symbol":"BTC","action":"skip"}], {"ETH"}),
    ([{"symbol":"BTC","action":"hold"}], {"BTC", "ETH"}),
    ([dict(entry(), margin_usd=60)], {"ETH"})])
def test_real_cycle_combines_rules_and_deepseek(reply, expected, monkeypatch):
    from test_desk import _sandbox, NOW
    from desk.signals import Reading
    monkeypatch.setattr(cli, "SYMBOLS", ["BTC", "ETH"])
    monkeypatch.setattr(cli.time, "sleep", lambda _: None)
    monkeypatch.setattr(cli, "read_symbol", lambda sym,*a,**k: Reading(
        sym, 100, side=1, score=85, long_score=85, short_score=10,
        sl_pct=.004, tp_pct=.008, trade_type="scalp", why=["synthetic breakout"]))
    monkeypatch.setattr(cli, "four_hour_bars", lambda *a: None)
    monkeypatch.setattr(cli._ds, "configured", lambda: True)
    monkeypatch.setattr(cli._ds, "in_window", lambda *a: True)
    monkeypatch.setattr(cli._ds, "reserve", lambda *a,**k: True)
    monkeypatch.setattr(cli._ds, "settle", lambda *a,**k: 0)
    monkeypatch.setattr(cli._ds, "call", lambda *a,**k: (json.dumps({"decisions":reply}), {}))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "synthetic-not-real")
    with _sandbox() as (directory, calls):
        state = {}
        cli.run_cycle(state, NOW)
        a = cli.make_account(state)
        assert set(a.positions) == expected
        assert state["last_opportunity_cycle"]["rule_eligible"] == 2
        assert all(p.source == "rules" for p in a.positions.values())
