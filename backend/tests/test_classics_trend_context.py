"""Classics keep their original symmetric LONG/SHORT path; turn is not a gate."""
import unittest
from director.trend_advisory import observe
from desk.signals import read_symbol
from backend.tests.test_trend_advisory import NOW,bars

try:
    import numpy as np
except ImportError:
    np=None


class ClassicAdvisory(unittest.TestCase):
    def test_watch_is_not_an_entry_or_stop_decision(self):
        shift=observe('BTC',bars(900000),NOW,900000)
        self.assertEqual(shift['phase'],'early_upshift')
        self.assertFalse(shift['may_authorize_entry'])
        self.assertFalse(shift['may_block_entry'])

    @unittest.skipIf(np is None,'numpy unavailable')
    def test_frozen_scoring_is_identical_before_after_sensor(self):
        interval=900000
        data=[]
        px=100
        for i in range(1024):
            px*=1.00002
            data.append([NOW-(1024-i)*interval,px,px*1.001,
                         px*.999,px,100])
        arr=np.array(data,dtype=float)
        first=read_symbol('BTC',arr,NOW)
        self.assertIsNotNone(first)
        self.assertIsNone(observe('BTC',[],NOW,900000))
        second=read_symbol('BTC',arr,NOW)
        self.assertEqual(first,second)
        self.assertTrue(shift_allows_both_directions())

def shift_allows_both_directions():
    # Existing classical scorer ranks both long_score and short_score;
    # the new observer is never consulted to change that rank.
    reading=observe('BTC',bars(900000),NOW,900000)
    return reading['may_block_entry'] is False and reading['may_authorize_entry'] is False


if __name__=='__main__':unittest.main()
