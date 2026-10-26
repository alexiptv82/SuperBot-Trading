"""Regime di mercato (desk/regime.py) e sua integrazione in rules_decisions. Funzioni pure: nessuna rete."""
import os
import pytest
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DESK_MACRO_FETCH", "0")

from desk import regime as rg  # noqa: E402
from desk.brain import rules_decisions  # noqa: E402
from desk.signals import Reading  # noqa: E402

P = rg.FULL


@pytest.fixture(autouse=True)
def _full_profile(monkeypatch):
    """I test provano ogni funzione: si parte dal profilo COMPLETO; il profilo di produzione ha un test suo."""
    monkeypatch.setattr(rg, "DEFAULT", rg.FULL)



def rd(sym, ls, ss, roc=0.0, score=None, trade_type="scalp"):
    side = 1 if ls > ss else -1 if ss > ls else 0
    return Reading(symbol=sym, price=100.0, side=side, score=max(ls, ss) if score is None else score,
                   long_score=ls, short_score=ss, sl_pct=0.01, tp_pct=0.018, facts={"roc24h": roc},
                   why=["trend 1h (+15)", "trend 4h (+14)"], trade_type=trade_type)


ALTS = ["SOL", "ADA", "DOGE", "AVAX", "DOT", "LINK", "UNI", "ATOM", "LTC", "BCH"]


def market(ls, ss, roc=0.0):
    return [rd("BTC", ls, ss, roc), rd("ETH", ls, ss)] + [rd(a, ls, ss) for a in ALTS]


# ---------------------------------------------------------------- lettura del regime
def test_bear_bull_and_range():
    assert rg.compute(market(15, 80, -0.02), []).state == "down"
    assert rg.compute(market(80, 15, 0.02), []).state == "up"
    assert rg.compute(market(45, 45, 0.0), []).state == "range"


def test_commodities_do_not_count_in_breadth():
    base = market(50, 50)
    gold = [rd("XAU", 90, 5), rd("XAG", 90, 5)]
    assert rg.compute(base + gold, []).breadth == rg.compute(base, []).breadth == 0.0


def test_smoothing_follows_history():
    r = rg.compute(market(15, 80, -0.02), [0.6, 0.6, 0.6])
    assert r.smooth > r.raw                       # trascinato dalla storia rialzista
    assert rg.compute(market(15, 80, -0.02), []).smooth == rg.compute(market(15, 80, -0.02), []).raw


def test_turn_up_detected_after_a_low():
    hist = [-0.7, -0.7, -0.6, -0.5]
    r = rg.compute(market(65, 25, 0.015), hist)
    assert r.smooth - min(hist) >= P.turn_delta and r.turn == "up"


def test_turn_down_detected_after_a_high():
    hist = [0.7, 0.7, 0.6, 0.5]
    r = rg.compute(market(25, 65, -0.015), hist)
    assert r.turn == "down"


def test_no_turn_without_enough_history():
    assert rg.compute(market(80, 15, 0.02), [-0.7]).turn == ""


def test_push_hist_is_bounded():
    h = []
    r = rg.compute(market(50, 50), [])
    for _ in range(100):
        h = rg.push_hist(h, r)
    assert len(h) == rg.HIST_MAX


# ---------------------------------------------------------------- ingressi
def R(state, turn="", smooth=0.0, roc=0.0):
    return rg.Regime(smooth=smooth, raw=smooth, state=state, turn=turn, lead=0.0, breadth=0.0, roc=roc)


def test_entry_gate_short():
    assert rg.entry_gate(-1, "SOL", R("down", smooth=-0.5)) == (True, 0)
    assert rg.entry_gate(-1, "SOL", R("range")) == (True, P.range_extra)
    assert rg.entry_gate(-1, "SOL", R("up", smooth=0.5))[0] is False
    assert rg.entry_gate(-1, "SOL", R("range", turn="up", smooth=0.0))[0] is False
    assert rg.entry_gate(-1, "SOL", R("down", smooth=-0.5, roc=-0.04))[0] is False      # dopo un crollo: niente short
    assert rg.entry_gate(-1, "SOL", R("down", smooth=-0.5, roc=-0.02)) == (True, 0)


def test_entry_gate_long():
    assert rg.entry_gate(1, "SOL", R("up", smooth=0.5)) == (True, 0)
    assert rg.entry_gate(1, "SOL", R("range", turn="up", smooth=0.0)) == (True, P.range_extra)
    assert rg.entry_gate(1, "SOL", R("down", smooth=-0.5))[0] is False          # i rimbalzi in un ribasso non si comprano
    assert rg.entry_gate(1, "SOL", R("range"))[0] is False
    assert rg.entry_gate(1, "SOL", R("range", turn="up", smooth=-0.5))[0] is False   # inversione ma ancora troppo in basso


def test_gate_switch_disables_the_filter_only():
    off = rg.RegimeParams(gate=False)
    assert rg.entry_gate(-1, "SOL", R("up", smooth=0.9), off) == (True, 0)
    assert rg.entry_gate(1, "SOL", R("down", smooth=-0.9), off) == (True, 0)
    # il resto (protezione, uscita su inversione) resta attivo
    assert rg.ratchet(1, 100.0, 99.0, 101.2, 101.2, 1.0, off)[0] == "sl"
    assert rg.flip_exit(-1, "SOL", 0.4, R("up", smooth=0.5), off) is not None


def test_management_closes_adds_flip_and_protect_without_duplicates():
    pos = [{"symbol": "SOL", "side": -1, "cur_r": 0.4, "trade_type": "scalp"},
           {"symbol": "ADA", "side": -1, "cur_r": 0.4, "trade_type": "scalp"},
           {"symbol": "DOT", "side": 1, "cur_r": 0.4, "trade_type": "scalp"}]
    decisions = [{"symbol": "ADA", "action": "close"}]
    got = rg.management_closes(pos, decisions, R("up", smooth=0.5), {"DOT": 101.0})
    syms = {d["symbol"]: d["close_why"] for d in got}
    assert syms == {"SOL": "chiusura regime", "DOT": "chiusura profitto protetto"}


def test_apply_ratchet_moves_the_stop_of_engine_positions():
    from types import SimpleNamespace as NS
    pos = NS(side=1, entry=100.0, sl=99.0, entry0=100.0, r_dist=0.01, px_hi=101.3, px_lo=99.8)
    moved = rg.apply_ratchet({"SOL": pos}, {"SOL": 101.0})
    assert moved == {} and abs(pos.sl - 100.25) < 1e-9                   # pareggio a +0.25R (R = 1.0)
    pos2 = NS(side=1, entry=100.0, sl=99.0, entry0=100.0, r_dist=0.01, px_hi=101.9, px_lo=99.8)
    closes = rg.apply_ratchet({"SOL": pos2}, {"SOL": 100.5})                         # prezzo gia' sotto il livello 101.3: chiudi
    assert set(closes) == {"SOL"} and abs(closes["SOL"] - 101.3) < 1e-9


def test_entry_gate_ignores_commodities_and_bad_side():
    for sd in (1, -1):
        assert rg.entry_gate(sd, "XAU", R("up", smooth=0.9)) == (True, 0)
    assert rg.entry_gate(0, "SOL", R("up"))[0] is False


# ---------------------------------------------------------------- gestione
def test_r_metrics():
    assert rg.r_metrics(1, 100.0, 102.0, 103.0, 1.0) == (2.0, 3.0)
    assert rg.r_metrics(-1, 100.0, 98.0, 97.0, 1.0) == (2.0, 3.0)
    assert rg.r_metrics(1, 100.0, 102.0, 103.0, 0.0) == (0.0, 0.0)


def test_ratchet_breakeven_then_trailing_long():
    # 1R = 1.0; stop iniziale 99
    assert rg.ratchet(1, 100.0, 99.0, 100.5, 100.8, 1.0)[0] == "none"                 # picco 0.8R: ancora niente
    k, lvl = rg.ratchet(1, 100.0, 99.0, 101.2, 101.2, 1.0)                              # picco 1.2R: pareggio
    assert (k, round(lvl, 4)) == ("sl", round(100.0 + P.be_lock_r, 4))
    k, lvl = rg.ratchet(1, 100.0, 100.25, 101.9, 101.9, 1.0)                            # picco 1.9R: segue a -0.6R
    assert (k, round(lvl, 4)) == ("sl", 101.3)


def test_ratchet_never_loosens_and_short_is_symmetric():
    assert rg.ratchet(1, 100.0, 101.5, 102.0, 102.0, 1.0)[0] == "none"                 # stop gia' piu' alto
    k, lvl = rg.ratchet(-1, 100.0, 101.0, 98.8, 98.8, 1.0)
    assert (k, round(lvl, 4)) == ("sl", round(100.0 - P.be_lock_r, 4))
    k, lvl = rg.ratchet(-1, 100.0, 99.75, 98.1, 98.1, 1.0)
    assert (k, round(lvl, 4)) == ("sl", 98.7)
    assert rg.ratchet(-1, 100.0, 98.5, 99.0, 98.1, 1.0)[0] == "none"                   # nuovo livello 98.7 > stop 98.5: non migliora


def test_ratchet_closes_if_price_already_back_through_the_level():
    k, lvl = rg.ratchet(1, 100.0, 99.0, 100.1, 101.6, 1.0)      # picco 1.6R -> livello 101.0; prezzo 100.1 e' sotto
    assert k == "close" and abs(lvl - 101.0) < 1e-9


def test_ratchet_can_be_disabled():
    off = rg.RegimeParams(ratchet=False)
    assert rg.ratchet(1, 100.0, 99.0, 101.6, 101.6, 1.0, off)[0] == "none"


def test_flip_exit():
    assert rg.flip_exit(-1, "SOL", 0.4, R("up", smooth=0.5)) is not None
    assert rg.flip_exit(-1, "SOL", -0.8, R("up", smooth=0.5)) is None            # gia' oltre -0.5R: decide lo stop
    assert rg.flip_exit(1, "SOL", 0.4, R("down", smooth=-0.5)) is not None
    assert rg.flip_exit(1, "SOL", 0.4, R("range", turn="down", smooth=-0.2)) is not None
    assert rg.flip_exit(-1, "SOL", 0.4, R("down", smooth=-0.5)) is None
    assert rg.flip_exit(-1, "XAU", 0.4, R("up", smooth=0.5)) is None
    assert rg.flip_exit(-1, "SOL", 0.4, R("up"), rg.RegimeParams(flip_exit=False)) is None


# ---------------------------------------------------------------- rules_decisions
def opens(decs):
    return {d["symbol"]: d["action"] for d in decs if d["action"].startswith("open")}


def test_without_regime_behaviour_is_unchanged():
    readings = [rd("SOL", 20, 70), rd("ADA", 70, 20), rd("DOT", 50, 50), rd("LTC", 20, 58)]
    got = opens(rules_decisions(readings, [], set(), 60))
    assert got == {"SOL": "open_short", "ADA": "open_long"}


def test_bear_regime_blocks_longs_keeps_shorts():
    readings = [rd("SOL", 20, 70), rd("ADA", 70, 20)]
    got = opens(rules_decisions(readings, [], set(), 60, regime=R("down", smooth=-0.5)))
    assert got == {"SOL": "open_short"}


def test_bull_regime_blocks_shorts_keeps_longs():
    readings = [rd("SOL", 20, 70), rd("ADA", 70, 20)]
    got = opens(rules_decisions(readings, [], set(), 60, regime=R("up", smooth=0.5)))
    assert got == {"ADA": "open_long"}


def test_blocked_top_side_falls_back_to_the_allowed_one_if_it_passes_the_threshold():
    readings = [rd("SOL", 66, 68)]          # lo short vince di poco, ma il mercato e' rialzista e il long supera la soglia
    decs = rules_decisions(readings, [], set(), 60, regime=R("up", smooth=0.5), tier_fn=lambda s: 63)
    assert opens(decs) == {"SOL": "open_long"} and decs[0]["confidence"] == 66
    assert "consentito" in decs[0]["reason"]
    assert opens(rules_decisions([rd("SOL", 60, 68)], [], set(), 60, regime=R("up", smooth=0.5),
                                 tier_fn=lambda s: 63)) == {}      # il long non arriva alla soglia


def test_range_requires_extra_points_and_tier_threshold():
    r = R("range")
    assert opens(rules_decisions([rd("SOL", 20, 65)], [], set(), 60, regime=r, tier_fn=lambda s: 63)) == {}       # 65 < 63+3
    assert opens(rules_decisions([rd("SOL", 20, 66)], [], set(), 60, regime=r, tier_fn=lambda s: 63)) == {"SOL": "open_short"}


def test_regime_closes_positions_against_the_market_but_not_deep_losers():
    pos = [{"symbol": "SOL", "side": -1, "cur_r": 0.3}, {"symbol": "ADA", "side": -1, "cur_r": -0.9}]
    readings = [rd("SOL", 40, 55), rd("ADA", 40, 55)]
    decs = rules_decisions(readings, pos, {"SOL", "ADA"}, 60, regime=R("up", smooth=0.5))
    closes = {d["symbol"]: d["reason"] for d in decs if d["action"] == "close"}
    assert set(closes) == {"SOL"} and "mercato girato" in closes["SOL"]


def test_signal_flip_close_still_works_with_regime():
    pos = [{"symbol": "SOL", "side": -1, "cur_r": 0.3}]
    decs = rules_decisions([rd("SOL", 70, 30)], pos, {"SOL"}, 60, regime=R("down", smooth=-0.5))
    assert [d["action"] for d in decs] == ["close"] and "segnale sceso" in decs[0]["reason"]


def test_only_manage_never_opens():
    decs = rules_decisions([rd("SOL", 20, 80)], [], set(), 60, only_manage=True, regime=R("down", smooth=-0.5))
    assert decs == []


def test_production_profile_is_filter_only(monkeypatch):
    import importlib
    for k in ("DESK_REGIME_RATCHET", "DESK_REGIME_FLIP", "DESK_REGIME_RANGE_EXTRA"):
        monkeypatch.delenv(k, raising=False)
    d = importlib.reload(rg).DEFAULT
    assert d.gate is True and d.ratchet is False and d.flip_exit is False and d.range_extra == 0
    assert d.capitulation_roc == -0.03 and d.long_needs_up is True and d.block_short_in_up is True
    # con il profilo di produzione lo stop non si muove e non ci sono chiusure per inversione
    assert rg.ratchet(1, 100.0, 99.0, 102.0, 103.0, 1.0, d) == ("none", 0.0)
    assert rg.flip_exit(1, "SOL", 0.4, R("down"), d) is None
    # il banco di prova usa il profilo completo
    assert rg.FULL.ratchet is True and rg.FULL.flip_exit is True and rg.FULL.range_extra == 3
