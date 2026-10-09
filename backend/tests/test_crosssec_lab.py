"""Test del laboratorio cross-sezionale: nessuna rete, dati sintetici."""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import crosssec_lab as cs  # noqa: E402
import strategy_lab as sl  # noqa: E402

D1 = cs.D1


def test_monday_detection():
    assert cs.is_monday(sl.ms(2026, 10, 5) // D1)
    assert not cs.is_monday(sl.ms(2026, 10, 9) // D1)
    assert cs.is_monday(sl.ms(2020, 1, 6) // D1)


def test_select_weights_are_dollar_neutral_and_pick_extremes():
    score = np.arange(30, dtype=float)
    w = cs.select_weights(score, np.ones(30, bool))
    k = max(3, round(0.2 * 30))
    assert abs(w[w > 0].sum() - 1) < 1e-12 and abs(w[w < 0].sum() + 1) < 1e-12
    assert (w > 0).sum() == k and (w < 0).sum() == k
    assert w[-1] > 0 and w[0] < 0 and w[15] == 0
    assert cs.select_weights(score[:11], np.ones(11, bool)) is None
    avail = np.ones(30, bool)
    avail[-5:] = False                                  # le coppie non disponibili non entrano mai
    w2 = cs.select_weights(score, avail)
    assert (w2[-5:] == 0).all()


def trending_panel(n_syms=20, n_days=120, start_day=None):
    d0 = (sl.ms(2023, 1, 2) // D1) if start_day is None else start_day      # lunedi'
    rates = 0.001 * np.arange(n_syms)
    C = 100 * np.exp(np.outer(np.arange(n_days), rates))
    O = np.vstack([np.full(n_syms, 100.0), C[:-1]])
    return O, C, d0, rates


def test_momentum_earns_positive_spread_and_reversal_the_opposite():
    O, C, d0, rates = trending_panel()
    rows = cs.weekly_returns(O, C, d0, 7, +1)
    series = cs.run_variant(rows)
    assert len(series) >= 8
    k = max(3, round(0.2 * 20))
    expected = (np.expm1(7 * rates[-k:]).mean() - np.expm1(7 * rates[:k]).mean()) * 1e4
    assert abs(series[2]["gross"] - expected) / expected < 0.02
    rev = cs.run_variant(cs.weekly_returns(O, C, d0, 7, -1))
    assert abs(rev[2]["gross"] + series[2]["gross"]) / series[2]["gross"] < 0.02


def test_turnover_zero_when_weights_unchanged_and_two_on_first_week():
    O, C, d0, _ = trending_panel()
    series = cs.run_variant(cs.weekly_returns(O, C, d0, 7, +1))
    assert abs(series[0]["turnover"] - 2.0) < 1e-9
    assert abs(series[1]["turnover"]) < 1e-9            # stesso ordinamento -> stesse posizioni
    assert abs(series[1]["A"] - series[1]["gross"]) < 1e-9
    assert abs(series[0]["A"] - (series[0]["gross"] - 2.0 * cs.SIDE_COST["A"])) < 1e-9


def test_weights_do_not_depend_on_prices_from_the_rebalance_day_onward():
    rng = np.random.default_rng(4)
    n_syms, n_days = 25, 200
    d0 = sl.ms(2023, 1, 2) // D1
    C = 100 * np.exp(np.cumsum(rng.normal(0, 0.03, (n_days, n_syms)), axis=0))
    O = np.vstack([np.full(n_syms, 100.0), C[:-1]])
    rows = cs.weekly_returns(O, C, d0, 30, +1)
    day, w = rows[5][0], rows[5][1]
    d = day - d0
    C2, O2 = C.copy(), O.copy()
    C2[d:] *= rng.uniform(0.5, 2.0, (n_days - d, n_syms))     # il futuro cambia radicalmente
    O2[d + 1:] *= rng.uniform(0.5, 2.0, (n_days - d - 1, n_syms))
    rows2 = cs.weekly_returns(O2, C2, d0, 30, +1)
    w2 = [r[1] for r in rows2 if r[0] == day][0]
    assert np.array_equal(w, w2)


def test_permutation_pvalue_behaves():
    rng = np.random.default_rng(1)
    n_syms = 25
    d0 = sl.ms(2023, 1, 2) // D1
    rows = []
    for wk in range(40):
        score = rng.normal(size=n_syms)
        ret = rng.normal(0, 0.05, n_syms)
        w = cs.select_weights(score, np.ones(n_syms, bool))
        rows.append((d0 + 7 * wk, w, ret, np.ones(n_syms, bool)))
    series = cs.run_variant(rows)                         # selezione indipendente dai rendimenti
    obs = float(np.mean([s["gross"] for s in series]))
    p = cs.permutation_p(rows, obs, [True] * 40, 300, 1)
    assert p > 0.02
    assert cs.permutation_p(rows, 10_000.0, [True] * 40, 300, 1) <= 1 / 300 + 1e-9
    assert cs.permutation_p(rows, 0.0, [False] * 40, 300, 1) != cs.permutation_p(rows, 0.0, [False] * 40, 300, 1)  # nan


def test_evaluate_rules():
    good = {"A": 5.0}
    pp = {"dev": good, "val": good, "test": good}
    assert cs.evaluate(pp, 3.0, 0.005)["pass"]
    assert not cs.evaluate(pp, 2.0, 0.005)["pass"]
    assert not cs.evaluate(pp, 3.0, 0.02)["pass"]
    assert not cs.evaluate({"dev": good, "val": {"A": -1.0}, "test": good}, 3.0, 0.005)["pass"]


def test_end_to_end_with_cached_synthetic_data(tmp_path):
    cache = str(tmp_path)
    syms = [f"S{i}/USDT:USDT" for i in range(16)]
    json.dump(syms, open(os.path.join(cache, "universe.json"), "w"))
    n = (sl.DATA_END - sl.DATA_START) // sl.H1
    for i, s in enumerate(syms):
        rng = np.random.default_rng(100 + i)
        c = 100 * np.exp(np.cumsum(rng.normal(0, 0.004, n)))
        o = np.r_[100.0, c[:-1]]
        t = sl.DATA_START + np.arange(n) * sl.H1
        np.save(os.path.join(cache, f"{s.split('/')[0]}_1h_{sl.DATA_END}.npy"),
                np.column_stack([t, o, np.maximum(o, c), np.minimum(o, c), c, np.ones(n)]))

    class A:
        pass
    a = A()
    a.cache_dir, a.out, a.top_n, a.workers, a.annotate = cache, os.path.join(cache, "o.json"), 80, 2, False
    res = cs.run(a)
    assert set(res) == {"M30", "M7", "R7"}
    assert all(r["overall"]["weeks"] > 300 for r in res.values())
    assert not any(r["checks"]["pass"] for r in res.values())      # passeggiate casuali: nessun vantaggio
