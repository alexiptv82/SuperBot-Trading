import json
import os
from pathlib import Path
import subprocess
import sys
import pytest
from fastapi import FastAPI,HTTPException,Request
from fastapi.testclient import TestClient
from classical_operator_api import register

NOW=1800000061000
GROUP='b'*16
ACCOUNT='desk-hawk-paper-run-8'

@pytest.fixture
def api(tmp_path,monkeypatch):
    source=tmp_path/'manual_operator_reviews.json'
    source.write_text(json.dumps({'paper':True,'account_id':ACCOUNT,'ts_ms':NOW,
        'groups':[{'group_id':GROUP,'symbols':['BTC'],'count':1,'net_usd':12.,'expires_ms':NOW+7200000}]}))
    monkeypatch.setenv('DESK_HAWK_OPERATOR_REVIEWS_PATH',str(source))
    monkeypatch.setenv('DESK_HAWK_OPERATOR_INBOX_PATH',str(tmp_path/'manual.confirmations.sqlite3'))
    monkeypatch.setenv('DESK_OPERATOR_ALLOWED_ORIGIN','https://example.test')
    monkeypatch.setattr('classical_operator_api.time.time',lambda:NOW/1000)
    def session(request:Request):
        if request.headers.get('x-test-auth')!='yes':raise HTTPException(401,'login')
        return {'user':'owner'}
    app=FastAPI();register(app,session)
    return TestClient(app),source

HEADERS={'X-Test-Auth':'yes','Origin':'https://example.test','X-Brain-Operator':'1'}
def command(account=ACCOUNT,group=GROUP):
    return {'request_id':'a'*32,'account_id':account,'group_id':group,'choice':'yes'}

def test_auth_scope_origin_and_schema(api):
    client,source=api;base='/api/desk/operator/hawk'
    assert client.get(base+'/reviews').status_code==401
    assert client.post(base+'/confirm',json=command()).status_code==401
    assert client.get(base+'/reviews',headers=HEADERS).json()['account_id']==ACCOUNT
    assert client.post(base+'/confirm',headers={**HEADERS,'Origin':'https://wrong.test'},json=command()).status_code==403
    assert client.post(base+'/confirm',headers=HEADERS,json=command(account='desk-bull-paper-run-8')).status_code==400
    assert client.post(base+'/confirm',headers=HEADERS,json=command(group='c'*16)).status_code==400
    assert client.get('/api/desk/operator/other/reviews',headers=HEADERS).status_code==404
    original=source.read_bytes()
    assert client.post(base+'/confirm',headers=HEADERS,json=command()).json()['status']=='pending'
    assert client.get(base+'/result/'+'a'*32,headers=HEADERS).json()['status']=='pending'
    assert source.read_bytes()==original

@pytest.mark.parametrize('bad',[[],{'paper':False},{'paper':True,'account_id':ACCOUNT,'ts_ms':NOW+1,'groups':[]}])
def test_malformed_or_future_publication_is_unavailable(api,bad):
    client,source=api;source.write_text(json.dumps(bad))
    assert client.get('/api/desk/operator/hawk/reviews',headers=HEADERS).json()=={'status':'unavailable','groups':[]}

def test_actual_classical_owner_round_trip(api,tmp_path):
    client,source=api
    core=os.environ.get('CLASSICS_TEST_ROOT')
    assert core,'explicit classical producer checkout required'
    script=r'''
import json,sys
from pathlib import Path
from desk.manual_teaching_service import queue_close,poll
root=Path(sys.argv[1]);action=sys.argv[2];now=1800000061000
path=root/'state.json'
if action=='setup':
    state={'run_no':8,'main':{'positions':{}}}
    row={'id':42,'symbol':'BTC','side':-1,'entry':100.,'exit':98.,
         'leverage':10.,'margin':100.,'net':15.,'open_ms':1800000000000,
         'close_ms':1800000060000,'why':'chiusura manuale','account':'hawk','closed_by':'utente'}
    queue_close(state,row,'hawk')
    path.write_text(json.dumps(state))
else:state=json.loads(path.read_text())
result=poll(root,'hawk',path,state,now)
print(json.dumps(result))
'''
    env=dict(os.environ,PYTHONPATH=str(Path(core).resolve()/'backend')+os.pathsep+os.environ.get('PYTHONPATH',''))
    def owner(action):
        out=subprocess.run([sys.executable,'-c',script,str(tmp_path),action],cwd=core,env=env,check=True,capture_output=True,text=True)
        return json.loads(out.stdout)
    owner('setup')
    before=(tmp_path/'state.json').read_bytes()
    data=client.get('/api/desk/operator/hawk/reviews',headers=HEADERS).json()
    gid=data['groups'][0]['group_id']
    result=client.post('/api/desk/operator/hawk/confirm',headers=HEADERS,json=command(group=gid)).json()
    assert result['status']=='pending'
    result=owner('consume')
    assert result['confirmations']==[{'request_id':'a'*32,'status':'confirmed'}]
    assert len(result['preferences'])==1 and result['preferences'][0]['training_applied'] is False
    assert client.get('/api/desk/operator/hawk/result/'+'a'*32,headers=HEADERS).json()['status']=='confirmed'
    assert client.get('/api/desk/operator/hawk/reviews',headers=HEADERS).json()['groups']==[]
    assert owner('consume')['confirmations']==[]
    assert (tmp_path/'state.json').read_bytes()==before

