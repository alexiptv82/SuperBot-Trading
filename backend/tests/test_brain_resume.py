"""Synthetic offline integration. No profitability or provider-quality claims."""
from dataclasses import replace
import json
from pathlib import Path
import tempfile
from threading import Event
import unittest

from director.brain_scalp.config import HAWK,validate_spec
from director.brain_scalp.coordinator import BrainAccount
from director.brain_scalp.scanner import scan
from director.brain_scalp.snapshot import build_account_snapshot,read_snapshot
from director.brain_scalp.supervisor import PaperSupervisor
from director.brain_scalp.ai_context import decode,encode
from backend.tests.test_brain_ai_context import markets,shortlist
from backend.tests.test_brain_scalp_group1 import NOW,CONTRACTS,plan

SPEC=replace(HAWK,name='brain',account_id='brain-scalp-single-paper',start_cash=2000,
             max_margin_total=1600)  # test fixture only; no runtime default


def breakout(now=NOW,side=1):
    data=markets(now);m=data['BTC'];price=100+side*.4
    for tf in ('1m','5m'):
        b=m['bars'][tf][-1]
        b[2]=max(100.1,price);b[3]=min(99.9,price);b[4]=price;b[5]=200
    m['quote']['price']=price
    return data


def hold(system,user):
    p=decode(user)
    return encode({'context_id':p['context_id'],'plans':[],
        'assessments':[{'symbol':c['symbol'],'long_case':'Upward alternative',
                       'short_case':'Downward alternative','decision':'HOLD'}
                       for c in p['candidates']]})


class Resume(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.now=NOW
        self.account=BrainAccount(self.tmp.name,spec=SPEC,initialize=True,now_ms=NOW)
        self.supervisors=[];self.release=[]

    def tearDown(self):
        for event in self.release:event.set()
        for s in self.supervisors:
            if s.future is not None:s.future.result(timeout=3)
            s.close()
        self.account.close();self.tmp.cleanup()

    def supervisor(self,primary=hold,**kwargs):
        opts=dict(primary_call=primary,reviewer_call=None,clock_ms=lambda:self.now,
                  daily_budget_micro_usd=100,reservation_micro_usd=100,analysis_interval_ms=1000)
        opts.update(kwargs)
        s=PaperSupervisor(self.account,**opts);self.supervisors.append(s);return s

    def test_single_wallet_real_ledger_and_restart(self):
        state=self.account.brain.store.load()
        self.assertEqual(state['cash'],2000)
        self.assertEqual(set(self.account.wallets),{'brain'})
        self.assertFalse((Path(self.tmp.name)/'hawk').exists())
        self.account.close()
        self.account=BrainAccount(self.tmp.name,spec=SPEC)
        self.assertEqual(self.account.brain.store.load()['experiment_id'],state['experiment_id'])

    def test_mandate_change_does_not_reset(self):
        self.account.close()
        with self.assertRaisesRegex(ValueError,'migration'):
            BrainAccount(self.tmp.name,spec=replace(SPEC,risk_trade_usd=51))
        self.account=BrainAccount(self.tmp.name,spec=SPEC)
        self.assertEqual(self.account.brain.store.load()['cash'],2000)

    def test_second_writer_and_reinitialization_rejected(self):
        with self.assertRaisesRegex(ValueError,'writer_already_active'):
            BrainAccount(self.tmp.name,spec=SPEC)
        with self.assertRaisesRegex(ValueError,'not_empty'):
            BrainAccount(self.tmp.name,spec=SPEC,initialize=True,now_ms=NOW)

    def test_bad_mandates(self):
        for change in ({'start_cash':float('nan')},{'slots':True},{'risk_trade_usd':0},
                       {'max_margin_total':2100},{'min_margin':300},{'name':'../brain'}):
            with self.subTest(change=change),self.assertRaises(ValueError):validate_spec(replace(SPEC,**change))

    def test_backup_preserves_journal_and_state(self):
        state=self.account.brain.store.load()
        self.account.brain.store.commit(state,NOW,[{'kind':'test_event'}])
        p=self.account.brain.store.backup(Path(self.tmp.name)/'backup.sqlite3')
        self.assertTrue(p.is_file())

    def test_single_snapshot_uses_actual_initial_capital_and_rejects_dual_reader(self):
        s=self.supervisor(snapshot_path=Path(self.tmp.name)/'snapshot.json')
        s.step(markets(),CONTRACTS)
        snap=json.loads((Path(self.tmp.name)/'snapshot.json').read_text())
        self.assertEqual(snap['schema_version'],2)
        self.assertEqual(snap['account']['initial_cash'],2000)
        self.assertEqual(snap['account']['net_pnl_vs_initial'],0)
        self.assertFalse(read_snapshot(Path(self.tmp.name)/'snapshot.json',NOW)['available'])

    def test_diagnostics_do_not_change_shortlist(self):
        for side in (1,-1):
            data=breakout(side=side)
            base=scan(data,NOW);observed=scan(data,NOW,diagnostics=True)
            diag=observed.pop('diagnostics');self.assertEqual(base,observed)
            self.assertEqual(diag['counts']['LONG' if side==1 else 'SHORT']['SELECTED'],1)
            self.assertEqual(len(diag['rows']),2)

    def test_diagnostics_topk_and_missing_data(self):
        data=breakout();data['ETH']=data['BTC'];data['BAD']={'quote':{},'bars':{}}
        result=scan(data,NOW,limit=1,diagnostics=True)['diagnostics']
        self.assertEqual(result['counts']['LONG']['TOP_K'],1)
        self.assertEqual(result['counts']['LONG']['DATA_UNAVAILABLE'],1)
        self.assertEqual(result['counts']['SHORT']['DATA_UNAVAILABLE'],1)

    def test_diagnostics_causal(self):
        data=breakout();a=scan(data,NOW,diagnostics=True)
        data['BTC']['bars']['5m'].append([NOW,100,1000,1,1000,10000])
        self.assertEqual(a,scan(data,NOW,diagnostics=True))

    def test_hold_processed_on_owner_thread_and_budget_survives_restart(self):
        s=self.supervisor();r=s.step(breakout(),CONTRACTS)
        self.assertEqual(r['analysis_status'],'started')
        s.future.result(timeout=3);self.now+=1000
        r=s.step(breakout(self.now),CONTRACTS)
        self.assertEqual(r['analysis']['status'],'processed')
        s.close();self.account.close();self.account=BrainAccount(self.tmp.name,spec=SPEC)
        s2=self.supervisor();self.now+=1000
        self.assertEqual(s2.step(breakout(self.now),CONTRACTS)['analysis_status'],'budget_exhausted')

    def test_slow_ai_never_blocks_protective_tick_or_spawns_second_call(self):
        started=Event();release=Event();self.release.append(release)
        def slow(system,user):
            started.set();release.wait(3);return hold(system,user)
        s=self.supervisor(slow)
        # Open an existing PAPER position before starting slow analysis.
        self.account.accept_ai_plans('brain',{'plans':[plan()]},shortlist(),markets(),CONTRACTS,NOW)
        self.account.tick(markets(),CONTRACTS,NOW+1)
        self.assertIn('BTC',self.account.brain.store.load()['positions'])
        self.now=NOW+1000;s.step(breakout(self.now),CONTRACTS);self.assertTrue(started.wait(1))
        self.now+=1000;data=markets(self.now);data['BTC']['quote']['price']=90
        r=s.step(data,CONTRACTS)
        self.assertEqual(r['analysis_status'],'pending')
        self.assertFalse(self.account.brain.store.load()['positions'])
        release.set();s.future.result(timeout=3)
        self.assertEqual(s.step(data,CONTRACTS)['analysis']['status'],'rejected_context')

    def test_expired_request_not_admitted_and_not_retried_while_running(self):
        started=Event();release=Event();self.release.append(release)
        def slow(system,user):started.set();release.wait(3);return hold(system,user)
        s=self.supervisor(slow);s.step(breakout(),CONTRACTS);self.assertTrue(started.wait(1))
        self.now+=31000
        self.assertEqual(s.step(breakout(self.now),CONTRACTS)['analysis_status'],'expired_waiting_for_transport')
        release.set();s.future.result(timeout=3)
        self.assertEqual(s.step(breakout(self.now),CONTRACTS)['analysis']['status'],'rejected_context')

    def test_no_candidate_no_budget_or_provider_call(self):
        def forbidden(*args):raise AssertionError('must not call')
        s=self.supervisor(forbidden);s.step(markets(),CONTRACTS)
        self.assertIsNone(s.future)
        self.assertNotIn('ai_budget_reservation',self.account.brain.store.load())

    def test_guard_before_provider_and_no_provider_after_close(self):
        s=self.supervisor();req=self.account.prepare_ai_request('brain',shortlist(),markets(),CONTRACTS,{},NOW,NOW+1000)
        self.now+=1001
        with self.assertRaises(ValueError):s._guarded(hold,req)('','{}')
        s.close()
        with self.assertRaises(ValueError):s.step(markets(),CONTRACTS)

    def test_duplicate_supervisor_rejected(self):
        self.supervisor()
        with self.assertRaisesRegex(ValueError,'supervisor_already_active'):self.supervisor()

    def test_scanner_telemetry_persisted_once_per_minute(self):
        s=self.supervisor();s.step(markets(),CONTRACTS);s.step(markets(),CONTRACTS)
        rows=self.account.brain.store.db.execute("SELECT body FROM events WHERE kind='scanner_observed'").fetchall()
        self.assertEqual(len(rows),1)
        self.assertIn('LONG',json.loads(rows[0][0])['counts'])

    def test_ai_plan_reserved_then_executed_by_next_protective_tick(self):
        def opening(system,user):
            response=decode(hold(system,user));p=plan()
            p.update(trigger_price=100.4,stop=99,target=103)
            response['plans']=[p];response['assessments'][0]['decision']='LONG'
            return encode(response)
        s=self.supervisor(opening);s.step(breakout(),CONTRACTS);s.future.result(timeout=3)
        self.now+=1000
        result=s.step(breakout(self.now),CONTRACTS)
        self.assertEqual(len(result['analysis']['accepted']),1)
        self.now+=1000;s.step(breakout(self.now),CONTRACTS)
        self.assertIn('BTC',self.account.brain.store.load()['positions'])

    def test_failed_call_budget_not_refunded(self):
        def fail(*args):raise RuntimeError('SENSITIVE')
        s=self.supervisor(fail);s.step(breakout(),CONTRACTS);s.future.result(timeout=3)
        self.now+=1000;r=s.step(breakout(self.now),CONTRACTS)
        self.assertEqual(r['analysis']['status'],'primary_failed')
        self.assertEqual(s.step(breakout(self.now),CONTRACTS)['analysis_status'],'budget_exhausted')
        events=str(self.account.brain.store.db.execute('SELECT body FROM events').fetchall())
        self.assertNotIn('SENSITIVE',events)


if __name__=='__main__':unittest.main()
