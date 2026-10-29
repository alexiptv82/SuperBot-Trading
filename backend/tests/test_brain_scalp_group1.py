"""Brain Scalp Group 1 regression suite: no network, no orders, PAPER only."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from director.brain_scalp.coordinator import BrainPair
from director.brain_scalp.engine import PaperWallet
from director.brain_scalp.config import ENTRY_PRICE_AGE_MS, PROTECT_PRICE_AGE_MS

NOW=1800000000000
CONTRACTS={'BTC':{'status':'normal','max_leverage':45,'maintenance':.005,
                  'price_step':.01,'qty_step':.001,'min_qty':.001,
                  'min_notional':5.0}}


def quote(price=100.,ts=NOW):
    return {'price':price,'ts_ms':ts}


def market(price=100.,ts=NOW):
    return {'BTC':{'quote':quote(price,ts),'bars':{'1m':[]},'funding':[]}}


def plan(plan_id="group1aaa",created=NOW):
    return {'plan_id':plan_id,'symbol':'BTC','side':1,'created_ms':created,
            'expires_ms':created+240000,'trigger':'break_above',
            'trigger_price':100.,'stop':99.8,'target':102.,'margin':100.,
            'leverage':10,'hold_max_ms':3600000,'protect_after_usd':5.,
            'take_net_usd':10.,'reason':'evidence backed breakout example',
            'invalidation':'trade canceled if breakout setup breaks'}


class Group1Wallet(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.hawk=PaperWallet(Path(self.tmp.name)/'hawk','hawk',True,NOW)

    def tearDown(self):
        self.hawk.close()
        self.tmp.cleanup()

    def open_long(self):
        self.hawk.submit(plan(),NOW,CONTRACTS,{'BTC':quote()})
        result=self.hawk.tick(market(),CONTRACTS,NOW+1000)
        self.assertEqual(result['positions'],1)

    def test_b3a_none_price_does_not_crash_or_unlock_openings(self):
        self.open_long()
        out=self.hawk.tick(market(None,NOW+2000),CONTRACTS,NOW+2000)
        self.assertFalse(out['opening_allowed'])
        self.assertEqual(out['positions'],1)
        self.assertTrue(any(e['kind']=='equity_unavailable' and
                            e['symbol']=='BTC' for e in out['events']))
        self.assertEqual(self.hawk.store.load()['positions']['BTC']['symbol'],'BTC')
        self.assertNotIn('BTC',self.hawk.store.load()['last_prices'])

    def test_b3a_nan_price_is_not_persisted_in_strict_json(self):
        self.open_long()
        result=self.hawk.tick(market(float('nan'),NOW+2000),
                              CONTRACTS,NOW+2000)
        self.assertEqual(result['positions'],1)
        self.assertFalse(result['opening_allowed'])
        self.assertTrue(any(e['kind']=='equity_unavailable' for e in result['events']))
        self.assertNotIn('BTC',self.hawk.store.load()['last_prices'])

    def test_b3b_backward_one_ms_still_closes_at_protective_stop(self):
        self.open_long()
        result=self.hawk.tick(market(99.,NOW+1000),CONTRACTS,NOW+999)
        self.assertEqual(result['positions'],0)
        self.assertTrue(any(e.get('kind')=='clock_adjusted' and
                            e['delta_ms']==1 for e in result['events']))
        self.assertTrue(any(e.get('kind')=='trade_closed' for e in result['events']))
        self.assertEqual(self.hawk.store.load()['last_ms'],NOW+1000)

    def test_b3b_large_backward_jump_prevents_new_openings(self):
        self.hawk.tick(market(ts=NOW+2000),CONTRACTS,NOW+2000)
        self.hawk.submit(plan('group1bbb',created=NOW+2000),NOW+2000,
                         CONTRACTS,{'BTC':quote(ts=NOW+2000)})
        result=self.hawk.tick(market(ts=NOW+2000),CONTRACTS,NOW+1000)
        self.assertFalse(result['opening_allowed'])
        self.assertEqual((result['positions'],result['pending']),(0,1))
        self.assertTrue(any(e['kind']=='clock_adjusted' for e in result['events']))

    def test_i4_stale_five_seconds_rejected_on_reservation(self):
        with self.assertRaisesRegex(ValueError,'quote_too_stale_for_entry'):
            self.hawk.submit(plan(),NOW,CONTRACTS,
                             {'BTC':quote(ts=NOW-5000)})
        self.assertEqual(self.hawk.store.load()['plans'],{})

    def test_i4_two_seconds_accepted_and_fill_drift_recorded(self):
        self.assertEqual(ENTRY_PRICE_AGE_MS,3000)
        self.assertEqual(PROTECT_PRICE_AGE_MS,10000)
        self.hawk.submit(plan(),NOW,CONTRACTS,
                         {'BTC':quote(ts=NOW-2000)})
        out=self.hawk.tick(market(ts=NOW-2000),CONTRACTS,NOW)
        self.assertEqual(out['positions'],1)
        fills=[e for e in out['events'] if e['kind']=='entry_fill']
        self.assertEqual(len(fills),1)
        self.assertEqual(fills[0]['trigger_price'],100.)
        self.assertGreater(fills[0]['slippage_pct'],0.)
        self.assertEqual(fills[0]['quote_age_ms'],2000)

    def test_i4_plan_waits_for_fresh_quote_at_actual_trigger(self):
        self.hawk.submit(plan(),NOW,CONTRACTS,{'BTC':quote()})
        out=self.hawk.tick(market(ts=NOW-5000),CONTRACTS,NOW)
        self.assertEqual((out['positions'],out['pending']),(0,1))
        fresh_out=self.hawk.tick(market(ts=NOW-1000),CONTRACTS,NOW)
        self.assertEqual((fresh_out['positions'],fresh_out['pending']),(1,0))


class PairErrorIsolation(unittest.TestCase):
    def test_b3c_hawk_failure_does_not_skip_bull(self):
        with tempfile.TemporaryDirectory() as root:
            pair=BrainPair(root,initialize=True,now_ms=NOW)
            try:
                with patch.object(pair.hawk,'tick',side_effect=ValueError('bad-market')):
                    result=pair.tick(market(),CONTRACTS,NOW+1000)
                self.assertEqual(result['hawk']['status'],'error')
                self.assertEqual(result['hawk']['error_type'],'ValueError')
                self.assertEqual(result['bull']['positions'],0)
                self.assertEqual(pair.bull.store.load()['last_ms'],NOW+1000)
                rows=pair.hawk.store.db.execute(
                    "SELECT kind FROM events WHERE kind='wallet_tick_error'").fetchall()
                self.assertEqual(rows,[('wallet_tick_error',)])
            finally:
                pair.close()

    def test_b3c_simultaneous_failures_are_both_reported(self):
        with tempfile.TemporaryDirectory() as root:
            pair=BrainPair(root,initialize=True,now_ms=NOW)
            try:
                with patch.object(pair.hawk,'tick',side_effect=ValueError('hawk')):
                    with patch.object(pair.bull,'tick',side_effect=TypeError('bull')):
                        result=pair.tick(market(),CONTRACTS,NOW+1000)
                self.assertEqual(result['hawk']['error_type'],'ValueError')
                self.assertEqual(result['bull']['error_type'],'TypeError')
            finally:
                pair.close()


if __name__=='__main__':
    unittest.main()
