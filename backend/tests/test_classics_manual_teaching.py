"""Classical 13-Oct PAPER manual-close teaching, isolated from running bots."""
import tempfile
from pathlib import Path
import unittest

from desk.manual_teaching_bridge import (
    to_attested_close,record_verified_manual_closures,
    review_messages,review_groups,answer_review,
)


def rec(symbol='BTC',why='chiusura manuale',net=15.0):
    return {'id':42,'symbol':symbol,'side':-1,'entry':100.,'exit':98.,
            'leverage':10,'margin':100.,'net':net,
            'open_ms':1800000000000,'close_ms':1800000060000,
            'why':why,'source':'rules','account':'hawk','partial':False}


class ClassicalManual(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()

    def test_only_saved_manual_paper_close_can_be_inbox_event(self):
        row=rec()
        with self.assertRaisesRegex(ValueError,'unverified_classical_manual_close'):
            to_attested_close(row,'hawk',8,persisted=False,remaining={})
        with self.assertRaisesRegex(ValueError,'unverified_classical_manual_close'):
            to_attested_close(row,'hawk',8,persisted=True,remaining={'BTC':{}})
        with self.assertRaisesRegex(ValueError,'unverified_classical_manual_close'):
            to_attested_close(rec(why='stop loss'),'hawk',8,persisted=True,remaining={})
        with self.assertRaisesRegex(ValueError,'unverified_classical_manual_close'):
            to_attested_close(row,'bull',8,persisted=True,remaining={})
        clean=to_attested_close(row,'hawk',8,persisted=True,remaining={})
        self.assertEqual(clean['source'],'manual_user')
        self.assertEqual(clean['account_id'],'desk-hawk-paper-run-8')

    def test_append_only_yes_and_replay_duplicate(self):
        row=rec()
        ids=record_verified_manual_closures(self.path,'hawk',8,[row],persisted=True,remaining={})
        self.assertEqual(len(ids),1)
        again=record_verified_manual_closures(self.path,'hawk',8,[row],persisted=True,remaining={})
        self.assertEqual(ids,again)
        self.assertEqual(len(review_groups(self.path)),1)
        prompt=review_messages(self.path)[0]
        self.assertIn('/insegna_si',prompt)
        self.assertIn('HAWK',prompt)
        self.assertEqual(answer_review(self.path,'/insegna_si',
                     row['close_ms']+1000),1)
        self.assertIn('profit_ok_free_slot',(self.path/'learning_log.jsonl').read_text())
        self.assertIn('Osservazione, non regola operativa',(self.path/'lessons.md').read_text())
        self.assertFalse(review_groups(self.path))

    def test_rejected_lesson_has_only_unknown_intent(self):
        row=rec()
        record_verified_manual_closures(self.path,'hawk',8,[row],persisted=True,remaining={})
        answer_review(self.path,'/insegna_no',row['close_ms']+1000)
        self.assertFalse((self.path/'lessons.md').exists())
        self.assertIn('"user_intent": "unknown"',(self.path/'learning_log.jsonl').read_text())

    def test_no_learning_before_confirmation(self):
        row=rec()
        record_verified_manual_closures(self.path,'hawk',8,[row],persisted=True,remaining={})
        self.assertFalse((self.path/'learning_log.jsonl').exists())
        self.assertFalse((self.path/'lessons.md').exists())


if __name__=='__main__':unittest.main()
