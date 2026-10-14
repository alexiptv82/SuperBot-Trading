"""Test del laboratorio strategie: nessuna rete, solo dati sintetici."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import strategy_lab as sl  # noqa: E402


def make_bars(o, h, l, c, v=None, tf=sl.M15):
    n = len(o)
    return sl.Bars(np.arange(n, dtype=np.int64) * tf, np.array(o, float), np.array(h, float),
                   np.array(l, float), np.array(c, float),
                   np.array(v if v is not None else [1.0] * n, float))


def flat(n, p=100.0):
    return make_bars([p] * n, [p] * n, [p] * n, [p] * n)


def sig_at(n, idx_side: dict, atr=1.0, tgt=None):
    side = np.zeros(n, dtype=np.int8)
    for i, s in idx_side.items():
        side[i] = s
    t = np.full(n, np.nan) if tgt is None else np.full(n, float(tgt))
    return sl.Sig(side, np.full(n, float(atr)), t)


def random_walk(n=9000, seed=7):
    rng = np.random.default_rng(seed)
    r = rng.normal(0, 0.002, n)
    c = 100 * np.exp(np.cumsum(r))
    o = np.r_[100.0, c[:-1]]
    spread = np.abs(rng.normal(0, 0.0015, n))
    h = np.maximum(o, c) * (1 + spread)
    l = np.minimum(o, c) * (1 - spread)
    v = rng.lognormal(0, 0.5, n)
    t = np.arange(n, dtype=np.int64) * sl.M15
    return sl.Bars(t, o, h, l, c, v)


# ---------------------------------------------------------------- aggregazione
def test_aggregate_ohlc_and_drops_incomplete():
    n = 12  # 3 ore da 4 barre
    o = np.arange(n) + 100.0
    b = make_bars(o, o + 5, o - 5, o + 1)
    b = sl.Bars(*(a[[i for i in range(n) if i != 6]] for a in (b.t, b.o, b.h, b.l, b.c, b.v)))
    h1 = sl.aggregate(b, sl.H1)
    assert len(h1) == 2                      # il gruppo con la barra mancante e' scartato
    assert h1.o[0] == 100 and h1.c[0] == 104 and h1.h[0] == 108 and h1.l[0] == 95
    assert h1.v[0] == 4
    assert h1.t[1] == 2 * sl.H1


def test_align_htf_uses_only_closed_bars():
    base = flat(16)                           # 4 ore di barre da 15m
    h1 = sl.aggregate(base, sl.H1)
    vals = np.array([10.0, 11.0, 12.0, 13.0])
    out = sl.align_htf(base.t, sl.M15, h1, sl.H1, vals)
    assert np.isnan(out[0]) and np.isnan(out[2])      # la barra 1h 0 chiude alla fine di base[3]
    assert out[3] == 10.0                              # base[3] chiude alle 01:00: barra 0 completa
    assert out[4] == 10.0 and out[6] == 10.0           # durante l'ora 1 vale ancora la barra 0
    assert out[7] == 11.0
    assert out[15] == 13.0


# ----------------------------------------------------------- niente look-ahead
def prefix_equal(builder, b15, k, tf):
    full = builder(sl.build_frames(b15))
    cut_frames = sl.build_frames(b15.head(k))
    cut = builder(cut_frames)
    base_full, base_cut = sl.build_frames(b15)[tf], cut_frames[tf]
    idx = {int(t): i for i, t in enumerate(base_full.t)}
    for j, t in enumerate(base_cut.t):
        i = idx[int(t)]
        if full.side[i] != cut.side[j]:
            return False
        for a, b in ((full.atr, cut.atr), (full.tgt, cut.tgt)):
            if not (np.isnan(a[i]) and np.isnan(b[j])) and not np.isclose(a[i], b[j]):
                return False
    return True


def test_strategies_do_not_look_ahead():
    b15 = random_walk()
    for st in sl.STRATEGIES:
        for k in (5000, 7123, 8800):
            assert prefix_equal(st.build, b15, k, st.tf), f"look-ahead in {st.name} (k={k})"


def test_prefix_check_detects_a_leaky_builder():
    def leaky(a):
        b = a["1h"]
        ahead = np.r_[b.c[30:], np.full(30, b.c[-1])]
        side = np.where(ahead > b.c, 1, -1).astype(np.int8)  # usa il futuro (30 barre)
        return sl.Sig(side, np.ones(len(b)), np.full(len(b), np.nan))
    assert not prefix_equal(leaky, random_walk(), 7000, "1h")


def test_htf_alignment_dense_series_is_prefix_stable():
    b15 = random_walk()
    for k in (5001, 6677, 8443):
        fa, fc = sl.build_frames(b15), sl.build_frames(b15.head(k))
        for tf, ms_ in (("1h", sl.H1), ("4h", sl.H4)):
            full = sl.align_htf(fa["15m"].t, sl.M15, fa[tf], ms_, sl.ema(fa[tf].c, 20))
            cut = sl.align_htf(fc["15m"].t, sl.M15, fc[tf], ms_, sl.ema(fc[tf].c, 20))
            m = len(cut)
            assert np.allclose(full[:m], cut, equal_nan=True), f"allineamento {tf} k={k}"


def test_strategies_produce_some_signals():
    frames = sl.build_frames(random_walk(n=40000, seed=3))
    counts = {st.name: int((st.build(frames).side != 0).sum()) for st in sl.STRATEGIES}
    assert sum(counts.values()) > 0, counts


# ------------------------------------------------------------------- motore
def trade(b, sig, cfg, tf=sl.M15):
    return sl.run_strategy(b, sig, cfg, tf)


def test_entry_is_next_bar_open_and_stop_fills_at_stop():
    o = [100, 100.5, 100, 100, 100]
    h = [100, 100.5, 100, 100, 100]
    l = [100, 100.5, 97.5, 100, 100]
    c = [100, 100.5, 100, 100, 100]
    b = make_bars(o, h, l, c)
    cfg = sl.ExitCfg(stop_mult=2.0, max_hold=10)
    t = trade(b, sig_at(5, {0: 1}), cfg)
    assert len(t) == 1
    assert t[0]["entry"] == 100.5                      # apertura della barra 1, non la chiusura della 0
    assert t[0]["why"] == "stop" and abs(t[0]["exit"] - 98.5) < 1e-9
    assert abs(t[0]["gross"] - (98.5 / 100.5 - 1) * 1e4) < 1e-6


def test_gap_through_stop_fills_at_open():
    b = make_bars([100, 100, 96, 100], [100, 100, 96, 100], [100, 100, 96, 100], [100, 100, 96, 100])
    t = trade(b, sig_at(4, {0: 1}), sl.ExitCfg(stop_mult=2.0, max_hold=10))
    assert t[0]["exit"] == 96 and t[0]["why"] == "stop"


def test_target_in_r_multiples_and_stop_wins_when_both_touched():
    b = make_bars([100, 100, 100, 100], [100, 100, 105, 100], [100, 100, 99.9, 100], [100, 100, 100, 100])
    cfg = sl.ExitCfg(stop_mult=1.0, target_r=2.0, max_hold=10)
    t = trade(b, sig_at(4, {0: 1}), cfg)
    assert t[0]["why"] == "target" and abs(t[0]["exit"] - 102.0) < 1e-9
    b2 = make_bars([100, 100, 100, 100], [100, 100, 105, 100], [100, 100, 98.5, 100], [100, 100, 100, 100])
    t2 = trade(b2, sig_at(4, {0: 1}), cfg)
    assert t2[0]["why"] == "stop" and abs(t2[0]["exit"] - 99.0) < 1e-9


def test_target_needs_to_be_exceeded_not_just_touched():
    cfg = sl.ExitCfg(stop_mult=1.0, target_r=2.0, max_hold=2)
    touch = make_bars([100, 100, 100, 100], [100, 100, 102.0, 100], [100, 100, 99.9, 100], [100, 100, 100.5, 100])
    assert trade(touch, sig_at(4, {0: 1}), cfg)[0]["why"] == "time"
    through = make_bars([100, 100, 100, 100], [100, 100, 102.05, 100], [100, 100, 99.9, 100], [100, 100, 100.5, 100])
    assert trade(through, sig_at(4, {0: 1}), cfg)[0]["why"] == "target"


def test_short_side_sign():
    b = make_bars([100, 100, 100, 100], [100, 100, 101.5, 100], [100, 100, 100, 100], [100, 100, 100, 100])
    t = trade(b, sig_at(4, {0: -1}), sl.ExitCfg(stop_mult=1.0, max_hold=10))
    assert t[0]["side"] == -1 and t[0]["why"] == "stop"
    assert abs(t[0]["exit"] - 101.0) < 1e-9 and t[0]["gross"] < 0
    b2 = make_bars([100, 100, 100, 100], [100, 100, 100, 100], [100, 100, 97, 100], [100, 100, 100, 100])
    t2 = trade(b2, sig_at(4, {0: -1}), sl.ExitCfg(stop_mult=1.0, target_r=2.0, max_hold=10))
    assert t2[0]["why"] == "target" and abs(t2[0]["exit"] - 98.0) < 1e-9 and t2[0]["gross"] > 0


def test_trailing_stop_ratchets_up_only():
    n = 8
    highs = [100, 100, 105, 110, 110, 110, 110, 110]
    lows = [100, 100, 104, 108, 109, 106.5, 106.5, 106.5]
    closes = [100, 100, 105, 110, 109.5, 107, 107, 107]
    opens = [100, 100, 104, 108, 109.5, 109, 107, 107]
    b = make_bars(opens, highs, lows, closes)
    cfg = sl.ExitCfg(stop_mult=2.0, trail_mult=3.0, max_hold=20)
    t = trade(b, sig_at(n, {0: 1}, atr=1.0), cfg)
    # massimo 110 -> stop trailing 107; la barra 5 tocca 106.5 <= 107
    assert t[0]["why"] == "stop" and abs(t[0]["exit"] - 107.0) < 1e-9


def test_time_exit_at_close_and_donchian_exit_at_next_open():
    b = flat(10)
    t = trade(b, sig_at(10, {0: 1}), sl.ExitCfg(stop_mult=2.0, max_hold=3))
    assert t[0]["why"] == "time" and abs(t[0]["hold_h"] - 3 * 0.25) < 1e-9
    # uscita Donchian: dopo 12 barre piatte la chiusura scende sotto il minimo delle 10 precedenti
    o = [100.0] * 14
    h = [100.0] * 14
    l = [100.0] * 14
    c = [100.0] * 14
    c[11] = 99.0
    l[11] = 99.0
    o[12] = 98.0
    b2 = make_bars(o, h, l, c)
    cfg = sl.ExitCfg(stop_mult=50.0, donch_exit=10, max_hold=13)
    t2 = trade(b2, sig_at(14, {0: 1}), cfg)
    assert t2[0]["why"] == "donchian" and t2[0]["exit"] == 98.0


def test_one_position_at_a_time_and_reentry_after_exit():
    # stop toccato sulla barra 2; segnali sulle barre 1 (bloccato), 2 (ammesso, nuova entrata alla barra 3)
    o = [100] * 8
    h = [100] * 8
    l = [100, 100, 98.0, 100, 100, 100, 100, 100]
    c = [100] * 8
    b = make_bars(o, h, l, c)
    t = trade(b, sig_at(8, {0: 1, 1: 1, 2: 1}), sl.ExitCfg(stop_mult=1.0, max_hold=2))
    assert [x["t"] for x in t] == [1 * sl.M15, 3 * sl.M15]


def test_absolute_target_on_wrong_side_is_skipped():
    b = flat(6)
    t = trade(b, sig_at(6, {0: 1}, tgt=99.0), sl.ExitCfg(stop_mult=1.0, abs_target=True, max_hold=3))
    assert t == []
    t2 = trade(b, sig_at(6, {0: 1}, tgt=101.0), sl.ExitCfg(stop_mult=1.0, abs_target=True, max_hold=3))
    assert len(t2) == 1


# ------------------------------------------------------------- statistiche
def test_costs_and_funding_only_on_longs():
    long_t = {"t": 0, "side": 1, "entry": 100, "exit": 100.5, "why": "time", "hold_h": 16.0, "gross": 50.0}
    short_t = dict(long_t, side=-1)
    sl_ = sl.stats([long_t])
    ss = sl.stats([short_t])
    assert abs(sl_["fund"] - 2.0) < 1e-9 and ss["fund"] == 0.0
    assert abs(sl_["A"] - (50 - 16 - 2)) < 1e-9
    assert abs(sl_["B"] - (50 - 10 - 2)) < 1e-9 and abs(ss["C"] - (50 - 4)) < 1e-9


def test_tier_rules():
    good = {"n": 30, "gross": 25.0, "A": 5.0, "B": 10.0}
    weak = {"n": 30, "gross": 12.0, "A": -4.0, "B": 2.0}
    pool = {"dev": good, "val": good, "test": good}
    sym = {"BTC": {p: good for p in pool}, "ETH": {p: good for p in pool}}
    assert sl.evaluate_tiers(pool, sym)["strict"]
    pool2 = {"dev": good, "val": weak, "test": good}
    r = sl.evaluate_tiers(pool2, sym)
    assert not r["strict"] and r["cond"]
    few = dict(good, n=10)
    assert not sl.evaluate_tiers({"dev": good, "val": few, "test": good}, sym)["cond"]
    neg_sym = {"BTC": {p: good for p in pool}, "ETH": {p: dict(good, gross=-1.0) for p in pool}}
    assert not sl.evaluate_tiers(pool, neg_sym)["strict"]


def test_period_assignment_by_entry_time():
    tr = [{"t": sl.ms(2023, 12, 31)}, {"t": sl.ms(2024, 1, 1)}, {"t": sl.ms(2026, 8, 10)}]
    assert len(sl.in_period(tr, "dev")) == 1 and len(sl.in_period(tr, "val")) == 1
    assert len(sl.in_period(tr, "fresh")) == 1 and len(sl.in_period(tr, "test")) == 0
