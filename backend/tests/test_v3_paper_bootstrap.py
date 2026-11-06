"""One-time creation of an isolated, paused PAPER run (no live trades)."""
import json
import os
from pathlib import Path
import pytest

from backend.v3.runner.bootstrap_paper import BootstrapRefused,initialize_new_paper_run,main
from backend.v3.runner.config import default_config_path,load_default_config
from backend.v3.runner.exit_worker import check_existing_data
from backend.v3.dashboard import build_summary

RUN='brain-v3-fresh-20261106'
CFG=default_config_path().read_bytes()
STAMP=1794000000000


def make(path, **k):
    return initialize_new_paper_run(data_dir=path,run_id=RUN,config_bytes=CFG,
                                    desk_mode='paper',confirmed=True,expected_initial_equity='1000',now_ms=STAMP,**k)


def test_new_run_paused_unsigned_and_no_trade(tmp_path):
    new=tmp_path/'run-001'
    rec=make(new)
    assert rec['status']=='PAUSED_UNAPPROVED'
    assert rec['initial_equity_usdt']==str(load_default_config().initial_equity)
    assert new.stat().st_mode & 0o777 == 0o700
    assert (new/'pause.flag').is_file()
    assert json.loads((new/'mandate.json').read_text())['approved'] is False
    assert (new/'budget.db').is_file()
    assert (new/'bootstrap_receipt.json').is_file()
    assert not (new/'.bootstrap-incomplete').exists()
    assert not (new/'heartbeat.json').exists()
    assert not (new/'exit_heartbeat.json').exists()
    j=check_existing_data(data_dir=new,run_id=RUN)
    assert j.verify_chain()==(1,rec['journal_head'])
    assert not build_summary(j,'brain',RUN).open_positions
    assert [x.event.kind for x in j.list_run('brain',RUN)]==['paper_run_initialized']


@pytest.mark.parametrize('desk_mode,confirmed', [('live',True),('paper',False),('',True)])
def test_no_explicit_permission_no_writes(tmp_path,desk_mode,confirmed):
    p=tmp_path/'new'
    with pytest.raises(BootstrapRefused):
        initialize_new_paper_run(data_dir=p,run_id=RUN,config_bytes=CFG,desk_mode=desk_mode,confirmed=confirmed,expected_initial_equity='1000')
    assert not p.exists()


def test_previous_dir_preserved_byte_identical(tmp_path):
    p=tmp_path/'prior-run';p.mkdir()
    old=p/'journal.db';old.write_bytes(b'legacy history do not touch')
    with pytest.raises(BootstrapRefused,match='destination_must_be_new'):
        make(p)
    assert old.read_bytes()==b'legacy history do not touch'


def test_replay_rejected_before_any_write(tmp_path):
    p=tmp_path/'run'
    make(p)
    before={x.name:x.read_bytes() for x in p.iterdir() if x.is_file()}
    with pytest.raises(BootstrapRefused,match='destination_must_be_new'):
        make(p)
    assert before=={x.name:x.read_bytes() for x in p.iterdir() if x.is_file()}


def test_symlink_dir_rejected(tmp_path):
    p=tmp_path/'x';p.mkdir()
    link=tmp_path/'l';link.symlink_to(p,target_is_directory=True)
    with pytest.raises(BootstrapRefused):make(link)
    assert not list(p.iterdir())


def test_invalid_config_and_run_do_not_create_files(tmp_path):
    for run,config in [('bad/run',CFG),(RUN,b'invalid')]:
        p=tmp_path/'run'
        with pytest.raises(BootstrapRefused):
            initialize_new_paper_run(data_dir=p,run_id=run,config_bytes=config,
                                     desk_mode='paper',confirmed=True,expected_initial_equity='1000',now_ms=STAMP)
        assert not p.exists()


def test_cli_default_does_not_start_or_create(tmp_path,capsys):
    p=tmp_path/'new'
    rc=main(['--data-dir',str(p),'--run-id',RUN,'--expected-initial-equity','1000'],env={'DESK_MODE':'paper'})
    assert rc==2 and not p.exists()
    assert 'explicit_bootstrap_confirmation_required' in capsys.readouterr().err


def test_cli_explicit_new_run_and_paused(tmp_path,capsys):
    p=tmp_path/'new'
    rc=main(['--data-dir',str(p),'--run-id',RUN,'--create-paper','--expected-initial-equity','1000'],env={'DESK_MODE':'paper'})
    assert rc==0
    assert json.loads(capsys.readouterr().out)['status']=='PAUSED_UNAPPROVED'
    assert (p/'pause.flag').exists()


def test_refuse_world_writable_nonsticky_parent(tmp_path):
    p=tmp_path/'parent';p.mkdir();p.chmod(0o777)
    with pytest.raises(BootstrapRefused,match='unsafe_parent_directory'):make(p/'new')
    assert not (p/'new').exists()


def test_invalid_timestamp(tmp_path):
    with pytest.raises(BootstrapRefused,match='invalid_bootstrap_time'):
        initialize_new_paper_run(data_dir=tmp_path/'new',run_id=RUN,config_bytes=CFG,desk_mode='paper',confirmed=True,expected_initial_equity='1000',now_ms=0)
    assert not (tmp_path/'new').exists()


def test_mismatched_capital_is_refused_before_mkdir(tmp_path):
    p=tmp_path/'new'
    with pytest.raises(BootstrapRefused,match='capital_confirmation_mismatch'):
        initialize_new_paper_run(data_dir=p,run_id=RUN,config_bytes=CFG,desk_mode='paper',confirmed=True,expected_initial_equity='2000',now_ms=STAMP)
    assert not p.exists()