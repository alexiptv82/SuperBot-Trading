"""Brain Scalp Group 5: PAPER observability and offline snapshots."""
import json
import tempfile
import unittest
from pathlib import Path

from director.brain_scalp.engine import PaperWallet
from director.brain_scalp.metrics import build_metrics
from backend.tests.test_brain_scalp_group1 import NOW,CONTRACTS,plan,quote,market


class Group5Metrics(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.w=PaperWallet(Path(self.tmp.name)/'hawk','hawk',True,NOW)

    def tearDown(self):
        self.w.close()
        self.tmp.cleanup()

    def test_i9_metrics_persist_and_observe_zero_slot_time(self):
        first=self.w.tick(market(ts=NOW+5000),CONTRACTS,NOW+5000)
        m=first['metrics']
        self.assertEqual(m['ts_ms'],NOW+5000)
        self.assertEqual((m['slots_used'],m['slots_free']),(0,10))
        self.assertAlmostEqual(m['minutes_at_zero_positions'],5/60)
        self.assertEqual(m['equity'],1000)
        self.assertEqual(self.w.store.load()['metrics'],m)

    def test_i9_counts_open_and_close_not_duplicated(self):
        self.w.submit(plan(),NOW,CONTRACTS,{'BTC':quote()})
        opened=self.w.tick(market(ts=NOW+1000),CONTRACTS,NOW+1000)
        self.assertEqual(opened['metrics']['trades_today'],1)
        self.assertEqual(opened['metrics']['long_count'],1)
        self.assertGreater(opened['metrics']['fee_paid_usd'],0)
        closed=self.w.tick(market(price=102,ts=NOW+2000),
                           CONTRACTS,NOW+2000)
        self.assertEqual(closed['metrics']['trades_closed'],1)
        self.assertEqual(closed['metrics']['slots_free'],10)
        previous=closed['metrics']['pnl_realized_usd']
        later=self.w.tick(market(ts=NOW+3000),CONTRACTS,NOW+3000)
        self.assertEqual(later['metrics']['pnl_realized_usd'],previous)
        self.assertEqual(later['metrics']['trades_closed'],1)

    def test_i9_partial_events_accumulate_single_segments(self):
        state=self.w.store.load()
        events=[
            {'kind':'open','fee_paid':.6},
            {'kind':'partial_trade','fee_paid':.2,
             'segment':{'net':2.0}},
            {'kind':'trade_closed','fee_paid':.3,
             'duration_minutes':3.,
             'net':13.,'segment':{'net':3.}},
        ]
        out=build_metrics(state,events,NOW+3000,self.w.spec,{},self.w.protect_cfg,True)
        self.assertAlmostEqual(out['pnl_realized_usd'],5.0)
        self.assertAlmostEqual(out['fee_paid_usd'],1.1)
        self.assertEqual(out['trades_closed'],1)
        self.assertEqual(out['avg_duration_min'],3.)

    def test_i9_incomplete_marks_never_publish_fabricated_equity(self):
        self.w.submit(plan(),NOW,CONTRACTS,{'BTC':quote()})
        self.w.tick(market(),CONTRACTS,NOW+1000)
        out=self.w.tick(market(price=None,ts=NOW+2000),
                        CONTRACTS,NOW+2000)
        self.assertIsNone(out['metrics']['equity'])
        self.assertFalse(out['metrics']['equity_complete'])
        self.assertEqual(out['metrics']['block_reason'],'mark_missing_or_stale')

    def test_i9_day_rollover_resets_today_count_not_cumulative(self):
        self.w.submit(plan(),NOW,CONTRACTS,{'BTC':quote()})
        self.w.tick(market(),CONTRACTS,NOW+1000)
        later=(NOW//86400000+1)*86400000+1000
        out=self.w.tick(market(price=100.,ts=later),CONTRACTS,later)
        self.assertEqual(out['metrics']['trades_today'],0)
        self.assertEqual(out['metrics']['trades_opened'],1)

    def test_i9_reserves_pending_margin_and_handles_paused_wallet(self):
        self.w.submit(plan(),NOW,CONTRACTS,{'BTC':quote()})
        state=self.w.store.load()
        state['paused']=True
        self.w.store.commit(state,NOW)
        out=self.w.tick(market(),CONTRACTS,NOW+1000)
        self.assertFalse(out['metrics']['opening_allowed'])
        self.assertEqual(out['metrics']['block_reason'],'paused')
        self.assertEqual(out['metrics']['pending_plans'],1)
        self.assertEqual(out['metrics']['margin_available'],850.)
