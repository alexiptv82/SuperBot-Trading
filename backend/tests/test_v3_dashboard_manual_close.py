"""Dashboard manual close: authenticated PAPER file protocol and read-only journal."""
from __future__ import annotations

import hashlib
import json
import time

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.tests.test_v3_dashboard_unified import _app, _journal_sample, _paths, RUN
from backend.v3_api import V3Paths


def _heartbeat(tmp_path, *, delta=0, state='running', run_id=RUN):
    (tmp_path / 'heartbeat.json').write_text(json.dumps({
        'ts_ms': int(time.time() * 1000) - delta, 'cycle': 1,
        'state': state, 'run_id': run_id, 'last_error': None,
    }), encoding='utf-8')


def _error(response, status, code):
    assert response.status_code == status, response.text
    assert response.json()['detail']['code'] == code
    assert response.headers['cache-control'] == 'no-store'


def test_single_close_contract_and_unchanged_journal(tmp_path):
    paths = _paths(tmp_path)
    pid = _journal_sample(paths, close=False)
    _heartbeat(tmp_path)
    before = hashlib.sha256((tmp_path / 'journal.db').read_bytes()).hexdigest()
    with TestClient(_app(paths)[0]) as client:
        response = client.post('/api/v3/brain/close', json={'position_id': pid})
        assert response.status_code == 200, response.text
        assert response.headers['cache-control'] == 'no-store'
        body = response.json()
        assert body == {'ok': True, 'pending': True, 'ts_ms': body['ts_ms']}
        assert json.loads((tmp_path / 'close_request.json').read_text()) == {
            'ts_ms': body['ts_ms'], 'position_ids': [pid]}
        assert client.get('/api/v3/brain/trades').json()['close_pending'] is True
        pending = client.get('/api/v3/brain/close-result')
        assert pending.status_code == 200
        assert pending.json() == {'result': None, 'pending': True}
    assert not list(tmp_path.glob('.close_request.*.tmp'))
    assert hashlib.sha256((tmp_path / 'journal.db').read_bytes()).hexdigest() == before


def test_close_all_contract_when_open(tmp_path):
    paths = _paths(tmp_path)
    _journal_sample(paths, close=False)
    _heartbeat(tmp_path, state='paused')
    with TestClient(_app(paths)[0]) as client:
        response = client.post('/api/v3/brain/close', json={'all': True})
        assert response.status_code == 200, response.text
    assert json.loads((tmp_path / 'close_request.json').read_text()) == {
        'ts_ms': response.json()['ts_ms'], 'all': True}


@pytest.mark.parametrize('data', [None, {}, {'all': False}, {'all': 1}, {'all': 'true'},
    {'position_id': 'p!'}, {'position_id': ''}, {'position_id': 'x' * 65},
    {'position_id': True}, {'position_id': 1}, {'position_id': 'x', 'all': True},
    {'position_id': 'x', 'other': 'y'}, ['BTCUSDT']])
def test_invalid_request_never_writes(tmp_path, data):
    paths = _paths(tmp_path)
    _journal_sample(paths, close=False)
    _heartbeat(tmp_path)
    with TestClient(_app(paths)[0]) as client:
        r = client.post('/api/v3/brain/close', json=data)
        _error(r, 422, 'richiesta_non_valida')
    assert not (tmp_path / 'close_request.json').exists()


@pytest.mark.parametrize('state,age,run_id', [
    ('running', 2_700_001, RUN), ('running', 0, 'another-run'),
    ('halted', 2_700_001, RUN), ('paused', 2_700_001, RUN),
])
def test_stale_or_wrong_run_refused(tmp_path, state, age, run_id):
    paths = _paths(tmp_path)
    pid = _journal_sample(paths, close=False)
    _heartbeat(tmp_path, state=state, delta=age, run_id=run_id)
    with TestClient(_app(paths)[0]) as client:
        _error(client.post('/api/v3/brain/close', json={'position_id': pid}), 409, 'brain_non_risponde')
    assert not (tmp_path / 'close_request.json').exists()


def test_missing_heartbeat_or_journal_refused(tmp_path):
    paths = _paths(tmp_path)
    with TestClient(_app(paths)[0]) as client:
        _error(client.post('/api/v3/brain/close', json={'all': True}), 409, 'brain_non_risponde')
    _heartbeat(tmp_path)
    with TestClient(_app(paths)[0]) as client:
        _error(client.post('/api/v3/brain/close', json={'all': True}), 409, 'brain_non_risponde')


def test_unknown_position_and_no_open(tmp_path):
    paths = _paths(tmp_path)
    _journal_sample(paths, close=True)
    _heartbeat(tmp_path)
    with TestClient(_app(paths)[0]) as client:
        _error(client.post('/api/v3/brain/close', json={'position_id': 'unknown'}), 404, 'posizione_non_aperta')
        _error(client.post('/api/v3/brain/close', json={'all': True}), 409, 'nessuna_posizione')
    assert not (tmp_path / 'close_request.json').exists()


@pytest.mark.parametrize('work_file', ['close_request.json', '.close_request.work'])
def test_existing_request_never_overwritten(tmp_path, work_file):
    paths = _paths(tmp_path)
    _journal_sample(paths, close=False)
    _heartbeat(tmp_path)
    old = b'{"existing":"do-not-touch"}'
    (tmp_path / work_file).write_bytes(old)
    with TestClient(_app(paths)[0]) as client:
        _error(client.post('/api/v3/brain/close', json={'all': True}), 409, 'richiesta_in_corso')
    assert (tmp_path / work_file).read_bytes() == old
    assert not list(tmp_path.glob('.close_request.*.tmp'))


def test_unauthorized_both_endpoints(tmp_path):
    paths = _paths(tmp_path)
    pid = _journal_sample(paths, close=False)
    _heartbeat(tmp_path)
    app, auth = _app(paths)
    def deny():
        raise HTTPException(401, 'session_missing')
    app.dependency_overrides[auth] = deny
    with TestClient(app) as client:
        assert client.post('/api/v3/brain/close', json={'position_id': pid}).status_code == 401
        assert client.get('/api/v3/brain/close-result').status_code == 401
    assert not (tmp_path / 'close_request.json').exists()


def test_close_result_missing_old_and_recent(tmp_path):
    paths = _paths(tmp_path)
    app, _ = _app(paths)
    now = int(time.time() * 1000)
    result = {'request_ts_ms': now - 50_000, 'done_ms': now,
              'status': 'done', 'closed': ['my-id'], 'failed': [['p2', 'price_unavailable']]}
    with TestClient(app) as client:
        r = client.get('/api/v3/brain/close-result')
        assert r.status_code == 200 and r.headers['cache-control'] == 'no-store'
        assert r.json() == {'result': None, 'pending': False}
        (tmp_path / 'close_result.json').write_text(json.dumps(result))
        assert client.get('/api/v3/brain/close-result').json() == {'result': result, 'pending': False}
        result['request_ts_ms'] = now - 601_000
        (tmp_path / 'close_result.json').write_text(json.dumps(result))
        assert client.get('/api/v3/brain/close-result').json()['result'] is None


@pytest.mark.parametrize('payload', [
    {'request_ts_ms': True, 'done_ms': 1, 'status': 'done', 'closed': [], 'failed': []},
    {'request_ts_ms': 2, 'done_ms': 2, 'status': '<script>', 'closed': [], 'failed': []},
    {'request_ts_ms': 2, 'done_ms': 2, 'status': 'done', 'closed': ['bad<id'], 'failed': []},
    {'request_ts_ms': 2, 'done_ms': 2, 'status': 'done', 'closed': [], 'failed': [['a', '<script>']]},
])
def test_close_result_untrusted_content_never_echoed(tmp_path, payload):
    paths = _paths(tmp_path)
    payload['request_ts_ms'] = int(time.time() * 1000) if type(payload['request_ts_ms']) is int else True
    (tmp_path / 'close_result.json').write_text(json.dumps(payload))
    with TestClient(_app(paths)[0]) as client:
        assert client.get('/api/v3/brain/close-result').json()['result'] is None


def test_environment_paths_and_default_sibling(tmp_path, monkeypatch):
    paths = _paths(tmp_path)
    assert paths.close_request_path == str(tmp_path / 'close_request.json')
    assert paths.close_result_path == str(tmp_path / 'close_result.json')
    monkeypatch.setenv('V3_HEARTBEAT_PATH', str(tmp_path / 'heartbeat.json'))
    monkeypatch.setenv('V3_CLOSE_REQUEST_PATH', str(tmp_path / 'requests.json'))
    monkeypatch.setenv('V3_CLOSE_RESULT_PATH', str(tmp_path / 'results.json'))
    env = V3Paths.from_env('f', 't')
    assert env.close_request_path == str(tmp_path / 'requests.json')
    assert env.close_result_path == str(tmp_path / 'results.json')


def test_classic_overview_capability_and_positions(tmp_path):
    paths = _paths(tmp_path)
    hawk = tmp_path / 'hawk'
    (hawk / 'heartbeat.json').write_text(json.dumps({'ts': time.time(), 'cycles': 1, 'close_position': True}))
    (hawk / 'state_v2.json').write_text(json.dumps({'main': {
        'cash': 900, 'positions': {'BTC': {'entry': 100, 'qty': 1, 'side': 1, 'margin': 35,
                                             'leverage': 20, 'sl': 92}},
        'closed': [], 'limits': {'start_equity': 1000}}}))
    with TestClient(_app(paths)[0]) as client:
        data = client.get('/api/v3/overview').json()['portfolios'][0]
        assert data['can_close_position'] is True
        assert len(data['positions']) == 1
        assert data['positions'][0]['symbol'] == 'BTC'
        assert data['positions'][0]['entry'] == '100.0'
        assert type(data['positions'][0]['unrealized_pnl']) is str
    (hawk / 'heartbeat.json').write_text(json.dumps({'ts': time.time(), 'cycles': 1}))
    with TestClient(_app(paths)[0]) as client:
        assert client.get('/api/v3/overview').json()['portfolios'][0]['can_close_position'] is False


def test_real_runner_file_protocol_roundtrip(tmp_path):
    """Executes on d3bfbdd, where Claude's manual_close.py is part of the tree."""
    manual_close = pytest.importorskip('backend.v3.runner.manual_close', reason='manual_close.py requires d3bfbdd')
    from decimal import Decimal
    from backend.v3.events import EventJournal
    from backend.v3.dashboard import build_summary

    paths = _paths(tmp_path)
    pid = _journal_sample(paths, close=False)
    _heartbeat(tmp_path)
    with TestClient(_app(paths)[0]) as client:
        request = client.post('/api/v3/brain/close', json={'position_id': pid})
        assert request.status_code == 200
        now_ms = request.json()['ts_ms'] + 1000
        result = manual_close.run_manual_close(
            journal=EventJournal(paths.journal_path), portfolio_id='brain', run_id=RUN,
            data_dir=tmp_path, price_of=lambda symbol, now: Decimal('102'),
            fee_bps=Decimal('6'), now_ms=now_ms)
        assert result.status == 'done'
        assert result.closed == (pid,)
        response = client.get('/api/v3/brain/close-result').json()
        assert response['pending'] is False
        assert response['result']['request_ts_ms'] == request.json()['ts_ms']
        assert response['result']['closed'] == [pid]
    summary = build_summary(EventJournal(paths.journal_path), 'brain', RUN)
    assert not summary.open_positions


def test_work_file_exposes_pending_to_dashboard(tmp_path):
    paths = _paths(tmp_path)
    _journal_sample(paths, close=False)
    (tmp_path / '.close_request.work').write_text('{}')
    with TestClient(_app(paths)[0]) as client:
        assert client.get('/api/v3/brain/trades').json()['close_pending'] is True
