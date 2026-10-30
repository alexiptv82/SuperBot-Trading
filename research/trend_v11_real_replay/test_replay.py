"""Offline tests for preregistered real replay. No outgoing network calls."""
import unittest
from unittest.mock import patch
import replay


class HistoricalReplayTests(unittest.TestCase):
    def test_strict_ohlcv_contract(self):
        for bad in (
            [120000,'100','90','99','100','1'],
            [120000,'100','101','105','100','1'],
            [120000,'100','101','99','0','1'],
            [120000,'100','101','99','100','-1'],
            [120001,'100','101','99','100','1']):
            with self.assertRaises(ValueError):
                replay.check_row(bad)
        v=replay.check_row(['120000','100','101','99','100','1','9999'])
        self.assertEqual(v,[120000,100.,101.,99.,100.,1.])

    def test_cannot_silently_backfill_missing_bitget_records(self):
        start=replay.START
        def fake(params):
            ts=params['startTime']
            stop=min(params['endTime']+1,ts+replay.MINUTE*200)
            return [[str(t),'100','101','99','100','1','999']
                    for t in range(ts,stop,replay.MINUTE)]
        bars,meta=replay.gather('BTC',loader=fake,delay=0)
        self.assertEqual(len(bars),replay.EXPECTED)
        self.assertEqual(meta['coverage_pct'],100.)
        self.assertEqual(meta['requests'],51)
        self.assertEqual(bars[0][0],start)
        self.assertEqual(bars[-1][0],replay.END-replay.MINUTE)

        def missing(params):
            rows=fake(params)
            return rows[:-1] if params['startTime']==replay.START else rows
        with self.assertRaisesRegex(ValueError,'history_gap'):
            replay.gather('BTC',loader=missing,delay=0)

    def test_conservative_same_bar_collision_is_not_success(self):
        price=100.
        bars=[[replay.START+i*replay.MINUTE,price,price,price,price,1.]
              for i in range(replay.HORIZON+3)]
        bars[1][2]=101.
        bars[1][3]=99.
        self.assertEqual(replay.first_barrier(bars,0,1)['outcome'],'adverse_first')
        self.assertEqual(replay.first_barrier(bars,0,-1)['outcome'],'adverse_first')
        self.assertEqual(replay.first_barrier(bars,2,1)['outcome'],'censored')

    def test_wilson_and_censoring_counted_separately(self):
        events=[{'outcome':'favorable_first','minutes':4},
                {'outcome':'adverse_first','minutes':2},
                {'outcome':'no_barrier','minutes':None},
                {'outcome':'censored','minutes':None}]
        result=replay.event_summary(events)
        self.assertEqual(result['events'],4)
        self.assertEqual(result['favorable_first_pct_given_barrier'],50.)
        self.assertEqual(result['outcomes']['censored'],1)
        self.assertEqual(result['median_min_to_favorable_barrier'],4)


if __name__=='__main__':
    unittest.main()
