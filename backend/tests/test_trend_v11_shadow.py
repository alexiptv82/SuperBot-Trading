"""The user's v1.1 trend engine: deterministic parity, safety and async isolation."""
import copy
import unittest
from unittest.mock import Mock

from director.trend_engine_v11 import safe_indicator,read_bitget_closed_1m
from director.trend_shadow import TrendShadow

NOW=1800000000000
MINUTE=60000


def stream(n=360,reversal=180):
    # Identical price path to tests/test_engine.py in the user's ZIP.
    start=NOW-n*MINUTE
    p=1000.
    rows=[]
    for i in range(n):
        q=p+(-1 if i<reversal else 1)
        rows.append([start+i*MINUTE,p,max(p,q)+.1,min(p,q)-.1,q,100,999999])
        p=q
    return rows


class NonblockingV11(unittest.TestCase):
    def test_exact_v1_1_reference_replay_state_and_score(self):
        rows=stream()
        full=read_bitget_closed_1m('BTC',rows,now_ms=NOW)
        self.assertEqual(full['state'],'BULLISH')
        self.assertAlmostEqual(full['bias'],0.6,places=5)
        self.assertTrue(full['five_minute_ready'])
        prior=read_bitget_closed_1m('BTC',rows[:171],now_ms=rows[170][0]+MINUTE)
        self.assertEqual(prior['state'],'BEARISH')
        self.assertAlmostEqual(prior['bias'],-0.6,places=5)
        early=read_bitget_closed_1m('BTC',rows[:50],now_ms=rows[49][0]+MINUTE)
        self.assertEqual(early['state'],'TRANSITION_DOWN')
        self.assertFalse(early['five_minute_ready'])

    def test_indicator_cannot_adjust_scores_or_authorize_execution(self):
        v=safe_indicator('BTC',stream(),now_ms=NOW)
        self.assertEqual(v['authority'],'advisory_only')
        self.assertFalse(v['may_authorize_entry'])
        self.assertFalse(v['may_block_entry'])
        self.assertFalse(v['may_modify_scores'])
        self.assertNotIn('long_delta',v)
        self.assertNotIn('short_delta',v)
        self.assertFalse(v['strength_is_probability'])

    def test_unclosed_bar_ignored_and_missing_data_never_vetoes_trade(self):
        rows=stream()
        ordinary=safe_indicator('BTC',rows,now_ms=NOW)
        future=copy.deepcopy(rows[-1]);future[0]=NOW;future[4]*=15
        self.assertEqual(safe_indicator('BTC',rows+[future],now_ms=NOW),ordinary)
        gap=rows[:40]+rows[41:]
        unavailable=safe_indicator('BTC',gap,now_ms=NOW)
        self.assertEqual(unavailable['quality'],'UNAVAILABLE')
        self.assertFalse(unavailable['may_block_entry'])
        self.assertFalse(unavailable['may_modify_scores'])
        stale=safe_indicator('BTC',rows,now_ms=NOW+200000)
        self.assertEqual(stale['quality'],'STALE')
        self.assertFalse(stale['ready'])

    def test_reject_revision_bad_ohlcv_and_quote_volume_is_not_taker_buy(self):
        rows=stream()
        contradiction=copy.deepcopy(rows)
        contradiction.insert(3,copy.deepcopy(contradiction[2]))
        contradiction[3][4]+=0.01
        self.assertEqual(safe_indicator('BTC',contradiction,now_ms=NOW)['quality'],'UNAVAILABLE')
        bad=copy.deepcopy(rows);bad[4][2]=-1
        self.assertEqual(safe_indicator('BTC',bad,now_ms=NOW)['quality'],'UNAVAILABLE')
        self.assertEqual(safe_indicator('BTC',rows,now_ms=NOW)['bias'],
                         safe_indicator('BTC',[r[:6] for r in rows],now_ms=NOW)['bias'])

    def test_async_worker_never_invokes_loader_or_blocks_owner(self):
        shadow=TrendShadow(interval_ms=60000)
        try:
            def broken(_):raise TimeoutError('network')
            self.assertEqual(shadow.poll_public(NOW,['BTC'],broken),{})
            # While network is pending, no wait on the financial thread.
            self.assertEqual(shadow.poll_public(NOW+10,['BTC'],broken),{})
            shadow.future.result(timeout=3)
            self.assertEqual(shadow.poll_public(NOW+20000,['BTC'],broken),{})
        finally:shadow.close()

    def test_async_existing_market_bars_produce_eventually_only_opinion(self):
        shadow=TrendShadow()
        try:
            self.assertEqual(shadow.poll(NOW,{'BTC':stream()}),{})
            shadow.future.result(timeout=3)
            result=shadow.poll(NOW+10,{'BTC':stream()})
            self.assertEqual(result['BTC']['state'],'BULLISH')
            self.assertFalse(result['BTC']['may_authorize_entry'])
            self.assertFalse(result['BTC']['may_block_entry'])
            self.assertEqual(shadow.poll(NOW+300000,{}),{})
        finally:shadow.close()


if __name__=='__main__':
    unittest.main()
