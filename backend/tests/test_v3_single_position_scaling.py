"""Posizione unica con ingresso progressivo e chiusure parziali (correzione del proprietario, 24/11/2026).

Verifica: una sola posizione all'ingresso; eventuale secondo ingresso a un prezzo diverso e migliore; rischio totale
entro i limiti gia' approvati (stop mai allargato); chiusure parziali senza doppio conteggio (quantita', margine,
commissioni, P&L, rischio, salvadanaio); dashboard, esiti e Telegram coerenti. Le posizioni a due quote aperte prima
restano gestite come prima (coperte da test_v3_brain_unico_2000)."""
from dataclasses import replace
from decimal import Decimal as D
from pathlib import Path

import pytest

from backend.tests.test_brain_f7_outcomes import _hand
from backend.tests.test_v3_brain_unico_2000 import CFG, MIN, T0, _bars, _rome_midnight, cfg
from backend.v3.dashboard import build_summary
from backend.v3.events import EventJournal
from backend.v3.executor.paper import ExecutionError, execute_paper
from backend.v3.executor.paper_close import close_paper
from backend.v3.executor.paper_scale import (add_price_ok, add_quantity, expand_scaled, position_state,
                                             reduce_paper)
from backend.v3.runner.exit_service import ExitService
from backend.v3.runner.monitor import MonitorReport, run_exit_monitor
from backend.v3.runner.open_serial import commit_paper_add

RUN = "r1"
RULES = {"exchange_leverage_limit": 50, "quantity_step": D("0.001"), "minimum_notional": D(5),
         "maintenance_fraction": D("0.005")}


def _journal(tmp_path):
    j = EventJournal(str(tmp_path / "journal.db"))
    j.init_schema()
    return j


def _short_btc(j, *, reserve=True, qty="0.080", margin="160", at=T0):
    """SHORT BTC a 60.200, stop 60.800 (rischio iniziale 600 per BTC), 30x: come il trade del 24/11 ma UNA posizione."""
    d = _hand(side=-1, entry="60200", stop="60800", qty=qty, margin=margin, lev=30, symbol="BTCUSDT",
              link="brain-req-0001")
    if reserve:
        d.proposal = replace(d.proposal, risk_fraction=0.65)
    return execute_paper(d, portfolio_id="brain", run_id=RUN, journal=j, now_ms=at).position_id


def _kinds(j):
    return [r.event.kind for r in j.list_run("brain", RUN)]


# ----------------------------------------------------------------------------- 1. una sola posizione all'ingresso
def test_new_openings_are_one_position_and_the_wiring_never_splits_them(tmp_path):
    j = _journal(tmp_path)
    _short_btc(j)
    assert _kinds(j) == ["paper_open"]
    p = j.list_run("brain", RUN)[0].event.payload
    assert "leg" not in p and p["scale_in_reserved"] is True
    src = (Path(__file__).resolve().parents[1] / "v3" / "runner" / "wiring.py").read_text()
    assert "split_legs" not in src and "partial=None)" in src          # nessuna quota automatica nel percorso reale


def test_scale_in_first_entry_uses_only_part_of_the_same_risk_budget(tmp_path):
    from backend.tests.test_v3_brain_unico_2000 import _engine
    from backend.v3.brain_f2.contracts import BrainDecision, DecisionKind, MarketContext, OpenProposal, ProposalStatus

    def gate(fraction):
        prop = OpenProposal("BTCUSDT", -1, D(100), D(101), 50, "sanitized", .8, "deepseek:mock", "a" * 32,
                            risk_fraction=fraction)
        d = BrainDecision(kind=DecisionKind.OPEN, proposal=prop, occurred_at_ms=T0, status=ProposalStatus.DRAFT,
                          rationale="sanitized", sources=["risk:quote"])
        return _engine(tmp_path, cfg().risk_policy)._apply_risk_gate(d, MarketContext("BTCUSDT", D(100), T0,
                                                                                       "TREND_DOWN"))
    full, first = gate(None).risk_quote, gate(0.65).risk_quote
    assert full.worst_case_loss_estimate <= D(86) and first.worst_case_loss_estimate <= D(86) * D("0.65")
    assert first.quantity < full.quantity                               # stesso stop: solo meno rischio subito


# ----------------------------------------------------------------------------- 2-3. secondo ingresso e rischio
def test_add_size_keeps_the_total_risk_within_the_per_trade_budget():
    # SHORT: prima entrata 60.200 col 65 % del rischio, stop 60.800; secondo ingresso a 60.400
    c = D("0.0016")
    q0 = D("0.0803")
    r0 = q0 * 600 + c * 60200 * q0
    q = add_quantity(side=-1, quantity=q0, avg_price=D(60200), stop=D(60800), price=D(60400), cost_fraction=c,
                     risk_budget=D(86), open_risk_room=D(1000), side_risk_room=D(1000), margin_room=D(1000),
                     leverage=30, step=D("0.0001"), minimum_notional=D(5))
    avg = (60200 * q0 + 60400 * q) / (q0 + q)
    total = (q0 + q) * (60800 - avg) + c * avg * (q0 + q)
    assert q > 0 and total <= D(86) and total > D(86) - D("0.0001") * 600 and r0 < D(86)
    assert add_quantity(side=-1, quantity=q0, avg_price=D(60200), stop=D(60800), price=D(60400), cost_fraction=c,
                        risk_budget=r0, open_risk_room=D(1000), side_risk_room=D(1000), margin_room=D(1000),
                        leverage=30, step=D("0.0001"), minimum_notional=D(5)) == 0      # nessun rischio riservato
    # prezzo: migliore (short: piu' alto) di almeno 0,25 R e non vicino allo stop
    ok = lambda p: add_price_ok(side=-1, avg_price=D(60200), initial_risk=D(600), stop=D(60800), price=D(p))  # noqa
    assert ok(60400) and not ok(60300) and not ok(60100) and not ok(60650)


def _guard(price, **over):
    s = dict(exit_ok=True, paused=False, mandate=None, budget=None, loss=False, fresh=True)
    s.update(over)
    return dict(initial_equity=D(2000), risk_policy=cfg().risk_policy, exit_healthy=lambda _: s["exit_ok"],
                mandate_problem=lambda: s["mandate"], budget_problem=lambda: s["budget"],
                daily_loss_halted=lambda _: s["loss"], paused=lambda: s["paused"], market_rules=lambda _: RULES,
                market_price=lambda *_: D(price), market_fresh=lambda *_: s["fresh"])


def _add(j, tmp_path, pid, price, **over):
    return commit_paper_add(journal=j, data_dir=tmp_path, run_id=RUN, position_id=pid, clock_ms=lambda: T0 + 30 * MIN,
                            guard_inputs=_guard(price, **over), desk_mode="paper")


def _sidecar(tmp_path):
    return ExitService(run_id=RUN, data_dir=tmp_path, run_commands=lambda _: None,
                       run_monitor=lambda _: MonitorReport(0, (), ()))


def test_second_entry_at_a_better_price_updates_average_and_keeps_the_stop(tmp_path):
    j = _journal(tmp_path)
    pid = _short_btc(j)
    with _sidecar(tmp_path) as sc:
        assert sc.tick(T0 + 30 * MIN).state == "healthy"
        assert _add(j, tmp_path, pid, "60250").code == "add_price_not_better"      # troppo vicino all'ingresso
        assert _add(j, tmp_path, pid, "60400", paused=True).code == "safety_gate_closed"
        res = _add(j, tmp_path, pid, "60400")
        assert res.allowed and res.code == "paper_add_committed"
        assert _add(j, tmp_path, pid, "60500").code == "add_not_allowed"            # al massimo un secondo ingresso
    st = position_state([r.event for r in j.list_run("brain", RUN)], pid)
    pos = build_summary(j, "brain", RUN).open_positions[0]
    assert st.adds == 1 and st.stop == D(60800) and pos.stop_price == D(60800)          # stop invariato
    assert D(60200) < pos.fill_price < D(60400) and pos.quantity > D("0.080") and pos.adds == 1
    risk = pos.quantity * (pos.stop_price - pos.fill_price) + pos.fill_price * pos.quantity * D("0.0016")
    assert risk <= D(2000) * D("0.043")                                                  # rischio per trade invariato
    from backend.v3.runner.cycle import snapshot_from_summary
    snap = snapshot_from_summary(build_summary(j, "brain", RUN), D(2000), D(16))
    assert snap.open_positions == 1 and snap.existing_open_risk <= D(2000) * D("0.12")


def test_no_reserve_or_after_a_partial_means_no_second_entry(tmp_path):
    j = _journal(tmp_path)
    pid = _short_btc(j, reserve=False)
    with _sidecar(tmp_path) as sc:
        sc.tick(T0 + 30 * MIN)
        assert _add(j, tmp_path, pid, "60400").code == "add_not_allowed"
    j2 = _journal(tmp_path / "b") if (tmp_path / "b").mkdir() is None else None
    pid2 = _short_btc(j2)
    reduce_paper(portfolio_id="brain", run_id=RUN, position_id=pid2, fraction=D("0.35"), exit_price=D(59000),
                 reason="take_profit", fee_bps=6, journal=j2, quantity_step=D("0.001"), now_ms=T0 + MIN)
    with _sidecar(tmp_path / "b") as sc:
        sc.tick(T0 + 30 * MIN)
        assert commit_paper_add(journal=j2, data_dir=tmp_path / "b", run_id=RUN, position_id=pid2,
                                clock_ms=lambda: T0 + 30 * MIN, guard_inputs=_guard("60400"),
                                desk_mode="paper").code == "add_not_allowed"   # mai mediare dopo aver incassato


# ----------------------------------------------------------------------------- 4. chiusure parziali, contabilita'
def test_partial_then_final_close_counts_everything_once(tmp_path):
    from backend.v3.compare_view import RunRef, read_run
    from backend.v3.outcomes import extract_outcomes
    import shutil
    shutil.copy(CFG, tmp_path / "runner_config.json")
    j = _journal(tmp_path)
    start = _rome_midnight(24) + 6 * 3_600_000
    pid = _short_btc(j, qty="0.100", margin="200", at=start)
    red = reduce_paper(portfolio_id="brain", run_id=RUN, position_id=pid, fraction=D("0.35"), exit_price=D(59000),
                       reason="take_profit", fee_bps=6, journal=j, quantity_step=D("0.001"), now_ms=start + 30 * MIN)
    assert (D(red["quantity"]), D(red["remaining_quantity"]), D(red["margin_released"])) == (D("0.035"), D("0.065"),
                                                                                                D("70"))
    # SHORT 60.200 -> 59.000 su 0,035: +42 lordi; commissioni di entrata e uscita della SOLA parte chiusa
    assert D(red["gross_pnl"]) == D("42") and D(red["fees"]) == D("2.5032")
    pos = build_summary(j, "brain", RUN).open_positions[0]
    assert (pos.quantity, pos.margin_used, pos.fill_price, pos.tp_reduced) == (D("0.065"), D(130), D(60200), True)
    fin = close_paper(portfolio_id="brain", run_id=RUN, position_id=pid, exit_price=D(59500), reason="stop",
                      fee_bps=6, journal=j, now_ms=start + 60 * MIN)
    assert fin.quantity == D("0.065") and fin.entry_price == D(60200)   # il residuo, al prezzo medio
    total = D(red["realized_pnl"]) + fin.realized_pnl
    whole_fees = (D(60200) * D("0.1") + D(59000) * D("0.035") + D(59500) * D("0.065")) * D("0.0006")
    assert D(red["fees"]) + fin.fees == pytest.approx(whole_fees, abs=D("0.00000002"))   # ogni unita' una volta
    s = build_summary(j, "brain", RUN)
    assert s.realized_pnl == total and not s.open_positions and len(s.closed_trades) == 2
    out = extract_outcomes(j, "brain", RUN)
    assert len(out.outcomes) == 2 and not out.skipped and sum(o.realized_pnl for o in out.outcomes) == total
    view = read_run(RunRef("brain_scalp", "Brain", tmp_path, RUN), _rome_midnight(25) + MIN)
    assert view["closed"] == 1 and view["closes"] == 2 and D(view["net_pnl"]) == total
    assert D(view["piggy"]["total"]) == max(total, D(0))                  # salvadanaio: realizzato, una volta


def test_market_value_views_match_the_average_price_calculation(tmp_path):
    """Guardian e perdita giornaliera leggono i segmenti equivalenti: stesso realizzato e stesso non realizzato."""
    j = _journal(tmp_path)
    pid = _short_btc(j)
    with _sidecar(tmp_path) as sc:
        sc.tick(T0 + 30 * MIN)
        assert _add(j, tmp_path, pid, "60400").allowed
    reduce_paper(portfolio_id="brain", run_id=RUN, position_id=pid, fraction=D("0.35"), exit_price=D(59500),
                 reason="brain_close", fee_bps=6, journal=j, quantity_step=D("0.001"), now_ms=T0 + 40 * MIN)
    events = [r.event for r in j.list_run("brain", RUN)]
    seg = expand_scaled(events)
    st = position_state(events, pid)
    live_q = {}
    realized = D(0)
    for e in seg:
        if e.kind == "paper_open":
            live_q[e.payload["position_id"]] = (D(e.payload["quantity"]), D(e.payload["fill_price"]))
        elif e.kind == "paper_close":
            live_q.pop(e.payload["position_id"], None)
            realized += D(e.payload["realized_pnl"])
    px = D(59800)
    unreal = sum((-1 * (px - f) * q for q, f in live_q.values()), D(0))
    assert realized == st.realized and sum(q for q, _f in live_q.values()) == st.quantity
    assert unreal == pytest.approx(-1 * (px - st.avg_price) * st.quantity, abs=D("0.000001"))


def test_exit_service_takes_35_percent_at_2r_by_reducing_the_same_position(tmp_path):
    j = _journal(tmp_path)
    pid = _short_btc(j, reserve=False, qty="0.100", margin="200")
    pol = cfg().exit_policy
    # SHORT 60.200, stop 60.800: 2R = 59.000. Minuto 2 tocca 58.990; poi resta sopra
    bars = _bars([(60200, 60250, 60100, 60150), (60150, 60160, 58990, 59100), (59100, 59200, 59050, 59150)],
                 T0 // MIN * MIN + MIN)
    kw = dict(journal=j, portfolio_id="brain", run_id=RUN, fetch_bars=lambda s, a, b: bars, policy=pol, fee_bps=D(6),
              now_ms=bars[-1].open_time_ms + 2 * MIN, partial=cfg().unico.partial, step_of=lambda s: D("0.001"))
    rep = run_exit_monitor(**kw)
    assert rep.closed == ((pid, "take_profit_partial"),) and _kinds(j) == ["paper_open", "paper_reduce"]
    red = [r.event.payload for r in j.list_run("brain", RUN) if r.event.kind == "paper_reduce"][0]
    assert (D(red["exit_price"]), D(red["quantity"]), red["reason"]) == (D(59000), D("0.035"), "take_profit")
    assert run_exit_monitor(**kw).closed == () and _kinds(j).count("paper_reduce") == 1      # una volta sola
    # stessa candela di stop e di 2R: vince lo stop, nessuna presa parziale
    j2 = _journal(tmp_path / "s") if (tmp_path / "s").mkdir() is None else None
    pid2 = _short_btc(j2, reserve=False)
    both = _bars([(60200, 60900, 58990, 60000)], T0 // MIN * MIN + MIN)
    rep = run_exit_monitor(**dict(kw, journal=j2, fetch_bars=lambda s, a, b: both, now_ms=both[-1].open_time_ms + MIN))
    assert [r for _p, r in rep.closed] == ["stop"] and "paper_reduce" not in _kinds(j2)


# ----------------------------------------------------------------------------- revisione AI, canale, Telegram
def test_ai_partial_close_reduces_the_single_position_through_the_exit_channel(tmp_path):
    from backend.v3.runner.manual_close import BRAIN_CHANNEL, run_manual_close
    from backend.v3.runner.position_review import ReviewProposal, review_open_positions

    class Rev:
        def __init__(self, props):
            self.props = list(props)

        def review(self, view, **kw):
            return self.props.pop(0)
    j = _journal(tmp_path)
    pid = _short_btc(j, reserve=False, qty="0.100", margin="200")
    out = review_open_positions(journal=j, run_id=RUN, data_dir=tmp_path, now_ms=T0 + 30 * MIN,
                                reviewer=Rev([ReviewProposal("PARTIAL_CLOSE", None, .7)]),
                                price_of=lambda s, t: D(59500))
    assert [(o.executed, o.code) for o in out] == [("PARTIAL_CLOSE", "reduce_position")]
    import json
    assert json.loads((tmp_path / BRAIN_CHANNEL["request_file"]).read_text())["fraction"] == "0.35"
    rep = run_manual_close(journal=j, portfolio_id="brain", run_id=RUN, data_dir=tmp_path,
                           price_of=lambda s, t: D(59500), fee_bps=D(6), now_ms=T0 + 31 * MIN,
                           step_of=lambda s: D("0.001"), **BRAIN_CHANNEL)
    assert rep.closed == (pid,) and _kinds(j) == ["paper_open", "position_review", "paper_reduce"]
    assert build_summary(j, "brain", RUN).open_positions[0].quantity == D("0.065")
    out = review_open_positions(journal=j, run_id=RUN, data_dir=tmp_path, now_ms=T0 + 60 * MIN,
                                reviewer=Rev([ReviewProposal("PARTIAL_CLOSE", None, .7)]),
                                price_of=lambda s, t: D(59500))
    assert out[0].code == "partial_not_available"                         # gia' incassata una volta


def test_second_entry_needs_both_ais_and_goes_through_the_serialized_writer(tmp_path):
    from backend.v3.runner.consult import ClaudeView, PositionMetrics, arbitrate_position
    from backend.v3.runner.position_review import ReviewProposal, review_open_positions
    m = PositionMetrics(D("-0.3"), D("-5"), None, None, "TREND_DOWN", "TREND_DOWN")
    assert arbitrate_position("ADD", None, .7, None, m).action == "HOLD"
    assert arbitrate_position("ADD", None, .7, ClaudeView("budget"), m).code == "claude_unavailable_critical"
    assert arbitrate_position("ADD", None, .7, ClaudeView("ok", "CONFIRM"), m).action == "ADD"
    v = arbitrate_position("ADD", None, .7, ClaudeView("ok", "CONTEST", action="HOLD", confidence=.6), m)
    assert (v.action, v.code) == ("HOLD", "claude_rejected_add")
    assert arbitrate_position("HOLD", None, .7, ClaudeView("ok", "CONTEST", action="ADD"), m).code == "add_needs_both"

    class Rev:
        def review(self, view, **kw):
            return ReviewProposal("ADD", None, .7)

    class Ok:                                                    # Claude conferma
        def start_cycle(self, k): pass
        def cooling(self, k, t): return False
        def ask(self, *a, **k): return ClaudeView("ok", "CONFIRM", confidence=.7)
    j = _journal(tmp_path)
    pid = _short_btc(j)
    calls = []
    out = review_open_positions(journal=j, run_id=RUN, data_dir=tmp_path, now_ms=T0 + 30 * MIN, reviewer=Rev(),
                                consultant=Ok(), price_of=lambda s, t: D(60400),
                                add_commit=lambda p, t: calls.append(p) or type("R", (), {"allowed": True,
                                                                                         "code": "ok"})())
    assert calls == [pid] and out[0].executed == "ADD"
    out = review_open_positions(journal=j, run_id=RUN, data_dir=tmp_path, now_ms=T0 + 60 * MIN, reviewer=Rev(),
                                consultant=Ok(), price_of=lambda s, t: D(60250), add_commit=lambda p, t: 1 / 0)
    assert (out[0].executed, out[0].code) == ("HOLD", "add_price_not_better")        # prezzo non conveniente
    out = review_open_positions(journal=j, run_id=RUN, data_dir=tmp_path, now_ms=T0 + 90 * MIN, reviewer=Rev(),
                                price_of=lambda s, t: D(60400), add_commit=lambda p, t: 1 / 0)
    assert out[0].executed == "HOLD"                                                    # senza consulente: mai


def test_telegram_reports_second_entry_partial_and_residual_close_once(tmp_path):
    from backend.v3.runner.telegram_feed import JournalNotifier
    j = _journal(tmp_path)
    sent = []
    n = JournalNotifier(journal=j, run_id=RUN, data_dir=tmp_path, send=lambda t: sent.append(t) or True,
                        initial_equity=D(2000), default_tp_r=D("3.5"))
    n.poll(T0)
    pid = _short_btc(j, at=T0 + MIN)
    msgs = n.poll(T0 + 2 * MIN)
    assert len(msgs) == 1 and "Apertura SHORT BTC · entrata 60200" in msgs[0] and "quote" not in msgs[0]
    with _sidecar(tmp_path) as sc:
        sc.tick(T0 + 30 * MIN)
        assert _add(j, tmp_path, pid, "60400").allowed
    reduce_paper(portfolio_id="brain", run_id=RUN, position_id=pid, fraction=D("0.35"), exit_price=D(59000),
                 reason="take_profit", fee_bps=6, journal=j, quantity_step=D("0.001"), now_ms=T0 + 40 * MIN)
    close_paper(portfolio_id="brain", run_id=RUN, position_id=pid, exit_price=D(59500), reason="stop", fee_bps=6,
                journal=j, now_ms=T0 + 50 * MIN, stop_kind="break_even")
    msgs = n.poll(T0 + 51 * MIN)
    assert msgs[0].startswith("➕ Secondo ingresso SHORT BTC a 60400 · prezzo medio")
    assert msgs[1].startswith("✂️ Chiusura parziale SHORT BTC · take profit · uscita 59000")
    assert msgs[2].startswith("✅ Chiusura del residuo SHORT BTC · stop a pareggio") and len(msgs) == 3
    assert n.poll(T0 + 52 * MIN) == []


def test_daily_performance_counts_each_trade_once_and_keeps_pnl_by_date(tmp_path):
    """Una posizione chiusa in piu' parti (anche su giorni diversi) e le due quote di prima del 24/11 contano UN trade,
    con il risultato complessivo, nel giorno in cui il trade e' chiuso del tutto; il P&L resta per data dell'evento."""
    import shutil
    from backend.tests.test_v3_brain_unico_2000 import _open as legs_open
    from backend.v3.compare_view import RunRef, read_run
    from backend.v3.paper_app_view import performance
    shutil.copy(CFG, tmp_path / "runner_config.json")
    j = _journal(tmp_path)
    day1 = _rome_midnight(24) + 10 * 3_600_000
    pid = _short_btc(j, reserve=False, qty="0.100", margin="200", at=day1)
    red = reduce_paper(portfolio_id="brain", run_id=RUN, position_id=pid, fraction=D("0.35"), exit_price=D(59000),
                       reason="take_profit", fee_bps=6, journal=j, quantity_step=D("0.001"), now_ms=day1 + 60 * MIN)
    fin = close_paper(portfolio_id="brain", run_id=RUN, position_id=pid, exit_price=D(60500), reason="stop",
                      fee_bps=6, journal=j, now_ms=_rome_midnight(25) + 60 * MIN)       # residuo chiuso il giorno dopo
    legs_open(j, at=_rome_midnight(25) + 2 * 3_600_000, decision_id="brain-req-legs", symbol="ETHUSDT")
    for i, p in enumerate(build_summary(j, "brain", RUN).open_positions):              # vecchio stile: due quote
        close_paper(portfolio_id="brain", run_id=RUN, position_id=p.position_id, exit_price=D(99), reason="stop",
                    fee_bps=6, journal=j, now_ms=_rome_midnight(25) + (3 + i) * 3_600_000)
    perf = performance(tmp_path, RUN, _rome_midnight(26) - MIN)
    d24, d25 = [d for d in perf["daily"] if d["date"] in ("2026-11-24", "2026-11-25")]
    assert (d24["closes"], d24["trades"], d24["wins"], d24["losses"]) == (1, 0, 0, 0)    # solo la parte incassata
    assert D(d24["net"]) == D(red["realized_pnl"])
    assert (d25["closes"], d25["trades"]) == (3, 2)                                      # BTC (residuo) + ETH (2 quote)
    total_btc = D(red["realized_pnl"]) + fin.realized_pnl
    assert d25["wins"] + d25["losses"] == 2 and d25["wins"] == (1 if total_btc > 0 else 0)
    assert sum(D(d["net"]) for d in perf["daily"]) == build_summary(j, "brain", RUN).realized_pnl
    view = read_run(RunRef("brain_scalp", "Brain", tmp_path, RUN), _rome_midnight(26) - MIN)
    assert sum(d["closes"] for d in perf["daily"]) == view["closes"] and sum(d["trades"] for d in perf["daily"]) == 2


def test_review_history_shows_the_ai_second_entry(tmp_path):
    import shutil
    from backend.v3.compare_view import RunRef, read_run
    from backend.v3.events import Event
    shutil.copy(CFG, tmp_path / "runner_config.json")
    j = _journal(tmp_path)
    _short_btc(j)
    j.append(Event("position_review.1.0", "brain", RUN, "position_review", T0 + MIN, "runner.position_review",
                   {"symbol": "BTCUSDT", "group": "g", "side": -1, "proposed": "ADD", "executed": "ADD",
                    "code": "add_requested", "source": "agreed", "claude": {"status": "ok", "verdict": "CONFIRM"}}))
    rev = read_run(RunRef("brain_scalp", "Brain", tmp_path, RUN), T0 + 2 * MIN)["reviews"][0]
    assert (rev["proposed"], rev["executed"], rev["source"]) == ("ADD", "ADD", "agreed")
