"""Operator PAPER closes are an attested ledger transaction, not an exchange watcher."""
import tempfile
from pathlib import Path
import unittest

from director.brain_scalp.coordinator import BrainAccount
from director.brain_scalp.operator import BrainOperator
from backend.tests.test_brain_resume import SPEC,NOW,markets,shortlist,plan,CONTRACTS


class ManualClose(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.account=BrainAccount(self.tmp.name,spec=SPEC,initialize=True,now_ms=NOW)
        raw={'plans':[plan()]}
        self.account.accept_ai_plans('brain',raw,shortlist(),markets(),CONTRACTS,NOW)
        self.account.tick(markets(),CONTRACTS,NOW+1)
        assert 'BTC' in self.account.brain.store.load()['positions']
        self.op=BrainOperator(self.account)
    def tearDown(self):
        self.account.close()
        self.tmp.cleanup()
    def current(self):
        return self.account.brain.store.load()['positions']['BTC']['id']

    def test_confirmed_manual_close_is_verified_and_append_only(self):
        ident=self.current()
        profitable=markets(NOW+1000)
        profitable['BTC']['quote']['price']=102.0
        result=self.op.close({'BTC':ident},profitable,NOW+1000)
        self.assertGreater(result['net_usd'],0)
        self.assertEqual(result['closed'],['BTC'])
        self.assertNotIn('BTC',self.account.brain.store.load()['positions'])
        last=self.account.brain.store.db.execute(
            "SELECT body FROM events WHERE kind='trade_closed' ORDER BY seq DESC LIMIT 1").fetchone()[0]
        self.assertIn('"source":"manual_user"',last)
        self.assertIn('"paper":true',last)
        pending=self.op.pending_reviews()
        self.assertEqual(len(pending),1)
        self.assertEqual(len(pending[0]['ids']),1)
        self.assertIn('/insegna_si',self.op.review_messages()[0])
        count=self.op.confirm('/insegna_si '+pending[0]['group_id'],NOW+2000)
        self.assertEqual(count,1)
        learn=Path(self.tmp.name)/'brain'/'learning_log.jsonl'
        self.assertTrue(learn.is_file())
        text=learn.read_text()
        self.assertIn('"user_intent":',text)
        self.assertIn('profit_ok_free_slot',text)
        self.assertEqual(self.op.sync(),0)
        self.assertEqual(len(learn.read_text().splitlines()),1)
        with self.assertRaisesRegex(ValueError,'stale_position_id'):
            self.op.close({'BTC':ident},markets(NOW+3000),NOW+3000)

    def test_fresh_quote_and_position_version_gate_before_any_close(self):
        ident=self.current()
        with self.assertRaisesRegex(ValueError,'stale_operator_quote'):
            self.op.close({'BTC':ident},markets(NOW),NOW+10000)
        self.assertIn('BTC',self.account.brain.store.load()['positions'])
        with self.assertRaisesRegex(ValueError,'stale_position_id'):
            self.op.close({'BTC':ident+1},markets(NOW+1000),NOW+1000)
        self.assertIn('BTC',self.account.brain.store.load()['positions'])

    def test_batch_is_all_or_nothing_if_one_symbol_missing(self):
        ident=self.current()
        with self.assertRaisesRegex(ValueError,'stale_position_id'):
            self.op.close({'BTC':ident,'ETH':10},markets(NOW+1000),NOW+1000)
        self.assertIn('BTC',self.account.brain.store.load()['positions'])
        self.assertFalse(self.op.pending_reviews())

    def test_reviewer_no_does_not_create_lesson(self):
        ident=self.current()
        self.op.close({'BTC':ident},markets(NOW+1000),NOW+1000)
        self.assertEqual(self.op.confirm('/insegna_no',NOW+2000),1)
        lessons=Path(self.tmp.name)/'brain'/'lessons.md'
        self.assertFalse(lessons.exists())
        text=(Path(self.tmp.name)/'brain'/'learning_log.jsonl').read_text()
        self.assertIn('"user_intent": "unknown"',text)

    def test_missing_post_commit_teaching_is_recoverable(self):
        ident=self.current()
        self.op.close({'BTC':ident},markets(NOW+1000),NOW+1000)
        # Simulate process restarted with an empty teaching inbox only
        journal=Path(self.tmp.name)/'brain'/'manual_close_reviews.jsonl'
        journal.unlink()
        self.assertEqual(self.op.sync(),1)
        self.assertEqual(len(self.op.pending_reviews()),1)


if __name__=='__main__':unittest.main()
