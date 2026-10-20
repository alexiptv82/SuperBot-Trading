import random
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from director.contracts.outcomes import OHLC
from director.research.range_detector_v2 import freeze_levels, detect_confirmation
from director.research.power_v2 import minimum_detectable_edge_bp

T=1800000000000
MS=300000

def flatbar(t, val, wick=0.04):
    return OHLC(t,val,max(val+wick,val),min(val-wick,val),val)

class RangeTests(unittest.TestCase):
    def test_reference_and_observation_are_separate_and_causal(self):
        prior=[flatbar(T+i*MS,100+1.7*__import__('math').sin(2*__import__('math').pi*i/16)) for i in range(96)]
        lv=freeze_levels(prior,bar_ms=MS,adx_1h=14,adx_asof_ms=prior[-1].open_ms+MS)
        self.assertIsNotNone(lv)
        self.assertEqual(lv.formed_by_ms,prior[-1].open_ms+MS)
        future=[flatbar(lv.formed_by_ms+i*MS,100+1.55*__import__('math').sin(2*__import__('math').pi*i/16)) for i in range(48)]
        result=detect_confirmation(lv,future)
        self.assertIsNotNone(result)
        self.assertEqual(result.touch_sides,("R","S","R","S") if result.touch_sides[0]=="R" else ("S","R","S","R"))
        self.assertGreater(result.activation_open_ms,lv.formed_by_ms)
        with self.assertRaisesRegex(ValueError,"lookahead"):
            freeze_levels(prior,bar_ms=MS,adx_1h=14,adx_asof_ms=lv.formed_by_ms+1)

    def test_breakout_after_fixed_levels_invalidates(self):
        prior=[flatbar(T+i*MS,100+1.5*__import__('math').sin(2*__import__('math').pi*i/16)) for i in range(96)]
        lv=freeze_levels(prior,bar_ms=MS,adx_1h=15,adx_asof_ms=prior[-1].open_ms+MS)
        bad=[flatbar(lv.formed_by_ms,lv.resistance+lv.tolerance+0.2)]
        self.assertIsNone(detect_confirmation(lv,bad))

    def test_strong_trend_with_false_low_adx_fails_displacement(self):
        prior=[flatbar(T+i*MS,100+3*i/95) for i in range(96)]
        self.assertIsNone(freeze_levels(prior,bar_ms=MS,adx_1h=12,adx_asof_ms=prior[-1].open_ms+MS))

    def test_power_table_is_monotonic_and_uses_effective_n(self):
        a=minimum_detectable_edge_bp(100,300)
        b=minimum_detectable_edge_bp(100,1000)
        c=minimum_detectable_edge_bp(100,3000)
        self.assertGreater(a,b);self.assertGreater(b,c)
        self.assertAlmostEqual(a, 16.18, delta=.1)
        self.assertGreater(minimum_detectable_edge_bp(100,100), a)

if __name__=='__main__':unittest.main()

class PlaceboSyntheticTests(unittest.TestCase):
    def test_fixed_level_confirmations_discriminate_synthetic_placebos(self):
        import math
        rng=random.Random(20261020)
        rates={}
        for kind in ('random_walk','trend','oscillation'):
            yes=0
            for run in range(100):
                px=100.0
                bars=[]
                for i in range(144):
                    if kind=='oscillation':
                        px=100+(1.7 if i<96 else 1.55)*math.sin(2*math.pi*i/16)
                    else:
                        px+=rng.gauss(0,px*0.003)+(0.025 if kind=='trend' else 0.0)
                    bars.append(flatbar(T+i*MS,px))
                # Deliberately supply low ADX for ALL series; ADX filter cannot
                # be the only reason synthetic trend and random walk fail.
                levels=freeze_levels(bars[:96],bar_ms=MS,adx_1h=14,
                                     adx_asof_ms=bars[95].open_ms+MS)
                yes+=int(levels is not None and detect_confirmation(levels,bars[96:]) is not None)
            rates[kind]=yes
        self.assertLess(rates['random_walk'],rates['oscillation'])
        self.assertLess(rates['trend'],rates['oscillation'])
        self.assertLess(rates['random_walk'],90)  # v1 had essentially 100%
        self.assertLess(rates['trend'],90)
