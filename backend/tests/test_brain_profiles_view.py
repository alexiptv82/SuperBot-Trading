"""Real SQLite/WAL fixtures only; never import or launch the trading runtime."""
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

from desk import brain_profiles_view as view
from desk.brain_view import register_fastapi

NOW=1793102400000


def state(profile='hawk',side=1):
    return {'version':view.VERSION,'profile':profile,'method':'a'*64,'last_step_ms':NOW,'steps_completed':5,
            'desk':{'last_prices':{'ETH':101},'last_price_times':{'ETH':NOW},'main':{
                'name':'brain-'+profile,'cash':798.2,'day':'2026-10-27','day_start_equity':1000,
                'limits':{'start_equity':1000,'daily_stop':.10,'fee_bp_side':6,'slip_bp_side':2,'funding_bp_8h_long':1},
                'positions':{'ETH':{'id':1,'side':side,'entry':100,'qty':30,'total_margin':200,'leverage':15,
                                    'open_ms':NOW-120000,'sl':99 if side==1 else 102,'tp':103 if side==1 else 98,
                                    'fee_open':1.8,'source':'brain-deepseek','reason':'<script>reason</script>'}}}}}


class ProfileViewTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.db=[]
    def tearDown(self):
        for db in self.db:db.close()
    def create(self,profile='hawk',data=None):
        path=self.root/('brain-'+profile);path.mkdir()
        db=sqlite3.connect(path/'brain.sqlite3');self.db.append(db)
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('CREATE TABLE state(id INTEGER PRIMARY KEY,body TEXT)')
        db.execute('CREATE TABLE events(seq INTEGER PRIMARY KEY,kind TEXT,body TEXT)')
        db.execute('INSERT INTO state VALUES(1,?)',(json.dumps(data or state(profile)),));db.commit()
        return db
    def read(self,profile='hawk',now=NOW):
        return view.read_profile(self.root,profile,now,time.monotonic()+2)
    def journal(self,db,row):
        db.execute('INSERT INTO events(kind,body) VALUES (?,?)',('journal',json.dumps(row)));db.commit()
    def test_missing_profiles_do_not_create_directories_or_fake_balances(self):
        before=list(self.root.iterdir())
        result=view.read_profiles(self.root,self.root/'old',now_ms=NOW)
        self.assertEqual(list(self.root.iterdir()),before)
        for p in result['profiles'].values():
            self.assertEqual(p['status'],'not_started');self.assertNotIn('portfolio',p)
    def test_native_margin_leverage_gross_and_estimated_net_are_distinct(self):
        self.create();r=self.read();self.assertEqual(r['status'],'ok',r)
        p=r['positions'][0]
        self.assertEqual((p['margin'],p['leverage'],p['notional_entry']),(200,15,3000))
        self.assertEqual(p['floating_pnl'],30)
        self.assertLess(p['net_close_estimate'],30)
        self.assertAlmostEqual(r['portfolio']['equity'],1028.2)
        self.assertEqual(r['daily_stop']['limit_pct'],10)
    def test_short_and_residual_dca_values_come_from_stored_position(self):
        s=state('bull',-1);s['desk']['last_prices']['ETH']=99
        p=s['desk']['main']['positions']['ETH'];p.update(total_margin=70,qty=21,leverage=30)
        self.create('bull',s);r=self.read('bull')
        self.assertEqual(r['positions'][0]['margin'],70)
        self.assertEqual(r['positions'][0]['notional_entry'],2100)
        self.assertEqual(r['positions'][0]['floating_pnl'],21)
    def test_missing_or_stale_price_times_never_look_fresh(self):
        s=state();s['desk']['last_price_times']={};db=self.create(data=s)
        self.assertTrue(self.read()['portfolio']['stale'])
        s['desk']['last_price_times']['ETH']=NOW-240000
        db.execute('UPDATE state SET body=?',(json.dumps(s),));db.commit()
        self.assertTrue(self.read()['positions'][0]['stale'])
        s['desk']['last_prices']={};db.execute('UPDATE state SET body=?',(json.dumps(s),));db.commit()
        self.assertIsNone(self.read()['portfolio']['equity'])
    def test_wrong_account_live_trade_and_unknown_state_are_rejected(self):
        s=state();s['desk']['main']['name']='main';db=self.create(data=s)
        self.assertEqual(self.read()['status'],'unavailable')
        db.execute('UPDATE state SET body=?',(json.dumps(state()),))
        db.execute('INSERT INTO events(kind,body) VALUES (?,?)',('trade',json.dumps({'account':'brain-hawk','profile':'hawk','mode':'live'})));db.commit()
        self.assertEqual(self.read()['status'],'unavailable')
    def test_partial_aggregation_uses_sqlite_not_optional_exports(self):
        db=self.create()
        for partial,net in ((True,5),(False,10)):
            r={'account':'brain-hawk','profile':'hawk','mode':'paper','id':1,'symbol':'ETH','side':1,'open_ms':NOW-100000,
               'close_ms':NOW,'net':net,'partial':partial,'why':'brain: adaptive_close','margin':100,'leverage':15}
            db.execute('INSERT INTO events(kind,body) VALUES (?,?)',('trade',json.dumps(r)))
        db.commit();r=self.read()
        self.assertEqual(r['stats']['closed_trades'],1);self.assertEqual(r['stats']['average_pnl'],15)
        self.assertEqual(len(r['trades']),2)
    def test_proposals_and_cycle_sources_are_allowlisted_separately(self):
        db=self.create()
        self.journal(db,{'kind':'adaptive_input','ts_ms':NOW,'input':{'raw':'PRIVATE_SENTINEL'}})
        self.journal(db,{'kind':'adaptive_advice','ts_ms':NOW,'decisions':[{'symbol':'ETH','action':'close','reason':'current evidence','private':'PRIVATE_SENTINEL'}]})
        self.journal(db,{'kind':'adaptive_cycle','ts_ms':NOW,'decision_source':'classical_rules','last_provider_status':'model_pending','fresh_fast_data':True})
        r=self.read()
        self.assertEqual(r['reasoning']['advice']['meaning'],'proposal_not_execution')
        self.assertEqual(r['execution']['decision_source'],'classical_rules')
        self.assertNotIn('PRIVATE_SENTINEL',json.dumps(r))
    def test_readonly_wal_observes_committed_state_without_changing_financial_files(self):
        db=self.create();paths=list((self.root/'brain-hawk').glob('brain.sqlite3*'))
        before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths if not p.name.endswith('-shm')}
        self.assertEqual(self.read()['status'],'ok')
        after={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths if not p.name.endswith('-shm')}
        self.assertEqual(before,after)
        db.execute('BEGIN IMMEDIATE');db.execute('UPDATE state SET body=?',(json.dumps(dict(state(),profile='bull')),))
        self.assertEqual(self.read()['status'],'ok');db.rollback()
    def test_deadline_and_symlink_cannot_mutate_or_read_other_profiles(self):
        self.create()
        self.assertEqual(view.read_profile(self.root,'hawk',NOW,time.monotonic()-1)['reason'],'query_timeout')
        alias=self.root/'alias';alias.symlink_to(self.root,target_is_directory=True)
        self.assertEqual(view.read_profile(alias,'hawk',NOW,time.monotonic()+2)['status'],'unavailable')
    def test_new_endpoint_uses_same_session_and_only_get_no_cache(self):
        from fastapi import FastAPI,HTTPException
        from fastapi.testclient import TestClient
        app=FastAPI()
        def denied():raise HTTPException(401)
        register_fastapi(app,denied)
        with TestClient(app) as client:self.assertEqual(client.get('/api/brain/profiles').status_code,401)
        app=FastAPI();register_fastapi(app,lambda:'session')
        with patch.dict('os.environ',{'BRAIN_ADAPTIVE_DATA_DIR':str(self.root),'BRAIN_DATA_DIR':str(self.root/'old')}),TestClient(app) as client:
            r=client.get('/api/brain/profiles');self.assertEqual(r.status_code,200)
            self.assertEqual(r.headers['cache-control'],'no-store')
            self.assertEqual(client.post('/api/brain/profiles').status_code,405)


if __name__=='__main__':unittest.main()
