"""Group 4: independent AI plan parsing and fail-closed PAPER execution guards.

All tests are offline; none call model, exchange, web or VPS.
"""
import tempfile
import unittest
from pathlib import Path

from director.brain_scalp.coordinator import BrainPair
from director.brain_scalp.engine import PaperWallet,PlanGuardError
from backend.tests.test_brain_scalp_group1 import NOW,CONTRACTS,plan as base_plan,quote,market


def plan(symbol='BTC',**kwargs):
    d=base_plan()
    d['symbol']=symbol
    d.update(kwargs)
    return d


def quotes():
    return {'BTC':quote(),'ETH':quote()}


def markets():
    return {'BTC':market()['BTC'],
            'ETH':{'quote':quote(),'bars':{'1m':[]},'funding':[]}}


def contracts():
    eth=dict(CONTRACTS['BTC'],max_leverage=30)
    return dict(CONTRACTS,ETH=eth)


class Group4AI(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.pair=BrainPair(self.tmp.name,initialize=True,now_ms=NOW)
        self.allowed={'candidates':[{'symbol':'BTC','side':1},
                                    {'symbol':'ETH','side':1}]}

    def tearDown(self):
        self.pair.close()
        self.tmp.cleanup()

    def accept(self,items,now=NOW):
        return self.pair.accept_ai_plans('hawk',{'plans':items},
                                        self.allowed,markets(),contracts(),now)

    def test_i6_unhashable_symbol_and_malformed_item_do_not_drop_valid_plans(self):
        result=self.accept([
            {'symbol':['BTC'],'side':1},None,
            plan('BTC',plan_id='evil-model-controlled-123',created_ms=NOW-8000000,
                 expires_ms=NOW-8000000+120000),
            plan('ETH',plan_id='Evil2-id-value',created_ms=NOW+100000,
                 expires_ms=NOW+160000)])
        self.assertEqual(len(result['accepted']),2)
        self.assertEqual(len(result['rejected']),2)
        self.assertEqual({x['symbol'] for x in result['accepted']},{'BTC','ETH'})
        self.assertTrue(all(x['plan_id'] not in
                            ('evil-model-controlled-123','Evil2-id-value')
                            for x in result['accepted']))
        for sym in ('BTC','ETH'):
            raw=self.pair.hawk.store.load()['plans'][sym]
            self.assertEqual(raw['created_ms'],NOW)
            self.assertTrue(NOW<raw['expires_ms']<=NOW+300000)
        kinds=[x[0] for x in self.pair.hawk.store.db.execute(
            "SELECT kind FROM events ORDER BY seq").fetchall()]
        self.assertEqual(kinds.count('ai_plan_rejected'),2)
        self.assertEqual(kinds.count('ai_response_processed'),1)

    def test_i6_without_id_or_clock_engine_mints_both(self):
        raw=plan()
        for key in ('plan_id','created_ms','expires_ms'):
            del raw[key]
        raw['ttl_ms']=90000
        out=self.accept([raw])
        self.assertEqual(len(out['accepted']),1)
        stored=self.pair.hawk.store.load()['plans']['BTC']
        self.assertEqual(stored['created_ms'],NOW)
        self.assertEqual(stored['expires_ms'],NOW+90000)
        self.assertEqual(len(stored['plan_id']),32)

    def test_i6_one_invalid_numeric_and_duplicate_followed_by_valid(self):
        result=self.accept([plan('BTC',created_ms='not-a-timestamp',
                                expires_ms=NOW+240000),
                            plan('BTC'),plan('BTC'),plan('ETH')])
        self.assertEqual(len(result['accepted']),2)
        self.assertEqual(len(result['rejected']),2)
        self.assertIn('duplicate_symbol',[r['why'] for r in result['rejected']])

    def test_i6_unhashable_side_does_not_crash(self):
        out=self.accept([plan(side={'invalid':1}),plan('BTC')])
        self.assertEqual(len(out['accepted']),1)
        self.assertEqual(len(out['rejected']),1)

    def test_i6_raw_rejected_model_payload_not_persisted_in_audit(self):
        secret='DO-NOT-JOURNAL-RAW-MODEL-INPUT'
        raw=plan('BTC',reason=secret)
        raw['side']=0
        result=self.accept([raw,plan('ETH')])
        self.assertEqual(len(result['accepted']),1)
        journal=''.join(row[0] for row in self.pair.hawk.store.db.execute(
            "SELECT body FROM events WHERE kind LIKE 'ai_%'").fetchall())
        self.assertNotIn(secret,journal)

    def test_i6_invalid_top_level_and_bounded_payload(self):
        with self.assertRaisesRegex(ValueError,'model_response_wrong_schema'):
            self.pair.accept_ai_plans('hawk',{'plans':None},self.allowed,
                                      markets(),contracts(),NOW)
        with self.assertRaisesRegex(ValueError,'model_response_plan_limit'):
            self.accept([plan()]*33)

    def test_i6_cost_feedback_survives_partial_rejection(self):
        out=self.accept([plan('BTC',target=100.05),plan('ETH')])
        self.assertEqual(len(out['accepted']),1)
        self.assertEqual(out['rejected'][0]['why'],'target_below_costs')
        self.assertGreater(out['rejected'][0]['min_target_price'],100)

    def test_i6_two_wallets_have_different_ids(self):
        shortlist={'candidates':[{'symbol':'BTC','side':1}]}
        r1=self.pair.accept_ai_plans('hawk',{'plans':[plan()]},shortlist,
                                      markets(),contracts(),NOW)
        r2=self.pair.accept_ai_plans('bull',{'plans':[plan(margin=150.)]},shortlist,
                                      markets(),contracts(),NOW)
        self.assertNotEqual(r1['accepted'][0]['plan_id'],r2['accepted'][0]['plan_id'])


class Group4Engine(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.w=PaperWallet(Path(self.tmp.name)/'hawk','hawk',True,NOW)

    def tearDown(self):
        self.w.close()
        self.tmp.cleanup()

    def test_submit_overshoot_long_1p2pct_rejected_without_reservation(self):
        with self.assertRaisesRegex(ValueError,'trigger_already_breached') as ctx:
            self.w.submit(plan(),NOW,CONTRACTS,{'BTC':quote(101.2,NOW)})
        self.assertIsInstance(ctx.exception,PlanGuardError)
        self.assertAlmostEqual(ctx.exception.details['overshoot_pct'],1.2)
        self.assertEqual(self.w.store.load()['plans'],{})

    def test_submit_overshoot_short_1p2pct_rejected(self):
        with self.assertRaisesRegex(ValueError,'trigger_already_breached'):
            self.w.submit(plan(side=-1,trigger='break_below',
                               stop=100.2,target=98.,margin=150.),
                          NOW,CONTRACTS,{'BTC':quote(98.8,NOW)})
        self.assertEqual(self.w.store.load()['plans'],{})

    def test_overshoot_at_fill_cancels_pending_not_open(self):
        self.w.submit(plan(),NOW,CONTRACTS,{'BTC':quote()})
        out=self.w.tick(market(price=101.2,ts=NOW+1000),
                        CONTRACTS,NOW+1000)
        self.assertEqual((out['positions'],out['pending']),(0,0))
        matches=[e for e in out['events']
                 if e.get('why')=='trigger_already_breached']
        self.assertEqual(len(matches),1)
        self.assertGreater(matches[0]['overshoot_pct'],1)

    def test_small_overshoot_under_threshold_still_allowed(self):
        self.w.submit(plan(),NOW,CONTRACTS,{'BTC':quote(100.04,NOW)})
        out=self.w.tick(market(price=100.04,ts=NOW+1000),
                        CONTRACTS,NOW+1000)
        self.assertEqual(out['positions'],1)

    def test_stop_inside_noise_both_sides_rejected(self):
        for side in (1,-1):
            proposal=plan(side=side,trigger='break_above' if side==1
                          else 'break_below',
                          stop=99.96 if side==1 else 100.04,
                          target=102. if side==1 else 98.,
                          margin=100.)
            with self.subTest(side=side):
                with self.assertRaisesRegex(ValueError,'stop_inside_noise') as ctx:
                    self.w.submit(proposal,NOW,CONTRACTS,{'BTC':quote()})
                self.assertLess(ctx.exception.details['stop_pct'],
                                ctx.exception.details['cost_pct'])
                self.assertGreater(ctx.exception.details['ratio'],3.)
        self.assertEqual(self.w.store.load()['plans'],{})

    def test_stop_outside_cost_noise_accepted(self):
        self.w.submit(plan(stop=99.8),NOW,CONTRACTS,{'BTC':quote()})
        self.assertIn('BTC',self.w.store.load()['plans'])

    def test_stop_inside_noise_ai_feedback_has_min_stop_distance(self):
        with tempfile.TemporaryDirectory() as location:
            pair=BrainPair(location,initialize=True,now_ms=NOW)
            try:
                short={'candidates':[{'symbol':'BTC','side':1}]}
                out=pair.accept_ai_plans('hawk',
                    {'plans':[plan(stop=99.96)]},short,markets(),contracts(),NOW)
                self.assertEqual(out['accepted'],[])
                self.assertEqual(out['rejected'][0]['why'],'stop_inside_noise')
                self.assertAlmostEqual(out['rejected'][0]['min_stop_pct'],.16)
            finally:
                pair.close()

    def test_dynamic_daily_threshold_rejects_reservation_before_tick(self):
        s=self.w.store.load()
        s['cash']=790.
        self.w.store.commit(s,NOW,[])
        with self.assertRaisesRegex(ValueError,'opening_not_allowed:daily_stop_threshold'):
            self.w.submit(plan(),NOW,CONTRACTS,{'BTC':quote()})
        self.assertEqual(self.w.store.load()['plans'],{})

    def test_latched_stop_rejects_reservation(self):
        s=self.w.store.load()
        s['daily_stop_triggered']=True
        self.w.store.commit(s,NOW,[])
        with self.assertRaisesRegex(ValueError,'daily_stop_latched'):
            self.w.submit(plan(),NOW,CONTRACTS,{'BTC':quote()})
        self.assertEqual(self.w.store.load()['plans'],{})

    def test_paused_wallet_rejects_reservation(self):
        s=self.w.store.load()
        s['paused']=True
        self.w.store.commit(s,NOW,[])
        with self.assertRaisesRegex(ValueError,'opening_not_allowed:paused'):
            self.w.submit(plan(),NOW,CONTRACTS,{'BTC':quote()})
        self.assertEqual(self.w.store.load()['plans'],{})
