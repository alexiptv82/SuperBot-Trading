"""AI context integration with synthetic callbacks only: no HTTP, keys or VPS."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from director.brain_scalp.coordinator import BrainPair
from director.brain_scalp.ai_context import build_request,decode,encode,account_fingerprint
from director.brain_scalp.ai_analysis import evaluate,parse_reply,AIAnalysis
from director.brain_scalp.legacy_reference import REFERENCE_SOURCE_SHA,SOURCE_HASHES
from director.brain_scalp.store import wallet_spec_digest
from backend.tests.test_brain_scalp_group1 import NOW,CONTRACTS,plan


def markets(now=NOW):
    bars={}
    for tf,duration,n in [('1m',60000,18),('5m',300000,22)]:
        end=now//duration*duration
        bars[tf]=[[end-(n-i)*duration,100.,100.1,99.9,100.,80.] for i in range(n)]
    return {'BTC':{'quote':{'price':100.,'ts_ms':now},'bars':bars,'funding':[]}}


def shortlist():
    return {'candidates':[{'symbol':'BTC','side':1,'signal_close_ms':NOW,
                           'setup':'breakout_long'}]}


def references(side=1):
    return {'BTC':{'reading':{'symbol':'BTC','price':100.,'side':side,
            'long_score':70 if side==1 else 10,'short_score':10 if side==1 else 70,
            'facts':{'rsi1h':55.,'vol_ratio':1.8},'why':['trend 4h (+20)']},
            'source_sha':REFERENCE_SOURCE_SHA,'source_hashes':dict(SOURCE_HASHES),
            'observed_ms':NOW,'max_age_ms':60000}}


def reply(req,plans=None,flags=()):
    proposed=[] if plans is None else plans
    candidates=decode(req.payload_json)['candidates']
    return {'context_id':req.context_id,'plans':proposed,
        'assessments':[{'symbol':c['symbol'],'long_case':'Causal upward structure.',
            'short_case':'Downward alternative remains possible.',
            'decision':'LONG' if proposed else 'HOLD','review_flags':list(flags)}
            for c in candidates],'summary':'Synthetic PAPER decision.'}


def primary(req,plans=None,flags=()):
    return lambda system,user: {'content':encode(reply(req,plans,flags)),
        'usage':{'prompt_tokens':100,'completion_tokens':50},'finish_reason':'stop'}


class AIContext(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.pair=BrainPair(self.tmp.name,initialize=True,now_ms=NOW)
        self.w=self.pair.hawk

    def tearDown(self):
        self.pair.close();self.tmp.cleanup()

    def request(self,refs=None,market=None):
        return self.pair.prepare_ai_request('hawk',shortlist(),
            markets() if market is None else market,CONTRACTS,
            references() if refs is None else refs,NOW,NOW+30000)

    def admit(self,req,analysis,now=NOW+1000,market=None):
        return self.pair.accept_ai_analysis('hawk',req,analysis,
            markets(now) if market is None else market,CONTRACTS,now)

    def test_context_has_both_sides_costs_and_only_selected_wallet(self):
        before=[self.w.store.load(),self.pair.bull.store.load()]
        req=self.request();payload=decode(req.payload_json)
        ref=payload['candidates'][0]['classical_reference']['value']
        self.assertEqual(ref['direction_scores'],{'LONG':70.,'SHORT':10.})
        self.assertFalse(ref['execution_permission'])
        self.assertEqual(payload['costs']['taker_fee_per_side'],.0006)
        self.assertEqual(payload['account_id'],'brain-scalp-hawk-paper')
        self.assertNotIn('profiles',payload)
        self.assertEqual([self.w.store.load(),self.pair.bull.store.load()],before)

    def test_context_can_represent_one_2000_account_without_combining_databases(self):
        state=self.w.store.load()
        spec=replace(self.w.spec,name='brain',account_id='single-paper-fixture',start_cash=2000)
        state.update(account_id=spec.account_id,cash=2000,config_hash=wallet_spec_digest(spec))
        req=build_request(state,spec,markets(),CONTRACTS,shortlist(),references(),[],NOW,NOW+30000)
        payload=decode(req.payload_json)
        self.assertEqual(payload['account']['initial_cash'],2000)
        self.assertEqual(payload['account']['cash'],2000)
        self.assertNotIn('bull',payload)
        self.assertEqual(self.w.store.load()['cash'],1000)

    def test_untrusted_extra_fields_and_future_closed_bars_do_not_leak(self):
        data=markets();data['BTC']['api_key']='PRIVATE_KEY'
        data['BTC']['bars']['1m'][-1].append('PRIVATE_KEY')
        data['BTC']['bars']['1m'].append([NOW+60000,9999,9999,9999,9999,9999])
        raw=decode(self.request(market=data).payload_json)
        self.assertNotIn('PRIVATE_KEY',encode(raw))
        self.assertTrue(all(b[0]+60000<=NOW for b in raw['candidates'][0]['closed_bars']['1m']))

    def test_stale_market_is_excluded_and_bad_reference_is_only_unavailable(self):
        data=markets();data['BTC']['quote']['ts_ms']=NOW-4000
        req=self.request(market=data)
        self.assertEqual(decode(req.payload_json)['candidates'],[])
        self.assertEqual(self.admit(req,evaluate(req,primary(req)))['accepted'],[])
        bad=references();bad['BTC']['source_sha']='invalid'
        payload=decode(self.request(refs=bad).payload_json)
        self.assertEqual(payload['candidates'][0]['classical_reference']['status'],'unavailable')

    def test_recent_memory_excludes_future_and_foreign_account(self):
        events=[{'kind':'trade_closed','symbol':'BTC','close_ms':NOW-1000,'net':-2,
                 'api_key':'PRIVATE_KEY'},
                {'kind':'trade_closed','symbol':'BTC','close_ms':NOW+1000,'net':9999},
                {'kind':'trade_closed','symbol':'BTC','close_ms':NOW-500,
                 'account_id':'foreign','net':8888}]
        self.w.store.commit(self.w.store.load(),NOW,events)
        memory=decode(self.request().payload_json)['last_completed_trades']
        self.assertEqual(len(memory),1)
        self.assertEqual(memory[0]['net'],-2)
        self.assertNotIn('PRIVATE_KEY',encode(memory))

    def test_deepseek_reply_reserves_plan_and_tick_executes_under_existing_guards(self):
        req=self.request();analysis=evaluate(req,primary(req,[plan()]))
        out=self.admit(req,analysis)
        self.assertEqual(out['status'],'processed');self.assertEqual(len(out['accepted']),1)
        self.assertEqual(self.pair.bull.store.load()['plans'],{})
        result=self.pair.tick(markets(NOW+2000),CONTRACTS,NOW+2000)
        self.assertEqual(result['hawk']['positions'],1)
        self.assertLessEqual(self.w.store.load()['positions']['BTC']['margin'],100)

    def test_claude_gets_same_context_and_can_hold_a_disagreement(self):
        req=self.request(refs=references(-1));calls=[]
        def reviewer(system,user):
            data=decode(user);calls.append(data)
            self.assertEqual(data['context_id'],req.context_id)
            self.assertEqual(data['candidates'],decode(req.payload_json)['candidates'])
            return encode(reply(req)),{'input_tokens':70,'output_tokens':20}
        analysis=evaluate(req,primary(req,[plan()]),reviewer)
        self.assertTrue(analysis.reviewed);self.assertEqual(len(calls),1)
        out=self.admit(req,analysis)
        self.assertEqual(out['accepted'],[])
        self.assertTrue(out['reviewed'])
        self.assertEqual(self.w.store.load()['plans'],{})

    def test_claude_can_return_a_guarded_plan_despite_reference_disagreement(self):
        req=self.request(refs=references(-1))
        analysis=evaluate(req,primary(req,[plan()]),
            lambda system,user:(encode(reply(req,[plan()])),{'input_tokens':70,'output_tokens':20}))
        self.assertTrue(analysis.reviewed)
        self.assertEqual(len(self.admit(req,analysis)['accepted']),1)

    def test_review_is_selective_and_not_triggered_by_hold(self):
        req=self.request(refs=references(-1));calls=[]
        analysis=evaluate(req,primary(req),lambda *args:calls.append(args))
        self.assertEqual(analysis.status,'ready');self.assertFalse(analysis.reviewed)
        self.assertEqual(calls,[])

    def test_missing_or_failed_reviewer_never_falls_back_to_primary_trade(self):
        req=self.request(refs=references(-1))
        for reviewer in (None,lambda *args:(_ for _ in ()).throw(RuntimeError('SECRET')),
                         lambda *args:'malformed'):
            before=self.w.store.load()
            analysis=evaluate(req,primary(req,[plan()]),reviewer)
            self.assertIn(analysis.status,('review_required','review_failed'))
            self.assertEqual(self.admit(req,analysis)['accepted'],[])
            self.assertEqual(self.w.store.load(),before)
            self.assertNotIn('SECRET',repr(analysis))

    def test_timing_flag_and_float_side_do_not_bypass_review(self):
        req=self.request()
        analysis=evaluate(req,primary(req,[plan()],['timing_uncertain']))
        self.assertEqual(analysis.status,'review_required')
        req=self.request(refs=references(-1));p=plan();p['side']=1.0
        self.assertEqual(evaluate(req,primary(req,[p])).status,'review_required')

    def test_duplicate_keys_wrong_context_or_truncation_fail_closed(self):
        req=self.request()
        values=[
            '{"context_id":"a","context_id":"b","plans":[],"assessments":[]}',
            encode(dict(reply(req),context_id='foreign')),
            {'content':encode(reply(req)),'finish_reason':'length'},
            (encode(reply(req)),{'stop_reason':'max_tokens'}),
            encode(dict(reply(req),assessments=[])),
        ]
        for value in values:
            with self.subTest(value=value):
                before=self.w.store.load()
                analysis=evaluate(req,lambda *args:value)
                self.assertEqual(analysis.status,'primary_failed')
                self.assertEqual(self.admit(req,analysis)['accepted'],[])
                self.assertEqual(self.w.store.load(),before)

    def test_provider_failures_do_not_expose_raw_errors(self):
        req=self.request()
        analysis=evaluate(req,lambda *args:(_ for _ in ()).throw(RuntimeError('API_KEY_SECRET')))
        self.assertEqual(analysis.status,'primary_failed')
        self.assertNotIn('API_KEY_SECRET',repr(analysis))

    def test_changed_cash_pending_exposure_or_stop_rejects_old_context(self):
        for field,value in [('cash',999),('paused',True),('daily_stop_triggered',True)]:
            with self.subTest(field=field):
                req=self.request();analysis=evaluate(req,primary(req,[plan()]))
                original=self.w.store.load();state=deepcopy(original);state[field]=value
                self.w.store.commit(state,NOW)
                self.assertEqual(self.admit(req,analysis)['status'],'rejected_context')
                self.assertEqual(self.w.store.load()['plans'],{})
                restored=deepcopy(original);restored['_version']=self.w.store.load()['_version']
                self.w.store.commit(restored,NOW)

    def test_heartbeat_price_and_metrics_tick_can_advance_during_analysis(self):
        req=self.request();analysis=evaluate(req,primary(req,[plan()]))
        self.pair.tick(markets(NOW+500),CONTRACTS,NOW+500)
        self.assertEqual(len(self.admit(req,analysis)['accepted']),1)

    def test_new_reservation_during_analysis_rejects_old_answer(self):
        req=self.request();analysis=evaluate(req,primary(req,[plan()]))
        self.w.submit(plan(),NOW,CONTRACTS,{'BTC':markets()['BTC']['quote']})
        before=self.w.store.load()
        self.assertEqual(self.admit(req,analysis)['status'],'rejected_context')
        self.assertEqual(self.w.store.load(),before)

    def test_new_position_or_changed_protection_levels_invalidates_context(self):
        req=self.request();analysis=evaluate(req,primary(req,[plan()]))
        self.w.submit(plan(),NOW,CONTRACTS,{'BTC':markets()['BTC']['quote']})
        self.pair.tick(markets(NOW+500),CONTRACTS,NOW+500)
        self.assertEqual(self.admit(req,analysis)['status'],'rejected_context')
        state=self.w.store.load();fingerprint=account_fingerprint(state)
        for key in ('stop','target','qty','margin','funding'):
            with self.subTest(key=key):
                changed=deepcopy(state);changed['positions']['BTC'][key]+=0.01
                self.assertNotEqual(account_fingerprint(changed),fingerprint)

    def test_expired_request_reference_or_wrong_wallet_cannot_admit(self):
        req=self.request();analysis=evaluate(req,primary(req,[plan()]))
        self.assertEqual(self.admit(req,analysis,NOW+30001)['status'],'rejected_context')
        self.assertEqual(self.pair.accept_ai_analysis('bull',req,analysis,
            markets(NOW+1000),CONTRACTS,NOW+1000)['status'],'rejected_context')
        refs=references();refs['BTC']['max_age_ms']=1000
        req=self.request(refs=refs);analysis=evaluate(req,primary(req,[plan()]))
        self.assertEqual(self.admit(req,analysis,NOW+1001)['status'],'rejected_context')

    def test_request_body_mutation_is_detected(self):
        req=self.request();analysis=evaluate(req,primary(req,[plan()]))
        raw=decode(req.payload_json);raw['account']['cash']=9000
        altered=replace(req,payload_json=encode(raw))
        self.assertEqual(self.admit(altered,analysis)['status'],'rejected_context')
        altered=replace(req,account_id='foreign')
        self.assertEqual(self.admit(altered,analysis)['status'],'rejected_context')

    def test_invalid_or_altered_request_never_calls_a_provider(self):
        req=self.request();calls=[]
        for candidate in (None,replace(req,payload_json='{}')):
            with self.subTest(candidate=candidate):
                with self.assertRaises(ValueError):
                    evaluate(candidate,lambda *args:calls.append(args))
        self.assertEqual(calls,[])

    def test_replay_of_processed_hold_is_rejected_after_restart(self):
        req=self.request();analysis=evaluate(req,primary(req))
        self.assertEqual(self.admit(req,analysis)['status'],'processed')
        self.pair.close()
        self.pair=BrainPair(self.tmp.name);self.w=self.pair.hawk
        self.assertEqual(self.admit(req,analysis)['status'],'rejected_context')

    def test_each_plan_is_still_validated_independently(self):
        req=self.request()
        bad={'symbol':[],'side':1}
        out=self.admit(req,evaluate(req,primary(req,[bad,plan()])))
        self.assertEqual(len(out['accepted']),1);self.assertEqual(len(out['rejected']),1)

    def test_current_quote_overshoot_is_rejected_even_if_ai_context_is_valid(self):
        req=self.request();analysis=evaluate(req,primary(req,[plan()]))
        current=markets(NOW+1000);current['BTC']['quote']['price']=101.
        out=self.admit(req,analysis,market=current)
        self.assertEqual(out['accepted'],[])
        self.assertEqual(out['rejected'][0]['why'],'trigger_already_breached')

    def test_only_safe_request_metadata_and_usage_are_journalled(self):
        req=self.request()
        callback=lambda *args:{'content':encode(reply(req,[plan()])),
            'usage':{'prompt_tokens':100,'completion_tokens':50,'api_key':'SECRET'}}
        self.admit(req,evaluate(req,callback))
        body=json.loads(self.w.store.db.execute(
            "SELECT body FROM events WHERE kind='ai_context_processed'").fetchone()[0])
        self.assertEqual(body['context_id'],req.context_id)
        self.assertEqual(body['usage']['deepseek'],{'prompt_tokens':100,'completion_tokens':50})
        self.assertNotIn('SECRET',encode(body));self.assertNotIn('primary_proposal',body)

    def test_context_audit_rejects_nested_secrets_before_any_reservation(self):
        bad={'context_id':'a'*64,'provider':'deepseek','reviewed':False,
             'created_ms':NOW,'completed_ms':NOW,'usage':{'deepseek':{'api_key':'SECRET'}}}
        before=self.w.store.load()
        with self.assertRaisesRegex(ValueError,'invalid_context_audit'):
            self.pair.accept_ai_plans('hawk',{'plans':[plan()]},shortlist(),markets(),
                                     CONTRACTS,NOW,context_audit=bad)
        self.assertEqual(self.w.store.load(),before)
