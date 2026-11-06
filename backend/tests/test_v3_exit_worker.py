"""Exit-worker deployment boundary: no networking/LLM, all PAPER data synthetic."""
from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import time
from decimal import Decimal

import pytest

from backend.v3.events import Event, EventJournal
from backend.v3.runner.config import load_default_config
from backend.v3.runner.exit_service import exit_service_healthy
from backend.v3.runner.exit_worker import (
    ExitWorkerConfigurationError, check_existing_data, build_exit_worker, serve, main)

RUN='brain-test-worker'
NOW=1_800_001_200_000


def _existing(tmp_path, *, with_event=True):
    j=EventJournal(tmp_path/'journal.db');j.init_schema()
    if with_event:
        j.append(Event('checkpoint','brain',RUN,'heartbeat',NOW-60000,'test',{}))
    return j


def test_no_journal_never_creates_one(tmp_path):
    with pytest.raises(ExitWorkerConfigurationError,match='journal_validation_failed'):
        check_existing_data(data_dir=tmp_path,run_id=RUN)
    assert not (tmp_path/'journal.db').exists()


def test_no_directory_never_creates_it(tmp_path):
    p=tmp_path/'missing'
    with pytest.raises(ExitWorkerConfigurationError,match='invalid_exit_scope'):
        check_existing_data(data_dir=p,run_id=RUN)
    assert not p.exists()


def test_run_typo_failclosed(tmp_path):
    _existing(tmp_path)
    with pytest.raises(ExitWorkerConfigurationError,match='run_not_found'):
        check_existing_data(data_dir=tmp_path,run_id='typo')


def test_readonly_preflight_existing_does_not_mutate(tmp_path):
    _existing(tmp_path)
    path=tmp_path/'journal.db'; before=path.read_bytes()
    assert check_existing_data(data_dir=tmp_path,run_id=RUN).verify_chain()[0]==1
    assert path.read_bytes()==before


def test_empty_run_requires_explicit_dev_override(tmp_path):
    _existing(tmp_path,with_event=False)
    with pytest.raises(ExitWorkerConfigurationError,match='run_not_found'):
        check_existing_data(data_dir=tmp_path,run_id=RUN)
    assert check_existing_data(data_dir=tmp_path,run_id=RUN,require_existing_run=False).verify_chain()[0]==0


@pytest.mark.parametrize('bad',[True,'../x','',None,'\n','x'*65])
def test_invalid_run_scope(tmp_path,bad):
    _existing(tmp_path)
    with pytest.raises(ExitWorkerConfigurationError,match='invalid_exit_scope'):
        check_existing_data(data_dir=tmp_path,run_id=bad)


def test_symlink_journal_and_directory_failclosed(tmp_path):
    p=tmp_path/'real';p.mkdir();_existing(p)
    link=tmp_path/'link';link.symlink_to(p,target_is_directory=True)
    with pytest.raises(ExitWorkerConfigurationError,match='invalid_exit_scope'):
        check_existing_data(data_dir=link,run_id=RUN)
    d=tmp_path/'victim';d.mkdir(); db=d/'journal.db';db.symlink_to(p/'journal.db')
    with pytest.raises(ExitWorkerConfigurationError,match='journal_not_regular'):
        check_existing_data(data_dir=d,run_id=RUN)


def test_existing_wrong_schema_not_initialised(tmp_path):
    path=tmp_path/'journal.db'
    with sqlite3.connect(path) as db:db.execute('create table innocuous(id integer)')
    before=path.read_bytes()
    with pytest.raises(ExitWorkerConfigurationError,match='journal_schema_missing'):
        check_existing_data(data_dir=tmp_path,run_id=RUN)
    assert path.read_bytes()==before


def test_wrong_run_same_journal_not_accepted(tmp_path):
    j=EventJournal(tmp_path/'journal.db');j.init_schema()
    j.append(Event('other','hawk',RUN,'heartbeat',NOW-60_000,'test',{}))
    with pytest.raises(ExitWorkerConfigurationError,match='run_not_found'):
        check_existing_data(data_dir=tmp_path,run_id=RUN)


def test_main_no_paper_no_start_or_files(tmp_path, capsys):
    d=tmp_path/'missing'
    args=['--data-dir',str(d),'--run-id',RUN,'--validate-only']
    assert main(args,env={})==2
    assert not d.exists()
    assert 'paper_mode_required' in capsys.readouterr().err


def test_main_validate_existing_no_sidecar_lock(tmp_path,capsys):
    _existing(tmp_path)
    args=['--data-dir',str(tmp_path),'--run-id',RUN,'--validate-only']
    assert main(args,env={'DESK_MODE':'paper'})==0
    assert 'validated_existing_brain_run' in capsys.readouterr().out
    assert not list(tmp_path.glob('.exit_service*'))


def test_start_paper_optin_with_injected_no_network_data(tmp_path):
    _existing(tmp_path)
    config=load_default_config()
    svc=build_exit_worker(data_dir=tmp_path,run_id=RUN,config=config,get_json=lambda url: [])
    stamps=iter([NOW,NOW+5000,NOW+10000]); seen=[]
    def stop():return len(seen)>=2
    def sleep(_):seen.append('slept')
    notify=[]
    serve(service=svc,clock=lambda:next(stamps),sleep=sleep,stop=stop,notify=lambda m:notify.append(m) or True)
    assert notify==['READY=1','WATCHDOG=1','WATCHDOG=1','STOPPING=1']
    assert not exit_service_healthy(data_dir=tmp_path,run_id=RUN,now_ms=NOW+10000)


def test_degraded_tick_does_not_send_readiness_or_watchdog(tmp_path):
    from backend.v3.runner.exit_service import ExitService
    svc=ExitService(run_id=RUN,data_dir=tmp_path,run_commands=lambda _:None,run_monitor=lambda _: (_ for _ in ()).throw(RuntimeError('err')))
    signal=[]
    done=[]
    serve(service=svc,clock=lambda:NOW,sleep=lambda _:done.append(1),stop=lambda:bool(done),notify=lambda x:signal.append(x) or True)
    assert signal == []


def test_no_callbacks_to_exchange_when_run_validation_fails(tmp_path):
    calls=[]
    cfg=load_default_config()
    with pytest.raises(ExitWorkerConfigurationError,match='journal_validation_failed'):
        build_exit_worker(data_dir=tmp_path,run_id=RUN,config=cfg,get_json=lambda url:calls.append(url))
    assert calls==[]


def test_main_explicit_start_required(tmp_path):
    _existing(tmp_path)
    import subprocess,sys
    p=subprocess.run([sys.executable,'-m','backend.v3.runner.exit_worker','--data-dir',str(tmp_path),'--run-id',RUN],cwd=Path(__file__).parents[3],capture_output=True,text=True,timeout=5,env={**os.environ,'DESK_MODE':'paper'})
    assert p.returncode !=0 and not (tmp_path/'.exit_service.lock').exists()


def test_cli_rejects_sidecar_start_without_explicit_handover(tmp_path,capsys):
    _existing(tmp_path)
    args=['--data-dir',str(tmp_path),'--run-id',RUN,'--start-paper']
    assert main(args,env={'DESK_MODE':'paper'})==2
    assert 'handover_required' in capsys.readouterr().err
    assert not (tmp_path/'.exit_service.lock').exists()


def test_cli_explicit_start_handles_synthetic_one_tick(tmp_path):
    _existing(tmp_path)
    stopped=[];sent=[]
    def sleep(_):stopped.append(1)
    assert main(['--data-dir',str(tmp_path),'--run-id',RUN,'--start-paper',
                 '--legacy-exits-disabled'],env={'DESK_MODE':'paper'},
                 get_json=lambda _: [],clock=lambda:NOW,sleep=sleep,
                 should_stop=lambda:len(stopped)>0,notify=lambda msg:sent.append(msg) or True)==0
    assert 'READY=1' in sent and 'STOPPING=1' in sent
    assert not exit_service_healthy(data_dir=tmp_path,run_id=RUN,now_ms=NOW)


def test_systemd_notify_abstract_socket_no_external_network(tmp_path,monkeypatch):
    import socket
    from backend.v3.runner.exit_worker import systemd_notify
    sock=socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM)
    name='\0sbexit_test_'+str(os.getpid())
    try:
        sock.bind(name)
        sock.settimeout(1.0)
        monkeypatch.setenv('NOTIFY_SOCKET','@'+name[1:])
        assert systemd_notify('READY=1') is True
        assert sock.recv(100)==b'READY=1'
        assert systemd_notify('leak_environment') is False
    finally:
        sock.close()


def test_preflight_rejects_tampered_chain_without_sidecar_files(tmp_path):
    _existing(tmp_path)
    with sqlite3.connect(tmp_path/'journal.db') as db:
        db.execute('DROP TRIGGER v3_no_update')
        db.execute("UPDATE v3_events SET payload_json='{} ' WHERE event_id='checkpoint'")
    with pytest.raises(ExitWorkerConfigurationError,match='journal_validation_failed'):
        check_existing_data(data_dir=tmp_path,run_id=RUN)
    assert not (tmp_path/'.exit_service.lock').exists()
    assert not (tmp_path/'exit_heartbeat.json').exists()
