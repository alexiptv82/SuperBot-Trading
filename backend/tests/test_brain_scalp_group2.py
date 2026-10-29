"""Brain Scalp Group 2: physical costs, safe sizing, causal gap repair.

Offline: no network, no exchange, no changes to shared Brain Free.
"""
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from director.brain_scalp.coordinator import BrainPair
from director.brain_scalp.engine import PaperWallet,_risk
from director.brain_scalp.gap_repair import repair_markets
from backend.tests.test_brain_scalp_group1 import NOW,CONTRACTS,plan as base_plan,quote,market

MINUTE=60000


def plan(**overrides):
    raw=base_plan()
    raw.update(overrides)
    return raw


def bar(ts,low=99.9,high=100.1):
    return [ts,100.,high,low,100.,80.]


def incomplete_market(now):
    return {'BTC':{'quote':quote(100.,now),
                   'bars':{'1m':[bar(NOW+MINUTE),
                                 bar(NOW+3*MINUTE)]},
                   'funding':[]}}


class Group2Wallet(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.hawk=PaperWallet(Path(self.tmp.name)/'hawk','hawk',True,NOW)

    def tearDown(self):
        self.hawk.close()
        self.tmp.cleanup()

    def test_i2_reject_target_gross_below_roundtrip_costs(self):
        bad=plan(target=100.05)
        with self.assertRaisesRegex(ValueError,'target_below_costs'):
            self.hawk.submit(bad,NOW,CONTRACTS,{'BTC':quote()})
        self.assertEqual(self.hawk.store.load()['plans'],{})

    def test_i2_target_35bps_satisfies_32bps_gross_minimum(self):
        accepted=self.hawk.submit(plan(target=100.35),
                                  NOW,CONTRACTS,{'BTC':quote()})
        self.assertEqual(accepted.target,100.35)
        self.assertEqual(len(self.hawk.store.load()['plans']),1)

    def test_i2_recheck_target_after_price_moves(self):
        self.hawk.submit(plan(target=100.35),NOW,CONTRACTS,{'BTC':quote()})
        result=self.hawk.tick(market(price=100.25,ts=NOW+1000),
                              CONTRACTS,NOW+1000)
        self.assertEqual(result['positions'],0)
        self.assertEqual(result['pending'],0)
        self.assertIn('target_below_costs',
                      [e.get('why') for e in result['events']])

    def test_i2_short_symmetric_cost_guard(self):
        short=plan(side=-1,trigger='break_below',target=99.95,
                   stop=100.2,margin=150.)
        with self.assertRaisesRegex(ValueError,'target_below_costs'):
            self.hawk.submit(short,NOW,CONTRACTS,{'BTC':quote()})
        short['target']=99.5
        self.hawk.submit(short,NOW,CONTRACTS,{'BTC':quote()})

    def test_i3_overbudget_high_leverage_downsizes_before_apply(self):
        requested=plan(margin=250.,leverage=45,stop=98.)
        self.hawk.submit(requested,NOW,CONTRACTS,{'BTC':quote()})
        out=self.hawk.tick(market(ts=NOW+1000),CONTRACTS,NOW+1000)
        self.assertEqual(out['positions'],1)
        resized=[e for e in out['events'] if e['kind']=='plan_resized']
        self.assertEqual(len(resized),1)
        self.assertEqual(resized[0]['original_margin'],250.)
        self.assertEqual(resized[0]['original_leverage'],45)
        self.assertGreaterEqual(resized[0]['new_margin'],100.)
        self.assertLess(resized[0]['new_leverage'],45)
        self.assertLessEqual(resized[0]['new_margin'],250.)
        position=self.hawk.store.load()['positions']['BTC']
        self.assertLessEqual(_risk(position,self.hawk.cfg),
                             self.hawk.spec.risk_trade_usd+1e-7)

    def test_i3_min_margin_cannot_fit_risk_budget_rejected_atomically(self):
        # No arbitrary "fit" by cutting margin below approved minimum.
        self.hawk.spec=replace(self.hawk.spec,risk_trade_usd=1.)
        self.hawk.submit(plan(stop=98.),NOW,CONTRACTS,{'BTC':quote()})
        out=self.hawk.tick(market(ts=NOW+1000),CONTRACTS,NOW+1000)
        self.assertEqual((out['positions'],out['pending']),(0,0))
        self.assertTrue(any(e.get('why')=='below_min_margin_after_resize'
                            for e in out['events']))
        self.assertAlmostEqual(self.hawk.store.load()['cash'],1000.)

    def test_i3_resized_trade_survives_store_reopen(self):
        self.hawk.submit(plan(margin=250.,leverage=45,stop=98.),
                         NOW,CONTRACTS,{'BTC':quote()})
        self.hawk.tick(market(ts=NOW+1000),CONTRACTS,NOW+1000)
        positions=self.hawk.store.load()['positions']
        self.hawk.close()
        self.hawk=PaperWallet(Path(self.tmp.name)/'hawk','hawk')
        self.assertEqual(self.hawk.store.load()['positions'],positions)

    def test_i3_reservation_does_not_increase_original_margin_or_lev(self):
        self.hawk.submit(plan(),NOW,CONTRACTS,{'BTC':quote()})
        out=self.hawk.tick(market(ts=NOW+1000),CONTRACTS,NOW+1000)
        self.assertEqual(out['positions'],1)
        self.assertFalse(any(e['kind']=='plan_resized' for e in out['events']))


class CandleBackfill(unittest.TestCase):
    def test_b2_repaired_missing_minute_before_protection_can_close_stop(self):
        calls=[]
        def fetch(symbol,start,end):
            calls.append((symbol,start,end))
            return [bar(start,low=99.0)]
        with tempfile.TemporaryDirectory() as folder:
            pair=BrainPair(folder,initialize=True,now_ms=NOW,
                           candle_backfill=fetch)
            try:
                pair.hawk.submit(plan(),NOW,CONTRACTS,{'BTC':quote()})
                pair.tick(market(ts=NOW+1000),CONTRACTS,NOW+1000)
                result=pair.tick(incomplete_market(NOW+4*MINUTE),
                                 CONTRACTS,NOW+4*MINUTE)
                self.assertEqual(calls,[('BTC',NOW+2*MINUTE,NOW+3*MINUTE)])
                self.assertEqual(result['hawk']['positions'],0)
                self.assertTrue(any(e['kind']=='gap_backfilled' for e in
                                    result['market_events']))
                self.assertTrue(any(e['kind']=='trade_closed' and
                                    e['reason']=='stop_closed_bar' for e in
                                    result['hawk']['events']))
                self.assertEqual(pair.hawk.store.load()['coverage_gaps'],[])
                event_types=[r[0] for r in pair.hawk.store.db.execute(
                    "SELECT kind FROM events").fetchall()]
                self.assertIn('gap_backfilled',event_types)
            finally:
                pair.close()

    def test_b2_failed_backfill_quarantines_and_never_invents_bars(self):
        def failing(symbol,start,end):
            raise OSError('provider_unavailable')
        raw=incomplete_market(NOW+4*MINUTE)
        original=[list(b) for b in raw['BTC']['bars']['1m']]
        fixed,events=repair_markets(raw,NOW+4*MINUTE,failing,
                                    {'BTC':NOW})
        self.assertEqual(fixed['BTC']['bars']['1m'],original)
        self.assertTrue(any(e['kind']=='gap_backfill_failed' for e in events))
        self.assertTrue(any(e['kind']=='gap_unresolvable' for e in events))

    def test_b2_no_network_provider_fail_closed(self):
        raw=incomplete_market(NOW+4*MINUTE)
        result,events=repair_markets(raw,NOW+4*MINUTE,
                                     anchors={'BTC':NOW})
        self.assertEqual(result,raw)
        self.assertIn('gap_unresolvable',[e['kind'] for e in events])

    def test_b2_backfill_rejects_future_or_wrong_timestamp(self):
        raw=incomplete_market(NOW+4*MINUTE)
        fixed,events=repair_markets(raw,NOW+4*MINUTE,
                           lambda sym,a,b:[bar(a+MINUTE)],
                           {'BTC':NOW})
        self.assertEqual(fixed,raw)
        self.assertIn('gap_backfill_failed',[e['kind'] for e in events])

    def test_b2_invalid_backfill_no_partial_commit(self):
        raw={'BTC':{'quote':quote(ts=NOW+5*MINUTE),'bars':{'1m':[
            bar(NOW+MINUTE),bar(NOW+3*MINUTE),bar(NOW+5*MINUTE)]}}}
        # An invalid second segment must not publish the first segment.
        calls=[]
        def fetch(symbol,a,b):
            calls.append((a,b))
            return [bar(a)] if len(calls)==1 else [bar(a+MINUTE)]
        result,events=repair_markets(raw,NOW+6*MINUTE,fetch,
                                     {'BTC':NOW})
        self.assertEqual(result,raw)
        self.assertGreaterEqual(len(calls),2)
        self.assertIn('gap_unresolvable',[e['kind'] for e in events])

    def test_b2_unresolved_gap_blocks_new_plan_from_past_candles(self):
        with tempfile.TemporaryDirectory() as folder:
            pair=BrainPair(folder,initialize=True,now_ms=NOW)
            try:
                pair.hawk.submit(plan(),NOW,CONTRACTS,{'BTC':quote()})
                pair.tick(market(ts=NOW+1000),CONTRACTS,NOW+1000)
                result=pair.tick(incomplete_market(NOW+4*MINUTE),
                                 CONTRACTS,NOW+4*MINUTE)
                self.assertIn('BTC',pair.hawk.store.load()['coverage_gaps'])
                self.assertFalse(pair.hawk.store.load()['positions']['BTC']['coverage_complete'])
                self.assertTrue(any(e['kind']=='gap_unresolvable' for e in
                                    result['hawk']['events']))
            finally:
                pair.close()


    def test_b2_failed_gap_never_advances_past_unknown_stop(self):
        with tempfile.TemporaryDirectory() as folder:
            pair=BrainPair(folder,initialize=True,now_ms=NOW)
            try:
                pair.hawk.submit(plan(),NOW,CONTRACTS,{'BTC':quote()})
                pair.tick(market(ts=NOW+1000),CONTRACTS,NOW+1000)
                out=pair.tick(incomplete_market(NOW+4*MINUTE),
                              CONTRACTS,NOW+4*MINUTE)
                p=pair.hawk.store.load()['positions']['BTC']
                self.assertEqual(out['hawk']['positions'],1)
                self.assertEqual(p['last_bar_ms'],NOW+MINUTE)
                self.assertEqual(p['scalp_gap_cursor_ms'],NOW)
                self.assertFalse(p['coverage_complete'])
                self.assertIn('BTC',pair.hawk.store.load()['coverage_gaps'])
            finally:
                pair.close()

    def test_b2_delayed_repair_replays_missing_stop(self):
        with tempfile.TemporaryDirectory() as folder:
            pair=BrainPair(folder,initialize=True,now_ms=NOW)
            try:
                pair.hawk.submit(plan(),NOW,CONTRACTS,{'BTC':quote()})
                pair.tick(market(ts=NOW+1000),CONTRACTS,NOW+1000)
                pair.tick(incomplete_market(NOW+4*MINUTE),
                          CONTRACTS,NOW+4*MINUTE)
                pair.candle_backfill=lambda symbol,start,end: [
                    bar(ts,low=99.0) for ts in range(start,end,MINUTE)]
                out=pair.tick(incomplete_market(NOW+4*MINUTE),
                              CONTRACTS,NOW+4*MINUTE)
                self.assertEqual(out['hawk']['positions'],0)
                self.assertNotIn('BTC',pair.hawk.store.load()['coverage_gaps'])
                self.assertTrue(any(e.get('kind')=='trade_closed'
                                    and e.get('reason')=='stop_closed_bar'
                                    for e in out['hawk']['events']))
                self.assertTrue(any(e.get('kind')=='gap_recovered_verified'
                                    for e in out['hawk']['events']))
            finally:
                pair.close()

    def test_b2_safe_repair_restores_coverage_only_after_replay(self):
        with tempfile.TemporaryDirectory() as folder:
            pair=BrainPair(folder,initialize=True,now_ms=NOW)
            try:
                pair.hawk.submit(plan(),NOW,CONTRACTS,{'BTC':quote()})
                pair.tick(market(ts=NOW+1000),CONTRACTS,NOW+1000)
                pair.tick(incomplete_market(NOW+4*MINUTE),
                          CONTRACTS,NOW+4*MINUTE)
                pair.candle_backfill=lambda symbol,start,end: [
                    bar(ts) for ts in range(start,end,MINUTE)]
                out=pair.tick(incomplete_market(NOW+4*MINUTE),
                              CONTRACTS,NOW+4*MINUTE)
                self.assertEqual(out['hawk']['positions'],1)
                p=pair.hawk.store.load()['positions']['BTC']
                self.assertTrue(p['coverage_complete'])
                self.assertNotIn('scalp_gap_cursor_ms',p)
                self.assertEqual(p['last_bar_ms'],NOW+3*MINUTE)
                self.assertEqual(pair.hawk.store.load()['coverage_gaps'],[])
            finally:
                pair.close()


    def test_b2_upstream_feed_restores_full_history_without_fetcher(self):
        """An existing quarantine must be recoverable without a REST callback."""
        with tempfile.TemporaryDirectory() as folder:
            pair=BrainPair(folder,initialize=True,now_ms=NOW)
            try:
                pair.hawk.submit(plan(),NOW,CONTRACTS,{'BTC':quote()})
                pair.tick(market(ts=NOW+1000),CONTRACTS,NOW+1000)
                pair.tick(incomplete_market(NOW+4*MINUTE),
                          CONTRACTS,NOW+4*MINUTE)
                self.assertIn('BTC',pair.hawk.store.load()['coverage_gaps'])
                fully_restored=incomplete_market(NOW+4*MINUTE)
                fully_restored['BTC']['bars']['1m'].insert(
                    1,bar(NOW+2*MINUTE))
                out=pair.tick(fully_restored,CONTRACTS,NOW+4*MINUTE)
                self.assertEqual(out['hawk']['positions'],1)
                self.assertNotIn('BTC',pair.hawk.store.load()['coverage_gaps'])
                self.assertTrue(pair.hawk.store.load()['positions']['BTC']['coverage_complete'])
                self.assertTrue(any(e['kind']=='gap_history_complete'
                                    for e in out['market_events']))
                self.assertTrue(any(e['kind']=='gap_recovered_verified'
                                    for e in out['hawk']['events']))
            finally:
                pair.close()

    def test_b2_upstream_restored_stop_bar_is_replayed_before_unquarantine(self):
        """Complete feed may reveal a stop: close, never silently release."""
        with tempfile.TemporaryDirectory() as folder:
            pair=BrainPair(folder,initialize=True,now_ms=NOW)
            try:
                pair.hawk.submit(plan(),NOW,CONTRACTS,{'BTC':quote()})
                pair.tick(market(ts=NOW+1000),CONTRACTS,NOW+1000)
                pair.tick(incomplete_market(NOW+4*MINUTE),
                          CONTRACTS,NOW+4*MINUTE)
                fully_restored=incomplete_market(NOW+4*MINUTE)
                fully_restored['BTC']['bars']['1m'].insert(
                    1,bar(NOW+2*MINUTE,low=99.0))
                out=pair.tick(fully_restored,CONTRACTS,NOW+4*MINUTE)
                self.assertEqual(out['hawk']['positions'],0)
                self.assertNotIn('BTC',pair.hawk.store.load()['coverage_gaps'])
                self.assertTrue(any(e['kind']=='trade_closed' and
                                    e['reason']=='stop_closed_bar'
                                    for e in out['hawk']['events']))
                self.assertTrue(any(e['kind']=='gap_history_complete'
                                    for e in out['market_events']))
            finally:
                pair.close()



if __name__=='__main__':
    unittest.main()
