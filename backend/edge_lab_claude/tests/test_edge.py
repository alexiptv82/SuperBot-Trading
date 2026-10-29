"""
Test unitari per le funzioni matematiche del laboratorio edge.
Nessuna chiamata a desk.engine o API esterne.
"""
import sys, os, unittest
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))   # edge_lab_claude/

from edge_strategies import (
    resample_4h, _compute_atr, generate_signals, BAR_15M, BAR_4H,
)


class TestResample4h(unittest.TestCase):

    def test_16_barre_15m_diventano_1_barra_4h(self):
        """16 candele consecutive da 15m → 1 candela da 4h."""
        ts0 = 1_700_000_000_000   # ts qualsiasi allineato a 4h
        ts0 = (ts0 // BAR_4H) * BAR_4H
        rows = []
        for i in range(16):
            ts = ts0 + i * BAR_15M
            o = 100.0 + i
            h = o + 0.5
            l = o - 0.5
            c = o + 0.1
            rows.append([ts, o, h, l, c])
        arr = np.array(rows)
        r4  = resample_4h(arr)
        self.assertEqual(r4.shape[0], 1)
        self.assertAlmostEqual(r4[0, 1], 100.0)           # open = prima open
        self.assertAlmostEqual(r4[0, 2], 115.5 + 0.5)     # high = massimo dei high
        self.assertAlmostEqual(r4[0, 3], 100.0 - 0.5)     # low  = minimo dei low
        self.assertAlmostEqual(r4[0, 4], rows[-1][4])      # close = ultima close

    def test_array_vuoto(self):
        arr = np.empty((0, 5))
        r4  = resample_4h(arr)
        self.assertEqual(r4.shape[0], 0)

    def test_due_barre_4h(self):
        """32 candele 15m → 2 barre 4h."""
        ts0 = (1_700_000_000_000 // BAR_4H) * BAR_4H
        rows = [[ts0 + i * BAR_15M, 1, 2, 0.5, 1.5] for i in range(32)]
        r4   = resample_4h(np.array(rows))
        self.assertEqual(r4.shape[0], 2)


class TestATR(unittest.TestCase):

    def test_atr_costante(self):
        """Con OHLC costanti l'ATR converge a 0."""
        n = 50
        h = np.ones(n) * 10.5
        l = np.ones(n) * 9.5
        c = np.ones(n) * 10.0
        atr = _compute_atr(h, l, c, period=14)
        # Dalla barra 14 in poi deve essere definito
        self.assertFalse(np.isnan(atr[14]))
        # Con barre piatte l'ATR deve essere ≤ 1.0 (range = 1)
        self.assertLessEqual(atr[14], 1.01)

    def test_atr_positivo(self):
        rng = np.random.RandomState(0)
        c   = np.cumsum(rng.randn(100)) + 100
        h   = c + rng.uniform(0.1, 1.0, 100)
        l   = c - rng.uniform(0.1, 1.0, 100)
        atr = _compute_atr(h, l, c)
        valid = atr[~np.isnan(atr)]
        self.assertTrue((valid > 0).all())


class TestGenerateSignals(unittest.TestCase):

    def _make_bars(self, n: int, trend: str = "up") -> np.ndarray:
        """Crea barre 4h con trend lineare."""
        ts0 = (1_700_000_000_000 // BAR_4H) * BAR_4H
        bars = []
        for i in range(n):
            px = 100.0 + (i if trend == "up" else -i)
            bars.append([ts0 + i * BAR_4H, px, px + 1, px - 1, px + 0.5])
        return np.array(bars)

    def test_trend_up_genera_long(self):
        bars = self._make_bars(60, trend="up")
        sigs = generate_signals(bars, lookback=20)
        sides = [v[0] for v in sigs.values()]
        self.assertTrue(any(s == 1 for s in sides), "nessun segnale LONG in uptrend")

    def test_trend_down_genera_short(self):
        bars = self._make_bars(60, trend="down")
        sigs = generate_signals(bars, lookback=20)
        sides = [v[0] for v in sigs.values()]
        self.assertTrue(any(s == -1 for s in sides), "nessun segnale SHORT in downtrend")

    def test_invert_inverte_lato(self):
        bars = self._make_bars(60, trend="up")
        sigs_norm = generate_signals(bars, lookback=20, invert=False)
        sigs_inv  = generate_signals(bars, lookback=20, invert=True)
        # Stesso numero di segnali
        self.assertEqual(len(sigs_norm), len(sigs_inv))
        # Lati opposti per ogni timestamp comune
        for ts in sigs_norm:
            if ts in sigs_inv:
                self.assertEqual(sigs_norm[ts][0], -sigs_inv[ts][0])

    def test_sl_tp_nel_range(self):
        bars = self._make_bars(60, trend="up")
        sigs = generate_signals(bars, lookback=20, atr_sl=2.0, atr_tp=4.0)
        for ts, (side, sl_pct, tp_pct) in sigs.items():
            self.assertGreater(sl_pct, 0)
            self.assertGreater(tp_pct, sl_pct)  # TP sempre > SL

    def test_nessun_segnale_con_pochi_dati(self):
        bars = self._make_bars(5)
        sigs = generate_signals(bars, lookback=20)
        self.assertEqual(len(sigs), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
