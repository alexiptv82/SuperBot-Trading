"""Fail-closed PAPER AI position actions: real ledger, no exchange effects."""
import json
import tempfile
from unittest import TestCase

from director.brain_scalp.coordinator import BrainAccount
from director.brain_scalp.position_review import (
    build_position_review,record_position_review,evaluate_position_review)
from director.brain_scalp.supervisor import PaperSupervisor
from director.brain_scalp.ai_context import decode,encode
from backend.tests.test_brain_resume import SPEC,NOW,markets,CONTRACTS,plan,shortlist


def reply(system,user,action='SUGGEST_CLOSE',stop_price=None):
    payload=decode(user)
    ctx=payload.get('context',payload)
    reviews=[]
    for p in ctx['positions']:
        r={'symbol':p['symbol'],'position_id':p['position_id'],
           'action':action,'reason':'Net-cost aware PAPER review'}
        if stop_price is not None and action=='SUGGEST_TIGHTEN':
            r['stop_price']=stop_price
        reviews.append(r)
    return encode({'context_id':ctx['context_id'],'reviews':reviews})


class PaperPositionExecution(TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.wallet=BrainAccount(self.temp.name,spec=SPEC,
                                 initialize=True,now_ms=NOW)
        self.wallet.accept_ai_plans('brain',{'plans':[plan()]},
                                    shortlist(),markets(),CONTRACTS,NOW)
        self.wallet.tick(markets(),CONTRACTS,NOW+1)
        self.assertIn('BTC',self.wallet.brain.store.load()['positions'])
        self.now=NOW+1000

    def tearDown(self):
        self.wallet.close()
        self.temp.cleanup()

    def request(self):
        return build_position_review(self.wallet,markets(self.now),
                                     self.now,self.now+30000)

    def analysis(self,req,action='SUGGEST_CLOSE',stop=None,review_action=None,
                 reviewer=True,review_stop=None):
        def primary(system,user):
            return reply(system,user,action,stop)
        if reviewer:
            def second(system,user):
                return reply(system,user,
                             review_action or action,
                             review_stop if review_stop is not None else stop)
        else:
            second=None
        return evaluate_position_review(req,primary,second)

    def apply(self,req,result):
        return record_position_review(
            self.wallet,req,result,markets(self.now),self.now,
            execution_enabled=True,contracts=CONTRACTS)

    def events(self,kind):
        return [json.loads(row[0]) for row in self.wallet.brain.store.db.execute(
            'SELECT body FROM events WHERE kind=?',(kind,))]

    def test_default_advisory_never_changes_wallet(self):
        req=self.request();result=self.analysis(req)
        old=self.wallet.brain.store.load()
        receipt=record_position_review(
            self.wallet,req,result,markets(self.now),self.now)
        self.assertEqual(receipt['automatic_actions'],0)
        state=self.wallet.brain.store.load()
        self.assertEqual(state['positions'],old['positions'])
        self.assertEqual(state['cash'],old['cash'])

    def test_matching_closure_is_atomic_and_frees_slot(self):
        req=self.request();result=self.analysis(req)
        self.assertEqual(result.approved_symbols,('BTC',))
        receipt=self.apply(req,result)
        self.assertEqual(receipt['status'],'applied')
        self.assertEqual(receipt['automatic_actions'],1)
        state=self.wallet.brain.store.load()
        self.assertNotIn('BTC',state['positions'])
        self.assertEqual(state['metrics']['slots_used'],0)
        closed=self.events('trade_closed')
        self.assertEqual(len(closed),1)
        self.assertEqual(closed[0]['reason'],'AI:position_review')
        self.assertTrue(closed[0]['paper'])
        self.assertTrue(closed[0]['ai_reviewer_agreed'])
        self.assertEqual(self.events('ai_position_review_observed')[0]['automatic_actions'],1)
        self.assertEqual(self.apply(req,result)['status'],'rejected_context')
        self.assertEqual(len(self.events('trade_closed')),1)

    def test_action_requires_reviewer_and_primary_consensus(self):
        req=self.request();result=self.analysis(req,reviewer=False)
        self.assertFalse(result.reviewed)
        self.assertEqual(result.approved_symbols,())
        receipt=self.apply(req,result)
        self.assertEqual(receipt['status'],'observed')
        self.assertEqual(receipt['deferred'][0]['why'],'reviewer_agreement_required')
        self.assertIn('BTC',self.wallet.brain.store.load()['positions'])

    def test_reviewer_hold_vetoes_close(self):
        req=self.request();result=self.analysis(req,review_action='HOLD')
        self.assertTrue(result.reviewed)
        self.assertEqual(result.approved_symbols,())
        self.assertEqual(self.apply(req,result)['automatic_actions'],0)
        self.assertIn('BTC',self.wallet.brain.store.load()['positions'])

    def test_matching_stop_moves_only_toward_quote(self):
        state=self.wallet.brain.store.load()
        previous=state['positions']['BTC']['stop']
        quote=markets(self.now)['BTC']['quote']['price']
        stop=(quote+previous)/2
        self.assertGreater(stop,previous)
        req=self.request();result=self.analysis(
            req,action='SUGGEST_TIGHTEN',stop=stop)
        receipt=self.apply(req,result)
        self.assertEqual(receipt['status'],'applied')
        new=self.wallet.brain.store.load()['positions']['BTC']['stop']
        self.assertGreater(new,previous)
        self.assertLess(new,quote)
        self.assertEqual(len(self.events('ai_review_stop_tightened')),1)
        self.assertEqual(len(self.events('trade_closed')),0)

    def test_wrong_stop_reviewer_does_not_approve(self):
        state=self.wallet.brain.store.load()
        current=state['positions']['BTC']['stop']
        quote=markets(self.now)['BTC']['quote']['price']
        primary=(current+quote)/2
        secondary=(current+primary)/2
        req=self.request()
        result=self.analysis(req,action='SUGGEST_TIGHTEN',
                             stop=primary,review_stop=secondary)
        self.assertEqual(result.approved_symbols,())
        receipt=self.apply(req,result)
        self.assertEqual(receipt['automatic_actions'],0)
        self.assertEqual(self.wallet.brain.store.load()['positions']['BTC']['stop'],current)

    def test_widening_or_crossed_stop_is_rejected_atomically(self):
        state=self.wallet.brain.store.load()
        previous=state['positions']['BTC']['stop']
        quote=markets(self.now)['BTC']['quote']['price']
        for bad in (previous-2,quote+2):
            req=self.request();result=self.analysis(
                req,action='SUGGEST_TIGHTEN',stop=bad)
            self.assertEqual(self.apply(req,result)['status'],'rejected_context')
            after=self.wallet.brain.store.load()
            self.assertEqual(after['positions'],state['positions'])
            self.assertEqual(after['cash'],state['cash'])
            self.assertEqual(len(self.events('ai_review_stop_tightened')),0)

    def test_missing_stop_invalid_even_if_reviewed(self):
        req=self.request()
        result=self.analysis(req,action='SUGGEST_TIGHTEN')
        self.assertEqual(result.status,'primary_failed')
        self.assertEqual(self.apply(req,result)['status'],'primary_failed')

    def test_stale_market_and_expired_reply_cannot_close(self):
        req=self.request();result=self.analysis(req)
        moved=markets(self.now+1000);moved['BTC']['quote']['price']=109
        rejected=record_position_review(self.wallet,req,result,moved,self.now+1000,
                       execution_enabled=True,contracts=CONTRACTS)
        self.assertEqual(rejected['status'],'rejected_context')
        self.assertEqual(record_position_review(
            self.wallet,req,result,markets(self.now+31000),self.now+31000,
            execution_enabled=True,contracts=CONTRACTS)['status'],'rejected_context')
        self.assertIn('BTC',self.wallet.brain.store.load()['positions'])
        self.assertEqual(len(self.events('trade_closed')),0)

    def test_rejects_backward_owner_clock_even_with_fresh_mark(self):
        req=self.request();result=self.analysis(req)
        state=self.wallet.brain.store.load()
        state['last_ms']=self.now+2000
        self.wallet.brain.store.commit(state,self.now+2000,
                                      [{'kind':'test_advanced_clock'}])
        answer=record_position_review(
            self.wallet,req,result,markets(self.now+1000),self.now+1000,
            execution_enabled=True,contracts=CONTRACTS)
        self.assertEqual(answer['status'],'rejected_context')
        self.assertEqual(len(self.events('trade_closed')),0)

    def test_supervisor_reviewer_executes_after_protection_tick(self):
        supervisor=PaperSupervisor(
            self.wallet,primary_call=lambda s,u:reply(s,u),
            reviewer_call=lambda s,u:reply(s,u),clock_ms=lambda:self.now,
            daily_budget_micro_usd=200,reservation_micro_usd=100,
            analysis_interval_ms=1000,position_actions='paper')
        try:
            first=supervisor.step(markets(self.now),CONTRACTS)
            self.assertEqual(first['analysis_status'],'position_review_started')
            supervisor.future.result(timeout=5)
            self.now+=1000
            second=supervisor.step(markets(self.now),CONTRACTS)
            self.assertEqual(second['position_review']['status'],'applied')
            self.assertEqual(second['position_review']['automatic_actions'],1)
            self.assertNotIn('BTC',self.wallet.brain.store.load()['positions'])
            self.assertEqual(len(self.events('trade_closed')),1)
        finally:
            supervisor.close()

    def test_backup_integrity_includes_one_close_and_one_review(self):
        from pathlib import Path
        import sqlite3
        req=self.request();result=self.analysis(req)
        self.assertEqual(self.apply(req,result)['status'],'applied')
        backup=Path(self.temp.name)/'brain-after-close.sqlite'
        self.wallet.brain.store.backup(backup)
        with sqlite3.connect(backup) as db:
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM events WHERE kind='trade_closed'").fetchone()[0],1)
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM events WHERE kind='ai_position_review_observed'").fetchone()[0],1)

    def test_restored_backup_preserves_identity_events_and_rejects_replay(self):
        from pathlib import Path
        req=self.request();result=self.analysis(req)
        self.assertEqual(self.apply(req,result)['status'],'applied')
        expected=self.wallet.brain.store.load()
        events=self.wallet.brain.store.db.execute('SELECT * FROM events ORDER BY seq').fetchall()
        with tempfile.TemporaryDirectory() as restored_dir:
            root=Path(restored_dir)/'brain'
            root.mkdir()
            self.wallet.brain.store.backup(root/'brain_scalp.sqlite3')
            restored=BrainAccount(restored_dir,spec=SPEC,initialize=False,now_ms=self.now)
            try:
                self.assertEqual(restored.brain.store.load(),expected)
                self.assertEqual(restored.brain.store.db.execute('SELECT * FROM events ORDER BY seq').fetchall(),events)
                receipt=record_position_review(restored,req,result,markets(self.now),self.now,
                                               execution_enabled=True,contracts=CONTRACTS)
                self.assertEqual(receipt['status'],'rejected_context')
                self.assertEqual(restored.brain.store.load(),expected)
                self.assertEqual(restored.brain.store.db.execute('SELECT * FROM events ORDER BY seq').fetchall(),events)
            finally:
                restored.close()

    def test_service_defaults_off_and_requires_explicit_paper_mode(self):
        from pathlib import Path
        from backend.tests.test_brain_single_integration import setup_env
        from director.brain_scalp.service import required_env
        env=setup_env(Path(self.temp.name))
        self.assertEqual(required_env(env)['position_actions'],'off')
        env['BRAIN_AI_POSITION_ACTIONS']='paper'
        self.assertEqual(required_env(env)['position_actions'],'paper')
        for invalid in ('live','auto','yes','true'):
            env['BRAIN_AI_POSITION_ACTIONS']=invalid
            with self.assertRaisesRegex(ValueError,'invalid_brain_position_actions_mode'):
                required_env(env)

    def test_opt_in_mode_rejects_live_and_unknown(self):
        for mode in ('live','enabled',True,1,None):
            with self.assertRaises(ValueError):
                PaperSupervisor(self.wallet,primary_call=reply,
                                reviewer_call=None,clock_ms=lambda:self.now,
                                daily_budget_micro_usd=100,
                                reservation_micro_usd=100,
                                position_actions=mode)

    def test_provider_error_is_not_an_execution_authorization(self):
        req=self.request()
        result=evaluate_position_review(
            req,lambda s,u:(_ for _ in ()).throw(ValueError('offline')))
        self.assertEqual(result.status,'primary_failed')
        self.assertEqual(self.apply(req,result)['status'],'primary_failed')
        self.assertEqual(len(self.events('trade_closed')),0)

    def test_closed_position_version_changed_during_ai_is_rejected(self):
        req=self.request();result=self.analysis(req)
        state=self.wallet.brain.store.load()
        state['positions']['BTC']['id']+=1
        self.wallet.brain.store.commit(state,self.now,
                                      [{'kind':'test_changed_position_id'}])
        self.assertEqual(self.apply(req,result)['status'],'rejected_context')
        self.assertEqual(len(self.events('trade_closed')),0)
