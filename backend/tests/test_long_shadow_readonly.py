"""Isolated contract checks for the GET-only LONG shadow status extension."""
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from long_shadow_readonly import wallet_snapshot, read_dashboard

NOW = 1800000000000

def classic(root, positions, *, age=1000):
    root.mkdir(parents=True,exist_ok=True)
    path=root/'state_v2.json'
    path.write_text(json.dumps({'main':{'name':'main','positions':positions}}))
    os.utime(path, ns=((NOW-age)*1_000_000,)*2)
    (root/'heartbeat.json').write_text(json.dumps({'ts':(NOW-age)/1000}))

class ShadowContracts(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.roots={a:self.root/a for a in ('hawk','bull','brain')}

    def test_classic_authority_short(self):
        classic(self.roots['hawk'], {'BTC':{'side':-1}})
        r=wallet_snapshot('hawk',roots=self.roots,now_ms=NOW)
        self.assertEqual(r['status'],'ok')
        self.assertEqual(r['snapshot']['positions'][0]['side'],'SHORT')

    def test_cross_account_isolation(self):
        classic(self.roots['hawk'],{'BTC':{'side':-1}})
        classic(self.roots['bull'],{'ETH':{'side':1}})
        obj=read_dashboard(roots=self.roots,shadow_dir=self.root/'missing',now_ms=NOW)
        self.assertTrue(obj['consumers']['hawk']['positions']['BTCUSDT']['short_open'])
        self.assertFalse(obj['consumers']['bull']['positions']['BTCUSDT']['short_open'])
        self.assertTrue(obj['consumers']['bull']['positions']['ETHUSDT']['long_open'])

    def test_missing_wallet_never_empty(self):
        self.assertEqual(wallet_snapshot('hawk',roots=self.roots,now_ms=NOW)['status'],'unavailable')

    def test_bogus_side_fails_closed(self):
        for side in (True,None,'SHORT',0,2):
            classic(self.roots['hawk'], {'BTC':{'side':side}})
            self.assertEqual(wallet_snapshot('hawk',roots=self.roots,now_ms=NOW)['status'],'unavailable')

    def test_stale_fails_closed(self):
        classic(self.roots['hawk'],{},age=30*60000)
        self.assertEqual(wallet_snapshot('hawk',roots=self.roots,now_ms=NOW)['status'],'unavailable')

    def test_other_brain_kind_rejected(self):
        root=self.roots['brain'];root.mkdir()
        with sqlite3.connect(root/'brain.sqlite3') as db:
            db.execute('CREATE TABLE state(id INTEGER PRIMARY KEY,body TEXT)')
            db.execute('INSERT INTO state VALUES(1,?)',(json.dumps({'mode':'paper','account_id':'brain-free-paper','positions':{'ETH':{'side':1}},'heartbeat_ms':NOW}),))
        self.assertEqual(wallet_snapshot('brain',roots=self.roots,now_ms=NOW)['status'],'unavailable')
        self.assertEqual(wallet_snapshot('brain',roots=self.roots,now_ms=NOW,brain_source='free')['status'],'ok')
        self.assertEqual(wallet_snapshot('brain',roots=self.roots,now_ms=NOW,brain_source='pilot')['status'],'unavailable')

    def test_pilot_reads_status_json_heartbeat_not_state(self):
        root=self.roots['brain'];root.mkdir()
        with sqlite3.connect(root/'brain.sqlite3') as db:
            db.execute('CREATE TABLE state(id INTEGER PRIMARY KEY, body TEXT)')
            db.execute('INSERT INTO state VALUES(1,?)',
                       (json.dumps({'version':'brain-pilot-v1',
                                    'account':{'name':'brain-paper','positions':{
                                        'BTC':{'side':-1}}}}),))
        (root/'status.json').write_text(json.dumps({'mode':'paper','applied':False,'ts_ms':NOW}))
        status=wallet_snapshot('brain',roots=self.roots,now_ms=NOW,brain_source='pilot')
        self.assertEqual(status['status'],'ok')
        self.assertEqual(status['snapshot']['positions'][0]['side'],'SHORT')

    def test_pilot_rejects_bad_or_stale_status_json(self):
        root=self.roots['brain'];root.mkdir()
        with sqlite3.connect(root/'brain.sqlite3') as db:
            db.execute('CREATE TABLE state(id INTEGER PRIMARY KEY, body TEXT)')
            db.execute('INSERT INTO state VALUES(1,?)',
                       (json.dumps({'version':'brain-pilot-v1',
                                    'account':{'name':'brain-paper','positions':{}}}),))
        for beat in ({'mode':'paper','applied':True,'ts_ms':NOW},
                     {'mode':'paper','applied':False,'ts_ms':NOW-60*60*1000},
                     {'mode':'live','applied':False,'ts_ms':NOW}):
            (root/'status.json').write_text(json.dumps(beat))
            status=wallet_snapshot('brain',roots=self.roots,now_ms=NOW,brain_source='pilot')
            self.assertEqual(status['status'],'unavailable')

    def test_observer_never_can_trade(self):
        obj=read_dashboard(roots=self.roots,shadow_dir=self.root/'none',now_ms=NOW)
        for key in ('enabled','can_execute_orders','paper_eligible','engine_running'):
            self.assertFalse(obj[key])

    def test_untrusted_record_cannot_escalate(self):
        out=self.root/'output';out.mkdir()
        classic(self.roots['hawk'],{})
        row={'schema':'long-shadow-record-v1','consumer':'hawk','authority':'execute',
             'observation_only':True,'as_of_ms':NOW,'symbol':'BTCUSDT',
             'setup':'REVERSAL','decision':'CANDIDATE','reasons':['test']}
        (out/'hawk.json').write_text(json.dumps(row))
        obj=read_dashboard(roots=self.roots,shadow_dir=out,now_ms=NOW)
        self.assertEqual(obj['consumers']['hawk']['advisory_status'],'not_available')

    def test_wallet_missing_suppresses_candidate_even_if_shadow_record_exists(self):
        out=self.root/'output';out.mkdir()
        record={'schema':'long-shadow-record-v1','consumer':'hawk',
                'authority':'advisory_only','observation_only':True,
                'as_of_ms':NOW,'symbol':'BTCUSDT','setup':'REVERSAL',
                'decision':'CANDIDATE','reasons':['test']}
        (out/'hawk.json').write_text(json.dumps(record))
        result=read_dashboard(roots=self.roots,shadow_dir=out,now_ms=NOW)
        self.assertEqual(result['consumers']['hawk']['wallet_status'],'unavailable')
        self.assertEqual(result['consumers']['hawk']['advisory_status'],'wallet_unavailable')
        self.assertIsNone(result['consumers']['hawk']['advice'])

    def test_wallet_files_never_written(self):
        classic(self.roots['hawk'],{'BTC':{'side':-1}})
        before={p.name:(p.read_bytes(),p.stat().st_mtime_ns) for p in self.roots['hawk'].iterdir()}
        read_dashboard(roots=self.roots,shadow_dir=self.root/'none',now_ms=NOW)
        after={p.name:(p.read_bytes(),p.stat().st_mtime_ns) for p in self.roots['hawk'].iterdir()}
        self.assertEqual(before,after)

    def test_api_authenticated_and_get_only(self):
        from fastapi import FastAPI,HTTPException
        from fastapi.testclient import TestClient
        from long_shadow_api import register
        def denied():raise HTTPException(status_code=401)
        app=FastAPI();register(app,denied)
        with TestClient(app) as client:
            self.assertEqual(client.get('/api/long/shadow').status_code,401)
            self.assertEqual(client.post('/api/long/shadow').status_code,405)
        app=FastAPI();register(app,lambda:'owner')
        with patch.dict(os.environ, {'DESK_DATA_DIR':str(self.root/'hawk'),
                                     'DESK_DATA_DIR_BULL':str(self.root/'bull'),
                                     'LONG_SHADOW_OUTPUT_DIR':str(self.root/'none')}):
            with TestClient(app) as client:
                resp=client.get('/api/long/shadow')
                self.assertEqual(resp.status_code,200)
                self.assertEqual(resp.headers['cache-control'],'no-store')
                self.assertFalse(resp.json()['can_execute_orders'])

if __name__=='__main__':
    unittest.main()
