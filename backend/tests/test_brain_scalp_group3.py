"""Brain Scalp Group 3: UTC stop latch, risk config, net profit protections.

All examples are isolated PAPER simulations; no network/exchange/VPS.
"""
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from director.brain_scalp.engine import PaperWallet,_net_at_quote
from director.brain_scalp.plans import parse_plan
from director.brain_scalp.config import HAWK
from director.brain_scalp.store import wallet_spec_digest
from backend.tests.test_brain_scalp_group1 import NOW,CONTRACTS,plan as group1_plan,quote,market


def plan(**changes):
    raw=group1_plan()
    raw.update(changes)
    return raw

DAY=86400000


class Group3Wallet(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=Path(self.tmp.name)/'hawk'
        self.w=PaperWallet(self.path,'hawk',True,NOW)

    def tearDown(self):
        self.w.close()
        self.tmp.cleanup()

    def _open(self,**changes):
        data=plan()
        data.update(changes)
        self.w.submit(data,NOW,CONTRACTS,{'BTC':quote()})
        a=self.w.tick(market(),CONTRACTS,NOW+1000)
        self.assertEqual(a['positions'],1)
        return self.w.store.load()['positions']['BTC']

    def _update_cash(self,value):
        state=self.w.store.load()
        state['cash']=value
        self.w.store.commit(state,state['last_ms'])

    def test_i5_stop_latches_on_loss_even_after_recovery(self):
        self._update_cash(790.)
        a=self.w.tick(market(ts=NOW+1000),CONTRACTS,NOW+1000)
        self.assertFalse(a['opening_allowed'])
        self.assertEqual([e['kind'] for e in a['events']].count('daily_stop_latched'),1)
        self.assertTrue(self.w.store.load()['daily_stop_triggered'])
        self._update_cash(950.)
        b=self.w.tick(market(ts=NOW+2000),CONTRACTS,NOW+2000)
        self.assertFalse(b['opening_allowed'])
        self.assertFalse(any(e['kind']=='daily_stop_latched' for e in b['events']))
        with self.assertRaisesRegex(ValueError,'daily_stop_latched'):
            self.w.submit(plan(plan_id='group3new'),NOW+2000,
                          CONTRACTS,{'BTC':quote(ts=NOW+2000)})

    def test_i5_stop_remains_latched_after_sqlite_reopen(self):
        self._update_cash(790.)
        self.w.tick(market(ts=NOW+1000),CONTRACTS,NOW+1000)
        self.w.close()
        self.w=PaperWallet(self.path,'hawk')
        self.assertTrue(self.w.store.load()['daily_stop_triggered'])
        self._update_cash(900.)
        t=self.w.tick(market(ts=NOW+2000),CONTRACTS,NOW+2000)
        self.assertFalse(t['opening_allowed'])

    def test_i5_day_change_requires_valid_fresh_marks_then_rearms(self):
        self._update_cash(790.)
        self.w.tick(market(ts=NOW+1000),CONTRACTS,NOW+1000)
        newday=(NOW//DAY+1)*DAY+1000
        with self.assertRaisesRegex(ValueError,'daily_rollover_tick_required'):
            self.w.submit(plan(plan_id='group3next',created_ms=newday,
                     expires_ms=newday+240000),newday,CONTRACTS,
                     {'BTC':quote(ts=newday)})
        tick=self.w.tick(market(ts=newday),CONTRACTS,newday)
        self.assertTrue(tick['opening_allowed'])
        st=self.w.store.load()
        self.assertFalse(st['daily_stop_triggered'])
        self.assertEqual(st['daily']['utc'],newday//DAY)
        self.assertEqual(st['daily']['start_equity'],790.)
        self.assertTrue(any(e['kind']=='daily_stop_reset_utc' for e in tick['events']))
        self.w.submit(plan(plan_id='group3next',created_ms=newday,
                     expires_ms=newday+240000),newday,CONTRACTS,
                     {'BTC':quote(ts=newday)})

    def test_i5_rollover_does_not_use_partial_equity(self):
        self._open()
        newday=(NOW//DAY+1)*DAY+1000
        stale=self.w.tick(market(price=None,ts=newday),CONTRACTS,newday)
        self.assertFalse(stale['opening_allowed'])
        self.assertNotEqual(self.w.store.load()['daily']['utc'],newday//DAY)
        fresh=self.w.tick(market(price=100,ts=newday),CONTRACTS,newday)
        self.assertEqual(self.w.store.load()['daily']['utc'],newday//DAY)
        self.assertTrue(any(e['kind']=='daily_stop_reset_utc' for e in fresh['events']))

    def test_i5_fingerprint_detects_changed_margin(self):
        self.assertEqual(wallet_spec_digest(HAWK),
                         self.w.store.load()['config_hash'])
        old=self.w.store.spec
        self.w.store.spec=replace(old,max_margin_trade=old.max_margin_trade+50)
        with self.assertRaisesRegex(ValueError,'explicit_config_migration_required'):
            self.w.store.load()
        self.w.store.spec=old
        self.assertAlmostEqual(self.w.store.load()['cash'],1000.)

    def test_i5_legacy_config_is_rejected_not_reset(self):
        state=self.w.store.load()
        state['config_hash']='brain-scalp-dual-v0.1:hawk'
        self.w.store.commit(state,NOW)
        with self.assertRaisesRegex(ValueError,'explicit_config_migration_required'):
            self.w.store.load()
        raw=self.w.store.db.execute('SELECT body FROM state').fetchone()[0]
        self.assertIn('brain-scalp-dual-v0.1:hawk',raw)
        self.assertIn('1000.0',raw)

    def test_i1_long_breakeven_covers_fee_slippage_and_funding(self):
        self._open(protect_after_usd=3.5,take_net_usd=999.)
        state=self.w.store.load()
        p=state['positions']['BTC']
        p['funding']=0.25
        self.w.store.commit(state,NOW+1000)
        out=self.w.tick(market(price=100.8,ts=NOW+2000),CONTRACTS,NOW+2000)
        self.assertEqual(out['positions'],1)
        p=self.w.store.load()['positions']['BTC']
        self.assertTrue(p['scalp_policy']['breakeven_set'])
        self.assertGreater(p['stop'],p['entry'])
        self.assertGreaterEqual(_net_at_quote(p,p['stop'],self.w.cfg),-1e-5)
        self.assertIn('breakeven_set',[e['kind'] for e in out['events']])

    def test_i1_short_breakeven_moves_downward_never_looser(self):
        self._open(side=-1,trigger='break_below',stop=100.2,target=98.,
                   margin=150.,protect_after_usd=3.5,take_net_usd=999.)
        out=self.w.tick(market(price=99.2,ts=NOW+2000),CONTRACTS,NOW+2000)
        self.assertEqual(out['positions'],1)
        p=self.w.store.load()['positions']['BTC']
        self.assertLess(p['stop'],100.)
        self.assertGreaterEqual(_net_at_quote(p,p['stop'],self.w.cfg),-1e-4)

    def test_i1_giveback_closes_even_when_net_negative(self):
        self._open(protect_after_usd=3.5,breakeven_after_usd=100.,
                   take_net_usd=999.)
        first=self.w.tick(market(price=100.8,ts=NOW+2000),CONTRACTS,NOW+2000)
        self.assertEqual(first['positions'],1)
        second=self.w.tick(market(price=99.85,ts=NOW+3000),CONTRACTS,NOW+3000)
        self.assertEqual(second['positions'],0)
        matches=[e for e in second['events'] if e.get('reason')=='scalp_net_giveback_observed']
        self.assertEqual(len(matches),1)
        self.assertLess(matches[0]['net'],0)

    def test_i1_trailing_tightens_and_never_loosens_long(self):
        self._open(protect_after_usd=3.5,take_net_usd=999.,trail_bps=10)
        self.w.tick(market(price=100.8,ts=NOW+2000),CONTRACTS,NOW+2000)
        first=self.w.store.load()['positions']['BTC']['stop']
        self.assertGreater(first,100.6)
        self.w.tick(market(price=100.9,ts=NOW+3000),CONTRACTS,NOW+3000)
        second=self.w.store.load()['positions']['BTC']['stop']
        self.assertGreater(second,first)

    def test_i1_scaleout_reduces_quantity_and_persists(self):
        before=self._open(protect_after_usd=3.5,take_net_usd=999.,
                          scale_out=[{'net_usd':4.,'fraction':0.5}])
        original=before['qty']
        out=self.w.tick(market(price=100.8,ts=NOW+2000),CONTRACTS,NOW+2000)
        self.assertEqual(out['positions'],1)
        p=self.w.store.load()['positions']['BTC']
        self.assertAlmostEqual(p['qty'],original*0.5,delta=1e-6)
        self.assertEqual(p['scalp_policy']['scale_out_done'],[0])
        self.assertIn('partial_trade',[e['kind'] for e in out['events']])
        self.w.close()
        self.w=PaperWallet(self.path,'hawk')
        self.assertEqual(self.w.store.load()['positions']['BTC']['scalp_policy']['scale_out_done'],[0])

    def test_i1_invalidation_cancels_untriggered_plan(self):
        a=plan(invalidate_price=99.9)
        self.w.submit(a,NOW,CONTRACTS,{'BTC':quote()})
        out=self.w.tick(market(price=99.95,ts=NOW+1000),CONTRACTS,NOW+1000)
        self.assertEqual((out['positions'],out['pending']),(0,1))
        out=self.w.tick(market(price=99.8,ts=NOW+2000),CONTRACTS,NOW+2000)
        self.assertEqual((out['positions'],out['pending']),(0,0))
        self.assertTrue(any(e['kind']=='plan_invalidated' for e in out['events']))

    def test_i1_invalidation_after_open_closes_position(self):
        self._open(invalidate_price=99.9)
        out=self.w.tick(market(price=99.9,ts=NOW+2000),CONTRACTS,NOW+2000)
        self.assertEqual(out['positions'],0)
        self.assertTrue(any(e.get('reason')=='scalp_invalidation_observed'
                            for e in out['events']))

    def test_i1_bad_optional_fields_rejected(self):
        for item in [
            plan(trail_bps=0),plan(trail_bps=1001),
            plan(invalidate_price=101.),
            plan(scale_out=[{'net_usd':4,'fraction':0.8},
                            {'net_usd':8,'fraction':0.4}]),
            plan(scale_out=[{'net_usd':4,'fraction':0.5},
                            {'net_usd':3,'fraction':0.5}]),
        ]:
            with self.subTest(item=item),self.assertRaises(ValueError):
                parse_plan(item,HAWK,NOW,CONTRACTS)


    def test_i5_stale_open_mark_does_not_create_fake_daily_latch(self):
        self._open(protect_after_usd=500.)
        stale=self.w.tick(market(price=60.,ts=NOW-20000),
                          CONTRACTS,NOW+2000)
        self.assertFalse(stale['opening_allowed'])
        self.assertFalse(self.w.store.load()['daily_stop_triggered'])
        refreshed=self.w.tick(market(price=100.,ts=NOW+3000),
                              CONTRACTS,NOW+3000)
        self.assertFalse(self.w.store.load()['daily_stop_triggered'])
        self.assertTrue(refreshed['opening_allowed'])

    def test_i1_breakeven_is_recalculated_when_funding_increases(self):
        self._open(protect_after_usd=3.5,take_net_usd=999.)
        self.w.tick(market(price=100.8,ts=NOW+2000),CONTRACTS,NOW+2000)
        old=self.w.store.load()['positions']['BTC']['stop']
        state=self.w.store.load()
        state['positions']['BTC']['funding']+=0.50
        state['cash']-=0.50
        self.w.store.commit(state,NOW+2000)
        after=self.w.tick(market(price=100.9,ts=NOW+3000),
                          CONTRACTS,NOW+3000)
        self.assertEqual(after['positions'],1)
        p=self.w.store.load()['positions']['BTC']
        self.assertGreater(p['stop'],old)
        self.assertGreaterEqual(_net_at_quote(p,p['stop'],self.w.cfg),-1e-5)


    def test_i5_latches_after_exit_fees_before_opening_another_trade(self):
        self._open(hold_max_ms=60000,take_net_usd=999.,
                   protect_after_usd=500.)
        state=self.w.store.load()
        p=state['positions']['BTC']
        # Marked portfolio equity is just ABOVE the 20% loss limit before
        # the time exit; exit slippage/fees push it BELOW 800 USD.
        state['cash']=800.2-p['margin']-p['side']*(100.-p['entry'])*p['qty']
        self.w.store.commit(state,NOW+1000)
        out=self.w.tick(market(price=100.,ts=NOW+62000),
                        CONTRACTS,NOW+62000)
        self.assertEqual(out['positions'],0)
        self.assertLess(self.w.store.load()['cash'],800.)
        self.assertFalse(out['opening_allowed'])
        self.assertTrue(self.w.store.load()['daily_stop_triggered'])
        self.assertTrue(any(e['kind']=='daily_stop_latched' for e in out['events']))


if __name__=='__main__':
    unittest.main()
