"""Test del simulatore storico dei profili di rischio (puro Python: nessun
accesso a rete, pandas o exchange)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from risk_profile_sim import (  # noqa: E402
    MMR, ONE_MINUTE_MS, Profile, build_round2, build_sweep, lev_target, liquidation_price,
    resample, run_portfolio, simulate_exit, size_trade,
)

LEGACY = Profile(name="legacy")


def bars(rows, start=0):
    """rows: lista di (open, high, low, close) -> candele 1m."""
    return [[start + k * ONE_MINUTE_MS, o, h, l, c, 1.0] for k, (o, h, l, c) in enumerate(rows)]


def flat(n, price=100.0):
    return [(price, price, price, price)] * n


# ── sizing ───────────────────────────────────────────────────────────────────

def test_legacy_matches_risk_manager():
    try:
        from risk_manager import risk_manager
        from config import config
    except ImportError:          # dotenv non installato in locale: il test gira in CI
        return
    config.MAX_LEVERAGE = 10
    config.RISK_PER_TRADE_PERCENT = 1.0
    config.MAX_POSITION_PERCENT = 20.0
    cases = [
        (1000.0, 65000.0, 40.0, "long", "scalp", 55),
        (1000.0, 65000.0, 40.0, "short", "medium", 100),
        (2500.0, 3200.0, 4.5, "long", "scalp", 70),
        (800.0, 2400.0, 3.0, "short", "medium", 110),
        (1000.0, 30.0, 0.02, "long", "scalp", 52),
        (1000.0, 100.0, 7.0, "long", "medium", 60),   # stop largo: qui vince il rischio, non il tetto
    ]
    for capital, price, atr, side, ttype, strength in cases:
        ref = risk_manager.calculate_trade_params(capital, price, atr, side, ttype, strength)
        mine = size_trade(LEGACY, capital, price, atr, side, ttype, strength)
        assert mine["leverage"] == ref["leverage"]
        assert abs(mine["quantity"] - ref["quantity"]) < 1e-9
        assert abs(mine["stop_loss"] - ref["stop_loss"]) < 1e-9
        assert abs(mine["take_profit"] - ref["take_profit"]) < 1e-9


def test_legacy_leverage_follows_strength():
    assert lev_target(LEGACY, 55) == 5
    assert lev_target(LEGACY, 100) == 10
    assert lev_target(LEGACY, 110) == 10      # tetto MAX_LEVERAGE
    assert lev_target(LEGACY, 10) == 2        # minimo


def test_scaled_leverage_interpolates_between_min_and_max():
    p = Profile(name="s", max_lev=30, min_lev=2, lev_mode="scaled")
    assert lev_target(p, 50) == 2
    assert lev_target(p, 110) == 30
    assert lev_target(p, 80) == 16
    assert lev_target(p, 30) == 2            # sotto soglia: minimo
    assert lev_target(p, 500) == 30


def test_cap_binds_and_leverage_is_cosmetic_when_k_is_1():
    """Con stop stretto il tetto decide la size: cambiare la leva (k=1) non
    cambia il nozionale, solo il margine."""
    a = size_trade(Profile(name="a", max_lev=10, lev_mode="scaled"), 1000, 100.0, 0.05, "long", "scalp", 110)
    b = size_trade(Profile(name="b", max_lev=30, lev_mode="scaled"), 1000, 100.0, 0.05, "long", "scalp", 110)
    assert abs(a["notional"] - 200.0) < 0.01       # 20% del capitale
    assert abs(b["notional"] - 200.0) < 0.01
    assert b["leverage"] == 30 and a["leverage"] == 10
    assert b["margin"] < a["margin"]                # piu' leva = meno margine


def test_higher_leverage_uses_less_budget_but_more_exposure_with_k_half():
    mk = lambda lev: size_trade(                                       # noqa: E731
        Profile(name="k", max_lev=lev, min_lev=lev, lev_mode="scaled", margin_exp=0.5),
        1000, 100.0, 0.05, "long", "scalp", 100)
    lo, hi = mk(10), mk(30)
    assert hi["notional"] > lo["notional"]                       # un po' piu' esposizione...
    assert hi["margin"] < lo["margin"]                           # ...ma molto meno margine
    assert abs(hi["notional"] / lo["notional"] - 3 ** 0.5) < 1e-3


def test_risk_binds_when_stop_is_wide():
    # stop al 10% del prezzo: rischio 1% => nozionale 10% del capitale (< tetto 20%)
    r = size_trade(LEGACY, 1000, 100.0, 10.0, "long", "scalp", 100)
    assert abs(r["notional"] - 100.0) < 0.01


def test_liq_safety_lowers_leverage_for_wide_stops_and_skips_when_impossible():
    p = Profile(name="p", max_lev=30, min_lev=2, lev_mode="scaled", liq_safety=3.0)
    narrow = size_trade(p, 1000, 100.0, 0.05, "long", "scalp", 110)
    assert narrow["leverage"] == 30
    wide = size_trade(p, 1000, 100.0, 1.0, "long", "scalp", 110)      # stop 1%
    assert wide["leverage"] < 30
    # distanza di liquidazione >= 3x stop
    assert (1.0 / wide["leverage"] - MMR) >= 3.0 * 0.01 - 1e-9
    assert size_trade(p, 1000, 100.0, 40.0, "long", "scalp", 110) is None   # stop 40%: nessuna leva basta


def test_bad_inputs_return_none():
    assert size_trade(LEGACY, 1000, 100.0, 0.0, "long", "scalp", 80) is None
    assert size_trade(LEGACY, 1000, 100.0, float("nan"), "long", "scalp", 80) is None
    assert size_trade(LEGACY, 0, 100.0, 1.0, "long", "scalp", 80) is None
    assert size_trade(LEGACY, 1000, 100.0, 200.0, "long", "scalp", 80) is None   # SL <= 0


def test_liquidation_price():
    assert abs(liquidation_price("long", 100.0, 10) - 100.0 * (1 - (0.1 - MMR))) < 1e-9
    assert abs(liquidation_price("short", 100.0, 10) - 100.0 * (1 + (0.1 - MMR))) < 1e-9
    assert abs(liquidation_price("long", 100.0, 30) - 100.0 * (1 - (1 / 30 - MMR))) < 1e-9


# ── uscita ───────────────────────────────────────────────────────────────────

def test_exit_long_take_profit():
    c = bars(flat(1) + [(100, 101, 99.9, 100.5), (100.5, 102.1, 100.4, 102.0)])
    j, px, why = simulate_exit(c, 0, "long", 99.0, 102.0, 90.0, 100, 0.0)
    assert (j, px, why) == (2, 102.0, "tp")


def test_exit_long_stop_loss_with_slippage():
    c = bars(flat(1) + [(100, 100.2, 98.5, 99.0)])
    j, px, why = simulate_exit(c, 0, "long", 99.0, 105.0, 90.0, 100, 0.001)
    assert why == "sl" and j == 1
    assert abs(px - 99.0 * (1 - 0.001)) < 1e-9


def test_exit_both_in_same_bar_assumes_stop():
    c = bars(flat(1) + [(100, 106.0, 98.0, 101.0)])
    assert simulate_exit(c, 0, "long", 99.0, 105.0, 90.0, 100, 0.0)[2] == "sl"
    assert simulate_exit(c, 0, "short", 101.0, 95.0, 110.0, 100, 0.0)[2] == "sl"


def test_exit_gap_below_stop_fills_at_open():
    c = bars(flat(1) + [(97.0, 97.5, 96.0, 96.5)])
    j, px, why = simulate_exit(c, 0, "long", 99.0, 105.0, 90.0, 100, 0.0)
    assert why == "sl" and px == 97.0


def test_exit_liquidation_before_stop():
    # stop molto sotto la liquidazione (leva alta, stop largo): liquidazione per prima
    c = bars(flat(1) + [(100, 100, 96.0, 97.0)])
    j, px, why = simulate_exit(c, 0, "long", 90.0, 120.0, 97.0, 100, 0.0)
    assert why == "liq" and px == 97.0


def test_exit_stop_fill_through_liquidation_is_liquidation():
    # stop appena sopra la liquidazione ma la slippage lo spinge oltre
    c = bars(flat(1) + [(100, 100, 96.9, 97.0)])
    assert simulate_exit(c, 0, "long", 97.05, 120.0, 97.0, 100, 0.002)[2] == "liq"


def test_exit_short_mirror():
    c = bars(flat(1) + [(100, 101.5, 99.5, 101.2)])
    j, px, why = simulate_exit(c, 0, "short", 101.0, 95.0, 120.0, 100, 0.0)
    assert why == "sl" and abs(px - 101.0) < 1e-9
    c2 = bars(flat(1) + [(100, 100.2, 94.0, 95.5)])
    assert simulate_exit(c2, 0, "short", 101.0, 95.0, 120.0, 100, 0.0)[2] == "tp"


def test_exit_timeout():
    c = bars(flat(10))
    j, px, why = simulate_exit(c, 0, "long", 90.0, 110.0, 50.0, 5, 0.0)
    assert (j, why) == (5, "timeout") and px == 100.0


# ── portafoglio ──────────────────────────────────────────────────────────────

def _sig(sym, i, ts, side="long", price=100.0, atr=0.5, trade_type="scalp", strength=100):
    return {"symbol": sym, "i": i, "ts": ts, "price": price, "atr": atr, "side": side,
            "trade_type": trade_type, "strength": strength}


def _run(profile, sigs, candles, **kw):
    base = dict(initial_capital=1000.0, fee_frac=0.0, slip_frac=0.0, max_hold=100)
    base.update(kw)
    return run_portfolio(profile, sigs, candles, **base)


def test_winning_trade_pnl_and_fees():
    # long a 100, TP a 100.75 (atr .5 * 1.5): +0.75%; nozionale 200 USDT => +1.5 USDT lordo
    candles = {"A": bars(flat(1) + [(100, 100.8, 99.99, 100.7)] + flat(5, 100.7))}
    sigs = [_sig("A", 0, ONE_MINUTE_MS)]
    r = _run(LEGACY, sigs, candles)
    assert r["trades"] == 1 and r["tp"] == 1
    assert abs(r["gross_return_pct"] * 10 - 1.5) < 1e-6            # 1.5 USDT su 1000
    r_fee = _run(LEGACY, sigs, candles, fee_frac=0.0006)
    fees = 200.0 * 0.0006 + (200.0 / 100.0) * 100.75 * 0.0006
    assert abs(r_fee["fees"] - fees) < 1e-6
    assert abs(r_fee["return_pct"] * 10 - (1.5 - fees)) < 1e-6


def test_losing_trade_and_drawdown():
    candles = {"A": bars(flat(1) + [(100, 100.1, 99.4, 99.5)] + flat(5, 99.5))}
    r = _run(LEGACY, [_sig("A", 0, ONE_MINUTE_MS)], candles)
    assert r["trades"] == 1 and r["sl"] == 1
    assert r["return_pct"] < 0 and r["max_dd_pct"] > 0
    assert r["win_rate"] == 0.0


def test_liquidation_loses_the_whole_margin():
    # SL a 5 (sl_scale alto) -> oltre la liquidazione a 30x (~-2.83%)
    p = Profile(name="hi", max_lev=30, min_lev=30, lev_mode="scaled", cap_ref_pct=50.0, margin_exp=0.0, sl_scale=20.0)
    candles = {"A": bars(flat(1) + [(100, 100, 96.0, 97.0)] + flat(5, 97.0))}
    sig = _sig("A", 0, ONE_MINUTE_MS, atr=0.25)        # SL = 100 - 5 = 95 < liq 97.17
    r = _run(p, [sig], candles)
    assert r["trades"] == 1 and r["liquidations"] == 1
    # senza commissioni la perdita e' esattamente il margine bloccato (nozionale / 30)
    assert abs(r["return_pct"] + r["avg_margin_pct"]) < 1e-9
    assert r["worst_trade_pct"] < 0


def test_one_position_per_symbol_and_max_open():
    candles = {s: bars(flat(60)) for s in "ABCD"}
    sigs = [_sig(s, 0, ONE_MINUTE_MS) for s in "ABCD"] + [_sig("A", 1, 2 * ONE_MINUTE_MS)]
    r = _run(LEGACY, sigs, candles, max_hold=30, max_open=3)
    assert r["trades"] == 3                                   # D saltato (max_open); A secondo saltato (occupato)
    assert r["skips"].get("max_posizioni") == 1
    assert r["skips"].get("simbolo_gia_aperto") == 1


def test_daily_loss_limit_pauses_new_entries():
    # una perdita grande chiude con SL, poi nello stesso giorno nessuna nuova entrata
    # nozionale 9x il capitale (margine 900 a leva 10), stop all'1%: perde ~9% > limite 5%
    p = Profile(name="big", cap_ref_pct=900.0, risk_pct=100.0, lev_mode="legacy")
    candles = {"A": bars(flat(1) + [(100, 100, 99.0, 99.0)] + flat(20, 99.0))}
    sigs = [_sig("A", 0, ONE_MINUTE_MS, atr=1.0), _sig("A", 5, 6 * ONE_MINUTE_MS, atr=1.0)]
    r = _run(p, sigs, candles, max_hold=10)
    assert r["trades"] == 1
    assert r["skips"].get("limite_giornaliero") == 1


def test_resample_drops_incomplete_buckets():
    c = [[k * ONE_MINUTE_MS, 1, 2, 0.5, 1.5, 1.0] for k in range(35)]      # 35 minuti
    out = resample(c, 15)
    assert len(out) == 2                                       # 0-14 e 15-29; 30-34 incompleto
    assert out[0][2] == 2 and out[0][3] == 0.5 and out[0][5] == 15.0


def test_sweep_has_baseline_and_grid():
    names = [p.name for p in build_sweep("standard")]
    assert names[0].startswith("ATTUALE")
    assert len(names) == len(set(names)) and len(names) > 20
    assert len(build_sweep("legacy")) == 2


def test_scaled_leverage_uses_profile_min_strength():
    p = Profile(name="m", max_lev=30, min_lev=2, lev_mode="scaled", min_strength=70)
    assert lev_target(p, 70) == 2
    assert lev_target(p, 110) == 30
    assert lev_target(p, 90) == 16


def test_min_strength_skips_weak_signals_without_blocking_the_symbol():
    candles = {"A": bars(flat(1) + [(100, 100.8, 99.99, 100.7)] + flat(30, 100.7))}
    p = Profile(name="sel", min_strength=70)
    weak = _sig("A", 0, ONE_MINUTE_MS, strength=60)
    strong = _sig("A", 0, ONE_MINUTE_MS + 1, strength=90)
    r = _run(p, [weak, strong], candles)
    assert r["trades"] == 1
    assert r["skips"].get("forza_insufficiente") == 1
    assert "simbolo_gia_aperto" not in r["skips"]


def test_stats_by_type():
    candles = {"A": bars(flat(1) + [(100, 100.8, 99.99, 100.7)] + flat(30, 100.7))}
    r = _run(LEGACY, [_sig("A", 0, ONE_MINUTE_MS)], candles)
    assert r["by_type"]["scalp"]["n"] == 1 and r["by_type"]["scalp"]["net"] > 0


def test_round2_sweep_shape():
    ps = build_round2()
    names = [p.name for p in ps]
    assert len(ps) == 60 and len(set(names)) == 60
    assert any(p.sl_scale == 8.0 and p.min_strength == 90 for p in ps)
    assert sum(1 for p in ps if p.name.startswith("ATT")) == 15
