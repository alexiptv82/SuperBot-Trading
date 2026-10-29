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


from director.brain_scalp.coordinator import BrainPair
from director.brain_scalp.snapshot import (
    SnapshotPublisher,atomic_write,read_snapshot,build_snapshot)


class Group5Snapshots(unittest.TestCase):
    def test_i7_both_wallets_atomic_publication_and_throttle(self):
        with tempfile.TemporaryDirectory() as root:
            pair=BrainPair(root,initialize=True,now_ms=NOW)
            try:
                path=Path(root)/'scalp_dashboard.json'
                publisher=SnapshotPublisher(path)
                pair.tick(market(),CONTRACTS,NOW+1000)
                self.assertTrue(publisher.publish_if_due(pair,NOW+1000))
                before=path.read_bytes()
                self.assertFalse(publisher.publish_if_due(pair,NOW+2000))
                self.assertEqual(path.read_bytes(),before)
                self.assertTrue(publisher.publish_if_due(pair,NOW+6000))
                data=read_snapshot(path,NOW+6000)
                self.assertEqual(data['status'],'ok')
                self.assertEqual(data['profiles']['hawk']['account_id'],
                                 'brain-scalp-hawk-paper')
                self.assertEqual(data['profiles']['bull']['account_id'],
                                 'brain-scalp-bull-paper')
                self.assertEqual(data['profiles']['hawk']['metrics']['equity'],1000)
                self.assertTrue(data['read_only'])
            finally:
                pair.close()

    def test_i7_stopped_writer_shows_stale_not_online(self):
        with tempfile.TemporaryDirectory() as root:
            pair=BrainPair(root,initialize=True,now_ms=NOW)
            try:
                path=Path(root)/'status.json'
                pair.tick(market(),CONTRACTS,NOW+1000)
                publisher=SnapshotPublisher(path)
                publisher.publish_if_due(pair,NOW+1000)
            finally:
                pair.close()
            still=read_snapshot(path,NOW+1000+90000)
            self.assertTrue(still['available'])
            self.assertTrue(still['stale'])
            self.assertEqual(still['status'],'stale')
            self.assertFalse(still['profiles']['hawk']['online'])
            self.assertFalse(still['profiles']['bull']['online'])

    def test_i7_corrupt_snapshot_fails_closed(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'status.json'
            path.write_text('not-json',encoding='utf-8')
            self.assertEqual(read_snapshot(path,NOW)['status'],'unavailable')
            path.unlink()
            self.assertEqual(read_snapshot(path,NOW)['status'],'not_started')

    def test_i7_refuses_foreign_wallet_and_preserves_existing_snapshot(self):
        with tempfile.TemporaryDirectory() as root:
            pair=BrainPair(root,initialize=True,now_ms=NOW)
            try:
                output=Path(root)/'snapshot.json'
                pair.tick(market(),CONTRACTS,NOW+1000)
                pub=SnapshotPublisher(output)
                pub.publish_if_due(pair,NOW+1000)
                original=output.read_bytes()
                state=pair.hawk.store.load()
                state['account_id']='brain-free-paper'
                with self.assertRaisesRegex(ValueError,'foreign_wallet'):
                    build_snapshot(state,pair.bull.store.load(),NOW+2000)
                self.assertEqual(output.read_bytes(),original)
            finally:
                pair.close()

    def test_i7_refuses_snapshot_symlink(self):
        with tempfile.TemporaryDirectory() as root:
            target=Path(root)/'other.json'
            target.write_text('keep',encoding='utf-8')
            link=Path(root)/'link.json'
            link.symlink_to(target)
            with self.assertRaisesRegex(ValueError,'invalid_snapshot_path'):
                atomic_write(link,{'paper':True})
            self.assertEqual(target.read_text(encoding='utf-8'),'keep')

    def test_i7_snapshot_contains_no_api_key_or_untrusted_thesis(self):
        with tempfile.TemporaryDirectory() as root:
            pair=BrainPair(root,initialize=True,now_ms=NOW)
            try:
                raw=plan()
                raw['reason']='PRIVATE THESIS DO NOT PUBLISH'
                pair.hawk.submit(raw,NOW,CONTRACTS,{'BTC':quote()})
                pair.tick(market(),CONTRACTS,NOW+1000)
                output=Path(root)/'snapshot.json'
                SnapshotPublisher(output).publish_if_due(pair,NOW+1000)
                text=output.read_text(encoding='utf-8')
                self.assertNotIn('PRIVATE THESIS',text)
                self.assertNotIn('plan_ids',text)
                self.assertEqual(read_snapshot(output,NOW+1000)['profiles']['hawk']['positions'][0]['symbol'],'BTC')
            finally:
                pair.close()
