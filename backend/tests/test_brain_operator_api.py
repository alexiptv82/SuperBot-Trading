import importlib
import time
import pytest
from fastapi import FastAPI,HTTPException
from fastapi.testclient import TestClient
from brain_operator_api import register
from director.brain_scalp.operator_inbox import OperatorInbox

def test_authenticated_confirmation_is_enqueued_not_executed(tmp_path,monkeypatch):
    queue=tmp_path/'inbox.sqlite'
    monkeypatch.setenv('BRAIN_OPERATOR_INBOX_PATH',str(queue))
    monkeypatch.setenv('BRAIN_OPERATOR_ALLOWED_ORIGIN','https://example.test')
    app=FastAPI()
    register(app,lambda:{'user':'owner'})
    client=TestClient(app)
    data={'request_id':'a'*32,'group_id':'b'*16,'choice':'yes'}
    assert client.post('/api/brain/operator/confirm',json=data).status_code==403
    headers={'Origin':'https://example.test','X-Brain-Operator':'1'}
    result=client.post('/api/brain/operator/confirm',json=data,headers=headers)
    assert result.status_code==200 and result.json()['status']=='pending'
    result=client.get('/api/brain/operator/result/'+'a'*32)
    assert result.json()['status']=='pending'
    q=OperatorInbox(queue)
    try:
        assert q.db.execute('SELECT COUNT(*) FROM commands').fetchone()[0]==1
    finally:q.close()

def test_auth_is_required_for_read_and_write(monkeypatch):
    app=FastAPI()
    def deny():raise HTTPException(401,'Login richiesto')
    register(app,deny)
    client=TestClient(app)
    assert client.get('/api/brain/operator/reviews').status_code==401
    assert client.post('/api/brain/operator/confirm',json={}).status_code==401

@pytest.mark.parametrize('payload',['[]','null','42','"invalid"'])
def test_malformed_review_document_is_unavailable(tmp_path,monkeypatch,payload):
    source=tmp_path/'reviews.json'
    source.write_text(payload)
    monkeypatch.setenv('BRAIN_OPERATOR_REVIEWS_PATH',str(source))
    app=FastAPI()
    register(app,lambda:{'user':'owner'})
    result=TestClient(app).get('/api/brain/operator/reviews')
    assert result.status_code==200
    assert result.json()=={'status':'unavailable','groups':[]}
