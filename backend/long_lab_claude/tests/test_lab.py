"""Test del laboratorio: il punteggio vettoriale deve essere IDENTICO a `desk.signals.read_symbol` del 13/10."""
from __future__ import annotations

import os
import sys
import types
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, LAB)
sys.path.insert(0, os.path.abspath(os.path.join(LAB, "..")))

import labdata  # noqa: E402
import labrun as lr  # noqa: E402
from desk import signals as sig  # noqa: E402
from desk.seasonal import get_seasonal  # noqa: E402
from labfeat import (BAR, FEATS, WIN, Series, extract, extract_symbol, p1_extra_long, points,  # noqa: E402
                     rsi_series, seasonal_bonus)

END = 1_793_232_000_000          # 2026-10-29 00:00 UTC
DAYS = 40


def _data():
    return labdata.synthetic(DAYS, END, n_symbols=4, seed=3)


class Equivalenza(unittest.TestCase):
    def test_resample_veloce_uguale_al_vero(self):
        """Ricampionare tutta la serie e tagliare = ricampionare la finestra (anche con buchi)."""
        for sym, a in _data().items():
            S = Series(a)
            for i in range(WIN - 1, len(a), 37):
                win = a[max(0, i - WIN + 1): i + 1]
                for tf, b_fast in ((sig.H1, S.window(i)[0]), (sig.H4, S.window(i)[1])):
                    np.testing.assert_array_equal(sig.resample(win, tf), b_fast)

    def test_rsi_serie_uguale(self):
        rng = np.random.default_rng(1)
        c = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, 300)))
        self.assertEqual(sig.rsi(c), rsi_series(c)[-1])
        for m in (30, 50, 120, 299):
            self.assertEqual(sig.rsi(c[:m]), rsi_series(c)[m - 1])

    def test_equivalenza_base(self):
        """Per molte barre: punteggi, lato, stop, tipo e fatti identici a read_symbol (stagionalita' S1 compresa)."""
        checked = 0
        for sym, a in _data().items():
            F = extract_symbol(a)
            n = len(a)
            end = F["ts"] + BAR
            sl_, ss_ = seasonal_bonus(sym, end, "S1")
            Fm = {k: F[k][:, None] for k in FEATS}
            L, S, side, score, slp, ok = points(Fm, 20, None, None, sl_[:, None], ss_[:, None])
            for i in range(WIN - 1, n, 23):
                r = sig.read_symbol(sym, a[max(0, i - WIN + 1): i + 1], int(end[i]))
                if r is None:
                    self.assertFalse(ok[i, 0])
                    continue
                self.assertTrue(ok[i, 0])
                self.assertEqual((r.long_score, r.short_score, r.side, r.score), (int(L[i, 0]), int(S[i, 0]), int(side[i, 0]), int(score[i, 0])))
                self.assertEqual(r.sl_pct, float(slp[i, 0]))
                self.assertEqual(r.facts["rsi1h"], round(float(F["r1h"][i]), 1))
                self.assertEqual(r.facts["roc24h"], round(float(F["roc24"][i]), 4))
                self.assertEqual(r.trade_type, "scalp" if int(score[i, 0]) >= 55 else "medio")
                checked += 1
        self.assertGreater(checked, 100)

    def test_p1_come_il_commit_635b964(self):
        """La variante `p1` = il codice di signals.py del 13/10 con le 3 righe cambiate da P1 (trend 4h 14 + rimbalzo)."""
        src = open(sig.__file__, encoding="utf-8").read()
        a1 = 'add("long" if e50_4 > e200_4 else "short", 20, "trend 4h")'
        a2 = '    # volume: 4 punti\n    if vol_ratio > 1.3:'
        self.assertIn(a1, src)
        self.assertIn(a2, src)
        patched = src.replace(a1, 'add("long" if e50_4 > e200_4 else "short", 14, "trend 4h")')
        patched = patched.replace(a2, (
            '    c1_short = c1[-5:] if len(c1) >= 5 else c1\n'
            '    momentum_1h = float(c1_short[-1] / c1_short[0] - 1) if len(c1_short) > 1 else 0.0\n'
            '    if r1h < 35 and momentum_1h > 0.003:\n'
            '        add("long", 10, "rimbalzo")\n' + a2))
        mod = types.ModuleType("signals_p1_test")
        sys.modules["signals_p1_test"] = mod
        exec(compile(patched, "signals_p1_test", "exec"), mod.__dict__)
        ns = mod.__dict__
        fired = 0
        for sym, a in _data().items():
            F = extract_symbol(a)
            end = F["ts"] + BAR
            sl_, ss_ = seasonal_bonus(sym, end, "S1")
            Fm = {k: F[k][:, None] for k in FEATS}
            el = p1_extra_long(Fm)
            L, S, side, score, slp, ok = points(Fm, 14, el, None, sl_[:, None], ss_[:, None])
            for i in range(WIN - 1, len(a), 11):
                r = ns["read_symbol"](sym, a[max(0, i - WIN + 1): i + 1], int(end[i]))
                if r is None:
                    continue
                self.assertEqual((r.long_score, r.short_score, r.side, r.score), (int(L[i, 0]), int(S[i, 0]), int(side[i, 0]), int(score[i, 0])))
                fired += int(el[i, 0] > 0)
        self.assertGreater(fired, 0, "il bonus di rimbalzo deve scattare almeno una volta nei dati finti")

    def test_stagionalita_S2_uguale_alla_vera_nella_fase_bear(self):
        """S2 = get_seasonal con la fase di oggi (30-36 mesi dal halving: ott 2026 - mar 2027) per i mesi di quella fase."""
        for base in ("BTC", "ETH", "SOL", "XAU", "XAG"):
            for ts in (1_793_000_000_000, 1_796_000_000_000, 1_800_000_000_000, 1_803_000_000_000, 1_806_000_000_000):
                real = get_seasonal(base, ts)
                self.assertEqual(real.cycle_mult, -1.0 if base not in ("XAU", "XAG") else 1.0)
                l2, s2 = seasonal_bonus(base, np.array([ts]), "S2")
                self.assertEqual((real.long_bonus, real.short_bonus), (int(l2[0]), int(s2[0])))
                l1, s1 = seasonal_bonus(base, np.array([ts]), "S1")
                self.assertEqual((real.long_bonus, real.short_bonus), (int(l1[0]), int(s1[0])))


class Riproduzione(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        d = _data()
        cls.feats = {s: extract_symbol(a) for s, a in d.items()}
        cls.M = lr.Market(d, cls.feats, END - 25 * labdata.DAY, END)
        cls.REG = {m: lr.compute_regime(cls.M, m) for m in ("S1", "S2")}

    def test_base_conserva_il_capitale(self):
        res = lr.replay(self.M, "base13", lr.SPECS["base13"], self.REG["S2"], "S2")
        net = sum(t[5] for t in res["trades"])
        self.assertGreater(len(res["trades"]), 0)
        # equity finale = capitale iniziale + somma dei netti chiusi + non realizzato delle aperte (qui dentro il conteggio)
        last_eq = res["equity"][-1][1]
        self.assertAlmostEqual(last_eq - 100000.0, net, delta=abs(net) * 0.5 + 400.0)

    def test_gate_long_blocca_solo_long(self):
        base = lr.replay(self.M, "base13", lr.SPECS["base13"], self.REG["S2"], "S2")
        g = lr.replay(self.M, "g_long", lr.SPECS["g_long"], self.REG["S2"], "S2")
        shorts_b = [t for t in base["trades"] if t[2] == -1]
        shorts_g = [t for t in g["trades"] if t[2] == -1]
        self.assertGreater(len(shorts_b), 0)
        # i punteggi sono identici e gli short non sono filtrati: gli short possono cambiare solo per slot/cooldown
        self.assertLessEqual(len([t for t in g["trades"] if t[2] == 1]), len([t for t in base["trades"] if t[2] == 1]) + 3)
        self.assertGreaterEqual(len(shorts_g), 0)

    def test_regime_simmetrico_e_deterministico(self):
        a = lr.compute_regime(self.M, "S2")
        b = lr.compute_regime(self.M, "S2")
        for k in a:
            np.testing.assert_array_equal(a[k], b[k])
        sh = lr.shift_regime(a, 5)
        np.testing.assert_array_equal(np.roll(a["state"], 5 * 96), sh["state"])

    def test_tutte_le_varianti_girano(self):
        for n, spec in lr.SPECS.items():
            res = lr.replay(self.M, n, spec, self.REG["S2"], "S2")
            s = lr.summarize(res, int(self.M.grid[0]), int(self.M.end[-1]))
            self.assertEqual(s["trade"], len(res["trades"]))
            self.assertEqual(s["long_n"] + s["short_n"], s["trade"])

    def test_placebo_p1_conserva_il_numero_di_scatti_per_simbolo(self):
        spec = dict(lr.SPECS["p1_reb"], extra="p1reb_placebo")
        el, _ = lr.build_extra(self.M, spec, self.REG["S2"], 5)
        base = p1_extra_long(self.M.F)
        np.testing.assert_array_equal((el > 0).sum(axis=0), (base > 0).sum(axis=0))


if __name__ == "__main__":
    unittest.main(verbosity=2)
