import json
from pathlib import Path
import tempfile
import unittest
from brain_scalp_view import read_all
from backend.tests.test_brain_scalp_view import NOW,seed


def snapshot():
    return {'schema_version':2,'paper':True,'read_only':True,'ts_ms':NOW,
        'account':{'status':'ok','paper':True,'account_id':'brain-scalp-single-paper',
        'name':'brain','heartbeat_ms':NOW,'cash':2000.,'equity':2015.,'initial_cash':2000.,
        'margin':0.,'margin_limit':1600.,'max_slots':10,'positions':[],'pending':[],
        'net_pnl_vs_initial':99999.,'metrics':{}}}


class SingleView(unittest.TestCase):
    def test_review_telemetry_is_optional_and_malformed_isolated(self):
        obj=snapshot()
        self.assertNotIn('position_review',self.read(obj)['profiles']['brain'])
        for bad in ({'mode':'live','status':'none','last':None},
                    {'mode':'paper','status':'recorded','last':{'ts_ms':NOW+1}},
                    {'mode':'paper','status':'recorded','last':{'ts_ms':NOW,
                     'reviewer_checked':True,'proposals':'bad','executed':[]}}):
            with self.subTest(bad=bad):
                obj['account']['position_review']=bad
                result=self.read(obj)
                self.assertEqual(result['status'],'ok')
                self.assertEqual(result['profiles']['brain']['position_review']['mode'],'unknown')
                self.assertEqual(result['profiles']['brain']['cash'],2000)
        good={'mode':'off','status':'recorded','last':{'ts_ms':NOW,
              'reviewer_checked':True,'proposals':[{'symbol':'BTC','action':'SUGGEST_CLOSE','reason':'example'}],
              'executed':[]}}
        obj['account']['position_review']=good
        self.assertEqual(self.read(obj)['profiles']['brain']['position_review'],good)

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'snapshot.json'

    def test_partial_review_preserves_readable_account(self):
        obj=snapshot()
        obj['account']['position_review']={'mode':'paper','status':'recorded',
            'last':{'ts_ms':NOW,'reviewer_checked':True,
                    'proposals':[{'symbol':'BTC','action':'SUGGEST_REDUCE','reason':'partial'}],
                    'executed':[{'symbol':'BTC','action':'reduced'}]}}
        value=self.read(obj)['profiles']['brain']
        self.assertEqual(value['position_review'],obj['account']['position_review'])
        self.assertEqual(value['cash'],2000.)

    def test_attempt_whitelist_discards_untrusted_fields(self):
        obj=snapshot();attempt={'ts_ms':NOW,'purpose':'review','provider':'deepseek',
                               'status':'primary_failed','failure_code':'balance'}
        obj['account']['ai_attempt']=dict(attempt,response_body='SYNTHETIC_SECRET_BODY')
        self.assertEqual(self.read(obj)['profiles']['brain']['ai_attempt'],attempt)
        for key,value in (('ts_ms',NOW+1),('provider','other'),('failure_code','free text')):
            obj['account']['ai_attempt']=dict(attempt,**{key:value})
            result=self.read(obj)
            self.assertEqual(result['status'],'ok')
            self.assertNotIn('ai_attempt',result['profiles']['brain'])
    def tearDown(self):self.tmp.cleanup()
    def read(self,obj=None,now=NOW,layout='single'):
        if obj is not None:self.path.write_text(json.dumps(obj))
        return read_all(self.tmp.name,now,snapshot_path=self.path,layout=layout)

    def test_unique_identity_actual_capital_and_recomputed_pnl(self):
        result=self.read(snapshot(),layout='auto')
        self.assertEqual(result['layout'],'single');self.assertEqual(set(result['profiles']),{'brain'})
        p=result['profiles']['brain'];self.assertEqual(p['initial_cash'],2000)
        self.assertEqual(p['net_pnl_vs_initial'],15);self.assertTrue(p['online'])

    def test_missing_single_never_falls_back_to_dual_databases(self):
        seed(self.tmp.name,'hawk');seed(self.tmp.name,'bull')
        result=self.read()
        self.assertEqual(set(result['profiles']),{'brain'})
        self.assertFalse(result['profiles']['brain']['available'])
        self.assertNotIn('cash',result['profiles']['brain'])

    def test_corrupt_single_never_falls_back(self):
        seed(self.tmp.name,'hawk');self.path.write_text('broken')
        self.assertEqual(self.read()['status'],'unavailable')
        self.assertEqual(set(self.read()['profiles']),{'brain'})

    def test_stale_snapshot_and_heartbeat(self):
        r=self.read(snapshot(),now=NOW+61000)
        self.assertFalse(r['profiles']['brain']['online'])
        self.assertTrue(r['snapshot_stale'])
        obj=snapshot();obj['account']['heartbeat_ms']=NOW-61000
        self.assertFalse(self.read(obj)['profiles']['brain']['online'])

    def test_foreign_mixed_or_wrong_layout_rejected(self):
        obj=snapshot();obj['account']['account_id']='brain-free-paper'
        self.assertEqual(self.read(obj)['status'],'unavailable')
        obj=snapshot();obj['profiles']={}
        self.assertEqual(self.read(obj)['status'],'unavailable')
        self.assertEqual(self.read(snapshot(),layout='dual')['status'],'unavailable')
        obj=snapshot();obj['schema_version']=True
        self.assertEqual(self.read(obj)['status'],'unavailable')

    def test_invalid_capital_capacity_or_position_rejected(self):
        for key,value in [('initial_cash',0),('initial_cash',float('nan')),
                          ('margin_limit','1600'),('max_slots',True),('positions',[{'leverage':'bad'}])]:
            with self.subTest(key=key):
                obj=snapshot();obj['account'][key]=value
                self.assertEqual(self.read(obj)['status'],'unavailable')

    def test_unknown_equity_not_zero_and_file_unchanged(self):
        obj=snapshot();obj['account']['equity']=None
        self.read(obj);before=self.path.read_bytes();r=self.read()
        self.assertIsNone(r['profiles']['brain']['net_pnl_vs_initial'])
        self.assertEqual(self.path.read_bytes(),before)

    def test_future_symlink_rejected(self):
        obj=snapshot();obj['ts_ms']=NOW+1
        self.assertEqual(self.read(obj)['status'],'unavailable')
        target=Path(self.tmp.name)/'actual.json';target.write_text(json.dumps(snapshot()))
        self.path.unlink();self.path.symlink_to(target)
        self.assertEqual(self.read()['status'],'unavailable')

class ProducerContract(unittest.TestCase):
    def test_actual_single_wallet_producer_round_trip(self):
        import os,subprocess,sys
        core=os.environ.get('BRAIN_TEST_CORE_ROOT')
        if not core:self.skipTest('pinned producer checkout supplied by CI')
        script='''
from dataclasses import replace
from director.brain_scalp.config import HAWK
from director.brain_scalp.coordinator import BrainAccount
from director.brain_scalp.snapshot import build_account_snapshot,atomic_write
from pathlib import Path
import sys
spec=replace(HAWK,name='brain',account_id='brain-scalp-single-paper',start_cash=2000,max_margin_total=1600)
a=BrainAccount(sys.argv[1],spec=spec,initialize=True,now_ms=1800000000000)
a.tick({}, {},1800000000000)
atomic_write(Path(sys.argv[1])/'snapshot.json',build_account_snapshot(a,1800000000000))
a.close()
'''
        with tempfile.TemporaryDirectory() as root:
            env=dict(os.environ,PYTHONPATH=str(Path(core).resolve()/'backend'))
            subprocess.run([sys.executable,'-c',script,root],env=env,cwd=core,check=True,timeout=15)
            r=read_all(root,NOW,snapshot_path=Path(root)/'snapshot.json',layout='single')
            self.assertEqual(r['status'],'ok');self.assertEqual(r['profiles']['brain']['equity'],2000)
            self.assertEqual(r['profiles']['brain']['net_pnl_vs_initial'],0)
