"""Brain PAPER-only per-position exit capability: never unlock from a stale/pause-only heartbeat."""
import json
import time

import pytest
from fastapi.testclient import TestClient

from backend.v3.cutover_gate import brain_single_close_enabled, should_refuse_mutation
from backend.tests.test_v3_dashboard_unified import _app, _journal_sample, _paths
from backend.tests.test_v3_dashboard_manual_close import _heartbeat


def environment(path):
    return {
        'V3_CUTOVER_READONLY': '1',
        'V3_ALLOW_BRAIN_SINGLE_CLOSE': '1',
        'TRADING_MODE': 'paper',
        'DESK_MODE': 'paper',
        'V3_HEARTBEAT_PATH': str(path),
        'V3_RUN_ID': 'brain-run-test',
    }


def beat(path, now, **updates):
    heartbeat={'ts_ms':now,'cycle':2,'state':'paused','run_id':'brain-run-test',
               'last_error':None,'manual_close_capable':True}
    heartbeat.update(updates)
    path.write_text(json.dumps(heartbeat),encoding='utf-8')


def test_brain_manual_close_requires_current_matching_run_and_real_consumer(tmp_path):
    now=int(time.time()*1000)
    path=tmp_path/'heartbeat.json'
    env=environment(path)
    assert not brain_single_close_enabled(env,now)
    beat(path,now)
    assert brain_single_close_enabled(env,now)
    assert not should_refuse_mutation('POST','/api/v3/brain/close',readonly=True,
                                      allow_paper_brain_single_close=True)
    for key,invalid in [('V3_CUTOVER_READONLY','0'),('V3_ALLOW_BRAIN_SINGLE_CLOSE','0'),
                        ('TRADING_MODE','live'),('DESK_MODE','live'),
                        ('V3_RUN_ID','another-run')]:
        assert not brain_single_close_enabled({**env,key:invalid},now), key
    for updates in [
        {'ts_ms':now-16_000}, {'ts_ms':now+1000},
        {'run_id':'another-run'}, {'manual_close_capable':False},
        {'manual_close_capable':None}, {'state':'unknown'}
    ]:
        beat(path,now,**updates)
        assert not brain_single_close_enabled(env,now),updates
    beat(path,now)
    assert brain_single_close_enabled(env,now)


@pytest.mark.parametrize('path',[
    '/api/v3/brain/close-result', '/api/v3/brain/start',
    '/api/v3/brain/stop', '/api/desk/close-all',
    '/api/desk/resume', '/api/v3/brain/close/extra'
])
def test_brain_single_manual_exit_never_unlocks_other_commands(path):
    assert should_refuse_mutation('POST',path,readonly=True,
                                  allow_paper_brain_single_close=True)


def test_brain_close_all_is_denied_even_if_single_close_route_was_unlocked(tmp_path, monkeypatch):
    paths=_paths(tmp_path)
    _journal_sample(paths,close=False)
    _heartbeat(tmp_path)
    monkeypatch.setenv('V3_CUTOVER_READONLY','1')
    with TestClient(_app(paths)[0]) as client:
        bad=client.post('/api/v3/brain/close',json={'all':True})
        assert bad.status_code==423
        assert bad.json()['detail']['code']=='chiusura_totale_disabilitata'
        assert not (tmp_path/'close_request.json').exists()
    # Existing one-position semantics are not changed by this narrow gate.
    monkeypatch.setenv('V3_CUTOVER_READONLY','0')


def test_fresh_heartbeat_without_real_manual_consumer_is_not_authorization(tmp_path):
    now=int(time.time()*1000)
    path=tmp_path/'heartbeat.json'
    beat(path,now,manual_close_capable=False,state='running')
    assert not brain_single_close_enabled(environment(path),now)
