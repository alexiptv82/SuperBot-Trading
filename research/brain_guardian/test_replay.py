"""Regole del replay su candele costruite a mano: nessuno sguardo al futuro, stop prima del target, costi."""
from __future__ import annotations

import pytest

from research.brain_guardian.replay import (MINUTE, Bar, Costs, Entry, EntryFilter, ExitPolicy, PortfolioGuard,
                                            Variant, atr15, metrics, run_portfolio, simulate_exit)

T0 = 1_700_000_000_000 // MINUTE * MINUTE
NOC = Costs(fee_bp=0, entry_slippage_bp=0, stop_slippage_bp=0)


def bars(*ohlc, start=T0 + MINUTE):
    return [Bar(start + i * MINUTE, *x) for i, x in enumerate(ohlc)]


LONG = Entry(T0 + 5_000, "BTCUSDT", 1, 100.0, 99.0)       # rischio 1 = 1R


def test_entry_minute_is_ignored_and_stop_wins_in_the_same_bar():
    b = [Bar(T0, 100, 103, 98, 100)] + bars((100, 102.5, 98.9, 101))  # candela d'ingresso: ignorata
    r = simulate_exit(LONG, b, 1.0, ExitPolicy(), NOC)
    assert r.reason == "stop" and r.pnl == pytest.approx(-1.0)          # tocca anche 2R ma vince lo stop


def test_gap_beyond_stop_exits_at_open_with_slippage_and_fees():
    r = simulate_exit(LONG, bars((98.0, 98.5, 97.5, 98)), 1.0, ExitPolicy(), Costs(fee_bp=6, entry_slippage_bp=0,
                                                                                  stop_slippage_bp=2))
    px = 98.0 * (1 - 2e-4)
    assert r.pnl == pytest.approx((px - 100) - (100 + px) * 6e-4)


def test_take_profit_and_timeout():
    r = simulate_exit(LONG, bars((100, 101, 99.5, 100.5), (100.5, 102.1, 100, 102)), 1.0, ExitPolicy(), NOC)
    assert r.reason == "take_profit" and r.pnl == pytest.approx(2.0) and r.r_realized == pytest.approx(2.0)
    flat = bars(*[(100, 100.5, 99.6, 100.2)] * (24 * 60 + 5))
    r = simulate_exit(LONG, flat, 1.0, ExitPolicy(), NOC)
    assert r.reason == "timeout" and r.pnl == pytest.approx(0.2) and r.exit_t <= LONG.t + 24 * 3_600_000 + MINUTE


def test_breakeven_is_armed_only_from_the_next_bar():
    # stessa candela: tocca +1,2R e scende sotto l'ingresso (ma sopra lo stop) -> nessuna uscita
    b = bars((100, 101.2, 99.5, 100), (100, 100.2, 99.95, 100.1))
    r = simulate_exit(LONG, b + bars(*[(100, 100.1, 99.99, 100)] * 2000, start=b[-1].t + MINUTE),
                      1.0, ExitPolicy(be_trigger_r=1.0), NOC)
    assert r.reason == "breakeven" and r.exit_t == b[1].t + MINUTE and r.pnl == pytest.approx(0.0)
    assert r.mfe_r == pytest.approx(1.2)


def test_trailing_follows_the_best_excursion():
    b = bars((100, 101.5, 99.8, 101.4), (101.4, 101.6, 101.0, 101.2), (101.2, 101.3, 100.4, 100.5))
    r = simulate_exit(LONG, b, 1.0, ExitPolicy(tp_r=None, trail_trigger_r=1.0, trail_r=1.0), NOC)
    # best dopo la 2a candela = 1,6R -> stop a 100,6 nella 3a candela
    assert r.reason == "trail" and r.pnl == pytest.approx(0.6)


def test_partial_then_stop_and_stop_first_over_partial():
    b = bars((100, 101.1, 99.9, 101), (101, 101.0, 98.8, 99))
    r = simulate_exit(LONG, b, 1.0, ExitPolicy(partial_r=1.0, partial_frac=0.5), NOC)
    assert r.pnl == pytest.approx(0.5 * 1.0 + 0.5 * -1.0)
    r = simulate_exit(LONG, bars((100, 101.1, 98.9, 99)), 1.0, ExitPolicy(partial_r=1.0), NOC)
    assert r.pnl == pytest.approx(-1.0)                                    # stessa candela: nessuna parziale


def test_atr_uses_only_closed_bars_before_entry():
    hist = [Bar(T0 - (300 - i) * MINUTE, 100, 100.2, 99.8, 100) for i in range(300)]
    spike = [Bar(T0 + i * MINUTE, 100, 110, 90, 100) for i in range(30)]  # futuro: non deve contare
    assert atr15(hist + spike, T0) == pytest.approx(0.4)
    tight = Entry(T0, "X", 1, 100, 99.9)
    from research.brain_guardian.replay import entry_allowed
    assert entry_allowed(tight, EntryFilter(min_stop_atr_mult=1.0), NOC, hist + spike) == "stop_inside_noise"
    assert entry_allowed(tight, EntryFilter(min_stop_cost_mult=1.0), Costs(), hist) == "stop_inside_costs"


def _down_after(t, sym):
    return bars((100, 100.2, 98.5, 98.6), start=t // MINUTE * MINUTE + MINUTE)


def test_portfolio_cooldown_cap_hwm_and_no_future_information():
    b = {}
    e1 = Entry(T0, "AAA", 1, 100, 99)
    e2 = Entry(T0 + 30 * MINUTE, "AAA", 1, 100, 99)          # dopo lo stop di e1 (minuto 2)
    e3 = Entry(T0 + 30 * MINUTE, "BBB", 1, 100, 99)
    for e in (e1, e2, e3):
        b.setdefault(e.symbol, []).extend(_down_after(e.t, e.symbol))
    base = run_portfolio([e1, e2, e3], b, Variant("A"), NOC)
    assert len(base.trades) == 3 and all(t.reason == "stop" for t in base.trades)
    cool = run_portfolio([e1, e2, e3], b, Variant("D", guard=PortfolioGuard(cooldown_h_after_stop=4)), NOC)
    assert len(cool.trades) == 2 and cool.skipped == {"cooldown_after_stop": 1}
    halt = run_portfolio([e1, e2, e3], b, Variant("H", guard=PortfolioGuard(hwm_drawdown_halt=0.02)), NOC)
    assert len(halt.trades) == 1 and halt.skipped == {"hwm_drawdown_halt": 2}
    # tetto: due aperture contemporanee nello stesso verso, la seconda e' rifiutata finche' la prima e' aperta
    same = [Entry(T0, "AAA", -1, 100, 101), Entry(T0 + 5_000, "BBB", -1, 100, 101)]
    flat = {s: bars(*[(100, 100.3, 99.7, 100)] * 30) for s in ("AAA", "BBB")}
    capped = run_portfolio(same, flat, Variant("C", exit=ExitPolicy(max_hold_h=0.25),
                                               guard=PortfolioGuard(max_same_side_open=1)), NOC)
    assert len(capped.trades) == 1 and capped.skipped == {"correlated_cap": 1}


def test_sizing_respects_risk_and_margin_and_metrics():
    e = Entry(T0, "AAA", 1, 100, 99)
    res = run_portfolio([e], {"AAA": _down_after(T0, "AAA")}, Variant("A"), NOC)
    t = res.trades[0]
    # rischio 4,2857% di 2000 = 85,71 USDT su stop 1% -> 8571 di nozionale; margine 20% x 20x = 8000: vince il MARGINE
    # (con gli stop del Brain, 0,40-0,91%, il margine vincola sempre: nozionale 8000 per operazione)
    assert t.qty == pytest.approx(80.0)
    m = metrics(res)
    assert m["trades"] == 1 and m["win_rate"] == 0 and m["max_drawdown_pct"] == pytest.approx(4.0)       # 80 unita x 1 = 80 USDT su 2000
