"""Offline transport and restart tests; no Telegram requests or AI calls."""
import io
import json
import threading
import urllib.error
from unittest.mock import Mock

import pytest

from director.brain_scalp.notification_outbox import NotificationOutbox,telegram_sender
from director.brain_scalp.service import BrainService

NOW=1800000000000

def attempt(**fields):
    return dict({'provider':'deepseek','failure_code':'balance','ts_ms':NOW},**fields)

def complete(outbox,now=NOW):
    outbox.future.result(timeout=2)
    return outbox.step(now)

def test_durable_dedup_and_sanitized_provider_message(tmp_path):
    path=tmp_path/'brain.notifications.sqlite3';sent=[]
    wallet=tmp_path/'wallet.json';wallet.write_text('{"paper":true}')
    before=wallet.read_bytes()
    q=NotificationOutbox(path,lambda message:sent.append(message) or 'delivered')
    try:
        assert q.stage(attempt(response_body='SYNTHETIC_SECRET'))
        assert not q.stage(attempt(ts_ms=NOW+1))
        assert q.step(NOW)=='sending'
        assert complete(q)=='delivered'
        assert 'DeepSeek' in sent[0] and 'saldo residuo non disponibile' in sent[0]
        assert 'UTC' in sent[0] and 'NO_TRADE' in sent[0]
        assert 'SYNTHETIC_SECRET' not in sent[0]
        assert wallet.read_bytes()==before
    finally:q.close()
    q=NotificationOutbox(path,lambda message:pytest.fail('duplicate delivery'))
    try:
        assert not q.stage(attempt())
        assert q.step(NOW+1)=='idle'
        assert q.stage(attempt(provider='claude'))
    finally:q.close()

@pytest.mark.parametrize('fields',[{'provider':'other'},{'failure_code':'exception body'},
    {'failure_code':[]},{'ts_ms':True},{'ts_ms':-1},{'ts_ms':10**20},{'failure_code':None}])
def test_invalid_attempt_is_not_persisted(tmp_path,fields):
    q=NotificationOutbox(tmp_path/'brain.notifications.sqlite3',lambda _: 'delivered')
    try:
        assert not q.stage(attempt(**fields))
        assert q.db.execute('SELECT COUNT(*) FROM notifications').fetchone()[0]==0
    finally:q.close()

def test_only_explicit_rate_rejection_retries_with_backoff_and_limit(tmp_path):
    q=NotificationOutbox(tmp_path/'brain.notifications.sqlite3',lambda _: 'retry')
    try:
        q.stage(attempt())
        now=NOW
        for number in (1,2,3):
            assert q.step(now)=='sending'
            assert complete(q,now)=='retry'
            row=q.db.execute('SELECT status,tries,due FROM notifications').fetchone()
            assert row[1]==number
            assert row[0]==('pending' if number<3 else 'rejected')
            assert q.step(now+1)=='idle'
            now=row[2]
        assert q.step(now+999999)=='idle'
    finally:q.close()

@pytest.mark.parametrize('result',['uncertain','rejected','unexpected'])
def test_uncertain_or_rejected_delivery_never_resends(tmp_path,result):
    calls=[];path=tmp_path/'brain.notifications.sqlite3'
    q=NotificationOutbox(path,lambda text:calls.append(text) or result)
    try:
        q.stage(attempt());q.step(NOW);complete(q)
    finally:q.close()
    q=NotificationOutbox(path,lambda text:calls.append(text))
    try:
        assert q.step(NOW+999999)=='idle'
        assert len(calls)==1
    finally:q.close()

def test_slow_delivery_does_not_block_owner_and_restart_marks_uncertain(tmp_path):
    gate=threading.Event();started=threading.Event();calls=[]
    def slow(text):
        calls.append(text);started.set();gate.wait(2);return 'delivered'
    path=tmp_path/'brain.notifications.sqlite3';q=NotificationOutbox(path,slow)
    try:
        q.stage(attempt());assert q.step(NOW)=='sending'
        assert started.wait(1)
        assert q.step(NOW+5000)=='sending'
        q.close()
        restored=NotificationOutbox(path,lambda _:pytest.fail('uncertain resend'))
        try:
            assert restored.db.execute('SELECT status FROM notifications').fetchone()[0]=='uncertain'
            assert restored.step(NOW+5001)=='idle'
        finally:restored.close()
    finally:gate.set();q.close()
    assert len(calls)==1

def test_second_owner_and_wallet_path_are_rejected(tmp_path):
    path=tmp_path/'brain.notifications.sqlite3'
    q=NotificationOutbox(path,lambda _: 'delivered')
    try:
        with pytest.raises(BlockingIOError):NotificationOutbox(path,lambda _: 'delivered')
        with pytest.raises(ValueError):NotificationOutbox(tmp_path/'brain.sqlite3',lambda _: 'delivered')
        alias=tmp_path/'alias.notifications.sqlite3';alias.symlink_to(path)
        with pytest.raises(ValueError):NotificationOutbox(alias,lambda _: 'delivered')
    finally:q.close()

def test_pending_capacity_is_bounded(tmp_path):
    q=NotificationOutbox(tmp_path/'brain.notifications.sqlite3',lambda _: 'delivered')
    try:
        for number in range(100):assert q.stage(attempt(ts_ms=NOW+1800000*number))
        assert not q.stage(attempt(ts_ms=NOW+1800000*101))
        assert q.db.execute('SELECT COUNT(*) FROM notifications').fetchone()[0]==100
    finally:q.close()

@pytest.mark.parametrize('body,expected',[
    ({'ok':True,'result':{'message_id':1}},'delivered'),
    ({'ok':False,'error_code':429},'retry'),
    ({'ok':False,'description':'SYNTHETIC_SECRET'},'uncertain'),
    ({'ok':True,'result':{}},'uncertain')])
def test_telegram_protocol_receipt(body,expected):
    seen=[]
    def opener(request,timeout):
        seen.append((request,timeout));return io.BytesIO(json.dumps(body).encode())
    send=telegram_sender('synthetic-token','synthetic-chat',opener=opener)
    assert send('test')==expected
    assert seen[0][1]==3
    assert json.loads(seen[0][0].data)=={'chat_id':'synthetic-chat','text':'test'}

@pytest.mark.parametrize('code,expected',[(429,'retry'),(400,'rejected'),(403,'rejected'),(500,'uncertain')])
def test_http_error_classification(code,expected):
    def opener(*args,**kwargs):raise urllib.error.HTTPError('synthetic',code,'',{},None)
    assert telegram_sender('synthetic-token','synthetic-chat',opener=opener)('test')==expected

def test_network_timeout_does_not_expose_provider_text():
    def opener(*args,**kwargs):raise TimeoutError('SYNTHETIC_SECRET')
    assert telegram_sender('synthetic-token','synthetic-chat',opener=opener)('test')=='uncertain'
    with pytest.raises(ValueError):telegram_sender(None,'synthetic-chat')

def test_service_protects_before_notification_and_uses_current_attempt():
    order=[];s=BrainService.__new__(BrainService)
    s.clock=lambda:NOW;s.account=Mock()
    s.account.brain.store.load.side_effect=[{'positions':{}},AssertionError('no second wallet read')]
    s.feed=Mock();s.feed.poll.return_value=({}, {})
    s.trend_v11=Mock();s.trend_v11.poll.return_value={}
    s.structure_enabled=False;s.last_teaching_recovery=None
    s.teaching_status='pending_recovery';s.supervisor=Mock()
    def protect(*args,**kwargs):
        order.append('protect');return {'tick':'ok','ai_attempt':attempt()}
    s.supervisor.step.side_effect=protect;s.operator=Mock()
    s.operator.sync.side_effect=OSError('synthetic teaching outage')
    s.notifications=Mock()
    def stage(value):
        order.append('stage');assert value==attempt()
    s.notifications.stage.side_effect=stage
    s.notifications.step.side_effect=OSError('synthetic queue outage')
    result=s.tick()
    assert result['tick']=='ok' and result['notification_status']=='unavailable'
    assert order==['protect','stage']

def test_notification_configuration_is_explicit_and_validation_does_not_send(tmp_path):
    from backend.tests.test_brain_single_integration import setup_env
    from director.brain_scalp.service import required_env
    env=setup_env(tmp_path)
    assert required_env(env)['notification_sender'] is None
    env['BRAIN_NOTIFY_TELEGRAM']='yes'
    with pytest.raises(ValueError,match='invalid_notification_mode'):required_env(env)
    env['BRAIN_NOTIFY_TELEGRAM']='on'
    with pytest.raises(ValueError,match='explicit_telegram_destination_required'):required_env(env)
    env.update(TELEGRAM_BOT_TOKEN='synthetic-token',TELEGRAM_CHAT_ID='synthetic-chat')
    assert callable(required_env(env)['notification_sender'])
    assert not (tmp_path/'wallet').exists()

def test_real_service_queue_preserves_financial_state(tmp_path):
    from backend.tests.test_brain_single_integration import setup_env,FakeReader
    from director.brain_scalp.market_bridge import PublicBrainFeed
    from director.brain_scalp.service import required_env
    sent=[];config=required_env(setup_env(tmp_path))
    config['notification_sender']=lambda message:sent.append(message) or 'delivered'
    config['primary']=lambda *args:pytest.fail('unexpected AI call')
    service=BrainService(config,feed=PublicBrainFeed(reader=FakeReader(),fetcher=lambda _:None),
                         clock_ms=lambda:NOW,initialize=True)
    try:
        before=service.account.brain.store.load()
        service.account.brain.store.commit(dict(before,last_ai_attempt=attempt()),NOW,[])
        # An empty feed exercises owner protection without requesting analysis.
        service.feed.poll=lambda *args:({}, {})
        result=service.tick()
        assert result['notification_status']=='sending'
        assert complete(service.notifications)=='delivered'
        after=service.account.brain.store.load()
        for field in ('positions','cash','realized_net'):
            assert after.get(field)==before.get(field)
        assert len(sent)==1 and 'DeepSeek' in sent[0]
    finally:service.close()

