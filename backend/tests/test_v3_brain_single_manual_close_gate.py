"""Brain individual PAPER exits: isolated sidecar owner, not AI heartbeat.

Synthetic test data only. Never reads or changes VPS PAPER positions.
"""
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
import json
import time

from fastapi.testclient import TestClient

from backend.tests.test_v3_dashboard_unified import _app, _journal_sample, _paths, RUN
from backend.v3.events import EventJournal
from backend.v3.dashboard import build_summary
from backend.v3.outcomes import extract_outcomes
from backend.v3.runner.exit_service import ExitService
from backend.v3.runner.manual_close import run_manual_close
from backend.v3.runner.monitor import MonitorReport
from backend.v3_api import _brain_single_close_ready

def _configure(tmp_path, monkeypatch):
    paths=_paths(tmp_path)
    cfg=tmp_path/'runner_config.json'
    cfg.write_text('{"paper":true}')
    paths=replace(paths,brain_config_path=str(cfg))
    (tmp_path/'pause.flag').write_text('paused')
    for key,val in (
        ('V3_CUTOVER_READONLY','1'),('V3_ALLOW_BRAIN_SINGLE_CLOSE','1'),
        ('TRADING_MODE','paper'),('DESK_MODE','paper')
    ):
        monkeypatch.setenv(key,val)
    return paths


def _sidecar(paths, tmp_path):
    journal=EventJournal(paths.journal_path)
    return ExitService(
        run_id=RUN, data_dir=tmp_path,
        run_commands=lambda t: run_manual_close(
            journal=journal,portfolio_id='brain',run_id=RUN,data_dir=tmp_path,
            price_of=lambda s,t:Decimal('102'),fee_bps=Decimal('6'),now_ms=t),
        run_monitor=lambda _:MonitorReport(0,(),())
    )


def test_pause_ai_with_live_exit_owner_can_close_one_brain_trade_without_starting_ai(tmp_path,monkeypatch):
    paths=_configure(tmp_path,monkeypatch)
    pid=_journal_sample(paths,close=False)
    now=int(time.time()*1000)
    assert _brain_single_close_ready(paths,now) is False
    app,_=_app(paths)
    with TestClient(app) as client:
        assert client.get('/api/v3/overview').json()['brain_single_close_allowed'] is False
        with _sidecar(paths,tmp_path) as exit_owner:
            assert exit_owner.tick(now).state=='healthy'
            assert _brain_single_close_ready(paths,now) is True
            overview=client.get('/api/v3/overview').json()
            assert overview['brain_single_close_allowed'] is True
            assert overview['portfolios'][2]['manual_close_allowed'] is True
            # This is the same confirmation payload as the mobile button.
            resp=client.post('/api/v3/brain/close',json={'position_id':pid})
            assert resp.status_code==200,resp.text
            assert client.post('/api/v3/brain/close',json={'position_id':pid}).status_code==409
            assert client.post('/api/v3/brain/close',json={'all':True}).status_code==423
            assert exit_owner.tick(now+3000).state=='healthy'
            result=client.get('/api/v3/brain/close-result').json()
            assert result['pending'] is False and result['result']['closed']==[pid]
            assert client.get('/api/v3/brain/trades').json()['open_positions']==[]
    journal=EventJournal(paths.journal_path)
    summary=build_summary(journal,'brain',RUN)
    assert not summary.open_positions
    outcomes=extract_outcomes(journal,'brain',RUN).outcomes
    assert len(outcomes)==1 and outcomes[0].exit_reason=='manual'
    assert len([e for e in journal.list_run('brain',RUN) if e.event.kind=='paper_close'])==1


def test_stale_ai_heartbeat_cannot_substitute_for_missing_sidecar(tmp_path,monkeypatch):
    paths=_configure(tmp_path,monkeypatch)
    pid=_journal_sample(paths,close=False)
    (tmp_path/'heartbeat.json').write_text(json.dumps({
        'ts_ms':int(time.time()*1000),'run_id':RUN,'cycle':1,
        'state':'paused','last_error':None
    }))
    with TestClient(_app(paths)[0]) as client:
        assert client.get('/api/v3/overview').json()['brain_single_close_allowed'] is False
        result=client.post('/api/v3/brain/close',json={'position_id':pid})
        assert result.status_code==409
        assert result.json()['detail']['code']=='servizio_uscita_non_pronto'
    assert not (tmp_path/'close_request.json').exists()


def test_malformed_owner_and_wrong_ipc_path_do_not_unlock_brain(tmp_path,monkeypatch):
    paths=_configure(tmp_path,monkeypatch)
    _journal_sample(paths,close=False)
    with _sidecar(paths,tmp_path) as exit_owner:
        now=int(time.time()*1000)
        exit_owner.tick(now)
        assert _brain_single_close_ready(paths,now)
        for change in (
            {'run_id':'other-run'},
            {'close_request_path':str(tmp_path/'manual_close_request.json')},
            {'close_result_path':str(tmp_path/'manual_close_result.json')},
            {'journal_path':str(tmp_path/'other_journal.db')},
        ):
            assert not _brain_single_close_ready(replace(paths,**change),now)
    assert not _brain_single_close_ready(paths,now) # heartbeat file without lease is insufficient


def test_explicit_paper_flag_requires_every_condition_even_with_owner(tmp_path,monkeypatch):
    paths=_configure(tmp_path,monkeypatch)
    _journal_sample(paths,close=False)
    with _sidecar(paths,tmp_path) as exit_owner:
        now=int(time.time()*1000)
        exit_owner.tick(now)
        assert _brain_single_close_ready(paths,now)
        for key,value in (
            ('V3_ALLOW_BRAIN_SINGLE_CLOSE','0'),
            ('V3_CUTOVER_READONLY','0'),
            ('TRADING_MODE','live'),('DESK_MODE','live'),
        ):
            with monkeypatch.context() as patch:
                patch.setenv(key,value)
                assert not _brain_single_close_ready(paths,now)
