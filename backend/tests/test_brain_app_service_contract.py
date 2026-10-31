"""Pinned app API with real PAPER ledger, teaching journal and service tick."""
import json
from unittest.mock import Mock
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from brain_operator_api import register
from director.brain_scalp.service import BrainService
from director.brain_scalp.operator_inbox import OperatorInbox
from backend.tests import test_brain_operator as fixtures
from backend.tests.test_brain_resume import NOW,markets

def test_committed_ai_close_is_visible_as_execution_in_app(tmp_path):
    from backend.tests.test_brain_position_execution_chat import PaperPositionExecution
    from director.brain_scalp.snapshot import build_account_snapshot,atomic_write
    from brain_scalp_snapshot_view import read_published_snapshot
    case=PaperPositionExecution();case.setUp()
    try:
        request=case.request()
        case.apply(request,case.analysis(request))
        before=case.wallet.brain.store.load()
        path=tmp_path/'snapshot.json'
        atomic_write(path,build_account_snapshot(case.wallet,case.now,
                     markets(case.now),position_actions='paper'))
        view=read_published_snapshot(path,case.now,layout='single')
        review=view['profiles']['brain']['position_review']
        assert review['mode']=='paper'
        assert review['last']['reviewer_checked'] is True
        assert review['last']['proposals'][0]['action']=='SUGGEST_CLOSE'
        assert review['last']['executed'][0]=={'symbol':'BTC','action':'closed'}
        assert case.wallet.brain.store.load()==before
    finally:
        case.tearDown()

@pytest.mark.parametrize('choice',['yes','no'])
def test_published_review_to_api_receipt_and_next_analysis(tmp_path,monkeypatch,choice):
    case=fixtures.ManualClose();case.setUp()
    queue=OperatorInbox(tmp_path/'inbox.sqlite')
    try:
        quote=markets(NOW+1000);quote['BTC']['quote']['price']=102
        case.op.close({'BTC':case.current()},quote,NOW+1000)
        before=case.account.brain.store.load()
        now=[NOW+2000]
        service=BrainService.__new__(BrainService)
        service.clock=lambda:now[0]
        service.account=case.account;service.operator=case.op
        service.operator_inbox=queue
        service.operator_reviews_path=tmp_path/'reviews.json'
        service.feed=Mock();service.feed.poll.return_value=({}, {})
        service.trend_v11=Mock();service.trend_v11.poll.return_value={}
        service.structure_enabled=False
        service.operator_preferences=[]
        service.teaching_status='recorded';service.last_teaching_recovery=now[0]
        service.supervisor=Mock();service.supervisor.step.return_value={'tick':'protected'}
        service.tick()
        monkeypatch.setenv('BRAIN_OPERATOR_REVIEWS_PATH',str(service.operator_reviews_path))
        monkeypatch.setenv('BRAIN_OPERATOR_INBOX_PATH',str(tmp_path/'inbox.sqlite'))
        monkeypatch.setenv('BRAIN_OPERATOR_ALLOWED_ORIGIN','https://example.test')
        monkeypatch.setattr('brain_operator_api.time.time',lambda:now[0]/1000)
        app=FastAPI();register(app,lambda:{'user':'owner'})
        client=TestClient(app)
        review=client.get('/api/brain/operator/reviews').json()
        assert review['status']=='available' and len(review['groups'])==1
        group=review['groups'][0]
        assert group['symbols']==['BTC'] and group['count']==1 and group['net_usd']>0
        data={'request_id':'a'*32,'group_id':group['group_id'],'choice':choice}
        headers={'Origin':'https://example.test','X-Brain-Operator':'1'}
        assert client.post('/api/brain/operator/confirm',json=data,headers=headers).json()['status']=='pending'
        assert case.account.brain.store.load()==before
        now[0]+=1
        result=service.tick()
        assert result['operator_confirmations']==[{'request_id':'a'*32,'status':'confirmed'}]
        assert client.get('/api/brain/operator/result/'+'a'*32).json()['status']=='confirmed'
        assert client.get('/api/brain/operator/reviews').json()['groups']==[]
        assert len(service.operator_preferences)==(1 if choice=='yes' else 0)
        if choice=='yes':
            assert service.operator_preferences[0]['confirmed_ms']==now[0]
            assert service.operator_preferences[0]['training_applied'] is False
        # Confirmation occurs after protection; the next analysis sees it.
        assert service.supervisor.step.call_args.kwargs['operator_preferences']==[]
        now[0]+=5000;service.tick()
        assert len(service.supervisor.step.call_args.kwargs['operator_preferences'])==(1 if choice=='yes' else 0)
        assert service.tick()['operator_confirmations']==[]
        assert case.account.brain.store.load()==before
        learning=case.op.teaching.learning.read_text().splitlines()
        assert len(learning)==1
        assert json.loads(learning[0])['confirmed']==(choice=='yes')
    finally:
        queue.close();case.tearDown()

def test_review_publication_expiry_is_rejected(tmp_path,monkeypatch):
    source=tmp_path/'reviews.json'
    source.write_text(json.dumps({'paper':True,'account_id':'brain-scalp-single-paper',
        'ts_ms':NOW,'groups':[]}))
    monkeypatch.setenv('BRAIN_OPERATOR_REVIEWS_PATH',str(source))
    monkeypatch.setattr('brain_operator_api.time.time',lambda:(NOW+120001)/1000)
    app=FastAPI();register(app,lambda:{'user':'owner'})
    assert TestClient(app).get('/api/brain/operator/reviews').json()=={'status':'unavailable','groups':[]}

def test_real_single_snapshot_is_readable_by_pinned_app_and_stales(tmp_path):
    from director.brain_scalp.snapshot import build_account_snapshot,atomic_write
    from brain_scalp_snapshot_view import read_published_snapshot
    case=fixtures.ManualClose();case.setUp()
    try:
        before=case.account.brain.store.load()
        snapshot=build_account_snapshot(case.account,NOW+1000,markets(NOW+1000))
        path=tmp_path/'snapshot.json';atomic_write(path,snapshot)
        view=read_published_snapshot(path,NOW+1000,layout='single')
        assert view['layout']=='single' and view['status']=='ok'
        assert set(view['profiles'])=={'brain'}
        position=view['profiles']['brain']['positions'][0]
        assert position['symbol']=='BTC' and position['price_status']=='fresh'
        stale=read_published_snapshot(path,NOW+62000,layout='single')
        assert stale['snapshot_stale'] is True
        assert stale['profiles']['brain']['online'] is False
        assert case.account.brain.store.load()==before
    finally:case.tearDown()
