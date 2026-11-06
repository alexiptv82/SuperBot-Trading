"""Unified PAPER dashboard: session gate, read-only, real journal, synthetic data."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from decimal import Decimal

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.v3.events import Event, EventJournal
from backend.v3.executor.paper import execute_paper
from backend.v3.executor.paper_close import close_paper
from backend.v3.brain_f2.contracts import BrainDecision, DecisionKind, OpenProposal, ProposalStatus
from backend.v3.risk import RiskQuote
from backend.v3_api import V3Paths, make_router

D = Decimal
RUN = 'run-test'
T0 = 1_700_000_000_000


def _app(paths, get_ticker=None):
    app = FastAPI()
    def auth():
        return 'authorized'
    app.include_router(make_router(auth, paths, get_ticker))
    app.dependency_overrides[auth] = lambda: 'authorized'
    return app, auth


def _paths(tmp_path):
    hawk = tmp_path / 'hawk'
    bull = tmp_path / 'bull'
    hawk.mkdir()
    bull.mkdir()
    return V3Paths(
        journal_path=str(tmp_path / 'journal.db'), run_id=RUN,
        budget_db_path=str(tmp_path / 'budget.db'),
        heartbeat_path=str(tmp_path / 'heartbeat.json'),
        pause_flag_path=str(tmp_path / 'pause.flag'),
        falco_data_dir=str(hawk), toro_data_dir=str(bull),
    )


def _journal_sample(paths, close=True):
    journal = EventJournal(paths.journal_path)
    journal.init_schema()
    decision_id = 'decision-01'
    journal.append(Event(decision_id, 'brain', RUN, 'brain_decision', T0,
                         'test', {'kind': 'OPEN', 'status': 'APPROVED', 'symbol': 'BTCUSDT',
                                  'regime': 'TREND_UP', 'strategy_id': 'S07',
                                  'strategy_origin': 'library'}))
    proposal = OpenProposal('BTCUSDT', 1, D('100'), D('95'), 5,
                            'test', 0.6, 'deepseek', 'mock')
    quote = RiskQuote(True, 'ok', D('2'), D('200'), D('40'), D('10'), D('100'))
    decision = BrainDecision(DecisionKind.OPEN, proposal=proposal, risk_quote=quote,
                             status=ProposalStatus.APPROVED, journal_event_id=decision_id)
    receipt = execute_paper(decision, portfolio_id='brain', run_id=RUN,
                            journal=journal, now_ms=T0 + 1_000)
    if close:
        close_paper(portfolio_id='brain', run_id=RUN, position_id=receipt.position_id,
                    exit_price=D('102'), reason='take_profit', fee_bps=D('6'),
                    journal=journal, now_ms=T0 + 61_000)
    return receipt.position_id


def _get(client, path):
    result = client.get(path)
    assert result.status_code == 200, result.text
    assert result.headers['cache-control'] == 'no-store'
    return result.json()


def test_missing_all_files_is_not_started(tmp_path):
    paths = _paths(tmp_path)
    app, _ = _app(paths)
    with TestClient(app) as c:
        o = _get(c, '/api/v3/overview')
        assert [x['id'] for x in o['portfolios']] == ['falco', 'toro', 'brain']
        assert all(x['state'] == 'not_started' for x in o['portfolios'])
        assert o['portfolios'][2]['last_event_ms'] is None
        s = _get(c, '/api/v3/brain/status')
        assert s['heartbeat'] is None and s['spend'] is None and s['last_decision'] is None
        assert _get(c, '/api/v3/brain/scoreboard')['regimes'] == []
        assert _get(c, '/api/v3/brain/trades')['closed_trades'] == []
        assert _get(c, '/api/v3/brain/trades')['open_positions'] == []


def test_login_and_only_get(tmp_path):
    paths = _paths(tmp_path)
    app, auth = _app(paths)
    def deny():
        raise HTTPException(401, 'session_missing')
    app.dependency_overrides[auth] = deny
    with TestClient(app) as c:
        for path in ('/api/v3/overview', '/api/v3/brain/status',
                     '/api/v3/brain/scoreboard', '/api/v3/brain/trades'):
            assert c.get(path).status_code == 401
            assert c.post(path).status_code == 405
            assert c.put(path).status_code == 405
            assert c.delete(path).status_code == 405
    methods = {route.path: route.methods for route in make_router(auth, paths).routes}
    assert methods['/api/v3/brain/close'] == {'POST'}
    assert all(methods[path] == {'GET'} for path in methods if path != '/api/v3/brain/close')


def test_real_journal_closed_trade_score_and_immutable(tmp_path):
    paths = _paths(tmp_path)
    position_id = _journal_sample(paths)
    before = hashlib.sha256((tmp_path / 'journal.db').read_bytes()).hexdigest()
    app, _ = _app(paths)
    with TestClient(app) as c:
        overview = _get(c, '/api/v3/overview')
        brain = overview['portfolios'][2]
        assert brain['realized_pnl'] == '3.75760000'
        assert brain['open_positions'] == 0
        assert brain['margin_in_use'] == '0'
        status = _get(c, '/api/v3/brain/status')
        assert status['last_decision']['strategy_id'] == 'S07'
        assert status['last_decision']['regime'] == 'TREND_UP'
        scores = _get(c, '/api/v3/brain/scoreboard')
        assert len(scores['regimes']) == 1
        assert scores['regimes'][0]['regime'] == 'TREND_UP'
        cell = scores['regimes'][0]['cells'][0]
        assert (cell['strategy_id'], cell['side'], cell['n'], cell['status']) == ('S07', 1, 1, 'insufficient')
        trades = _get(c, '/api/v3/brain/trades?limit=1')
        assert trades['closed_trades'][0]['position_id'] == position_id
        assert trades['closed_trades'][0]['exit_reason'] == 'take_profit'
        assert trades['closed_trades'][0]['strategy_origin'] == 'library'
        assert isinstance(trades['closed_trades'][0]['net_bp'], str)
    assert hashlib.sha256((tmp_path / 'journal.db').read_bytes()).hexdigest() == before


def test_real_journal_open_position_with_optional_mark(tmp_path):
    paths = _paths(tmp_path)
    pid = _journal_sample(paths, close=False)
    app, _ = _app(paths)
    with TestClient(app) as c:
        data = _get(c, '/api/v3/brain/trades')
        assert data['closed_trades'] == []
        assert data['open_positions'][0]['position_id'] == pid
        assert data['open_positions'][0]['unrealized_pnl'] is None
        assert data['open_positions'][0]['strategy_id'] == 'S07'
    async def ticker(symbol):
        assert symbol == 'BTCUSDT'
        return {'price': '105'}
    app, _ = _app(paths, ticker)
    with TestClient(app) as c:
        assert _get(c, '/api/v3/brain/trades')['open_positions'][0]['unrealized_pnl'] == '10'


@pytest.mark.parametrize('delta,state,expected', [
    (0, 'running', 'running'),
    (2_700_001, 'running', 'stale'),
    (9_000_000, 'halted', 'halted'),
    (0, 'paused', 'paused'),
])
def test_heartbeat_states(tmp_path, delta, state, expected):
    paths = _paths(tmp_path)
    now_ms = int(time.time() * 1000)
    (tmp_path / 'heartbeat.json').write_text(json.dumps({
        'ts_ms': now_ms - delta, 'cycle': 4, 'state': state,
        'run_id': RUN, 'last_error': 'halted:no_mandate'}))
    app, _ = _app(paths)
    with TestClient(app) as c:
        assert _get(c, '/api/v3/brain/status')['state'] == expected
        assert _get(c, '/api/v3/overview')['portfolios'][2]['state'] == expected


def test_pause_flag_without_changing_file(tmp_path):
    paths = _paths(tmp_path)
    (tmp_path / 'heartbeat.json').write_text(json.dumps({
        'ts_ms': int(time.time() * 1000), 'cycle': 1, 'state': 'running', 'run_id': RUN}))
    flag = tmp_path / 'pause.flag'
    flag.write_bytes(b'')
    app, _ = _app(paths)
    with TestClient(app) as c:
        assert _get(c, '/api/v3/brain/status')['paused'] is True
        assert _get(c, '/api/v3/brain/status')['state'] == 'paused'
    assert flag.read_bytes() == b''


def test_read_only_budget_day_month_without_writes(tmp_path):
    paths = _paths(tmp_path)
    month = time.strftime('%Y-%m', time.gmtime())
    with sqlite3.connect(paths.budget_db_path) as db:
        db.executescript('CREATE TABLE spend_events (id INTEGER PRIMARY KEY, occurred_at TEXT, provider TEXT, units INTEGER, metadata TEXT);')
        db.execute('INSERT INTO spend_events VALUES(1, ?, ?, ?, ?)',
                   (month + '-01T10:20:30+00:00', 'deepseek', 123000, '{}'))
        db.commit()
    original = (tmp_path / 'budget.db').read_bytes()
    app, _ = _app(paths)
    with TestClient(app) as c:
        data = _get(c, '/api/v3/brain/status')['spend']
        assert data['month'] == '0.123'
        assert data['day_limit'] is not None
        assert isinstance(data['day'], str)
    assert (tmp_path / 'budget.db').read_bytes() == original
    assert not (tmp_path / 'budget.db-wal').exists()


def test_classic_desk_mapping_uses_real_readers(tmp_path):
    paths = _paths(tmp_path)
    hawk = tmp_path / 'hawk'
    now = time.time()
    (hawk / 'heartbeat.json').write_text(json.dumps({'ts': now, 'cycles': 1}))
    (hawk / 'state_v2.json').write_text(json.dumps({'main': {
        'cash': 900, 'positions': {'BTC': {'entry': 100, 'qty': 1, 'side': 1, 'margin': 35}},
        'closed': [{'net': '4.5', 'close_ms': T0 + 100}],
        'limits': {'start_equity': 1000}}, 'last_prices_ms': T0}))
    app, _ = _app(paths)
    with TestClient(app) as c:
        data = _get(c, '/api/v3/overview')
        falco = data['portfolios'][0]
        assert falco['state'] == 'running'
        assert falco['open_positions'] == 1
        assert falco['margin_in_use'] == '35'
        assert falco['realized_pnl'] == '4.5'
        assert data['portfolios'][1]['state'] == 'not_started'


def test_limit_validation_and_no_json_float(tmp_path):
    paths = _paths(tmp_path)
    _journal_sample(paths)
    app, _ = _app(paths)
    with TestClient(app) as c:
        assert c.get('/api/v3/brain/trades?limit=0').status_code == 422
        assert c.get('/api/v3/brain/trades?limit=201').status_code == 422
        for endpoint in ('overview', 'brain/status', 'brain/scoreboard', 'brain/trades'):
            obj = _get(c, '/api/v3/' + endpoint)
            def check(value):
                assert type(value) is not float
                if isinstance(value, dict):
                    for item in value.values(): check(item)
                elif isinstance(value, list):
                    for item in value: check(item)
            check(obj)


def test_not_started_when_missing_journal_but_heartbeat_exists(tmp_path):
    paths = _paths(tmp_path)
    app, _ = _app(paths)
    with TestClient(app) as c:
        assert _get(c, '/api/v3/overview')['portfolios'][2]['open_positions'] == 0


def test_environment_paths_override_no_opt_guess(monkeypatch):
    monkeypatch.setenv('V3_JOURNAL_PATH', '/tmp/journal-demo.db')
    monkeypatch.setenv('V3_RUN_ID', 'example')
    assert V3Paths.from_env('f', 't').journal_path == '/tmp/journal-demo.db'
    assert V3Paths.from_env('f', 't').run_id == 'example'


def test_error_tokens_redacted_but_symbol_code_preserved(tmp_path):
    paths = _paths(tmp_path)
    (tmp_path / 'heartbeat.json').write_text(json.dumps({
        'ts_ms': int(time.time() * 1000), 'cycle': 1, 'state': 'running',
        'run_id': RUN, 'last_error': 'cycle:BTCUSDT:feed_error;IGNORE THIS TEXT;<html>'}))
    app, _ = _app(paths)
    with TestClient(app) as c:
        hb = _get(c, '/api/v3/brain/status')['heartbeat']
        assert hb['last_error'] == 'cycle:BTCUSDT:feed_error'


def test_bad_ticker_is_not_http_failure(tmp_path):
    paths = _paths(tmp_path)
    _journal_sample(paths, close=False)
    async def ticker(symbol):
        raise RuntimeError('unavailable')
    app, _ = _app(paths, ticker)
    with TestClient(app) as c:
        position = _get(c, '/api/v3/brain/trades')['open_positions'][0]
        assert position['unrealized_pnl'] is None


def test_rich_brain_open_position_exposes_leverage_margin_and_live_price(tmp_path):
    paths = _paths(tmp_path)
    _journal_sample(paths, close=False)
    async def ticker(symbol):
        assert symbol == 'BTCUSDT'
        return {'price': '105'}
    app, _ = _app(paths, ticker)
    with TestClient(app) as c:
        p = _get(c, '/api/v3/brain/trades')['open_positions'][0]
        assert p['symbol'] == 'BTCUSDT'
        assert p['side'] == 1 and p['leverage'] == 5
        assert p['margin'] == '2'
        assert p['quantity'] == '2'
        assert p['entry'] == '100' and p['stop'] == '95'
        assert p['price'] == '105' and p['price_source'] == 'ticker'
        assert p['unrealized_pnl'] == '10'
        assert p['roi_pct'] == '500'
        assert p['opened_at_ms'] == T0 + 1000


def test_rich_brain_closed_trade_contains_financial_outcome(tmp_path):
    paths = _paths(tmp_path)
    _journal_sample(paths, close=True)
    app, _ = _app(paths)
    with TestClient(app) as c:
        t = _get(c, '/api/v3/brain/trades')['closed_trades'][0]
        assert t['leverage'] == 5
        assert t['margin'] == '2'
        assert t['entry'] == '100'
        assert t['exit'] == '102'
        assert Decimal(t['realized_pnl']) > 0
        assert Decimal(t['fees']) >= 0
        assert t['closed_at_ms'] == T0 + 61000


def test_rich_classic_overview_keeps_open_positions_when_close_unsupported(tmp_path):
    paths = _paths(tmp_path)
    hawk = tmp_path / 'hawk'
    now = time.time()
    (hawk / 'heartbeat.json').write_text(json.dumps({'ts': now, 'cycles': 1}))
    (hawk / 'state_v2.json').write_text(json.dumps({
        'main': {
            'cash': 900,
            'positions': {'BTCUSDT': {'entry': 100, 'qty': 1, 'side': -1,
                                     'leverage': 20, 'total_margin': 100, 'sl': 102,
                                     'tp': 95, 'trade_type': 'scalp'}},
            'closed': [{'symbol': 'ETHUSDT', 'side': 1, 'leverage': 20,
                        'entry': 100, 'exit': 103, 'net': 4.5,
                        'margin': 150, 'close_ms': T0+100, 'why': 'target'}],
            'limits': {'start_equity': 1000}},
        'last_prices': {'BTCUSDT': 99}, 'last_prices_ms': T0
    }))
    app, _ = _app(paths)
    with TestClient(app) as c:
        p = _get(c, '/api/v3/overview')['portfolios'][0]
        assert p['id'] == 'falco'
        assert p['can_close_position'] is False
        assert p['positions'][0]['symbol'] == 'BTCUSDT'
        assert p['positions'][0]['leverage'] == 20
        assert p['positions'][0]['price'] == '99'
        assert p['positions'][0]['price_source'] == 'bot'
        assert p['positions'][0]['margin'] == '100'
        assert p['positions'][0]['stop'] == '102'
        assert p['positions'][0]['take_profit'] == '95'
        assert p['positions'][0]['unrealized_pnl'] == '1.0'
        assert p['equity'] is not None
        assert p['closed_trades'][0]['symbol'] == 'ETHUSDT'
        assert p['closed_trades'][0]['realized_pnl'] == '4.5'


def test_classic_absent_price_is_not_replaced_with_unverified_mark(tmp_path):
    paths = _paths(tmp_path)
    hawk = tmp_path / 'hawk'
    (hawk / 'state_v2.json').write_text(json.dumps({'main': {
        'cash': 900, 'positions': {'BTCUSDT': {'entry': 100, 'qty': 1,
                                                'side': 1, 'total_margin': 100}},
        'limits': {'start_equity': 1000}}}))
    app, _ = _app(paths)
    with TestClient(app) as c:
        p = _get(c, '/api/v3/overview')['portfolios'][0]['positions'][0]
        assert p['price'] is None
        assert p['unrealized_pnl'] is None
