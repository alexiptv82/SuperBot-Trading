"""Read-only dashboard contract: never invent a PAPER mark or a closed trade."""
import tempfile
import unittest
from director.brain_scalp.coordinator import BrainAccount
from director.brain_scalp.snapshot import build_account_snapshot
from director.brain_scalp.operator import BrainOperator
from backend.tests.test_brain_resume import SPEC,NOW,markets,shortlist,plan,CONTRACTS


class SnapshotReadability(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.account=BrainAccount(self.tmp.name,spec=SPEC,initialize=True,now_ms=NOW)
        self.account.accept_ai_plans('brain',{'plans':[plan()]},
                                     shortlist(),markets(),CONTRACTS,NOW)
        self.account.tick(markets(),CONTRACTS,NOW+1)
    def tearDown(self):
        self.account.close();self.tmp.cleanup()

    def test_active_trade_has_mark_entry_leverage_and_net(self):
        q=markets(NOW+1000)
        q['BTC']['quote']['price']=101
        snap=build_account_snapshot(self.account,NOW+1000,q)
        self.assertEqual(snap['schema_version'],2)
        pos=snap['account']['positions'][0]
        self.assertEqual(pos['symbol'],'BTC')
        self.assertEqual(pos['mark_price'],101)
        self.assertEqual(pos['price_status'],'fresh')
        self.assertIsInstance(pos['net_close_estimate'],float)
        self.assertIsInstance(pos['pnl_pct_margin'],float)
        self.assertGreater(pos['pnl_pct_margin'],-100)

    def test_missing_or_old_price_shows_unknown_not_false_zero(self):
        for q in ({},markets(NOW)):
            snap=build_account_snapshot(self.account,NOW+20000,q)
            pos=snap['account']['positions'][0]
            self.assertIsNone(pos['mark_price'])
            self.assertIsNone(pos['net_close_estimate'])
            self.assertEqual(pos['price_status'],'unavailable')

    def test_closed_trade_history_is_account_local_and_derived_from_sqlite(self):
        operator=BrainOperator(self.account)
        q=markets(NOW+1000)
        q['BTC']['quote']['price']=102
        operator.close({'BTC':self.account.brain.store.load()['positions']['BTC']['id']},
                       q,NOW+1000)
        snap=build_account_snapshot(self.account,NOW+1000,q)
        account=snap['account']
        self.assertFalse(account['positions'])
        self.assertEqual(account['closed_total'],1)
        self.assertEqual(account['trades_shown'],1)
        self.assertEqual(account['trades'][0]['symbol'],'BTC')
        self.assertEqual(account['trades'][0]['source'],'manual_user')
        self.assertEqual(account['recent_closed_wins'],1)
        self.assertGreater(account['recent_closed_net_usd'],0)

if __name__=='__main__':unittest.main()
