"""Test puri (nessun DB, rete o exchange) del modulo risk_profiles: regole di
uscita del paper trading, costi, tetti di leva e modalita'."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from risk_profiles import (  # noqa: E402
    PRESETS, Profile, entry_fill, liquidation_price, market_exit_price, modes_to_profiles,
    paper_exit, paper_pnl, size_trade, with_leverage_ceiling,
)

SLIP = 0.0002
FEE = 0.0006


def test_modes_to_profiles():
    assert modes_to_profiles("both") == ["conservative", "aggressive"]
    assert modes_to_profiles("aggressive") == ["aggressive"]
    assert modes_to_profiles("conservative") == ["conservative"]
    assert modes_to_profiles("qualcosa-di-strano") == ["conservative"]      # in dubbio, il piu' prudente


def test_presets_are_what_the_simulation_selected():
    c, a = PRESETS["conservative"], PRESETS["aggressive"]
    for p in (c, a):
        assert p.sl_scale == 8.0 and p.min_strength == 70 and p.liq_safety == 3.0
    assert c.max_lev == 10 and c.margin_exp == 1.0 and c.cap_ref_pct == 20.0
    assert a.max_lev == 30 and a.margin_exp == 0.5 and a.cap_ref_pct == 50.0


def test_leverage_ceiling_never_raises_and_keeps_min_below_max():
    a = PRESETS["aggressive"]
    assert with_leverage_ceiling(a, None) is a
    assert with_leverage_ceiling(a, 50) is a
    capped = with_leverage_ceiling(a, 5)
    assert capped.max_lev == 5 and capped.min_lev <= capped.max_lev
    one = with_leverage_ceiling(a, 1)
    assert one.max_lev == 1 and one.min_lev == 1
    r = size_trade(one, 1000, 100.0, 0.05, "long", "medium", 100)
    assert r["leverage"] == 1                                            # mai oltre il tetto


def test_aggressive_uses_more_leverage_and_exposure_but_less_margin_per_unit():
    kw = dict(capital=1000, price=100.0, atr=0.05, side="long", trade_type="medium", strength=90, slip_frac=SLIP)
    c = size_trade(PRESETS["conservative"], **kw)
    a = size_trade(PRESETS["aggressive"], **kw)
    assert a["leverage"] > c["leverage"]
    assert a["notional"] > c["notional"]
    assert a["margin"] / a["notional"] < c["margin"] / c["notional"]     # piu' leva => meno margine per euro di esposizione
    assert abs(c["notional"] - 200.0) < 0.5                              # tetto 20% del capitale


def test_leverage_drops_automatically_when_the_stop_is_close_to_liquidation():
    p = PRESETS["aggressive"]
    calm = size_trade(p, 1000, 100.0, 0.05, "long", "medium", 110, SLIP)
    wild = size_trade(p, 1000, 100.0, 0.5, "long", "medium", 110, SLIP)   # stop 8% : serve leva molto piu' bassa
    assert calm["leverage"] == 30
    assert wild["leverage"] < 10
    assert (1.0 / wild["leverage"] - 0.005) >= 3.0 * (0.08 + SLIP) - 1e-9
    assert size_trade(p, 1000, 100.0, 5.0, "long", "medium", 110, SLIP) is None   # stop impossibile: salta


def test_entry_and_market_exit_slippage_is_adverse():
    assert abs(entry_fill(100.0, "long", SLIP) - 100.02) < 1e-9
    assert abs(entry_fill(100.0, "short", SLIP) - 99.98) < 1e-9
    assert abs(market_exit_price("long", 100.0, SLIP) - 99.98) < 1e-9
    assert abs(market_exit_price("short", 100.0, SLIP) - 100.02) < 1e-9


def test_paper_exit_long():
    sl, tp, liq = 99.0, 102.0, 90.0
    assert paper_exit("long", 100.0, sl, tp, liq, SLIP) is None
    why, px = paper_exit("long", 102.5, sl, tp, liq, SLIP)
    assert why == "tp" and px == tp                                      # ordine limite: al prezzo del TP
    why, px = paper_exit("long", 98.9, sl, tp, liq, SLIP)
    assert why == "sl" and abs(px - 98.9 * (1 - SLIP)) < 1e-9            # stop: peggiore tra stop e prezzo, con slippage
    why, px = paper_exit("long", 80.0, sl, tp, liq, SLIP)
    assert why == "liq" and px == liq                                    # crollo oltre la liquidazione


def test_paper_exit_short_mirror():
    sl, tp, liq = 101.0, 98.0, 110.0
    assert paper_exit("short", 100.0, sl, tp, liq, SLIP) is None
    assert paper_exit("short", 97.9, sl, tp, liq, SLIP) == ("tp", tp)
    why, px = paper_exit("short", 101.2, sl, tp, liq, SLIP)
    assert why == "sl" and abs(px - 101.2 * (1 + SLIP)) < 1e-9
    assert paper_exit("short", 120.0, sl, tp, liq, SLIP) == ("liq", liq)


def test_liquidation_comes_first_when_it_sits_inside_the_stop():
    # leva alta e stop largo (liquidazione piu' vicina dello stop): vince la liquidazione
    liq = liquidation_price("long", 100.0, 30)                           # ~97.17
    assert paper_exit("long", 97.0, 90.0, 110.0, liq, SLIP) == ("liq", liq)


def test_paper_exit_without_liquidation_price_is_legacy_like():
    assert paper_exit("long", 98.0, 99.0, 102.0, None, 0.0) == ("sl", 98.0)
    assert paper_exit("long", 103.0, 99.0, 102.0, None, 0.0) == ("tp", 102.0)


def test_paper_pnl_take_profit_includes_both_fees():
    # long 1 unita' a 100.02, esce al TP 100.75
    gross, fees, net = paper_pnl("long", 1.0, 100.02, 100.75, 10.0, "tp", FEE)
    assert abs(gross - 0.73) < 1e-9
    assert abs(fees - (100.02 * FEE + 100.75 * FEE)) < 1e-4
    assert abs(net - (gross - fees)) < 1e-4


def test_paper_pnl_short_and_liquidation():
    gross, fees, net = paper_pnl("short", 2.0, 99.98, 99.0, 12.0, "tp", FEE)
    assert abs(gross - 1.96) < 1e-9 and net < gross
    gross, fees, net = paper_pnl("long", 2.0, 100.0, 97.0, 12.0, "liq", FEE)
    assert gross == -12.0                                                # si perde tutto il margine
    assert abs(fees - 2.0 * 100.0 * FEE) < 1e-9                          # solo la commissione d'ingresso
    assert abs(net - (-12.0 - fees)) < 1e-9


def test_conservative_trade_at_taker_fees_needs_more_than_the_stop_to_pay_the_cost():
    """Promemoria numerico del risultato del simulatore: con commissioni
    taker il costo di andata e ritorno (~0,12% + slippage) e' grande rispetto
    al guadagno medio di un trade."""
    p = PRESETS["conservative"]
    r = size_trade(p, 1000, 100.0, 0.05, "long", "medium", 80, SLIP)
    entry = entry_fill(100.0, "long", SLIP)
    gross, fees, net = paper_pnl("long", r["quantity"], entry, r["take_profit"], r["margin"], "tp", FEE)
    cost_pct = fees / r["notional"] * 100
    assert 0.11 < cost_pct < 0.14
    assert net < gross
