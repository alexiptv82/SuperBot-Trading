"""Brain unico PAPER 2000 (24/11/2026): configurazione schema 3, leva "fit", quote, salvadanaio, livelli di profitto,
stop stretti e chiusure della revisione AI. Le run storiche (schemi 1 e 2) restano coperte dai loro test."""
import json
from dataclasses import replace
from decimal import Decimal as D
from pathlib import Path

import pytest

from backend.v3.brain_f2.analyst import MockDeepSeekAnalyst
from backend.v3.brain_f2.contracts import (BrainDecision, DecisionKind, MarketContext, OpenProposal,
                                           ProposalStatus)
from backend.v3.brain_f2.engine import BrainEngine, BrainPortfolioSnapshot
from backend.v3.brain_f2.reviewer import MockClaudeReviewer
from backend.v3.dashboard import build_summary, open_groups
from backend.v3.events import Event, EventJournal
from backend.v3.executor.paper import execute_paper
from backend.v3.features.indicators import Bar
from backend.v3.guardian import GuardianPolicy, GuardianState, _apply_tiers
from backend.v3.risk import RiskQuote
from backend.v3.runner.config import load_runner_config
from backend.v3.runner.cycle import snapshot_from_summary
from backend.v3.runner.exits import ExitPolicy, evaluate_exit
from backend.v3.runner.manual_close import BRAIN_CHANNEL, run_manual_close
from backend.v3.runner.monitor import run_exit_monitor
from backend.v3.runner.position_review import (GroupView, ReviewProposal, groups_from_journal,
                                               review_open_positions, validate)
from backend.v3.unico import PartialTakeProfit, PiggyPolicy, piggy_bank, split_legs

CFG = Path(__file__).resolve().parents[1] / "v3" / "runner" / "runner_config_brain_unico_2000_paper.json"
T0 = 1_795_500_000_000          # 24/11/2026 ~05:20 UTC
MIN = 60_000


def cfg():
    return load_runner_config(CFG.read_bytes())


# ----------------------------------------------------------------------------- configurazione
def test_config_values_are_the_owner_profile():
    c = cfg()
    p = c.risk_policy
    assert c.initial_equity == D(2000) and len(c.symbols) == 27 and {"XAUUSDT", "XAGUSDT"} <= set(c.symbols)
    assert (p.max_loss_fraction, p.max_open_risk_fraction, p.max_total_margin_fraction) == (D("0.043"), D("0.12"),
                                                                                           D("0.55"))
    assert (p.min_leverage, p.max_leverage, p.max_margin, p.max_positions, p.leverage_fit) == (15, 50, D(400), 10, True)
    assert c.daily_loss_halt == D("0.25") and c.initial_equity * (1 - c.daily_loss_halt) > p.minimum_equity
    assert c.daily_loss_halt < c.guardian.global_drawdown_lock and c.guardian.session_hour == 0
    assert c.unico.partial == PartialTakeProfit(D("0.35"), D("2")) and c.unico.position_review and c.unico.guidance
    assert (c.guardian.tiers.selective_usd, c.guardian.tiers.protect_usd) == (D(300), D(400))
    assert c.unico.piggy == PiggyPolicy(D(2000), "Europe/Rome", 0)
    assert c.exit_policy.take_profit_r == D("3.5") and c.exit_policy.max_hold_ms is None    # nessun limite di tempo
    cl = c.unico.claude
    assert (cl.model, cl.effort, cl.daily_cap_usd, cl.max_per_cycle) == ("claude-opus-5-5", "medium", D(3), 4)


@pytest.mark.parametrize("mutate", [
    lambda d: d.pop("brain_unico"),
    lambda d: d["brain_unico"].update(extra=True),
    lambda d: d["brain_unico"]["piggy_bank"].update(reference_equity="2500"),
    lambda d: d["brain_unico"]["partial_take_profit"].update(fraction="1"),
    lambda d: d["brain_unico"]["profit_tiers"].update(protect_usd="200"),
    lambda d: [d["risk_policy"].pop(k) for k in ("min_margin_usd", "max_margin_usd", "max_positions",
                                                  "max_same_side_risk_fraction")],
    lambda d: d.update(schema_version=2),
])
def test_config_rejects_incomplete_or_incoherent_sections(mutate):
    d = json.loads(CFG.read_bytes())
    mutate(d)
    with pytest.raises(ValueError, match="invalid_config"):
        load_runner_config(json.dumps(d).encode())


# ----------------------------------------------------------------------------- leva "fit"
def _engine(tmp_path, policy):
    j = EventJournal(str(tmp_path / "journal.db"))
    j.init_schema()
    return BrainEngine(MockDeepSeekAnalyst(force_no_trade=True), MockClaudeReviewer(), risk_policy=policy,
                       portfolio_snapshot=BrainPortfolioSnapshot(D(2000), D(2000), D(0), D(0)),
                       market_params={"exchange_leverage_limit": 50, "quantity_step": D(".0001"),
                                      "minimum_notional": D(5), "maintenance_fraction": D(".005"),
                                      "market_data_fresh": True, "paused": False, "daily_loss_latched": False},
                       journal=j, run_id="unico_test")


def _gate(tmp_path, stop, proposed_lev=50):
    prop = OpenProposal("BTCUSDT", 1, D(100), stop, proposed_lev, "sanitized", .8, "deepseek:mock", "a" * 32)
    d = BrainDecision(kind=DecisionKind.OPEN, proposal=prop, occurred_at_ms=T0, status=ProposalStatus.DRAFT,
                      rationale="sanitized", sources=["risk:quote"])
    return _engine(tmp_path, cfg().risk_policy)._apply_risk_gate(d, MarketContext("BTCUSDT", D(100), T0, "TREND_UP"))


@pytest.mark.parametrize("stop,lev,qty,margin_max", [
    (D("98"), 15, D("39.8148"), D("266")),        # stop 2 %: rischio pieno gia' a 15x (la leva minima)
    (D("99.6"), 39, D("153.5714"), D("400")),     # stop 0,4 %: la leva piu' bassa che fa stare 153,57 in 400 USDT
    (D("99.8"), 50, D("200"), D("400")),          # stop 0,2 %: margine al tetto anche a 50x -> 50x, rischio < pieno
])
def test_leverage_fit_is_the_lowest_reaching_full_size(tmp_path, stop, lev, qty, margin_max):
    out = _gate(tmp_path, stop, proposed_lev=50)
    assert out.status == ProposalStatus.APPROVED
    assert out.proposal.leverage == lev and out.risk_quote.quantity == qty
    assert out.risk_quote.margin <= margin_max and out.proposal.stop_price == stop       # lo stop non si stringe mai
    assert out.risk_quote.worst_case_loss_estimate <= D(2000) * D("0.043")


def test_leverage_fit_ignores_the_ai_leverage_and_still_refuses_near_liquidation(tmp_path):
    assert _gate(tmp_path, D("99.6"), proposed_lev=15).proposal.leverage == 39
    out = _gate(tmp_path, D("96"))                 # 4 %: oltre il 60 % della distanza di liquidazione anche a 15x
    assert out.kind == DecisionKind.NO_TRADE and out.status == ProposalStatus.RISK_REJECTED


# ----------------------------------------------------------------------------- quote e aperture divise
def test_split_legs_rounds_to_step_and_falls_back_to_one_position():
    p = PartialTakeProfit(D("0.35"), D("2"))
    legs = split_legs(D("153.5714"), step=D(".0001"), price=D(100), minimum_notional=D(5), partial=p)
    assert legs == (("tp1", D("53.7499"), D("2")), ("runner", D("99.8215"), None))
    assert split_legs(D("0.08"), step=D(".01"), price=D(100), minimum_notional=D(5), partial=p) == (
        ("", D("0.08"), None),)                    # 0,02 x 100 = 2 USDT < 5: posizione unica
    assert split_legs(D(10), step=D(1), price=D(1), minimum_notional=D(5), partial=None) == (("", D(10), None),)


def _journal(tmp_path):
    j = EventJournal(str(tmp_path / "journal.db"))
    j.init_schema()
    return j


def _open(j, *, stop=D("99"), qty=D("10"), legs=True, decision_id="brain_decision.t.1", at=T0, symbol="BTCUSDT"):
    prop = OpenProposal(symbol, 1, D(100), stop, 20, "deepseek:analysis", .8, "deepseek", "a" * 32)
    d = BrainDecision(kind=DecisionKind.OPEN, proposal=prop, occurred_at_ms=at, status=ProposalStatus.APPROVED,
                      rationale="risk_quote_ok", sources=[])
    d.journal_event_id = decision_id
    d.risk_quote = RiskQuote(True, "quote_only", qty, qty * 100, qty * 100 / 20, qty * D("1.16"), D(86))
    lg = split_legs(qty, step=D("0.001"), price=D(100), minimum_notional=D(5),
                    partial=PartialTakeProfit(D("0.35"), D("2")) if legs else None)
    return execute_paper(d, portfolio_id="brain", run_id="r1", journal=j, slippage_bps=0, now_ms=at, legs=lg)


def test_two_legs_are_ordinary_positions_in_one_slot(tmp_path):
    j = _journal(tmp_path)
    receipt = _open(j)
    s = build_summary(j, "brain", "r1")
    assert [(p.leg, p.quantity, p.take_profit_r) for p in s.open_positions] == [("tp1", D("3.5"), D("2")),
                                                                                ("runner", D("6.5"), None)]
    assert receipt.position_id == s.open_positions[0].position_id and open_groups(s.open_positions) == 1
    assert sum(p.margin_used for p in s.open_positions) == D(50)
    snap = snapshot_from_summary(s, D(2000), D(16))
    assert snap.open_positions == 1 and snap.existing_open_risk == D("10") * D("1.16")


def _bars(prices_hl, start):
    return [Bar(start + i * MIN, D(o), D(h), D(l), D(c), D(1)) for i, (o, h, l, c) in enumerate(prices_hl)]


def test_tp1_leg_takes_profit_at_2r_and_runner_stays_open(tmp_path):
    j = _journal(tmp_path)
    _open(j)
    bars = _bars([(100, "100.5", "99.9", "100.4"), ("100.4", "102.1", "100.3", 102)], T0 // MIN * MIN + MIN)
    pol = cfg().exit_policy
    rep = run_exit_monitor(journal=j, portfolio_id="brain", run_id="r1", fetch_bars=lambda s, a, b: bars,
                           policy=pol, fee_bps=D(6), now_ms=bars[-1].open_time_ms + 2 * MIN)
    assert [r for _p, r in rep.closed] == ["take_profit"]
    s = build_summary(j, "brain", "r1")
    assert [p.leg for p in s.open_positions] == ["runner"] and s.realized_pnl > 0


# ----------------------------------------------------------------------------- stop stretti dall'AI
def test_brain_stop_move_only_tightens_and_applies_from_the_next_candle():
    pol = ExitPolicy(D("3.5"), 12 * 3_600_000, D(0))
    bars = _bars([(100, "100.2", "99.6", 100), (100, "100.1", "99.4", 100)], T0)
    kw = dict(side=1, fill_price=D(100), stop_price=D(99), opened_at_ms=T0, bars=bars, candle_ms=MIN, policy=pol)
    assert evaluate_exit(**kw) is None
    hit = evaluate_exit(**kw, stop_moves=((T0 + MIN, D("99.5")),))
    assert (hit.reason, hit.price, hit.stop_kind, hit.bar_open_time_ms) == ("stop", D("99.5"), "brain", T0 + MIN)
    assert evaluate_exit(**kw, stop_moves=((T0, D("98")),)) is None      # piu' largo dello stop: ignorato


def _view(**kw):
    base = dict(group="g", symbol="BTCUSDT", side=1, fill_price=D(100), initial_stop=D(99), stop_now=D(99),
                opened_at_ms=T0, legs={"tp1": "a", "runner": "b"}, take_profit_r={"tp1": D(2), "runner": None})
    base.update(kw)
    return GroupView(**base)


def test_review_validator_allows_only_safe_actions():
    v = _view()
    assert validate(ReviewProposal("CLOSE"), v, D(101)) == ("CLOSE", "close_all_legs", ("a", "b"))
    assert validate(ReviewProposal("PARTIAL_CLOSE"), v, D(101)) == ("PARTIAL_CLOSE", "close_tp1_leg", ("a",))
    assert validate(ReviewProposal("PARTIAL_CLOSE"), _view(legs={"runner": "b"}), D(101))[1] == "partial_not_available"
    assert validate(ReviewProposal("MODIFY_STOP", D("100.2")), v, D(101))[0] == "MODIFY_STOP"
    assert validate(ReviewProposal("MODIFY_STOP", D("98.5")), v, D(101))[1] == "stop_not_tighter"
    assert validate(ReviewProposal("MODIFY_STOP", D("100.98")), v, D(101))[1] == "stop_too_close_to_price"
    short = _view(side=-1, fill_price=D(100), initial_stop=D(101), stop_now=D(101))
    assert validate(ReviewProposal("MODIFY_STOP", D("99.8")), short, D(99))[0] == "MODIFY_STOP"
    assert validate(ReviewProposal("MODIFY_STOP", D("101.5")), short, D(99))[1] == "stop_not_tighter"


class _Reviewer:
    def __init__(self, props):
        self.props = list(props)

    def review(self, view, *, price, now_ms, mode, **kw):
        return self.props.pop(0)


def test_review_round_trip_stop_move_then_ai_close_through_the_exit_channel(tmp_path):
    j = _journal(tmp_path)
    _open(j)
    now = T0 + 30 * MIN
    out = review_open_positions(journal=j, run_id="r1", data_dir=tmp_path, now_ms=now,
                                reviewer=_Reviewer([ReviewProposal("MODIFY_STOP", D("99.7"), .7)]),
                                price_of=lambda s, t: D("100.5"))
    assert [(o.executed, o.code) for o in out] == [("MODIFY_STOP", "stop_tightened")]
    assert groups_from_journal(j, "r1")[0].stop_now == D("99.7")
    out = review_open_positions(journal=j, run_id="r1", data_dir=tmp_path, now_ms=now + 30 * MIN,
                                reviewer=_Reviewer([ReviewProposal("CLOSE")]), price_of=lambda s, t: D("100.5"))
    assert out[0].executed == "CLOSE" and (tmp_path / BRAIN_CHANNEL["request_file"]).is_file()
    rep = run_manual_close(journal=j, portfolio_id="brain", run_id="r1", data_dir=tmp_path,
                           price_of=lambda s, t: D("100.5"), fee_bps=D(6), now_ms=now + 31 * MIN, **BRAIN_CHANNEL)
    assert len(rep.closed) == 2 and not build_summary(j, "brain", "r1").open_positions
    closes = [r.event.payload for r in j.list_run("brain", "r1") if r.event.kind == "paper_close"]
    assert {c["reason"] for c in closes} == {"brain_close"}
    kinds = [r.event.kind for r in j.list_run("brain", "r1")]
    assert kinds.count("position_review") == 2 and kinds.count("stop_move") == 2


def test_review_failure_leaves_the_position_protected(tmp_path):
    from backend.v3.brain_f3.providers import ProviderUnavailable

    class Down:
        def review(self, *a, **k):
            raise ProviderUnavailable("budget_denied")
    j = _journal(tmp_path)
    _open(j)
    out = review_open_positions(journal=j, run_id="r1", data_dir=tmp_path, now_ms=T0 + MIN, reviewer=Down(),
                                price_of=lambda s, t: D(100))
    assert [(o.executed, o.code) for o in out] == [("HOLD", "budget_denied")]
    assert len(build_summary(j, "brain", "r1").open_positions) == 2


# ----------------------------------------------------------------------------- salvadanaio
ROME = PiggyPolicy(D(2000), "Europe/Rome", 0)


def _rome_midnight(day):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    return int(datetime(2026, 11, day, tzinfo=ZoneInfo("Europe/Rome")).timestamp() * 1000)


def test_piggy_bank_sweeps_only_realized_profit_at_midnight_and_never_refills():
    m25, m26, m27 = _rome_midnight(25), _rome_midnight(26), _rome_midnight(27)
    closed = [(m25 - 3_600_000, D(150)), (m25 - 1_800_000, D(-30)),    # 24/11: +120 netti
              (m25 + 3_600_000, D(-200)),                                # 25/11: -200
              (m26 + 3_600_000, D(250))]                                 # 26/11: +250
    s = piggy_bank(closed, initial_equity=D(2000), start_ms=T0, now_ms=m25 - 1, policy=ROME)
    assert (s.total, s.operating_equity, s.next_sweep_ms) == (D(0), D(2120), m25)      # prima di mezzanotte: niente
    s = piggy_bank(closed, initial_equity=D(2000), start_ms=T0, now_ms=m26 - 1, policy=ROME)
    assert (s.total, s.operating_equity, s.sweeps) == (D(120), D(1800), ((m25, D(120)),))   # perdita: nessun reintegro
    s = piggy_bank(closed, initial_equity=D(2000), start_ms=T0, now_ms=m26 + 1, policy=ROME)
    assert (s.total, s.operating_equity) == (D(120), D(1800))          # la mezzanotte dopo la perdita non reintegra
    s = piggy_bank(closed, initial_equity=D(2000), start_ms=T0, now_ms=m27 + 1, policy=ROME)
    assert (s.total, s.operating_equity) == (D(170), D(2000))          # 26/11: 1800+250=2050 -> 50 accantonati
    assert s.operating_equity + s.total == D(2000) + sum(v for _t, v in closed)       # nessun doppio conteggio


def test_snapshot_excludes_the_piggy_bank_from_the_capital_used():
    from backend.v3.dashboard import ClosedTrade, PortfolioSummary
    s = PortfolioSummary("brain", "r1", 0, (), (ClosedTrade("x", "BTCUSDT", D(300), T0),), 0, 0, D(300), D(0), T0)
    assert snapshot_from_summary(s, D(2000), D(16), reserve=D(300)).equity == D(2000)
    with pytest.raises(ValueError):
        snapshot_from_summary(s, D(2000), D(16), reserve=D(-1))


# ----------------------------------------------------------------------------- livelli di profitto
def _gstate(state="NORMAL", realized="0", ai="0", cap=None, conf=None):
    return GuardianState(state=state, reasons=(), session_start_ms=T0, session_start_equity=D(2000),
                         equity=D(2000), realized_session=D(realized), unrealized=D(0), peak_equity=D(2000),
                         giveback=D(0), armed=False, floor=None, open_risk=D(0), budget=None, r_unit=D(86),
                         risk_cap=cap, min_confidence=conf, allow_reentry=True, global_drawdown=D(0),
                         ai_cost_session=D(ai))


def test_profit_tiers_tighten_new_entries_on_net_realized_session_profit():
    pol = replace(GuardianPolicy(session_hour=0), tiers=cfg().guardian.tiers)
    assert _apply_tiers(_gstate(realized="299"), pol).state == "NORMAL"
    g = _apply_tiers(_gstate(realized="302", ai="1"), pol)               # 301 netti: SELETTIVO
    assert (g.state, g.risk_cap, g.min_confidence, g.allow_reentry) == ("SELECTIVE", D("51.6"), D("0.65"), True)
    g = _apply_tiers(_gstate(realized="402", ai="3"), pol)               # 399 netti dopo l'AI: ancora SELETTIVO
    assert g.state == "SELECTIVE"
    g = _apply_tiers(_gstate(realized="450"), pol)
    assert (g.state, g.risk_cap, g.min_confidence, g.allow_reentry) == ("PROTECTED", D("30.10"), D("0.8"), False)
    assert "profit_protect" in g.reasons
    # il vincolo gia' piu' severo resta: tetto e confidenza non si allentano mai
    g = _apply_tiers(_gstate(state="PROTECTED", realized="310", cap=D(10), conf=D("0.9")), pol)
    assert (g.state, g.risk_cap, g.min_confidence) == ("PROTECTED", D(10), D("0.9"))
    assert _apply_tiers(_gstate(realized="999"), GuardianPolicy()).state == "NORMAL"     # senza livelli: invariato


# ----------------------------------------------------------------------------- dashboard
def test_dashboard_counts_one_trade_per_open_and_shows_piggy_and_reviews(tmp_path):
    import shutil
    from backend.v3.compare_view import RunRef, read_run
    from backend.v3.executor.paper_close import close_paper
    shutil.copy(CFG, tmp_path / "runner_config.json")
    j = _journal(tmp_path)
    start = _rome_midnight(24) + 6 * 3_600_000
    _open(j, at=start)                                                  # due quote: un trade
    review_open_positions(journal=j, run_id="r1", data_dir=tmp_path, now_ms=start + 10 * MIN,
                          reviewer=_Reviewer([ReviewProposal("MODIFY_STOP", D("99.5"))]),
                          price_of=lambda s, t: D(101))
    for i, p in enumerate(build_summary(j, "brain", "r1").open_positions):
        close_paper(portfolio_id="brain", run_id="r1", position_id=p.position_id, exit_price=D(102),
                    reason="take_profit", fee_bps=D(6), journal=j, now_ms=start + (20 + i) * MIN)
    _open(j, at=start + 60 * MIN, decision_id="brain_decision.t.2", symbol="ETHUSDT")    # aperto a mezzanotte
    out = read_run(RunRef("brain_scalp", "Brain", tmp_path, "r1"), _rome_midnight(25) + MIN)
    assert out["available"] and out["closed"] == 1 and out["closes"] == 2 and out["wins"] == 1
    assert out["open_trades"] == 1 and {p["leg"] for p in out["open_positions"]} == {"tp1", "runner"}
    realized = D(out["net_pnl"])
    assert D(out["piggy"]["total"]) == realized and D(out["piggy"]["operating_equity"]) == D(2000)
    assert out["reviews"][0]["executed"] == "MODIFY_STOP" and out["config"]["unico"]["partial"]["at_r"] == "2"


# ----------------------------------------------------------------------------- runner cablato (schema 3)
def test_wired_runner_uses_fit_leverage_guidance_portfolio_state_and_reviews_open_positions():
    import dataclasses
    import json as _json
    import tempfile
    from backend.tests.test_v3_runner_e2e import G, LEGACY, VIEW, _get_json_factory
    from backend.v3.brain_f3.providers import TransportResponse
    from backend.v3.runner.wiring import build_runner, mandate_template

    class Model:
        def __init__(self):
            self.payloads = []

        def __call__(self, payload):
            self.payloads.append(_json.loads(_json.dumps(payload)))
            info = _json.loads(payload["messages"][1]["content"])
            if "position" in info:                    # revisione: stringe lo stop di meta' strada verso l'ingresso
                pos = info["position"]
                entry, stop = D(pos["entry"]), D(pos["stop_now"])
                content = {"action": "MODIFY_STOP", "stop_price": str((entry + stop) / 2), "confidence": 0.7}
            else:
                price = D(info["price"])
                long_ = info["symbol"] == "BTCUSDT"
                content = {"kind": "OPEN", "side": 1 if long_ else -1, "entry_price": str(price),
                           "stop_price": str(price * (D("0.99") if long_ else D("1.01"))), "leverage": 3,
                           "confidence": 0.8, "strategy_id": "S25", "strategy_origin": "library",
                           "reasons": ["trend_up" if long_ else "trend_down", "volume_confirms"]}
            return TransportResponse(200, {"choices": [{"finish_reason": "stop",
                                                        "message": {"content": _json.dumps(content)}}],
                                           "usage": {"prompt_tokens": 2500, "completion_tokens": 60}})

    claude_calls = []

    def claude(payload):                                  # Claude finto: conferma, con uso nel formato Anthropic
        claude_calls.append(_json.loads(_json.dumps(payload)))
        return TransportResponse(200, {"stop_reason": "end_turn", "content": [
            {"type": "thinking", "thinking": ""},
            {"type": "text", "text": _json.dumps({"verdict": "CONFIRM", "confidence": 0.7, "reasons": ["trend_up"]})}],
            "usage": {"input_tokens": 3000, "output_tokens": 400}})

    data_dir = Path(tempfile.mkdtemp())
    config = dataclasses.replace(cfg(), symbols=("BTCUSDT", "ETHUSDT"), **LEGACY)
    model = Model()
    built = build_runner(data_dir=data_dir, run_id="unico-e2e", config=config, get_json=_get_json_factory(),
                         inner_transport=model, view_params=VIEW, claude_inner_transport=claude)
    m = mandate_template(config.risk_policy, "unico-e2e")
    m.update(approved=True, approved_by="operator")
    (data_dir / "mandate.json").write_text(_json.dumps(m), encoding="utf-8")
    built.runner.tick(G + 25_000)
    opens = [r.event.payload for r in built.journal.list_run("brain", "unico-e2e") if r.event.kind == "paper_open"]
    assert {o["symbol"] for o in opens} == {"BTCUSDT", "ETHUSDT"}
    assert all(15 <= o["leverage"] <= 50 for o in opens)                  # la leva 3 dell'AI non conta
    sys0 = model.payloads[0]["messages"][0]["content"]
    assert "Operating style" in sys0 and "portfolio" in _json.loads(model.payloads[0]["messages"][1]["content"])
    decisions = [r.event.payload for r in built.journal.list_run("brain", "unico-e2e")
                 if r.event.kind == "brain_decision" and r.event.payload.get("kind") == "OPEN"]
    assert all("risk:leverage_fit" in d["sources"] for d in decisions)
    n = len(model.payloads)
    built.runner.tick(G + 15 * MIN + 25_000)                                      # giro dopo: revisione delle aperte
    reviews = [r.event.payload for r in built.journal.list_run("brain", "unico-e2e") if r.event.kind == "position_review"]
    still_open = build_summary(built.journal, "brain", "unico-e2e").open_positions
    assert len(reviews) == len({p.group for p in still_open}) >= 1
    assert all(r["executed"] == "MODIFY_STOP" for r in reviews) and len(model.payloads) > n
    moves = [r.event.payload for r in built.journal.list_run("brain", "unico-e2e") if r.event.kind == "stop_move"]
    assert {mv["position_id"] for mv in moves} == {p.position_id for p in still_open}
    # collaborazione: ogni OPEN registrata con la proposta DeepSeek; Claude chiamato solo sui criteri; costi separati
    consults = [r.event.payload for r in built.journal.list_run("brain", "unico-e2e") if r.event.kind == "ai_consultation"]
    assert len(consults) == 2 and all(c["deepseek"]["action"] == "OPEN" for c in consults)
    assert {tuple(c["deepseek"]["reasons"]) for c in consults} == {("trend_up", "volume_confirms"),
                                                                    ("trend_down", "volume_confirms")}
    asked = [c for c in consults if c["claude"] is not None]
    assert asked and all(c["code"] == "claude_confirmed" and c["final"]["source"] == "agreed" for c in asked)
    assert all(r["triggers"] and r["claude"]["status"] == "ok" for r in reviews)           # stop spostato: consulto
    assert claude_calls and claude_calls[0]["model"] == "claude-opus-5-5" and claude_calls[0]["fallbacks"] == "default"
    assert built.ledger.daily_spend("claude") == len(claude_calls) * (3000 * 4 + 400 * 20)
    assert built.ledger.daily_spend("deepseek") > 0
    # dashboard: collaborazione e costi separati, dagli stessi journal e registro
    import shutil
    from backend.v3.compare_view import RunRef, read_run
    shutil.copy(CFG, data_dir / "runner_config.json")
    out = read_run(RunRef("brain_scalp", "Brain", data_dir, "unico-e2e"), G + 16 * MIN)
    col = out["collaboration"]
    assert col["entry"]["consults"] == len(asked) and col["entry"]["agreed"] == len(asked)
    assert col["entry"]["deepseek_only"] == 2 - len(asked) and col["review"]["consults"] == len(reviews)
    assert set(out["ai_spend"]["by_provider"]) == {"deepseek", "claude"}
    assert out["reviews"][0]["source"] == "agreed" and out["reviews"][0]["claude"] == "CONFIRM"


def test_claude_unavailable_never_approves_a_decision_that_needed_it(tmp_path):
    import dataclasses
    import json as _json
    from backend.tests.test_v3_runner_e2e import G, LEGACY, VIEW, FakeModel, _get_json_factory
    from backend.v3.brain_f3.providers import ProviderUnavailable
    from backend.v3.runner.wiring import build_runner, mandate_template

    def down(payload):
        raise ProviderUnavailable("provider_unavailable")
    config = dataclasses.replace(cfg(), symbols=("BTCUSDT", "ETHUSDT"), **LEGACY)
    built = build_runner(data_dir=tmp_path, run_id="unico-down", config=config, get_json=_get_json_factory(),
                         inner_transport=FakeModel(), view_params=VIEW, claude_inner_transport=down)
    m = mandate_template(config.risk_policy, "unico-down")
    m.update(approved=True, approved_by="operator")
    (tmp_path / "mandate.json").write_text(_json.dumps(m), encoding="utf-8")
    built.runner.tick(G + 25_000)
    rows = [r.event for r in built.journal.list_run("brain", "unico-down")]
    consults = [e.payload for e in rows if e.kind == "ai_consultation"]
    needed = [c for c in consults if c["triggers"]]
    assert needed and all(c["claude"]["status"] != "ok" and c["code"] == "claude_unavailable_critical"
                          and c["final"]["open"] is False for c in needed)
    opened = {e.payload["symbol"] for e in rows if e.kind == "paper_open"}
    assert opened == {c["symbol"] for c in consults if not c["triggers"]}       # solo le decisioni ordinarie


# ----------------------------------------------------------------------------- collaborazione DeepSeek + Claude
from backend.v3.runner.consult import (ClaudeConsultant, ClaudeView, PositionMetrics, arbitrate_entry,  # noqa: E402
                                       arbitrate_position, entry_triggers, parse_claude, position_triggers)


def _prop(side=1, conf=0.8, reasons=(), uncertain=False):
    return OpenProposal("BTCUSDT", side, D(100), D(99) if side == 1 else D(101), 20, "deepseek:analysis", conf,
                        "deepseek", "h", reasons=reasons, uncertain=uncertain)


def test_entry_triggers_only_in_important_situations():
    calm = {"open_risk_pct": "0", "guardian_mode": "NORMAL"}
    assert entry_triggers(_prop(), "TREND_UP", calm) == ()
    assert entry_triggers(_prop(conf=0.6), "TREND_UP", calm) == ("uncertainty",)
    assert entry_triggers(_prop(uncertain=True), "TREND_UP", calm) == ("uncertainty",)
    assert entry_triggers(_prop(reasons=("conflicting_signals",)), "TREND_UP", calm) == ("trend_change_or_conflict",)
    assert entry_triggers(_prop(), "EXPANSION", calm) == ("trend_change_or_conflict",)
    assert entry_triggers(_prop(), "TREND_UP", {"open_risk_pct": "4.3", "guardian_mode": "NORMAL"}) == ("portfolio_risk",)
    assert entry_triggers(_prop(), "TREND_UP", {"open_risk_pct": "0", "guardian_mode": "PROTECTED"}) == ("guardian_mode",)


def test_entry_arbiter_can_adopt_claude_and_refuses_irreconcilable_or_missing_opinions():
    p = _prop(conf=0.55)
    assert arbitrate_entry(p, None, "TREND_UP").source == "deepseek"
    assert arbitrate_entry(p, ClaudeView("timeout_or_error"), "TREND_UP").code == "claude_unavailable_critical"
    assert arbitrate_entry(p, ClaudeView("ok", "CONFIRM"), "TREND_UP").source == "agreed"
    assert arbitrate_entry(p, ClaudeView("ok", "CONTEST"), "TREND_UP").open is False
    v = arbitrate_entry(p, ClaudeView("ok", "ALTERNATIVE", side=1, stop_price=D("99.4")), "TREND_UP")
    assert (v.open, v.stop, v.code) == (True, D("99.4"), "claude_stop_adopted")
    short = ClaudeView("ok", "ALTERNATIVE", side=-1, stop_price=D("100.8"), confidence=0.8)
    assert arbitrate_entry(p, short, "TREND_DOWN").code == "claude_alternative_adopted"          # numeri a favore
    assert arbitrate_entry(p, short, "TREND_UP").code == "irreconcilable_no_trade"               # regime contrario
    assert arbitrate_entry(_prop(conf=0.8), short, "TREND_DOWN").code == "irreconcilable_no_trade"


def _m(r="0.5", roe="5", mfe=None, give=None, entry="TREND_UP", now="TREND_UP"):
    return PositionMetrics(D(r), D(roe), None if mfe is None else D(mfe), None if give is None else D(give), entry, now)


def test_position_triggers_and_no_time_based_trigger():
    assert position_triggers("HOLD", False, _m()) == ()                  # durata mai un criterio
    assert position_triggers("CLOSE", False, _m()) == ("action_proposed",)
    assert position_triggers("HOLD", False, _m(r="1.6")) == ("interesting_profit",)
    assert position_triggers("HOLD", False, _m(roe="21")) == ("interesting_profit",)
    assert position_triggers("HOLD", False, _m(r="0.9", mfe="2", give="0.55")) == ("profit_given_back",)
    assert position_triggers("HOLD", False, _m(now="TREND_DOWN")) == ("trend_change",)


def test_position_arbiter_weighs_both_views_with_numbers_and_is_prudent_when_claude_is_missing():
    m = _m(r="0.9", mfe="2.4", give="0.62")
    assert arbitrate_position("HOLD", None, 0.6, None, m).source == "deepseek"
    for status in ("budget", "timeout_or_error", "invalid", "skipped_limit", "unavailable"):
        for act, stop in (("CLOSE", None), ("PARTIAL_CLOSE", None), ("MODIFY_STOP", D("100.5"))):
            v = arbitrate_position(act, stop, 0.8, ClaudeView(status), m)   # riduce il rischio: si esegue senza Claude
            assert (v.action, v.stop, v.source, v.code) == (act, stop, "deepseek", "claude_unavailable_risk_reducing")
        assert arbitrate_position("HOLD", None, 0.8, ClaudeView(status), m).code == "claude_unavailable_hold"
    claude_close = ClaudeView("ok", "CONTEST", action="CLOSE", confidence=0.6)
    v = arbitrate_position("HOLD", None, 0.7, claude_close, m)          # profitto restituito: i numeri danno ragione
    assert (v.action, v.source) == ("CLOSE", "claude")
    hold = ClaudeView("ok", "CONTEST", action="HOLD", confidence=0.6)
    v = arbitrate_position("CLOSE", None, 0.7, hold, _m(r="2"))            # +2R, trend intatto: proseguire
    assert (v.action, v.source) == ("HOLD", "claude")
    v = arbitrate_position("CLOSE", None, 0.9, hold, _m(r="2"))            # DeepSeek molto piu' convinto
    assert (v.action, v.source) == ("CLOSE", "deepseek")
    v = arbitrate_position("HOLD", None, 0.6, ClaudeView("ok", "CONTEST", action="HOLD"), m)
    assert v.source == "agreed"
    v = arbitrate_position("MODIFY_STOP", D("100.2"), 0.6, ClaudeView("ok", "CONTEST", action="MODIFY_STOP",
                                                                       stop_price=D("100.5")), m, side=1)
    assert (v.action, v.stop) == ("MODIFY_STOP", D("100.5"))                                     # il piu' stretto


def test_claude_answers_are_parsed_strictly_and_calls_are_limited():
    assert parse_claude({"verdict": "CONFIRM", "confidence": 0.7, "reasons": ["trend_up"]}, position=False).status == "ok"
    for bad in ({"verdict": "MAYBE"}, {"verdict": "ALTERNATIVE", "side": 2, "stop_price": "1"},
                {"verdict": "CONFIRM", "reasons": ["free text"]}, {"verdict": "CONFIRM", "note": "x"},
                {"verdict": "CONTEST", "action": "MODIFY_STOP"}):
        with pytest.raises(ValueError):
            parse_claude(bad, position="action" in bad)
    calls = []

    def ok(payload):
        from backend.v3.brain_f3.providers import TransportResponse
        calls.append(payload)
        return TransportResponse(200, {"stop_reason": "end_turn", "content": [
            {"type": "text", "text": '{"verdict":"CONFIRM"}'}]})
    c = ClaudeConsultant(transport=ok, model="claude-opus-5-5", effort="medium", max_tokens=8000,
                         spending_gate=lambda p: True, max_per_cycle=2, cooldown_ms=120 * MIN)
    c.start_cycle(1)
    assert [c.ask("s", {}, key=k, now_ms=T0, position=False).status for k in "abc"] == ["ok", "ok", "skipped_limit"]
    assert c.cooling("a", T0 + MIN) and not c.cooling("a", T0 + 121 * MIN) and len(calls) == 2
    assert calls[0]["thinking"] == {"type": "adaptive"} and calls[0]["output_config"] == {"effort": "medium"}
    refused = ClaudeConsultant(transport=ok, model="claude-opus-5-5", effort="medium", max_tokens=8000,
                               spending_gate=lambda p: False, max_per_cycle=2, cooldown_ms=0)
    assert refused.ask("s", {}, key="z", now_ms=T0, position=False).status == "budget" and len(calls) == 2


def test_no_time_limit_exit_policy_and_long_positions_use_a_window_plus_history(tmp_path):
    pol = cfg().exit_policy
    bars = _bars([(100, "100.2", "99.8", 100)] * 3, T0)
    assert evaluate_exit(side=1, fill_price=D(100), stop_price=D(99), opened_at_ms=T0 - 30 * 24 * 3_600_000,
                         bars=bars, candle_ms=MIN, policy=pol) is None          # 30 giorni: nessuna chiusura per tempo
    j = _journal(tmp_path)
    _open(j, at=T0)
    now = T0 + 30 * 3_600_000                                             # 30 ore: oltre la finestra da 1 minuto
    seen = {}

    def fetch(symbol, start, end):
        seen["start"] = start
        return [Bar(t, D(101), D(101), D("100.9"), D(101), D(1)) for t in range(start, end, MIN)]
    kw = dict(journal=j, portfolio_id="brain", run_id="r1", fetch_bars=fetch, policy=pol, fee_bps=D(6), now_ms=now,
              window_ms=20 * 60 * MIN)
    rep = run_exit_monitor(**kw, history_best=lambda *a: None)
    assert {e for _p, e in rep.errors} == {"exit_history_unavailable"} and rep.closed == ()   # segnalato, non chiuso
    assert seen["start"] == now // MIN * MIN - 20 * 60 * MIN
    rep = run_exit_monitor(**kw, history_best=lambda s, side, o, u: D("101.5"))   # +1,5R prima: nessuna protezione
    assert rep.errors == () and rep.closed == ()
    rep = run_exit_monitor(**kw, history_best=lambda s, side, o, u: D("102.6"))   # +2,6R prima: trailing a 101,6
    assert sorted(r for _p, r in rep.closed) == ["stop", "stop"] and rep.errors == ()
    kinds = {r.event.payload.get("stop_kind") for r in j.list_run("brain", "r1") if r.event.kind == "paper_close"}
    assert kinds == {"trailing"}                     # la storia prima della finestra conta: il profitto e' protetto


def test_claude_over_its_daily_cap_never_blocks_risk_reducing_exits(tmp_path):
    """Tetto di 3 USD raggiunto (gate negato): la chiusura proposta da DeepSeek passa e va al servizio delle uscite;
    il journal dice che il consulto era richiesto ma non disponibile; uno stop PIU' LARGO resta rifiutato; una nuova
    apertura che richiedeva Claude resta NO_TRADE."""
    j = _journal(tmp_path)
    _open(j)
    over_cap = ClaudeConsultant(transport=lambda p: (_ for _ in ()).throw(AssertionError("nessuna chiamata")),
                                model="claude-opus-5-5", effort="medium", max_tokens=8000,
                                spending_gate=lambda provider: False, max_per_cycle=4, cooldown_ms=0)
    now = T0 + 30 * MIN
    out = review_open_positions(journal=j, run_id="r1", data_dir=tmp_path, now_ms=now, consultant=over_cap,
                                reviewer=_Reviewer([ReviewProposal("CLOSE", None, 0.7)]), price_of=lambda s, t: D("100.5"))
    assert [(o.executed, o.code) for o in out] == [("CLOSE", "close_all_legs")]
    assert (tmp_path / BRAIN_CHANNEL["request_file"]).is_file()
    rev = [r.event.payload for r in j.list_run("brain", "r1") if r.event.kind == "position_review"][-1]
    assert rev["claude"]["status"] == "budget" and rev["claude_required_unavailable"] is True
    assert rev["arbiter"] == "claude_unavailable_risk_reducing" and rev["triggers"] == ["action_proposed"]
    rep = run_manual_close(journal=j, portfolio_id="brain", run_id="r1", data_dir=tmp_path,
                           price_of=lambda s, t: D("100.5"), fee_bps=D(6), now_ms=now + MIN, **BRAIN_CHANNEL)
    assert len(rep.closed) == 2 and not build_summary(j, "brain", "r1").open_positions
    # stop piu' largo senza Claude: il validatore lo rifiuta comunque
    j2 = _journal(tmp_path / "b") if (tmp_path / "b").mkdir() is None else None
    _open(j2)
    out = review_open_positions(journal=j2, run_id="r1", data_dir=tmp_path / "b", now_ms=now, consultant=over_cap,
                                reviewer=_Reviewer([ReviewProposal("MODIFY_STOP", D("98.5"), 0.7)]),
                                price_of=lambda s, t: D("100.5"))
    assert [(o.executed, o.code) for o in out] == [("HOLD", "stop_not_tighter")]
    assert not [r for r in j2.list_run("brain", "r1") if r.event.kind == "stop_move"]
    # nuova apertura critica senza Claude: mai autorizzata
    assert arbitrate_entry(_prop(conf=0.5), ClaudeView("budget"), "TREND_UP").open is False


# ----------------------------------------------------------------------------- verifica reale dell'API di Claude
def _resp(body, code=200):
    from backend.v3.brain_f3.providers import TransportResponse
    return TransportResponse(code, body)


GOOD = {"stop_reason": "end_turn", "content": [{"type": "thinking", "thinking": ""},
        {"type": "text", "text": '{"verdict":"CONTEST","confidence":0.6,"reasons":["setup_weak"]}'}],
        "usage": {"input_tokens": 2100, "output_tokens": 350}}


def test_claude_check_sends_the_brain_request_and_checks_http_format_and_tokens():
    from backend.v3.runner.claude_check import verify
    from backend.v3.runner.consult import ENTRY_PROMPT, consult_payload
    seen = []
    ok, code, det = verify(cfg(), key="sk-prova", transport=lambda p: seen.append(p) or _resp(GOOD))
    cp = cfg().unico.claude
    assert (ok, code, det["verdetto"], det["token_ingresso"], det["costo_usd"]) == (True, "DISPONIBILE", "CONTEST",
                                                                                    2100, "0.0154")
    sent = seen[0]
    assert {k: v for k, v in sent.items() if k != "messages"} == {
        k: v for k, v in consult_payload(cp.model, cp.effort, cp.max_tokens, ENTRY_PROMPT, {}).items() if k != "messages"}
    assert sent["model"] == "claude-opus-5-5" and sent["fallbacks"] == "default"
    for body, want in (({**GOOD, "stop_reason": "refusal"}, "RIFIUTO_DEL_MODELLO"),
                       ({**GOOD, "content": [{"type": "text", "text": "va bene"}]}, "FORMATO_DELLA_DECISIONE"),
                       ({**GOOD, "stop_reason": "max_tokens"}, "FORMATO_DELLA_DECISIONE"),
                       ({k: v for k, v in GOOD.items() if k != "usage"}, "TOKEN_NON_LEGGIBILI")):
        assert verify(cfg(), key="sk-prova", transport=lambda p, b=body: _resp(b))[:2] == (False, want)
    assert verify(cfg(), key="", transport=lambda p: _resp(GOOD))[:2] == (False, "CHIAVE_ASSENTE")
    assert verify(cfg(), key="sk", transport=lambda p: (_ for _ in ()).throw(OSError()))[:2] == (False, "HTTP_O_RETE")


def test_claude_check_reads_the_service_env_file_and_never_prints_the_key(tmp_path, monkeypatch, capsys):
    import backend.v3.transport as tr
    from backend.v3.runner import claude_check
    env = tmp_path / "brain-ai.env"
    env.write_text("DEEPSEEK_API_KEY=ds-segreta\nANTHROPIC_API_KEY=sk-ant-SEGRETISSIMA\n")
    assert claude_check.read_key(env) == "sk-ant-SEGRETISSIMA" and claude_check.read_key(tmp_path / "no") == ""
    monkeypatch.setattr(tr, "claude_transport", lambda **kw: (lambda p: _resp(GOOD)))
    assert claude_check.main(["--config", str(CFG), "--env-file", str(env)]) == 0
    out = capsys.readouterr().out
    assert out.startswith("CLAUDE_API=DISPONIBILE") and "SEGRETISSIMA" not in out and "ds-segreta" not in out
    env.write_text("DEEPSEEK_API_KEY=ds\n")
    assert claude_check.main(["--config", str(CFG), "--env-file", str(env)]) == 1
    assert capsys.readouterr().out.strip() == "CLAUDE_API=CHIAVE_ASSENTE"


# ----------------------------------------------------------------------------- notifiche Telegram (solo informative)
def test_telegram_feed_one_message_per_event_from_the_journal_only(tmp_path):
    from backend.v3.executor.paper_close import close_paper
    from backend.v3.runner.telegram_feed import JournalNotifier
    j = _journal(tmp_path)
    sent = []
    start = _rome_midnight(24) + 6 * 3_600_000
    mk = lambda: JournalNotifier(journal=j, run_id="r1", data_dir=tmp_path, send=lambda t: sent.append(t) or True,  # noqa: E731
                                 initial_equity=D(2000), piggy_policy=cfg().unico.piggy, default_tp_r=D("3.5"))
    n = mk()
    assert n.poll(start) == [sent[-1]] and "notifiche Telegram attive" in sent[-1]       # nessuno storico
    _open(j, at=start + MIN)
    msgs = n.poll(start + 2 * MIN)
    assert len(msgs) == 1 and "Apertura LONG BTC · 2 quote" in msgs[0] and "TP 2R a 102" in msgs[0] \
        and "TP 3.5R a 103.5" in msgs[0]
    a, b = [p.position_id for p in build_summary(j, "brain", "r1").open_positions]
    close_paper(portfolio_id="brain", run_id="r1", position_id=a, exit_price=D(102), reason="take_profit",
                fee_bps=D(6), journal=j, now_ms=start + 10 * MIN)
    msgs = n.poll(start + 11 * MIN)
    assert len(msgs) == 1 and msgs[0].startswith("✅ Chiusura parziale LONG BTC · take profit") and "resta aperta" in msgs[0]
    close_paper(portfolio_id="brain", run_id="r1", position_id=b, exit_price=D("101.5"), reason="stop", fee_bps=D(6),
                journal=j, now_ms=start + 20 * MIN, stop_kind="trailing")
    j.append(Event("g1", "brain", "r1", "guardian_state", start + 21 * MIN, "t", {"state": "NORMAL", "reasons": []}))
    j.append(Event("g2", "brain", "r1", "guardian_state", start + 22 * MIN, "t",
                   {"state": "SELECTIVE", "reasons": ["profit_selective"]}))
    msgs = n.poll(start + 23 * MIN)
    assert msgs[0].startswith("✅ Chiusura totale LONG BTC · trailing stop")
    assert msgs[1] == "🛡️ Guardian: modalità SELETTIVO (profit_selective)" and len(msgs) == 2
    assert n.poll(start + 24 * MIN) == [] and mk().poll(start + 25 * MIN) == []           # nessun doppione, anche al riavvio
    _open(j, at=start + 30 * MIN, decision_id="brain_decision.t.2", symbol="ETHUSDT")
    ids = [p.position_id for p in build_summary(j, "brain", "r1").open_positions]
    for pid in ids:                                                       # chiusura manuale di entrambe le quote
        close_paper(portfolio_id="brain", run_id="r1", position_id=pid, exit_price=D(99), reason="manual",
                    fee_bps=D(6), journal=j, now_ms=start + 40 * MIN)
    msgs = n.poll(start + 41 * MIN)
    assert [m.split(" · ")[1] for m in msgs[1:]] == ["chiusura manuale (operatore)"] and "Chiusura totale" in msgs[1]
    report = n.poll(_rome_midnight(25) + MIN)                             # mezzanotte: report con salvadanaio
    assert len(report) == 1 and report[0].startswith("📊 Report 2026-11-24") and "trade chiusi 2" in report[0]
    assert "salvadanaio" in report[0] and "capitale operativo 2000.00" in report[0]
    assert n.poll(_rome_midnight(25) + 2 * MIN) == []


def test_telegram_problems_never_stop_anything(tmp_path):
    from backend.v3.runner.telegram_feed import JournalNotifier, start_thread
    j = _journal(tmp_path)

    def broken(text):
        raise OSError("rete")
    n = JournalNotifier(journal=j, run_id="r1", data_dir=tmp_path, send=broken, initial_equity=D(2000))
    with pytest.raises(OSError):
        n.poll(T0)                                                        # primo messaggio: l'errore resta nel thread
    _open(j, at=T0 + MIN)
    assert len(n.poll(T0 + 2 * MIN)) == 1 and n.poll(T0 + 3 * MIN) == []   # stato salvato, nessuna ripetizione
    import threading
    stop = threading.Event()
    t = start_thread(lambda: (_ for _ in ()).throw(RuntimeError("journal")), lambda: T0, every_s=0.01, stop=stop)
    t.join(1)
    assert not t.is_alive()                                               # il thread esce in silenzio
    stop.set()


def test_telegram_check_reuses_the_old_bot_credentials_sends_one_test_and_prints_no_secret(tmp_path, capsys):
    from backend.v3.runner import telegram_check as tc

    class Resp:
        def __init__(self, status):
            self.status = status

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False
    calls = []
    ok = lambda req, timeout: calls.append(req) or Resp(200)          # noqa: E731
    env = tmp_path / "brain-ai.env"
    env.write_text("DEEPSEEK_API_KEY=ds\nTELEGRAM_BOT_TOKEN=123:SEGRETO\nTELEGRAM_CHAT_ID=999\n")
    assert tc.main(["--env-file", str(env)], opener=ok) == 0
    out = capsys.readouterr().out
    assert out.strip() == "TELEGRAM=ACCETTATO fonte=file" and len(calls) == 1 and "SEGRETO" not in out
    assert b"prova delle notifiche" in calls[0].data
    # credenziali assenti nel file: recuperate dall'ambiente del container della web, copia di riserva del file
    env.write_text("DEEPSEEK_API_KEY=ds\n")
    docker = tmp_path / "docker"
    docker.write_text('#!/bin/sh\n[ "$4" = superbot ] && echo \'["A=1","TELEGRAM_BOT_TOKEN=456:SEGRETO2","TELEGRAM_CHAT_ID=77"]\' '
                      '|| exit 1\n')
    docker.chmod(0o755)
    assert tc.main(["--env-file", str(env), "--docker", str(docker)], opener=ok) == 0
    out = capsys.readouterr().out
    assert out.strip() == "TELEGRAM=ACCETTATO fonte=superbot" and "SEGRETO2" not in out
    assert tc.read_env(env) == {"TELEGRAM_BOT_TOKEN": "456:SEGRETO2", "TELEGRAM_CHAT_ID": "77"}
    assert "DEEPSEEK_API_KEY=ds" in env.read_text() and list(tmp_path.glob("brain-ai.env.prima-telegram-*"))
    # Telegram rifiuta o non risponde: segnalato, mai bloccante
    assert tc.main(["--env-file", str(env)], opener=lambda r, timeout: Resp(401)) == 0
    assert capsys.readouterr().out.strip() == "TELEGRAM=NON_ACCETTATO fonte=file"
    env.write_text("X=1\n")
    assert tc.main(["--env-file", str(env), "--docker", "/bin/false"], opener=ok) == 0
    assert capsys.readouterr().out.strip() == "TELEGRAM=NON_CONFIGURATO fonte=nessuna"
