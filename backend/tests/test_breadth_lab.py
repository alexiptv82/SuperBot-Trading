"""Test del laboratorio ampiezza: nessuna rete, solo dati sintetici."""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import breadth_lab as bl  # noqa: E402
import strategy_lab as sl  # noqa: E402


def walk(n=24 * 900, seed=1, drift=0.0):
    rng = np.random.default_rng(seed)
    r = rng.normal(drift, 0.004, n)
    c = 100 * np.exp(np.cumsum(r))
    o = np.r_[100.0, c[:-1]]
    sp = np.abs(rng.normal(0, 0.002, n))
    t = sl.DATA_START + np.arange(n, dtype=np.int64) * sl.H1
    return sl.Bars(t, o, np.maximum(o, c) * (1 + sp), np.minimum(o, c) * (1 - sp), c,
                   rng.lognormal(0, 0.4, n))


def test_select_universe_filters_and_sorts():
    markets = {
        "AAA/USDT:USDT": {"swap": True, "linear": True, "quote": "USDT", "active": True},
        "BBB/USDT:USDT": {"swap": True, "linear": True, "quote": "USDT", "active": True},
        "CCC/USDT:USDT": {"swap": True, "linear": True, "quote": "USDT", "active": False},
        "DDD/USD:USD": {"swap": True, "linear": False, "quote": "USD", "active": True},
        "EEE/USDT": {"swap": False, "linear": False, "quote": "USDT", "active": True},
        "FFF/USDT:USDT": {"swap": True, "linear": True, "quote": "USDT", "active": True},
    }
    tickers = {"AAA/USDT:USDT": {"quoteVolume": 5.0}, "BBB/USDT:USDT": {"quoteVolume": 9.0},
               "CCC/USDT:USDT": {"quoteVolume": 99.0}, "DDD/USD:USD": {"quoteVolume": 50.0},
               "EEE/USDT": {"quoteVolume": 70.0}, "FFF/USDT:USDT": {"quoteVolume": None}}
    assert bl.select_universe(tickers, markets, 10) == ["BBB/USDT:USDT", "AAA/USDT:USDT"]
    assert bl.select_universe(tickers, markets, 1) == ["BBB/USDT:USDT"]


def test_clustered_t_uses_monthly_means_not_trades():
    jan, feb, mar, apr = (sl.ms(2024, m, 10) for m in (1, 2, 3, 4))
    trades = ([{"t": jan, "gross": 10.0}] * 50 + [{"t": jan, "gross": 30.0}] * 50   # media di gennaio 20
              + [{"t": feb, "gross": 10.0}, {"t": mar, "gross": 0.0}, {"t": apr, "gross": 30.0}])
    t, months = bl.clustered_t(trades)
    m = np.array([20.0, 10.0, 0.0, 30.0])
    assert months == 4
    assert abs(t - m.mean() / (m.std(ddof=1) / 2.0)) < 1e-9
    assert np.isnan(bl.clustered_t(trades[:1])[0])


def test_frames_daily_drops_incomplete_days():
    b = walk(n=24 * 3)
    keep = np.ones(len(b), bool)
    keep[30] = False                                  # un'ora mancante nel giorno 2
    b2 = sl.Bars(*(a[keep] for a in (b.t, b.o, b.h, b.l, b.c, b.v)))
    fr = bl.frames_from_1h(b2)
    assert len(fr["1d"]) == 2 and len(fr["4h"]) == 17 and len(fr["1h"]) == 71


def test_donchian_daily_needs_history_and_follows_trend():
    b = walk(drift=0.0006, seed=3)
    fr = bl.frames_from_1h(b)
    sig = bl.sig_donch1d(fr)
    assert (sig.side[:50] == 0).all()                  # niente segnali senza i 50 giorni precedenti
    assert (sig.side == 1).sum() > (sig.side == -1).sum()
    st = [s for s in bl.breadth_strategies() if s.name == "S6_donchian_1d"][0]
    assert st.tf == "1d" and st.cfg.donch_exit == 20 and st.cfg.stop_mult == 3.0
    assert [s.tf for s in bl.breadth_strategies()] == ["4h", "1h", "1d"]


def test_daily_strategy_does_not_look_ahead():
    b = walk(n=24 * 500, seed=5)
    full_fr = bl.frames_from_1h(b)
    full = bl.sig_donch1d(full_fr)
    idx = {int(t): i for i, t in enumerate(full_fr["1d"].t)}
    for k in (24 * 200 + 7, 24 * 300 + 13, 24 * 450 + 1):
        cut_fr = bl.frames_from_1h(b.head(k))
        cut = bl.sig_donch1d(cut_fr)
        for j, t in enumerate(cut_fr["1d"].t):
            i = idx[int(t)]
            assert cut.side[j] == full.side[i]
            a, c = cut.atr[j], full.atr[i]
            assert (np.isnan(a) and np.isnan(c)) or np.isclose(a, c)


def test_control_trades_are_deterministic_and_zero_on_flat_prices():
    n = 24 * 60
    t = np.arange(n, dtype=np.int64) * sl.H1
    flat = sl.Bars(t, *(np.full(n, 100.0) for _ in range(4)), np.ones(n))
    sig = sl.Sig(np.zeros(n, dtype=np.int8), np.full(n, 1.0), np.full(n, np.nan))
    cfg = sl.ExitCfg(stop_mult=2.0, max_hold=20)
    trades = [{"e": 700, "side": 1}, {"e": 900, "side": -1}]
    a = bl.control_trades(flat, sig, cfg, trades, sl.H1, seed=1)
    b = bl.control_trades(flat, sig, cfg, trades, sl.H1, seed=1)
    assert a == b and len(a) == 6
    assert all(abs(x["gross"]) < 1e-9 for x in a)
    c = bl.control_trades(flat, sig, cfg, trades, sl.H1, seed=2)
    assert [x["t"] for x in c] != [x["t"] for x in a]


def test_evaluate_breadth_rules():
    ok = {"n": 150, "gross": 25.0, "A": 5.0}
    pp = {"dev": ok, "val": ok, "test": ok}
    assert bl.evaluate_breadth(pp, ok, 0.7, 12.0, 3.0)["pass"]
    assert not bl.evaluate_breadth(pp, ok, 0.5, 12.0, 3.0)["pass"]          # poche coppie positive
    assert not bl.evaluate_breadth(pp, ok, 0.7, 5.0, 3.0)["pass"]           # eccesso troppo basso
    assert not bl.evaluate_breadth(pp, ok, 0.7, 12.0, 2.0)["pass"]          # t per mese basso
    weak = dict(ok, gross=15.0)
    assert not bl.evaluate_breadth({"dev": ok, "val": weak, "test": ok}, ok, 0.7, 12.0, 3.0)["pass"]
    few = dict(ok, n=99)
    assert not bl.evaluate_breadth({"dev": ok, "val": ok, "test": few}, ok, 0.7, 12.0, 3.0)["pass"]
    assert not bl.evaluate_breadth(pp, ok, 0.7, float("nan"), 3.0)["pass"]


def test_end_to_end_with_cached_synthetic_data(tmp_path):
    cache = str(tmp_path)
    syms = [f"S{i}/USDT:USDT" for i in range(6)]
    json.dump(syms, open(os.path.join(cache, "universe.json"), "w"))
    n = (sl.DATA_END - sl.DATA_START) // sl.H1
    for i, s in enumerate(syms):
        rng = np.random.default_rng(10 + i)
        c = 100 * np.exp(np.cumsum(rng.normal(0, 0.004, n)))
        o = np.r_[100.0, c[:-1]]
        sp = np.abs(rng.normal(0, 0.002, n))
        t = sl.DATA_START + np.arange(n) * sl.H1
        arr = np.column_stack([t, o, np.maximum(o, c) * (1 + sp), np.minimum(o, c) * (1 - sp), c, np.ones(n)])
        np.save(os.path.join(cache, f"{s.split('/')[0]}_1h_{sl.DATA_END}.npy"), arr)

    class A:
        pass
    a = A()
    a.cache_dir, a.out, a.top_n, a.workers, a.annotate = cache, os.path.join(cache, "o.json"), 80, 2, False
    res = bl.run(a)
    assert set(res) == {"S1_donchian_4h", "S2_donchian_1h", "S6_donchian_1d"}
    # su passeggiate casuali nessuna variante deve superare le soglie
    assert not any(r["checks"]["pass"] for r in res.values())
    assert all(r["overall"]["n"] > 50 for r in res.values())
