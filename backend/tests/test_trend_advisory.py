"""Pure trend reader regression: causal, mirror-neutral, never an order veto."""
import math
import unittest
from director.trend_advisory import MIN_BARS,observe,observe_many

NOW=1800000000000


def bars(bar_ms=300000):
    closes=[]
    p=150.0
    for i in range(MIN_BARS):
        p*=1.003 if i>=36 else 0.999
        closes.append(p)
    return [[NOW-(MIN_BARS-i)*bar_ms,p,p*1.001,p*0.999,p,20]
            for i,p in enumerate(closes)]


def mirror(rows):
    out=[]
    for t,o,h,l,c,v in rows:
        out.append([t,1000000/o,1000000/l,1000000/h,1000000/c,v])
    return out


class Advisory(unittest.TestCase):
    def test_early_turn_up_and_mirror_down_are_only_observations(self):
        q=observe('BTC',bars(),NOW,300000)
        self.assertEqual(q['phase'],'early_upshift')
        self.assertEqual(q['prior_direction'],'down')
        self.assertEqual(q['recent_direction'],'up')
        self.assertFalse(q['may_authorize_entry'])
        self.assertFalse(q['may_block_entry'])
        mirrored=observe('BTC',mirror(bars()),NOW,300000)
        self.assertEqual(mirrored['phase'],'early_downshift')
        self.assertEqual(mirrored['prior_direction'],'up')
        self.assertEqual(mirrored['recent_direction'],'down')
        self.assertAlmostEqual(q['prior_return_pct'],-mirrored['prior_return_pct'],delta=0.06)
        self.assertAlmostEqual(q['recent_return_pct'],-mirrored['recent_return_pct'],delta=0.02)

    def test_no_peeking_at_unclosed_candles(self):
        series=bars()
        future=[NOW,100000,100001,99999,100000,100000]
        self.assertEqual(observe('BTC',series,NOW,300000),
                         observe('BTC',series+[future],NOW,300000))

    def test_gap_bad_clock_and_stale_candles_do_not_fake_a_turn(self):
        series=bars()
        broken=series[:15]+series[16:]
        self.assertIsNone(observe('BTC',broken,NOW,300000))
        self.assertIsNone(observe('BTC',series,NOW+1200000,300000))
        self.assertIsNone(observe('BTC',series,NOW-300000,300000))
        duplicate=series[:]
        duplicate[-1]=duplicate[-2]
        self.assertIsNone(observe('BTC',duplicate,NOW,300000))
        self.assertIsNone(observe('BTC',series,NOW,1234))

    def test_series_independence_and_price_scale_invariance(self):
        observed=observe_many({'BTC':bars(),'ETH':[[1,2]],'DOGE':bars()},NOW,300000)
        self.assertEqual(set(observed),{'BTC','DOGE'})
        scaled=[[row[0]]+[v*10 if j in (1,2,3,4) else v
                   for j,v in enumerate(row[1:],start=1)] for row in bars()]
        self.assertEqual(observe('BTC',scaled,NOW,300000)['phase'],'early_upshift')
        self.assertEqual(observe('BTC',bars(900000),NOW,900000)['phase'],'early_upshift')

    def test_only_contiguous_closed_observations_available(self):
        flats=[[NOW-(MIN_BARS-i)*300000,100,101,99,100,0]
               for i in range(MIN_BARS)]
        o=observe('BTC',flats,NOW,300000)
        self.assertEqual(o['phase'],'uncertain')
        self.assertEqual(o['recent_direction'],'flat')
        self.assertEqual(o['interpretation'],'possible_turn_not_confirmed')


if __name__=='__main__':unittest.main()
