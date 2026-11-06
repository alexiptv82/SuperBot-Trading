"""Paused-first V3 onboarding must never modify the legacy PAPER history."""
from __future__ import annotations
import json
from pathlib import Path
import shutil
import sqlite3

import pytest
from backend.v3.dashboard import build_summary
from backend.v3.events import EventJournal
from backend.v3.runner.config import default_config_path
from backend.v3.runner.exit_worker import check_existing_data
from backend.v3.runner.prepare_paper_run import (RunPreparationError,
    prepare_new_paper_run,main)

CFG=default_config_path().read_bytes()

def invoke(parent, *, name='brain-v3-rcsafe',run='rc-safe-001',cfg=CFG,
           desk='paper',ts=1794000000000):
    return prepare_new_paper_run(parent=parent,run_name=name,run_id=run,
                                config_bytes=cfg,desk_mode=desk,now_ms=ts)

def test_new_run_is_paused_unapproved_and_accepted_by_worker(tmp_path):
    p=invoke(tmp_path)
    assert (p/'pause.flag').exists()
    assert (p/'mandate.json').is_file()
    assert json.loads((p/'mandate.json').read_text())['approved'] is False
    assert (p/'budget.db').is_file()
    check_existing_data(data_dir=p,run_id='rc-safe-001')
    j=EventJournal(p/'journal.db');assert len(j.list_run('brain','rc-safe-001'))==1
    s=build_summary(j,'brain','rc-safe-001')
    assert len(s.open_positions)==len(s.closed_trades)==s.brain_steps==0
    assert json.loads((p/'PREPARED_PAUSED_ONLY.json').read_text())['initial_equity']=='1000'
    with sqlite3.connect(p/'budget.db') as db:
        assert db.execute('SELECT count(*) FROM spend_events').fetchone()[0]==0

def test_duplicate_creation_never_changes_existing_run(tmp_path):
    p=invoke(tmp_path)
    before=(p/'journal.db').read_bytes()
    with pytest.raises(RunPreparationError, match='run_already_exists'):
        invoke(tmp_path)
    assert (p/'journal.db').read_bytes()==before

def test_never_writes_to_historical_siblings(tmp_path):
    old=tmp_path/'hawk';old.mkdir(); f=old/'state_v2.json';f.write_text('IMMUTABLE')
    invoke(tmp_path)
    assert f.read_text()=='IMMUTABLE'
    assert not (old/'journal.db').exists()

def test_wrong_mode_or_bad_config_refuses_without_writing(tmp_path):
    with pytest.raises(RunPreparationError,match='paper_only'):
        invoke(tmp_path,desk='live')
    with pytest.raises(RunPreparationError,match='invalid_config'):
        invoke(tmp_path,cfg=b'{}')
    assert list(tmp_path.iterdir())==[]

def test_unsafe_leaf_name_symlink_and_bad_run_refused(tmp_path):
    for name in ('../hawk','brain-v3-','hawk','brain-v3-old/../brain-v3-new'):
        with pytest.raises(RunPreparationError): invoke(tmp_path,name=name)
    with pytest.raises(RunPreparationError): invoke(tmp_path,run='bad run')
    q=tmp_path/'existing';q.mkdir()
    (tmp_path/'brain-v3-link').symlink_to(q,target_is_directory=True)
    with pytest.raises(RunPreparationError): invoke(tmp_path,name='brain-v3-link')

def test_no_action_without_explicit_cli_flag(tmp_path):
    cfg=tmp_path/'config.json';cfg.write_bytes(CFG)
    code=main(['--parent',str(tmp_path),'--run-name','brain-v3-rcsafe','--run-id','rc-safe-001','--config',str(cfg)],env={'DESK_MODE':'paper'})
    assert code==2
    assert not (tmp_path/'brain-v3-rcsafe').exists()

def test_cli_needs_paper_and_then_prepares_paused(tmp_path):
    cfg=tmp_path/'config.json';cfg.write_bytes(CFG)
    args=['--parent',str(tmp_path),'--run-name','brain-v3-rcsafe','--run-id','rc-safe-001','--config',str(cfg),'--prepare-paper-paused']
    assert main(args,env={'DESK_MODE':'live'})==2
    assert not (tmp_path/'brain-v3-rcsafe').exists()
    assert main(args,env={'DESK_MODE':'paper'})==0
    assert (tmp_path/'brain-v3-rcsafe'/'pause.flag').exists()

def test_invalid_existing_dir_never_modified(tmp_path):
    p=tmp_path/'brain-v3-rcsafe';p.mkdir();(p/'KEEP').write_text('SAFE')
    with pytest.raises(RunPreparationError):invoke(tmp_path)
    assert (p/'KEEP').read_text()=='SAFE'

def test_parent_must_exist_and_be_absolute(tmp_path):
    with pytest.raises(RunPreparationError): invoke(tmp_path/'missing')
    with pytest.raises(RunPreparationError): invoke(Path('.'))
