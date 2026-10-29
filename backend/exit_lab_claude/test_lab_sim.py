"""Test unitari del simulatore su percorsi sintetici (nessuna rete). Esecuzione: python -m unittest -v"""
import unittest

import numpy as np

import lab_sim as ls
from lab_sim import FEE, SLIP, Trade

DT = 60_000


def mk(rows, t0=0, dt=DT):
    """rows = [(o, h, l, c), ...] -> array t,o,h,l,c con candele contigue."""
    return np.array([[t0 + i * dt, o, h, l, c] for i, (o, h, l, c) in enumerate(rows)], dtype=float)


def trade(side=-1, price=100.0, d_sl=0.01, d_tp=0.018, lev=10, margin=100.0, t0=0):
    fill = price * (1 + side * SLIP)
    return Trade("k", "hawk", 2, "BTC", side, t0, price, fill, d_sl, d_tp, lev, margin, margin * lev,
                 margin * lev * d_sl, "golden", 0.0, "SL", 1)


def flat(n, px=100.0):
    return [(px, px + 0.05, px - 0.05, px)] * n


class ExitRules(unittest.TestCase):
    def test_short_tp_hit_net_matches_hand_calc(self):
        tr = trade(side=-1)
        rows = flat(3) + [(100, 100.1, 98.0, 98.2)] + flat(5, 98.2)
        r = ls.run_exit_variant(mk(rows), tr, 1.0, 1.0)
        self.assertEqual(r.kind, "TP")
        fill = 100 * (1 - SLIP)
        tp = fill * (1 - 0.018)
        exit_fill = tp * (1 + SLIP)
        qty = 1000 / fill
        expected = -1 * (exit_fill - fill) * qty - 1000 * FEE - qty * exit_fill * FEE
        self.assertAlmostEqual(r.net, expected, places=6)
        self.assertTrue(16.0 < r.net < 17.2, r.net)       # ~ +17,8 lordo - ~1,2 di costi

    def test_short_stop_hit(self):
        tr = trade(side=-1)
        rows = flat(2) + [(100, 101.5, 99.9, 101.2)] + flat(3, 101)
        r = ls.run_exit_variant(mk(rows), tr, 1.0, 1.0)
        self.assertEqual(r.kind, "SL")
        self.assertLess(r.net, -10.0)

    def test_stop_and_tp_same_candle_means_stop(self):
        tr = trade(side=-1)
        rows = flat(2) + [(100, 101.5, 97.0, 99.0)] + flat(3)
        self.assertEqual(ls.run_exit_variant(mk(rows), tr, 1.0, 1.0).kind, "SL")

    def test_long_gap_below_stop_fills_at_open(self):
        tr = trade(side=1)
        fill = 100 * (1 + SLIP)
        stop = fill * 0.99
        rows = flat(2) + [(stop - 1.0, stop - 0.5, stop - 1.5, stop - 1.0)] + flat(3)
        r = ls.run_exit_variant(mk(rows), tr, 1.0, 1.0)
        self.assertEqual(r.kind, "SL")
        exit_fill = (stop - 1.0) * (1 - SLIP)
        qty = 1000 / fill
        hours = r.exit_ms / ls.HOUR_MS
        funding = qty * fill * ls.FUNDING_8H_LONG * hours / 8
        expected = (exit_fill - fill) * qty - 1000 * FEE - qty * exit_fill * FEE - funding
        self.assertAlmostEqual(r.net, expected, places=6)

    def test_time_exit_at_cap(self):
        tr = trade(side=-1)
        r = ls.run_exit_variant(mk(flat(40)), tr, 1.0, 1.0, max_ms=30 * DT)
        self.assertEqual(r.kind, "TIME")
        self.assertEqual(r.exit_ms, 30 * DT)

    def test_no_funding_on_short_funding_on_long(self):
        rows = flat(200)
        rs = ls.run_exit_variant(mk(rows), trade(side=-1), 1.0, 1.0, max_ms=190 * DT)
        rl = ls.run_exit_variant(mk(rows), trade(side=1), 1.0, 1.0, max_ms=190 * DT)
        self.assertEqual(rs.kind, "TIME")
        self.assertEqual(rl.kind, "TIME")
        # a prezzo fermo short e long pagano gli stessi costi: la differenza e' SOLO il funding del long
        qty = 1000 / (100 * (1 + SLIP))
        funding = qty * 100 * (1 + SLIP) * ls.FUNDING_8H_LONG * (190 * DT / ls.HOUR_MS) / 8
        self.assertGreater(funding, 0.03)
        self.assertAlmostEqual(rs.net - rl.net, funding, delta=0.005)

    def test_flip_places_opposite_side(self):
        tr = trade(side=-1)
        rows = flat(2) + [(100, 100.1, 98.0, 98.2)] + flat(3, 98.2)
        self.assertEqual(ls.run_exit_variant(mk(rows), tr, 1.0, 1.0, flip=True).kind, "SL")

    def test_cap_distance_and_scale(self):
        self.assertEqual(ls.cap_distance(0.05, 20), (0.75 * (1 / 20 - 0.005), True))
        self.assertEqual(ls.cap_distance(0.01, 20), (0.01, False))
        tr = trade(side=-1, lev=20)
        r = ls.run_exit_variant(mk(flat(5)), tr, 2.0, 1.0)
        self.assertAlmostEqual(r.scale, 0.5)

    def test_wider_stop_survives_a_pullback_that_kills_the_tight_one(self):
        tr = trade(side=-1)
        rows = flat(2) + [(100, 101.3, 99.9, 100.5)] + [(100.5, 100.6, 97.9, 98.0)] + flat(3, 98)
        self.assertEqual(ls.run_exit_variant(mk(rows), tr, 1.0, 1.0).kind, "SL")
        self.assertEqual(ls.run_exit_variant(mk(rows), tr, 2.0, 1.0).kind, "TP")


class ScaleIn(unittest.TestCase):
    def test_second_leg_fills_and_averages(self):
        tr = trade(side=-1)
        rows = flat(2) + [(100, 100.6, 99.9, 100.2)] + flat(10, 100.2)
        r = ls.run_scalein_variant(mk(rows), tr, 0.5, 2.0, 1.0, "S", 3 * ls.HOUR_MS, max_ms=12 * DT)
        self.assertEqual(r.legs, 2)

    def test_second_leg_expires(self):
        tr = trade(side=-1)
        r = ls.run_scalein_variant(mk(flat(60)), tr, 0.5, 2.0, 1.0, "S", 10 * DT, max_ms=50 * DT)
        self.assertEqual(r.legs, 1)

    def test_R_sizing_caps_loss_near_one_R(self):
        tr = trade(side=-1)
        rows = flat(1) + [(100, 100.6, 99.9, 100.4)] + [(100.4, 102.5, 100.3, 102.4)] + flat(3, 102.4)
        r = ls.run_scalein_variant(mk(rows), tr, 0.5, 2.0, 1.0, "R", 3 * ls.HOUR_MS)
        self.assertEqual(r.kind, "SL")
        self.assertEqual(r.legs, 2)
        rr = r.net / tr.risk_usd
        self.assertTrue(-1.40 < rr < -1.05, rr)           # -1R piu' costi e slippage


class PullbackEntry(unittest.TestCase):
    def test_limit_not_touched_is_nofill(self):
        tr = trade(side=-1)
        r = ls.run_pullback_variant(mk(flat(100)), tr, "limit", 30 * DT, 0.5)
        self.assertEqual(r.kind, "NOFILL")

    def test_limit_fills_at_level_and_then_manages(self):
        tr = trade(side=-1)
        rows = flat(2) + [(100, 100.7, 99.9, 100.2)] + [(100.2, 100.3, 98.0, 98.1)] + flat(5, 98.1)
        r = ls.run_pullback_variant(mk(rows), tr, "limit", 30 * DT, 0.5)
        self.assertEqual(r.kind, "TP")
        self.assertEqual(r.entry_ms, 2 * DT)

    def test_limit_entry_candle_ignores_tp_but_not_stop(self):
        tr = trade(side=-1)
        # la candela del tocco arriva anche oltre lo stop del nuovo ingresso -> stop (caso peggiore)
        rows = flat(1) + [(100, 101.9, 97.0, 99.0)] + flat(3)
        r = ls.run_pullback_variant(mk(rows), tr, "limit", 30 * DT, 0.5)
        self.assertEqual(r.kind, "SL")

    def test_limit_entry_candle_ignores_tp(self):
        tr = trade(side=-1)
        # la candela del tocco arriva anche al TP del nuovo ingresso ma NON allo stop: il TP non vale su quella
        # candela (l'ordine dei tocchi e' ignoto), quindi si esce solo per tempo
        rows = flat(1) + [(100, 100.7, 97.0, 99.0)] + flat(12, 99.0)
        r = ls.run_pullback_variant(mk(rows), tr, "limit", 30 * DT, 0.5, max_ms=8 * DT)
        self.assertEqual(r.kind, "TIME")

    def test_bounce_waits_for_red_5m_bar(self):
        tr = trade(side=-1)
        rows = flat(1) + [(100, 100.6, 99.9, 100.4)] + flat(3, 100.4)           # tocco al minuto 1
        rows += [(100.4, 100.45, 100.0, 100.3)] + [(100.3, 100.35, 100.0, 100.2)] * 3 + [(100.2, 100.25, 100.0, 100.1)]
        rows += [(100.1, 100.15, 97.9, 98.0)] + flat(5, 98.0)                   # dopo la barra rossa il TP
        r = ls.run_pullback_variant(mk(rows), tr, "bounce", 30 * DT, 0.5)
        self.assertEqual(r.kind, "TP")
        self.assertEqual(r.entry_ms, 10 * DT)

    def test_bounce_green_bar_does_not_trigger_for_short(self):
        tr = trade(side=-1)
        rows = flat(1) + [(100, 100.6, 99.9, 100.4)] + flat(3, 100.4)
        rows += [(100.4, 100.9, 100.3, 100.5)] * 5 + flat(40, 100.5)
        r = ls.run_pullback_variant(mk(rows), tr, "bounce", 30 * DT, 0.5)
        self.assertEqual(r.kind, "NOFILL")


class Reversal(unittest.TestCase):
    def test_tp_first_after_stop(self):
        tr = trade(side=-1)
        rows = flat(2) + [(100, 101.5, 99.9, 101.2)] + [(101.2, 101.3, 97.9, 98.0)] + flat(3, 98)
        c = mk(rows)
        res = ls.run_exit_variant(c, tr, 1.0, 1.0)
        self.assertEqual(res.kind, "SL")
        self.assertEqual(ls.reversal_after_stop(c, tr, res), "TP_first")

    def test_stop2_first_after_stop(self):
        tr = trade(side=-1)
        rows = flat(2) + [(100, 101.5, 99.9, 101.2)] + [(101.2, 102.6, 101.0, 102.5)] + flat(3, 102.5)
        c = mk(rows)
        res = ls.run_exit_variant(c, tr, 1.0, 1.0)
        self.assertEqual(ls.reversal_after_stop(c, tr, res), "STOP2_first")


if __name__ == "__main__":
    unittest.main()
