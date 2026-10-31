"""MTF evidence is causal, bounded, deterministic, and non-authoritative."""
import unittest

from director.brain_scalp.mtf_context import FRAMES, project_closed_mtf

NOW = 1800000000000


def rows(duration, count=26, now=NOW, drift=0.15):
    end = now // duration * duration
    first = end - count * duration
    out = []
    for i in range(count):
        close = 100.0 + i * drift
        out.append([first + i * duration, close - .03, close + .2,
                    close - .2, close, 20.0])
    return out


class MTF(unittest.TestCase):
    def test_all_three_frames_available_and_nonbinding(self):
        market = {'bars': {frame: rows(d) for frame, d in FRAMES.items()}}
        first = project_closed_mtf(market, NOW)
        self.assertEqual(first['status'], 'available')
        self.assertEqual(first, project_closed_mtf(market, NOW))
        for k in ('may_authorize_entry', 'may_block_entry', 'may_modify_scores', 'may_execute_exit'):
            self.assertIs(first[k], False)
        for frame, val in first['timeframes'].items():
            self.assertEqual(val['status'], 'available', frame)
            self.assertEqual(val['bars_used'], 24)

    def test_unfinished_candle_excluded_causally(self):
        d = FRAMES['15m']
        old = rows(d)
        a = project_closed_mtf({'bars': {'15m': old}}, NOW)
        self.assertEqual(a['timeframes']['15m']['status'], 'available')
        current_open = NOW // d * d
        injected = old + [[current_open, 100, 999999, 50, 80000, 1]]
        b = project_closed_mtf({'bars': {'15m': injected}}, NOW)
        self.assertEqual(a, b)

    def test_explicit_missing_stale_and_gaps(self):
        partial = project_closed_mtf({'bars': {'4H': rows(FRAMES['4H'])}}, NOW)
        self.assertEqual(partial['status'], 'partial')
        self.assertEqual(partial['timeframes']['1H']['reason'], 'missing')
        d = FRAMES['15m']
        gap = rows(d)
        gap.pop(5)
        result = project_closed_mtf({'bars': {'15m': gap}}, NOW)
        self.assertEqual(result['timeframes']['15m']['reason'], 'candle_gap')
        stale = project_closed_mtf({'bars': {'15m': rows(d, now=NOW-4*d)}}, NOW)
        self.assertEqual(stale['timeframes']['15m']['reason'], 'stale')

    def test_bad_values_and_nonmonotonic_order_rejected(self):
        d = FRAMES['1H']
        good = rows(d)
        for broken in (good[:-1]+[good[-2]],
                       good[:-1]+[[good[-1][0], 100, float('nan'), 90, 100, 1]],
                       good[:-1]+[[good[-1][0], 100, 80, 90, 100, 1]]):
            x=project_closed_mtf({'bars': {'1H': broken}}, NOW)
            self.assertEqual(x['timeframes']['1H']['reason'], 'invalid_bars')
        with self.assertRaises(ValueError):project_closed_mtf({}, -1)

    def test_return_has_symmetric_sign_for_rising_falling(self):
        d=FRAMES['15m']
        up=project_closed_mtf({'bars': {'15m':rows(d, drift=.15)}},NOW)
        down=project_closed_mtf({'bars': {'15m':rows(d, drift=-.15)}},NOW)
        self.assertGreater(up['timeframes']['15m']['observed_return_pct_12bars'],0)
        self.assertLess(down['timeframes']['15m']['observed_return_pct_12bars'],0)


if __name__ == '__main__':unittest.main()
