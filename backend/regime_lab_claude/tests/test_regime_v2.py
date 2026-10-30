"""Test del lettore di regime v2: specchio esatto, causalita', equivalenza batch/vivo, buchi, isteresi, dati sporchi."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import regime_v2 as rg  # noqa: E402

BAR = 900_000
T0 = 1_767_225_600_000                    # 2026-01-01 00:00 UTC, multiplo di 4h


def make_base(n=6000, seed=3, drift=None, noise=0.0011, start=T0):
    """Passeggiata con tratti di salita/discesa/laterale, 15m."""
    rng = np.random.default_rng(seed)
    if drift is None:
        seg = np.repeat(rng.choice([-1.0, 0.0, 1.0], size=n // 500 + 2), 500)[:n] * 0.0007
    else:
        seg = drift
    r = rng.normal(0, noise, n) + seg
    c = 100.0 * np.exp(np.cumsum(r))
    o = np.concatenate([[c[0]], c[:-1]])
    h = np.maximum(o, c) * (1 + np.abs(rng.normal(0, 0.0005, n)))
    l = np.minimum(o, c) * (1 - np.abs(rng.normal(0, 0.0005, n)))
    return dict(ts=start + np.arange(n, dtype=np.int64) * BAR, o=o, h=h, l=l, c=c, v=rng.uniform(1, 10, n))


def mirror(b):
    return dict(ts=b["ts"], o=-b["o"], h=-b["l"], l=-b["h"], c=-b["c"], v=b["v"])


def cut(b, a, z):
    return {k: v[a:z] for k, v in b.items()}


def same(x, y, tol=0.0):
    x, y = np.asarray(x, float), np.asarray(y, float)
    return np.array_equal(np.isnan(x), np.isnan(y)) and np.allclose(np.nan_to_num(x), np.nan_to_num(y), atol=tol, rtol=0)


class TestMirror(unittest.TestCase):
    def test_exact_mirror(self):
        for seed in (1, 2, 3):
            b = make_base(seed=seed)
            a, m = rg.compute_series(b), rg.compute_series(mirror(b))
            for k in ("D", "K", "dD"):
                self.assertTrue(same(a[k], -m[k], 1e-12), k)
            for k in ("ER", "VR"):
                self.assertTrue(same(a[k], m[k], 1e-12), k)
            self.assertTrue(np.array_equal(rg.MIRROR[a["raw"]], m["raw"]))
            self.assertTrue(np.array_equal(rg.MIRROR[a["state"]], m["state"]))
            self.assertTrue(np.array_equal(rg.side_class(a["state"], rg.LONG), rg.side_class(m["state"], rg.SHORT)))
            self.assertTrue(np.array_equal(rg.side_class(a["state"], rg.SHORT), rg.side_class(m["state"], rg.LONG)))

    def test_all_states_symmetric_and_sets_disjoint(self):
        st = np.arange(11)
        self.assertTrue(np.array_equal(rg.MIRROR[rg.MIRROR[st]], st))
        self.assertTrue(np.array_equal(rg.side_class(st, rg.LONG), rg.side_class(rg.MIRROR[st], rg.SHORT)))
        self.assertTrue(rg._SHORT_ALIGNED.isdisjoint(rg._SHORT_OPPOSED))
        # uno stato non e' mai ALIGNED per entrambi i lati
        self.assertFalse(np.any((rg.side_class(st, rg.LONG) == rg.ALIGNED) & (rg.side_class(st, rg.SHORT) == rg.ALIGNED)))

    def test_states_all_reachable_on_synthetic(self):
        seen = set()
        for seed in range(1, 8):
            seen |= set(np.unique(rg.compute_series(make_base(seed=seed))["state"]).tolist())
        self.assertGreaterEqual(len(seen), 7, [rg.STATE_NAMES[s] for s in sorted(seen)])


class TestCausality(unittest.TestCase):
    def test_prefix_equals_full(self):
        b = make_base()
        full = rg.compute_series(b)
        for m in (1500, 2999, 4100):
            part = rg.compute_series(cut(b, 0, m))
            for k in ("D", "K", "dD", "ER", "VR"):
                self.assertTrue(same(part[k], full[k][:m]), (k, m))
            self.assertTrue(np.array_equal(part["state"], full["state"][:m]), m)

    def test_future_bar_changes_nothing_before_it(self):
        b = make_base()
        base = rg.compute_series(b)
        j = 3000
        b2 = {k: v.copy() for k, v in b.items()}
        b2["h"][j] *= 3.0
        b2["c"][j] *= 2.0
        b2["l"][j] *= 0.5
        alt = rg.compute_series(b2)
        for k in ("D", "K", "dD", "ER", "VR"):
            self.assertTrue(same(base[k][:j], alt[k][:j]), k)
        self.assertTrue(np.array_equal(base["state"][:j], alt["state"][:j]))

    def test_batch_equals_live_slice(self):
        b = make_base(n=7000)
        full = rg.compute_series(b)
        rng = np.random.default_rng(5)
        for t in rng.integers(1500, 7000, size=12):
            part = rg.compute_series(cut(b, int(t) - 1199, int(t) + 1))
            for k in ("D", "K", "dD", "ER", "VR"):
                self.assertTrue(same(part[k][-1:], full[k][t:t + 1], 1e-9), (k, t))
            self.assertEqual(part["state"][-1], full["state"][t], t)

    def test_read_regime_ignores_unclosed_bar_and_never_raises(self):
        b = make_base(n=2000)
        last_close = int(b["ts"][-1] + BAR)
        s_full = rg.read_regime(b, "BTC", now_ms=last_close)
        s_cut = rg.read_regime(b, "BTC", now_ms=last_close - 1)         # ultima barra non ancora chiusa
        self.assertEqual(s_full["as_of_close_ms"], last_close)
        self.assertEqual(s_cut["as_of_close_ms"], last_close - BAR)
        self.assertEqual(rg.read_regime(b, "BTC", now_ms=last_close + 10 * BAR)["fallback_reason"], "stale_data")
        self.assertEqual(rg.read_regime(cut(b, 0, 50), "BTC", now_ms=int(b["ts"][49] + BAR))["fallback_reason"], "insufficient_bars")
        bad = rg.read_regime({"ts": "x"}, "BTC", now_ms=1)
        self.assertEqual(bad["quality"], "degraded")
        self.assertEqual(bad["side_class"], {"LONG": "NEUTRAL", "SHORT": "NEUTRAL"})
        self.assertTrue(bad["fallback_reason"].startswith("exception:"))

    def test_deterministic_and_hash_stable(self):
        b = make_base()
        a1, a2 = rg.compute_series(b), rg.compute_series(b)
        self.assertTrue(np.array_equal(a1["state"], a2["state"]))
        self.assertEqual(rg.config_hash(rg.CLASSIC15, rg.Params()), rg.config_hash(rg.CLASSIC15, rg.Params()))
        self.assertNotEqual(rg.config_hash(rg.CLASSIC15, rg.Params()), rg.config_hash(rg.CLASSIC15, rg.Params(k_thr=0.3)))


class TestRobustness(unittest.TestCase):
    def test_gap_resets_warmup_and_recovers(self):
        b = make_base()
        keep = np.ones(len(b["ts"]), bool)
        keep[3000:3004] = False                                   # 4 barre 15m mancanti
        g = {k: v[keep] for k, v in b.items()}
        s = rg.compute_series(g)
        i = int(np.searchsorted(g["ts"], b["ts"][3003]))          # prima barra dopo il buco
        self.assertEqual(s["state"][i], rg.NA)
        self.assertEqual(s["state"][i + 20], rg.NA)               # 32 barre di avviamento per ogni timeframe
        self.assertNotEqual(s["state"][-1], rg.NA)                # poi si riprende
        self.assertTrue(np.all(np.isnan(s["D"][i:i + 5])))

    def test_flat_price_and_zero_range_bars(self):
        n = 2500
        b = dict(ts=T0 + np.arange(n, dtype=np.int64) * BAR, o=np.full(n, 50.0), h=np.full(n, 50.0), l=np.full(n, 50.0),
                 c=np.full(n, 50.0), v=np.ones(n))
        s = rg.compute_series(b)
        self.assertFalse(np.any(np.isnan(s["state"].astype(float))))
        valid = s["state"][s["state"] != rg.NA]
        self.assertTrue(len(valid) > 0 and np.all(valid == rg.RANGE))
        self.assertTrue(np.all(np.abs(s["D"][~np.isnan(s["D"])]) < 1e-9))

    def test_features_bounded(self):
        s = rg.compute_series(make_base(seed=9))
        for k in ("D", "K"):
            x = s[k][~np.isnan(s[k])]
            self.assertTrue(np.all(np.abs(x) <= 1.0 + 1e-12))
        x = s["ER"][~np.isnan(s["ER"])]
        self.assertTrue(np.all((x >= 0) & (x <= 1 + 1e-12)))

    def test_empty_and_short_inputs(self):
        e = dict(ts=np.empty(0, np.int64), o=np.empty(0), h=np.empty(0), l=np.empty(0), c=np.empty(0), v=np.empty(0))
        self.assertEqual(len(rg.compute_series(e)["state"]), 0)
        short = rg.compute_series(cut(make_base(), 0, 20))
        self.assertTrue(np.all(short["state"] == rg.NA))


class TestHysteresisAndAggregation(unittest.TestCase):
    P = rg.Params()

    def test_single_bar_spike_ignored_two_bars_switch(self):
        R, D = rg.RANGE, rg.DOWN_CLEAN
        raw = np.array([R] * 6 + [D] + [R] * 4 + [D, D] + [R] * 3, dtype=np.int8)
        st = rg.confirm(raw, self.P)
        self.assertEqual(st[0], rg.NA)                             # alla prima barra non esiste ancora una coppia
        self.assertTrue(np.all(st[1:11] == R))                     # il singolo D non cambia lo stato
        self.assertEqual(st[11], R)                                # il secondo D di fila ... e' la prima coppia
        raw2 = np.array([R] * 6 + [D, D] + [R] * 2, dtype=np.int8)
        st2 = rg.confirm(raw2, self.P)
        self.assertEqual(st2[6], R)                                # prima chiusura D: ancora RANGE
        self.assertEqual(st2[7], D)                                # seconda chiusura D: cambia
        self.assertEqual(st2[8], D)                                # un solo R non lo riporta indietro
        self.assertEqual(st2[9], R)                                # due R di fila si'

    def test_shock_is_immediate(self):
        raw = np.array([rg.DOWN_CLEAN] * 5 + [rg.SHOCK] + [rg.DOWN_CLEAN] * 3, dtype=np.int8)
        st = rg.confirm(raw, self.P)
        self.assertEqual(st[5], rg.SHOCK)
        self.assertEqual(st[6], rg.DOWN_CLEAN)                     # un solo SHOCK non cancella il regime di prima

    def test_na_is_immediate_and_not_bridged(self):
        D = rg.DOWN_CLEAN
        raw = np.array([D] * 6 + [rg.NA] + [D] * 4, dtype=np.int8)
        st = rg.confirm(raw, self.P)
        self.assertEqual(st[5], D)
        self.assertEqual(st[6], rg.NA)                             # dato mancante: subito NA
        self.assertEqual(st[7], rg.NA)                             # prima barra dopo il buco: nessuna coppia ancora
        self.assertEqual(st[8], D)                                 # coppia nuova dopo il buco: torna lo stato

    def test_lookback_cap_goes_to_range(self):
        raw = np.array([rg.DOWN_CLEAN, rg.DOWN_CLEAN] + [rg.UP_CLEAN, rg.DOWN_CLEAN] * 100, dtype=np.int8)
        st = rg.confirm(raw, self.P)
        self.assertEqual(st[-1], rg.RANGE)

    def test_aggregate_complete_only(self):
        ts = T0 + np.arange(10, dtype=np.int64) * BAR              # 2h30 di barre 15m, inizio su multiplo di 1h
        o = np.arange(10, dtype=float) + 100
        a = rg.aggregate(ts, o, o + 2, o - 1, o + 1, np.ones(10), BAR, 3_600_000)
        self.assertEqual(len(a["ts"]), 2)                          # il terzo bucket ha solo 2 barre: scartato
        self.assertEqual(a["o"][0], 100.0)
        self.assertEqual(a["c"][0], 104.0)                         # chiusura dell'ultima barra del bucket
        self.assertEqual(a["h"][0], 105.0)
        self.assertEqual(a["l"][0], 99.0)
        self.assertEqual(a["v"][0], 4.0)
        self.assertEqual(int(a["close_ms"][0]), int(ts[0] + 3_600_000))
        keep = np.ones(10, bool)
        keep[2] = False                                            # buco dentro il primo bucket
        b = rg.aggregate(ts[keep], o[keep], (o + 2)[keep], (o - 1)[keep], (o + 1)[keep], np.ones(9), BAR, 3_600_000)
        self.assertEqual(len(b["ts"]), 1)

    def test_market_median_and_min_symbols(self):
        b = make_base()
        res = {s: rg.compute_series(make_base(seed=sd)) for s, sd in (("BTC", 1), ("ETH", 2), ("SOL", 3), ("XRP", 4),
                                                                      ("ADA", 5), ("XAU", 6))}
        m = rg.market_series(res, res["BTC"]["close_ms"])
        self.assertEqual(int(np.nanmax(m["n_symbols"])), 5)       # oro escluso
        m2 = rg.market_series({k: res[k] for k in ("BTC", "ETH")}, res["BTC"]["close_ms"])
        self.assertTrue(np.all(m2["state"] == rg.NA))             # meno di 5 simboli: niente mercato inventato
        # specchio anche sul mercato
        resm = {s: rg.compute_series(mirror(make_base(seed=sd))) for s, sd in (("BTC", 1), ("ETH", 2), ("SOL", 3), ("XRP", 4),
                                                                              ("ADA", 5), ("XAU", 6))}
        mm = rg.market_series(resm, resm["BTC"]["close_ms"])
        self.assertTrue(np.array_equal(rg.MIRROR[m["state"]], mm["state"]))


class TestReversal(unittest.TestCase):
    def test_v_reversal_detected_before_ema_cross(self):
        n_half = 900
        drift = np.concatenate([np.full(n_half, -0.0012), np.full(n_half, 0.0012)])
        # avviamento: 700 barre laterali davanti
        drift = np.concatenate([np.zeros(700), drift])
        b = make_base(n=len(drift), seed=11, drift=drift, noise=0.0009)
        s = rg.compute_series(b)
        turn = 700 + n_half
        d = rg.DIR_OF_STATE[s["state"]]
        self.assertTrue(np.any(d[turn - 200:turn] == -1))          # prima della svolta e' giu'
        after = np.flatnonzero((d[turn:] == 1))
        self.assertTrue(len(after) > 0)
        first_v2 = int(after[0])
        # baseline: EMA20 > EMA50 sulle chiusure 1h
        agg = rg.aggregate(b["ts"], b["o"], b["h"], b["l"], b["c"], b["v"], BAR, 3_600_000)

        def ema(x, n):
            out, k = np.empty(len(x)), 2 / (n + 1)
            out[0] = x[0]
            for i in range(1, len(x)):
                out[i] = out[i - 1] + k * (x[i] - out[i - 1])
            return out
        cross = ema(agg["c"], 20) - ema(agg["c"], 50)
        t_ms = int(b["ts"][turn])
        j = np.flatnonzero((agg["close_ms"] >= t_ms) & (cross > 0))
        self.assertTrue(len(j) > 0)
        first_ema = int((agg["close_ms"][j[0]] - t_ms) // BAR)
        self.assertLess(first_v2, first_ema, (first_v2, first_ema))


if __name__ == "__main__":
    unittest.main(verbosity=2)
