"""Strictly authenticated offline Telegram updates for Brain PAPER closes."""
import tempfile
import unittest

from director.brain_scalp.coordinator import BrainAccount
from director.brain_scalp.operator import BrainOperator
from director.brain_scalp.telegram_commands import PaperTelegramCommands
from backend.tests.test_brain_resume import SPEC,NOW,markets,shortlist,plan,CONTRACTS


def update(ident,text,*,user=22,chat=11,at=NOW):
    return {'update_id':ident,'message':{
        'date':at//1000,'chat':{'id':chat},
        'from':{'id':user},'text':text,
    }}


class Commands(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.a=BrainAccount(self.tmp.name,spec=SPEC,initialize=True,now_ms=NOW)
        self.a.accept_ai_plans('brain',{'plans':[plan()]},shortlist(),markets(),CONTRACTS,NOW)
        self.a.tick(markets(),CONTRACTS,NOW+1)
        self.o=BrainOperator(self.a)
        self.h=PaperTelegramCommands(self.o,allowed_chat_id=11,allowed_user_id=22)
        self.m=markets(NOW+1000)
        self.m['BTC']['quote']['price']=101.0
    def tearDown(self):
        self.a.close();self.tmp.cleanup()
    def positions(self):
        return self.a.brain.store.load()['positions']

    def test_unauthorized_old_and_ambiguous_commands_cannot_close(self):
        for incoming in (update(1,'/chiudi brain BTCUSDT motivo=profitto_ok',user=4),
                         update(2,'/chiudi brain BTCUSDT motivo=profitto_ok',chat=4)):
            self.assertEqual(self.h.handle(incoming,self.m,NOW+1000)['status'],
                             'ignored_unauthorized')
        self.assertEqual(self.h.handle(update(3,'/chiudi all motivo=profitto_ok'),
                                       self.m,NOW+1000)['status'],
                         'unsupported_or_ambiguous_command')
        self.assertEqual(self.h.handle(update(4,'/chiudi brain BTCUSDT motivo=profitto_ok',
                              at=NOW-3600000),self.m,NOW+1000)['status'],
                         'stale_telegram_command')
        self.assertIn('BTC',self.positions())

    def test_account_scoped_close_idempotent_and_teaching_no(self):
        request=update(100,'/chiudi brain BTCUSDT motivo=profitto_ok')
        result=self.h.handle(request,self.m,NOW+1000)
        self.assertEqual(result['status'],'closed_paper_verified')
        self.assertEqual(result['result']['closed'],['BTC'])
        self.assertEqual(self.h.handle(request,self.m,NOW+1000)['status'],'duplicate_ignored')
        self.assertNotIn('BTC',self.positions())
        self.assertEqual(len(self.o.pending_reviews()),1)
        result=self.h.handle(update(101,'/insegna_no'),self.m,NOW+2000)
        self.assertEqual(result['status'],'teaching_recorded')
        self.assertEqual(result['count'],1)
        self.assertFalse(self.o.pending_reviews())

    def test_close_all_stale_quote_is_atomic_and_consumed_once(self):
        # Wrong timestamp cannot leave an ambiguous partially executed order.
        old=markets(NOW)
        req=update(103,'/chiudi brain all motivo=profitto_ok')
        with self.assertRaisesRegex(ValueError,'stale_operator_quote'):
            self.h.handle(req,old,NOW+5000)
        self.assertIn('BTC',self.positions())
        self.assertEqual(self.h.handle(req,self.m,NOW+1000)['status'],
                         'duplicate_ignored')

    def test_empty_command_returns_explicit_no_positions(self):
        self.h.handle(update(104,'/chiudi brain BTC motivo=profitto_ok'),
                      self.m,NOW+1000)
        r=self.h.handle(update(105,'/chiudi brain all motivo=profitto_ok'),
                        self.m,NOW+2000)
        self.assertEqual(r['status'],'no_open_paper_positions')


if __name__=='__main__':unittest.main()
