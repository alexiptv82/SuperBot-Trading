import json,sqlite3,hashlib
from pathlib import Path
import pytest
import brain_free_view as view

NOW=1800000000000

def database(root,**updates):
    state={'mode':'paper','account_id':'brain-free-paper','cash':2000,'positions':{},
           'verified_start_ms':NOW-1000,'heartbeat_ms':NOW,'config_hash':'synthetic',**updates}
    with sqlite3.connect(root/'brain.sqlite3') as db:
        db.executescript('CREATE TABLE state(id INTEGER,body TEXT); CREATE TABLE requests(ts INTEGER,body TEXT); CREATE TABLE events(seq INTEGER,kind TEXT,ts INTEGER,body TEXT);')
        db.execute('INSERT INTO state VALUES(1,?)',(json.dumps(state),))
    return state

def test_missing_or_inactive_does_not_invent_account(tmp_path):
    assert view.read(tmp_path,NOW)=={'available':False,'status':'not_started'}
    database(tmp_path,verified_start_ms=None)
    assert not view.read(tmp_path,NOW)['available']


def test_real_snapshot_spend_and_read_only_integrity(tmp_path):
    database(tmp_path)
    with sqlite3.connect(tmp_path/'brain.sqlite3') as db:
        db.execute('INSERT INTO requests VALUES(?,?)',(NOW,json.dumps({'billing':{'cost':1.5}})))
        db.execute('INSERT INTO requests VALUES(?,?)',(NOW,'{}'))
    before=(tmp_path/'brain.sqlite3').read_bytes()
    data=view.read(tmp_path,NOW)
    assert data['available'] and data['equity']==2000 and data['pnl']==0
    assert data['spend']['today_usd']==1.5 and data['spend']['uncertain_requests']==1
    assert (tmp_path/'brain.sqlite3').read_bytes()==before


def test_stale_position_does_not_show_fabricated_equity(tmp_path):
    p={'side':1,'qty':1,'entry':100,'margin':10,'leverage':10,'stop':95,'target':110,
       'liquidation':91,'reason':'synthetic','invalidation':'synthetic','open_ms':NOW-1000,'source':'deepseek'}
    database(tmp_path,positions={'BTC':p},last_prices={'BTC':{'price':100,'ts_ms':NOW-31000}})
    result=view.read(tmp_path,NOW)
    assert result['equity'] is None and result['positions'][0]['floating_gross'] is None

@pytest.mark.parametrize('updates',[{'mode':'live'},{'account_id':'other'},{'cash':float('nan')}])
def test_foreign_and_corrupt_accounts_are_not_displayed(tmp_path,updates):
    database(tmp_path,**updates);assert view.read(tmp_path,NOW)['status']=='unavailable'


def test_authenticated_get_only_and_no_store(tmp_path,monkeypatch):
    from fastapi import FastAPI,HTTPException
    from fastapi.testclient import TestClient
    from brain_free_api import register
    database(tmp_path);monkeypatch.setenv('BRAIN_FREE_DATA_DIR',str(tmp_path))
    app=FastAPI()
    def deny():raise HTTPException(401)
    register(app,deny)
    with TestClient(app) as client:assert client.get('/api/brain/free').status_code==401
    app=FastAPI();register(app,lambda:True)
    with TestClient(app) as client:
        r=client.get('/api/brain/free');assert r.status_code==200 and r.headers['cache-control']=='no-store'
        assert client.post('/api/brain/free').status_code==405
