"""Compatibility checks for reconstructed S0/S1 with the existing S2 projection.

These are NEW isolated tests, not original S0/S1 test suites. No deploy or trades.
"""
import hashlib
import json
import sqlite3
from decimal import Decimal

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import pytest

from backend.v3.events import Event, EventJournal
from backend.v3.supervisor.trace import read_brain_timeline
from backend.v3.supervisor.evidence import (record_skipped_candidate, record_resolution,
    read_evidence, EvidenceError, ObservationReceipt)
from backend.v3.supervisor.terminal import project_timeline
from backend.v3.supervisor_http import make_router
from backend.v3.brain_f2.contracts import BrainDecision, DecisionKind, ProposalStatus

RUN = 'reconstructed-s1-run'
TS = 1700000000000
SYMBOL = 'BTCUSDT'


def journal(tmp_path):
    j = EventJournal(tmp_path / 'journal.db')
    j.init_schema()
    return j


def test_s0_real_journal_no_trade_and_ai_down(tmp_path):
    j = journal(tmp_path)
    j.append(Event('dec1', 'brain', RUN, 'brain_decision', TS, 'test',
        {'symbol': SYMBOL, 'regime': 'TREND_UP', 'kind': 'NO_TRADE',
         'status': 'REJECTED', 'rationale': 'deepseek:analysis'}))
    j.append(Event('dec2', 'brain', RUN, 'brain_decision', TS+1, 'test',
        {'symbol': SYMBOL, 'regime': 'TREND_UP', 'kind': 'NO_TRADE',
         'status': 'REJECTED', 'rationale': 'ai_unavailable'}))
    s0 = read_brain_timeline(j, run_id=RUN, limit=10)
    assert s0['total_decisions'] == 2
    assert [c['reason_class'] for c in s0['decisions']] == ['ai_unavailable', 'brain_wait']
    assert all(c['realized_pnl'] is None for c in s0['decisions'])


def test_s1_preflight_skip_is_distinct_from_no_trade(tmp_path):
    j = journal(tmp_path)
    r = record_skipped_candidate(journal=j, run_id=RUN, symbol=SYMBOL,
       observed_at_ms=TS, candidate_index=0, reason='feed_error')
    evidence = read_evidence(j, run_id=RUN)
    assert evidence[0]['phase'] == 'skipped' and evidence[0]['decision'] is None
    s2 = project_timeline(read_brain_timeline(j,run_id=RUN, limit=50), evidence, run_id=RUN)
    assert s2['decisions'][0]['reason_class'] == 'preflight_skipped'
    assert s2['decisions'][0]['net_bp'] is None
    assert j.verify_chain()[0] == 1


def test_s1_idempotence_and_conflicting_id_fail_closed(tmp_path):
    j = journal(tmp_path)
    common = dict(journal=j, run_id=RUN, symbol=SYMBOL, observed_at_ms=TS,
                  candidate_index=0)
    a = record_skipped_candidate(**common, reason='feed_error')
    b = record_skipped_candidate(**common, reason='feed_error')
    assert a == b and len(j.list_run('brain',RUN)) == 1
    with pytest.raises(EvidenceError,match='^evidence_persist_failed$'):
        record_skipped_candidate(**common, reason='price_error')
    assert len(j.list_run('brain',RUN)) == 1


def test_s1_resolution_proves_its_parent_and_links_existing_decision(tmp_path):
    j = journal(tmp_path)
    obs = record_skipped_candidate(journal=j, run_id=RUN, symbol=SYMBOL,
       observed_at_ms=TS, candidate_index=0, reason='feed_error')
    # Must not attach to skipped observation.
    d = BrainDecision(kind=DecisionKind.NO_TRADE, proposal=None,
       status=ProposalStatus.REJECTED, rationale='ai_unavailable')
    with pytest.raises(EvidenceError):
        record_resolution(journal=j, receipt=obs, decided_at_ms=TS+1,
                          decision=d, allowed_strategy_ids=frozenset())
    assert read_evidence(j, run_id=RUN)[0]['resolution_state'] == 'skipped'


def test_s0_s1_s2_endpoint_reads_and_never_writes(tmp_path):
    j = journal(tmp_path)
    record_skipped_candidate(journal=j, run_id=RUN, symbol=SYMBOL,
       observed_at_ms=TS, candidate_index=0, reason='data_unavailable')
    j.append(Event('decision.a', 'brain', RUN, 'brain_decision', TS+2000, 'test',
        {'symbol': SYMBOL, 'kind':'NO_TRADE','status':'REJECTED', 'rationale':'ai_unavailable'}))
    before = hashlib.sha256(j.filename.read_bytes()).hexdigest()
    app=FastAPI()
    def session(): return 'ok'
    app.include_router(make_router(session, str(j.filename), RUN))
    with TestClient(app) as client:
        resp=client.get('/api/v3/brain/decision-timeline')
        assert resp.status_code == 200, resp.text
        assert resp.headers['cache-control'] == 'no-store'
        data=resp.json()
        assert data['state']=='ready' and len(data['decisions'])==2
        assert {x['kind'] for x in data['decisions']} == {'SKIPPED','NO_TRADE'}
        assert not any(x['net_bp'] for x in data['decisions'])
        for fn in (client.post,client.delete,client.put):
            assert fn('/api/v3/brain/decision-timeline').status_code == 405
        app.dependency_overrides[session] = lambda: (_ for _ in ()).throw(HTTPException(401))
        assert client.get('/api/v3/brain/decision-timeline').status_code==401
    assert hashlib.sha256(j.filename.read_bytes()).hexdigest() == before


def test_journal_tampering_is_not_silently_scored(tmp_path):
    j=journal(tmp_path)
    record_skipped_candidate(journal=j,run_id=RUN,symbol=SYMBOL,observed_at_ms=TS,
                             candidate_index=0,reason='feed_error')
    with sqlite3.connect(j.filename) as db:
        db.execute('DROP TRIGGER v3_no_update')
        db.execute("UPDATE v3_events SET payload_json='{}' WHERE kind='supervisor_observation'")
    with pytest.raises(EvidenceError,match='^journal_unavailable$'):
        read_evidence(j,run_id=RUN)


def test_s0_no_false_verification_without_close(tmp_path):
    j = journal(tmp_path)
    j.append(Event('a', 'brain', RUN, 'brain_decision', TS, 'test',
       {'symbol':SYMBOL,'kind':'OPEN','status':'APPROVED','rationale':'risk_quote_ok'}))
    s = read_brain_timeline(j,run_id=RUN,limit=5)
    assert s['decisions'][0]['execution']=='not_executed'
    assert s['decisions'][0]['realized_pnl'] is None


def test_isolation_by_run_and_portfolio(tmp_path):
    j=journal(tmp_path)
    record_skipped_candidate(journal=j,run_id='different',symbol=SYMBOL,
      observed_at_ms=TS,candidate_index=0,reason='view_error')
    assert read_evidence(j,run_id=RUN)==()
    assert read_brain_timeline(j,run_id=RUN,limit=5)['decisions']==[]


def test_verified_real_paper_open_close_reconstructs_net_pnl(tmp_path):
    from backend.v3.executor.paper import execute_paper
    from backend.v3.executor.paper_close import close_paper
    from backend.v3.brain_f2.contracts import OpenProposal
    from backend.v3.risk import RiskQuote
    from backend.v3.outcomes import extract_outcomes
    D = Decimal
    j=journal(tmp_path)
    j.append(Event('trade.dec', 'brain', RUN, 'brain_decision', TS, 'test',
       {'symbol':SYMBOL,'kind':'OPEN','status':'APPROVED','rationale':'risk_quote_ok',
        'regime':'TREND_UP','strategy_id':'S07','strategy_origin':'library'}))
    p=OpenProposal(symbol=SYMBOL,side=1,entry_price=D('100'),stop_price=D('98'),
                   leverage=2,rationale='risk_quote_ok',confidence=0.7,
                   originating_ai='deepseek',context_hash='a'*64,
                   strategy_id='S07',strategy_origin='library')
    d=BrainDecision(kind=DecisionKind.OPEN,proposal=p,status=ProposalStatus.APPROVED,
                    journal_event_id='trade.dec',risk_quote=RiskQuote(True,'ok',D('1'),D('100'),D('50')))
    receipt=execute_paper(d,portfolio_id='brain',run_id=RUN,journal=j,now_ms=TS+1000)
    close_paper(portfolio_id='brain',run_id=RUN,position_id=receipt.position_id,
        exit_price=D('105'),reason='brain_close',fee_bps=D('6'),journal=j,now_ms=TS+60000)
    expected=extract_outcomes(j,'brain',RUN).linked_outcomes[0]
    cards=read_brain_timeline(j,run_id=RUN,limit=10)
    assert cards['closed_verified']==1
    c=cards['decisions'][0]
    assert c['realized_pnl']==str(expected.realized_pnl)
    assert c['net_bp_after_costs']==str(expected.net_bp)
    assert c['execution']=='closed_verified'
    assert c['outcome_stats_eligible'] is True


def test_closed_candle_snapshot_and_verifiable_no_trade_link(tmp_path):
    from backend.v3.brain_market.params import load_default_params
    from backend.v3.features.indicators import Bar
    from backend.v3.supervisor.evidence import record_observation
    from decimal import Decimal as D
    j=journal(tmp_path)
    params=load_default_params()
    bars={}
    for spec in params.timeframes:
        count={'15m':3000,'1h':800,'4h':250}.get(spec.name,3000)
        end=(TS//spec.candle_ms)*spec.candle_ms
        series=[]
        for i in range(count):
            close=D('100')+D(i)*D('0.02')
            series.append(Bar(end-(count-i)*spec.candle_ms,close,close+D('.3'),close-D('.3'),close,D('1000')))
        bars[spec.name]=series
    receipt=record_observation(journal=j,run_id=RUN,symbol=SYMBOL,
       observed_at_ms=TS,candidate_index=0,bars_by_tf=bars,market_params=params,
       price=D('100'),open_position_count=0,equity=D('1000'),
       available_cash=D('1000'),margin_used=D('0'),existing_open_risk=D('0'))
    j.append(Event('ntrade', 'brain', RUN, 'brain_decision', TS+1000, 'test',
        {'kind':'NO_TRADE','status':'REJECTED','rationale':'deepseek:analysis','symbol':SYMBOL,
         'regime':'TREND_UP'}))
    decision=BrainDecision(kind=DecisionKind.NO_TRADE,proposal=None,
        status=ProposalStatus.REJECTED,rationale='deepseek:analysis',journal_event_id='ntrade')
    record_resolution(journal=j,receipt=receipt,decided_at_ms=TS+1000,
                      decision=decision,allowed_strategy_ids=frozenset())
    evidence=read_evidence(j,run_id=RUN)
    assert evidence[0]['market']['timeframes']
    assert evidence[0]['decision']['decision_event_id']=='ntrade'
    s2=project_timeline(read_brain_timeline(j,run_id=RUN,limit=50),evidence,run_id=RUN)
    assert s2['decisions'][0]['evidence_status']=='recorded'
    assert s2['decisions'][0]['evidence']['equity']=='1000'
    assert s2['decisions'][0]['kind']=='NO_TRADE'
    assert s2['decisions'][0]['net_bp'] is None
