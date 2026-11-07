"""S2 preview tests: only synthetic decision cards and real read-only FastAPI journal."""
from __future__ import annotations

import hashlib
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import pytest

from backend.v3.events import Event, EventJournal
from backend.v3.supervisor.terminal import project_timeline
from backend.v3.supervisor_http import make_router

RUN = 'test-S2'
T0 = 1_700_000_000_000


def s0(decisions=None, **overrides):
    x = {'portfolio_id': 'brain', 'run_id': RUN, 'has_more': False,
         'total_decisions': len(decisions or []), 'decisions': decisions or []}
    return {**x, **overrides}


def decision(**overrides):
    return {**{'decision_event_id': 'brain.dec.1', 'decision_at_ms': T0,
               'kind': 'OPEN', 'status': 'APPROVED', 'reason_class': 'approved_open',
               'reason_code': 'risk_quote_ok', 'symbol': 'BTCUSDT', 'regime': 'TREND_UP',
               'strategy_id': 'S07', 'execution': 'closed_verified',
               'net_bp_after_costs': '25.0000', 'realized_pnl': '2.50'}, **overrides}


def observation(**overrides):
    return {**{'observation_id': 'supervisor.1', 'event_hash': 'a' * 64,
               'at_ms': T0-100, 'symbol': 'BTCUSDT', 'phase': 'ready', 'reason': 'ready',
               'market_sha256': 'b'*64, 'portfolio': {'equity': '1000',
                'available_cash': '800'},
               'market': {'timeframes': [{'tf': '15m', 'status': 'ok',
                        'rsi': '44.12', 'adx': '20.5', 'regime': 'TREND_UP',
                        'ema_fast_gap_bp': '12.5'}]},
               'resolution_state':'resolved', 'decision': {'decision_event_id': 'brain.dec.1', 'status': 'APPROVED',
                            'kind':'OPEN', 'reason_code':'risk_quote_ok',
                            'risk_quote': {'worst_case_loss_estimate': '19.99',
                                           'risk_budget': '20'}}}, **overrides}


def test_verified_combination_is_readable_and_bounded():
    data = project_timeline(s0([decision()]), [observation()], run_id=RUN)
    assert data['portfolio_id'] == 'brain' and data['matched_in_window'] == 1
    c = data['decisions'][0]
    assert c['id'] == 'brain.dec.1' and c['evidence_status'] == 'recorded'
    assert c['evidence']['market_sha256'] == 'b'*64
    assert c['evidence']['risk_at_stop'] == '19.99'
    assert c['evidence']['timeframes'][0]['rsi'] == '44.12'
    assert c['net_bp'] == '25.0000'


def test_s1_skipped_is_separate_not_no_trade():
    o = observation(phase='skipped', reason='feed_error', market=None, decision=None,
                    resolution_state='skipped')
    c = project_timeline(s0(), [o], run_id=RUN)['decisions'][0]
    assert c['kind'] == 'SKIPPED' and c['reason_class'] == 'preflight_skipped'
    assert c['execution'] == 'preflight_skipped' and c['net_bp'] is None


def test_no_evidence_not_fabricated():
    c = project_timeline(s0([decision(kind='NO_TRADE', status='REJECTED',
                                            execution='not_executed', net_bp_after_costs=None)]),
                         [], run_id=RUN)['decisions'][0]
    assert c['evidence'] is None and c['evidence_status'] == 'not_recorded'


def test_multiple_matches_are_ambiguous_not_inferred():
    dup = observation(observation_id='supervisor.2')
    c = project_timeline(s0([decision()]), [observation(), dup], run_id=RUN)['decisions'][0]
    assert c['evidence'] is None and c['evidence_status'] == 'ambiguous'


def test_malicious_rationale_and_market_data_stripped():
    evil = '<script>alert(1)</script>'
    c = project_timeline(s0([decision(reason_class=evil, reason_code=evil,
                       strategy_id=evil, symbol=evil, net_bp_after_costs='NaN')]),
                [observation(market={'timeframes':[{'tf':'<script>', 'status':'ok',
                        'free_text':'reveal secret'}]})], run_id=RUN)['decisions'][0]
    assert evil not in str(c)
    assert 'reveal secret' not in str(c)
    assert c['reason_class'] == 'other_recorded_decision'
    assert c['net_bp'] is None and c['symbol'] is None


@pytest.mark.parametrize('field,value', [
    ('limit', 0), ('limit', 101), ('limit', True), ('limit', 1.0),
    ('symbol', '<BTC>'), ('symbol', 'btc'), ('reason', 'secret_provider_text'),
    ('run_id', '../run')
])
def test_filters_validate_before_reading(field, value):
    k = {'run_id': RUN, 'limit': 50, 'symbol': None, 'reason': None}
    k[field] = value
    with pytest.raises(ValueError, match='invalid_request'):
        project_timeline(s0([decision()]), (), **k)


def test_wrong_portfolio_run_rejected():
    for obj in [s0(portfolio_id='hawk'), s0(run_id='another'), {}, []]:
        with pytest.raises(ValueError, match='invalid_sources'):
            project_timeline(obj, (), run_id=RUN)


def test_filter_and_descending_page():
    cards = [decision(decision_event_id=f'brain.dec.{i}', decision_at_ms=T0+i*1000,
                      symbol='ETHUSDT' if i % 2 else 'BTCUSDT',
                      reason_class='ai_unavailable' if i % 3 == 0 else 'approved_open')
             for i in range(8)]
    x = project_timeline(s0(cards, has_more=True), (), run_id=RUN, limit=2,
                         symbol='BTCUSDT')
    assert x['source_window_limited'] is True
    assert x['matched_in_window'] == 4 and x['has_more'] is True
    assert [c['id'] for c in x['decisions']] == ['brain.dec.6', 'brain.dec.4']
    y = project_timeline(s0(cards), (), run_id=RUN, reason='ai_unavailable')
    assert [c['id'] for c in y['decisions']] == ['brain.dec.6','brain.dec.3','brain.dec.0']


def _app(path, s0_reader=None, s1_reader=None):
    app = FastAPI()
    def auth(): return 'session-ok'
    app.include_router(make_router(auth, str(path), RUN,
                                   s0_reader=s0_reader, s1_reader=s1_reader))
    return app, auth


def _sample_db(tmp_path):
    path = tmp_path / 'journal.db'
    j = EventJournal(path)
    j.init_schema()
    j.append(Event('brain.dec.1', 'brain', RUN, 'brain_decision', T0,
                   'test', {'kind':'OPEN','status':'APPROVED','symbol':'BTCUSDT'}))
    return path


def test_route_missing_database_is_explicit_not_started(tmp_path):
    app,_ = _app(tmp_path/'journal.db')
    with TestClient(app) as client:
        r=client.get('/api/v3/brain/decision-timeline')
    assert r.status_code == 200 and r.json()['state'] == 'not_started'
    assert r.headers['cache-control'] == 'no-store'


def test_route_missing_prerequisites_is_explicit_503(tmp_path, monkeypatch):
    # Missing module is simulated; the integrated tree normally contains S0/S1.
    import builtins
    old_import = builtins.__import__
    def import_guard(name, *args, **kwargs):
        if name == "backend.v3.supervisor.trace":
            raise ImportError("simulated_missing_s0")
        return old_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", import_guard)
    path = _sample_db(tmp_path)
    app,_ = _app(path)
    with TestClient(app) as client:
        r=client.get('/api/v3/brain/decision-timeline')
    assert r.status_code == 503
    assert r.json()['detail']['code'] == 'supervisor_not_integrated'


def test_route_same_auth_and_no_writes(tmp_path):
    path = _sample_db(tmp_path)
    before = hashlib.sha256(path.read_bytes()).digest()
    seen = []
    def read_s0(journal, *, run_id, limit):
        assert limit == 500 and run_id == RUN
        seen.append('S0'); return s0([decision()])
    def read_s1(journal, *, run_id):
        assert run_id == RUN
        seen.append('S1'); return [observation()]
    app, auth = _app(path, read_s0, read_s1)
    with TestClient(app) as client:
        result = client.get('/api/v3/brain/decision-timeline?symbol=BTCUSDT')
        assert result.status_code == 200, result.text
        assert result.json()['state'] == 'ready'
        assert result.json()['decisions'][0]['evidence']['risk_budget'] == '20'
        assert result.headers['cache-control'] == 'no-store'
        assert result.headers['x-content-type-options'] == 'nosniff'
        for method in (client.post, client.put, client.delete):
            assert method('/api/v3/brain/decision-timeline').status_code == 405
        app.dependency_overrides[auth] = lambda: (_ for _ in ()).throw(HTTPException(401))
        assert client.get('/api/v3/brain/decision-timeline').status_code == 401
    assert seen == ['S0','S1']
    assert hashlib.sha256(path.read_bytes()).digest() == before


def test_bad_filter_rejected_before_reader(tmp_path):
    path=_sample_db(tmp_path)
    calls=[]
    app,_=_app(path, lambda *a,**k:calls.append(1), lambda *a,**k:calls.append(1))
    with TestClient(app) as client:
        for value in ('?symbol=%3Cscript%3E', '?reason=unknown', '?limit=101'):
            assert client.get('/api/v3/brain/decision-timeline'+value).status_code == 422
    assert calls==[]


def test_invalid_configured_run_does_not_open_db(tmp_path):
    path=_sample_db(tmp_path)
    app=FastAPI()
    app.include_router(make_router(lambda: 'ok', str(path), '../run'))
    with TestClient(app) as client:
        r=client.get('/api/v3/brain/decision-timeline')
    assert r.status_code==503 and r.json()['detail']['code']=='supervisor_not_configured'

@pytest.mark.parametrize('field,value', [
    ('symbol','ETHUSDT'),
    ('at_ms', T0 + 1000),  # observation occurs after the decision it claims to support
    ('decision', {'decision_event_id':'brain.dec.1','kind':'NO_TRADE',
                  'status':'APPROVED','reason_code':'risk_quote_ok'}),
    ('decision', {'decision_event_id':'brain.dec.1','kind':'OPEN',
                  'status':'REJECTED','reason_code':'risk_quote_ok'}),
    ('decision', {'decision_event_id':'brain.dec.1','kind':'OPEN',
                  'status':'APPROVED','reason_code':'sanitized'}),
])
def test_forged_or_inconsistent_evidence_not_attached(field,value):
    e = observation(**{field:value})
    result=project_timeline(s0([decision()]), [e], run_id=RUN)
    card=result['decisions'][0]
    assert card['evidence'] is None
    assert card['evidence_status']=='inconsistent'
    assert card['net_bp']=='25.0000'  # S0 independently verifies the trade


def test_untrusted_evidence_with_no_status_not_pretended_verified():
    e=observation(resolution_state=None)
    c=project_timeline(s0([decision()]), [e], run_id=RUN)['decisions'][0]
    assert c['evidence'] is None and c['evidence_status']=='not_recorded'


def test_pending_evidence_cannot_be_joined_to_decision():
    e=observation(decision=None, resolution_state='pending')
    c=project_timeline(s0([decision()]), [e], run_id=RUN)['decisions'][0]
    assert c['evidence'] is None and c['evidence_status']=='not_recorded'


def test_s0_pnl_not_exposed_without_a_verified_close():
    for state in ('not_executed', 'open_unverified_outcome', 'closed_unverified',
                  'ambiguous_link', None):
        c=project_timeline(s0([decision(execution=state,
                                          net_bp_after_costs='999999',
                                          realized_pnl='888888')]), (), run_id=RUN)['decisions'][0]
        assert c['net_bp'] is None and c['realized_pnl'] is None


def test_duplicate_decision_id_does_not_invent_two_independent_events():
    with pytest.raises(ValueError, match='invalid_sources'):
        project_timeline(s0([decision(), decision(decision_at_ms=T0+1)]), (), run_id=RUN)


def test_impossible_total_count_rejected():
    with pytest.raises(ValueError, match='invalid_sources'):
        project_timeline(s0([decision()], total_decisions=0), (), run_id=RUN)


def test_multiple_evidence_claims_are_ambiguous_even_if_one_matches():
    dup=observation(observation_id='supervisor.2', symbol='ETHUSDT')
    c=project_timeline(s0([decision()]), [observation(),dup], run_id=RUN)['decisions'][0]
    assert c['evidence'] is None and c['evidence_status']=='ambiguous'


def test_unverified_skip_with_forged_decision_is_dropped():
    skip=observation(phase='skipped', reason='feed_error', market=None,
                     resolution_state='skipped')
    x=project_timeline(s0(), [skip], run_id=RUN)
    assert x['matched_in_window']==0


def test_supervisor_503_is_uncacheable_and_never_opens_missing_modules(tmp_path, monkeypatch):
    # Missing module is simulated; the integrated tree normally contains S0/S1.
    import builtins
    old_import = builtins.__import__
    def import_guard(name, *args, **kwargs):
        if name == "backend.v3.supervisor.trace":
            raise ImportError("simulated_missing_s0")
        return old_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", import_guard)
    path=_sample_db(tmp_path)
    app,_=_app(path)
    with TestClient(app) as client:
        res=client.get('/api/v3/brain/decision-timeline')
    assert res.status_code==503
    assert res.json()['detail']['code']=='supervisor_not_integrated'
    assert res.headers['cache-control']=='no-store'
    assert res.headers['x-content-type-options']=='nosniff'


def test_supervisor_422_filters_are_uncacheable(tmp_path):
    path=_sample_db(tmp_path)
    app,_=_app(path)
    with TestClient(app) as client:
        res=client.get('/api/v3/brain/decision-timeline?symbol=%3Cunsafe%3E')
    assert res.status_code==422 and res.headers['cache-control']=='no-store'
