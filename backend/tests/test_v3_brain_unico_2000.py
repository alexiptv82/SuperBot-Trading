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
    assert c.exit_policy.take_profit_r == D("3.5") and c.exit_policy.max_hold_ms == 12 * 3_600_000


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

    def review(self, view, *, price, now_ms, mode):
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
                           "confidence": 0.8, "strategy_id": "S25", "strategy_origin": "library"}
            return TransportResponse(200, {"choices": [{"finish_reason": "stop",
                                                        "message": {"content": _json.dumps(content)}}],
                                           "usage": {"prompt_tokens": 2500, "completion_tokens": 60}})

    data_dir = Path(tempfile.mkdtemp())
    config = dataclasses.replace(cfg(), symbols=("BTCUSDT", "ETHUSDT"), **LEGACY)
    model = Model()
    built = build_runner(data_dir=data_dir, run_id="unico-e2e", config=config, get_json=_get_json_factory(),
                         inner_transport=model, view_params=VIEW)
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
