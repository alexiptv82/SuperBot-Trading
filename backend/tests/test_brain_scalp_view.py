"""Reader tests with synthetic SQLite snapshots. No account writes by the reader."""
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from brain_scalp_view import read_wallet,read_all

NOW=1800000000000


def seed(base,name='hawk',**updates):
    root=Path(base)/name;root.mkdir(parents=True,exist_ok=True)
    s={'mode':'paper','account_id':'brain-scalp-'+name+'-paper',
       'cash':1000.0,'positions':{},'plans':{},'last_prices':{},
       'last_ms':NOW,'heartbeat_ms':NOW,
       'runtime_capacity':{'max_slots':10 if name=='hawk' else 3,'max_margin':950.}}
    s.update(updates)
    with sqlite3.connect(root/'brain_scalp.sqlite3') as db:
        db.executescript('''CREATE TABLE state(id INTEGER PRIMARY KEY,version INTEGER,body TEXT);
CREATE TABLE events(seq INTEGER PRIMARY KEY,id TEXT,ts INTEGER,kind TEXT,body TEXT);''')
        db.execute('INSERT INTO state VALUES(1,0,?)',(json.dumps(s),))
    return root


class BrainScalpReader(unittest.TestCase):
    def test_missing_wallet_is_not_initialized(self):
        with tempfile.TemporaryDirectory() as base:
            result=read_all(base,NOW)
            self.assertFalse(result['profiles']['hawk']['available'])
            self.assertFalse(result['profiles']['bull']['available'])
            self.assertEqual(list(Path(base).iterdir()),[])

    def test_two_independent_balances(self):
        with tempfile.TemporaryDirectory() as base:
            seed(base,'hawk')
            seed(base,'bull',cash=950.)
            data=read_all(base,NOW)
            self.assertEqual(data['profiles']['hawk']['equity'],1000.)
            self.assertEqual(data['profiles']['bull']['equity'],950.)
            self.assertEqual(data['profiles']['bull']['max_slots'],3)
            self.assertTrue(data['read_only'])

    def test_foreign_account_fails_closed(self):
        with tempfile.TemporaryDirectory() as base:
            seed(base,'hawk',account_id='brain-free-paper')
            self.assertEqual(read_wallet(base,'hawk',NOW)['status'],'unavailable')

    def test_stale_quote_displays_unknown_equity(self):
        with tempfile.TemporaryDirectory() as base:
            pos={'qty':1.,'entry':100.,'side':1,'margin':10.,'leverage':10.,
                 'entry_fees':.06,'stop':98.,'target':102.,
                 'open_ms':NOW-5000,'reason':'test','invalidation':'level'}
            seed(base,'hawk',cash=990.,positions={'BTC':pos},
                 last_prices={'BTC':{'price':101.,'ts_ms':NOW-31000}})
            item=read_wallet(base,'hawk',NOW)
            self.assertIsNone(item['equity'])
            self.assertIsNone(item['positions'][0]['net_close_estimate'])

    def test_read_does_not_change_sqlite_bytes(self):
        with tempfile.TemporaryDirectory() as base:
            root=seed(base,'hawk')
            path=root/'brain_scalp.sqlite3'
            before=path.read_bytes()
            item=read_wallet(base,'hawk',NOW)
            self.assertTrue(item['online'])
            self.assertEqual(path.read_bytes(),before)

    def test_reject_corrupt_cash_or_symlink(self):
        with tempfile.TemporaryDirectory() as base:
            seed(base,'hawk',cash=float('nan'))
            self.assertEqual(read_wallet(base,'hawk',NOW)['status'],'unavailable')
        with tempfile.TemporaryDirectory() as base:
            real=seed(base,'bull')
            (Path(base)/'hawk').symlink_to(real, target_is_directory=True)
            self.assertEqual(read_wallet(base,'hawk',NOW)['status'],'not_started')


if __name__=='__main__':unittest.main()


class BrainScalpEndpoint(unittest.TestCase):
    def test_only_authenticated_get_is_available(self):
        from fastapi import FastAPI,HTTPException
        from fastapi.testclient import TestClient
        from brain_scalp_api import register
        with tempfile.TemporaryDirectory() as base:
            import os
            old=os.environ.get('BRAIN_SCALP_DATA_DIR')
            os.environ['BRAIN_SCALP_DATA_DIR']=base
            try:
                app=FastAPI()
                def deny(): raise HTTPException(status_code=401)
                register(app,deny)
                with TestClient(app) as c:
                    self.assertEqual(c.get('/api/brain/scalp').status_code,401)
                app2=FastAPI();register(app2,lambda:True)
                with TestClient(app2) as c:
                    resp=c.get('/api/brain/scalp')
                    self.assertEqual(resp.status_code,200)
                    self.assertEqual(resp.headers['cache-control'],'no-store')
                    self.assertEqual(c.post('/api/brain/scalp').status_code,405)
            finally:
                if old is None:os.environ.pop('BRAIN_SCALP_DATA_DIR',None)
                else:os.environ['BRAIN_SCALP_DATA_DIR']=old
