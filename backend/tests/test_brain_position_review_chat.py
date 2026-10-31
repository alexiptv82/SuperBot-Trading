"""Offline regression: position observations cannot execute financial actions."""
import json
from threading import Event
from unittest import TestCase

from director.brain_scalp.coordinator import BrainAccount
from director.brain_scalp.supervisor import PaperSupervisor
from director.brain_scalp.position_review import (
    build_position_review,parse_review,evaluate_position_review,
    record_position_review)
from director.brain_scalp.ai_context import decode,encode
from backend.tests.test_brain_resume import SPEC,NOW,markets,CONTRACTS,plan,shortlist,breakout,hold
import tempfile


def answer(system,user,action='HOLD'):
    context=decode(user)
    assert context['scope']=='position_review_advisory_only'
    return encode({'context_id':context['context_id'],
                   'reviews':[{'symbol':p['symbol'],
                               'position_id':p['position_id'],
                               'action':action,'reason':'Tested paper observation'}
                              for p in context['positions']]})


class PositionReviews(TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.account=BrainAccount(self.tmp.name,spec=SPEC,initialize=True,now_ms=NOW)
        self.account.accept_ai_plans('brain',{'plans':[plan()]},
                                     shortlist(),markets(),CONTRACTS,NOW)
        self.account.tick(markets(),CONTRACTS,NOW+1)
        self.assertIn('BTC',self.account.brain.store.load()['positions'])
        self.now=NOW+1000
        self.supervisor=None
        self.release=None

    def tearDown(self):
        if self.release is not None:
            self.release.set()
        if self.supervisor is not None:
            if self.supervisor.future is not None:
                self.supervisor.future.result(timeout=5)
            self.supervisor.close()
        self.account.close()
        self.tmp.cleanup()

    def start(self,primary=answer,reviewer=None):
        self.supervisor=PaperSupervisor(
            self.account,primary_call=primary,reviewer_call=reviewer,
            clock_ms=lambda:self.now,daily_budget_micro_usd=200,
            reservation_micro_usd=100,analysis_interval_ms=1000)
        return self.supervisor

    def test_empty_scanner_still_reviews_open_position_without_trading(self):
        supervisor=self.start()
        before=self.account.brain.store.load()
        result=supervisor.step(markets(self.now),CONTRACTS)
        self.assertEqual(result['analysis_status'],'position_review_started')
        supervisor.future.result(timeout=5)
        self.now+=1000
        result=supervisor.step(markets(self.now),CONTRACTS)
        self.assertEqual(result['position_review']['status'],'observed')
        self.assertEqual(result['position_review']['automatic_actions'],0)
        after=self.account.brain.store.load()
        self.assertEqual(set(after['positions']),set(before['positions']))
        self.assertEqual(after['cash'],before['cash'])
        kinds=[r[0] for r in self.account.brain.store.db.execute('SELECT kind FROM events')]
        self.assertEqual(kinds.count('ai_position_review_observed'),1)
        self.assertEqual(after['ai_budget_reservation']['reserved_micro_usd'],100)

    def test_entries_start_first_and_review_gets_a_turn_when_both_exist(self):
        def both(system,user):
            if decode(user).get('scope')=='position_review_advisory_only':
                return answer(system,user)
            return hold(system,user)
        supervisor=self.start(primary=both)
        self.assertEqual(supervisor.step(
            breakout(self.now),CONTRACTS)['analysis_status'],'started')
        supervisor.future.result(timeout=5)
        self.now+=1000
        self.assertEqual(supervisor.step(
            breakout(self.now),CONTRACTS)['analysis_status'],'completed')
        self.now+=1000
        self.assertEqual(supervisor.step(
            breakout(self.now),CONTRACTS)['analysis_status'],'position_review_started')

    def test_failed_provider_is_persisted_without_exception_text_or_execution(self):
        from director.brain_scalp.snapshot import build_account_snapshot
        supervisor=self.start(primary=lambda s,u:{'error':'balance','usage':None})
        supervisor.step(markets(self.now),CONTRACTS)
        supervisor.future.result(timeout=5);self.now+=1000
        response=supervisor.step(markets(self.now),CONTRACTS)
        self.assertEqual(response['ai_attempt']['provider'],'deepseek')
        self.assertEqual(response['ai_attempt']['failure_code'],'balance')
        self.assertIn('BTC',self.account.brain.store.load()['positions'])
        snap=build_account_snapshot(self.account,self.now,markets(self.now))
        self.assertEqual(snap['account']['ai_attempt'],response['ai_attempt'])
        self.assertNotIn('position_review',response.get('analysis',{}))
        self.now+=1000
        def bad(s,u):raise RuntimeError('SYNTHETIC_SECRET_BODY')
        supervisor.primary=bad
        supervisor.step(markets(self.now),CONTRACTS)
        supervisor.future.result(timeout=5);self.now+=1000
        response=supervisor.step(markets(self.now),CONTRACTS)
        self.assertEqual(response['ai_attempt']['failure_code'],'invalid_response')
        self.assertNotIn('SYNTHETIC_SECRET_BODY',json.dumps(response))

    def test_reviewer_failure_names_claude_and_keeps_position(self):
        supervisor=self.start(primary=lambda s,u:answer(s,u,'SUGGEST_CLOSE'),
                              reviewer=lambda s,u:{'error':'auth','usage':None})
        supervisor.step(markets(self.now),CONTRACTS)
        supervisor.future.result(timeout=5);self.now+=1000
        result=supervisor.step(markets(self.now),CONTRACTS)
        self.assertEqual(result['ai_attempt']['provider'],'claude')
        self.assertEqual(result['ai_attempt']['failure_code'],'auth')
        self.assertIn('BTC',self.account.brain.store.load()['positions'])

    def test_duplicate_replay_is_idempotent(self):
        req=build_position_review(self.account,markets(self.now),self.now,self.now+30000)
        result=evaluate_position_review(req,answer)
        self.assertEqual(result.status,'ready')
        one=record_position_review(self.account,req,result,markets(self.now),self.now)
        two=record_position_review(self.account,req,result,markets(self.now),self.now)
        self.assertEqual(one['status'],'observed')
        self.assertEqual(two['status'],'duplicate')

    def test_quote_or_position_changed_rejects_review(self):
        req=build_position_review(self.account,markets(self.now),self.now,self.now+30000)
        result=evaluate_position_review(req,answer)
        moved=markets(self.now+1000)
        moved['BTC']['quote']['price']=110.0
        self.assertEqual(record_position_review(
            self.account,req,result,moved,self.now+1000)['status'],
            'rejected_context')
        self.assertEqual(record_position_review(
            self.account,req,result,markets(self.now+31000),self.now+31000)['status'],
            'rejected_context')
        self.assertNotIn('last_position_review_context_id',
                         self.account.brain.store.load())

    def test_bad_provider_response_has_no_journal_or_unsafe_fallback(self):
        req=build_position_review(self.account,markets(self.now),self.now,self.now+30000)
        def bad(system,user):
            return json.dumps({'context_id':req.context_id,'reviews':[
                {'symbol':'DOGE','position_id':'1','action':'SUGGEST_CLOSE',
                 'reason':'wrong position'}]})
        result=evaluate_position_review(req,bad)
        self.assertEqual(result.status,'primary_failed')
        self.assertEqual(record_position_review(
            self.account,req,result,markets(self.now),self.now)['status'],
            'primary_failed')

    def test_reviewer_selective_and_observational(self):
        req=build_position_review(self.account,markets(self.now),self.now,self.now+30000)
        def primary(system,user):
            return answer(system,user,'SUGGEST_CLOSE')
        count=[]
        def reviewer(system,user):
            count.append(1)
            return answer(system,encode(decode(user)['context']),'HOLD')
        result=evaluate_position_review(req,primary,reviewer)
        self.assertEqual(result.status,'ready')
        self.assertTrue(result.reviewed)
        self.assertEqual(len(count),1)
        self.assertEqual(decode(result.recommendations_json)[0]['action'],'HOLD')
        self.assertEqual(record_position_review(
            self.account,req,result,markets(self.now),self.now)['automatic_actions'],0)

    def test_protector_remains_independent_of_slow_review(self):
        gate=Event();started=Event();self.release=gate
        def slow(system,user):
            started.set();gate.wait(4)
            return answer(system,user)
        supervisor=self.start(primary=slow)
        self.assertEqual(supervisor.step(
            markets(self.now),CONTRACTS)['analysis_status'],'position_review_started')
        self.assertTrue(started.wait(2))
        self.now+=1000
        data=markets(self.now);data['BTC']['quote']['price']=90.0
        state=supervisor.step(data,CONTRACTS)
        self.assertEqual(state['analysis_status'],'pending')
        self.assertNotIn('BTC',self.account.brain.store.load()['positions'])
        gate.set();supervisor.future.result(timeout=5)
        self.assertEqual(supervisor.step(data,CONTRACTS)['position_review']['status'],
                         'rejected_context')
