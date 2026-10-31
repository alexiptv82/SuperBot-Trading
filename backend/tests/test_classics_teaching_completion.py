"""Real saved classical receipts -> sidecar confirmation -> causal preferences."""
import json
import os
from unittest.mock import patch
import pytest
from desk import cli
from desk.manual_teaching_service import queue_close,poll,preferences
from director.manual_teaching import ManualLessons
from director.scoped_confirmations import ScopedConfirmations
from backend.tests.test_classics_manual_teaching import rec

NOW=1800000061000

def setup(root,portfolio='hawk'):
    row=dict(rec(),account=portfolio,closed_by='utente')
    state={'run_no':8,'main':{'positions':{}},'cash_marker':1234}
    queue_close(state,row,portfolio)
    path=root/'state.json';path.write_text(json.dumps(state))
    return state,path

def test_unsaved_close_is_not_attested_and_recovery_is_idempotent(tmp_path):
    state,path=setup(tmp_path)
    disk=dict(state,manual_teaching_outbox=[])
    path.write_text(json.dumps(disk))
    poll(tmp_path,'hawk',path,state,NOW)
    assert ManualLessons(tmp_path).pending()==[]
    path.write_text(json.dumps(state));before=path.read_bytes()
    first=poll(tmp_path,'hawk',path,state,NOW)
    assert first['status']=='ready' and first['preferences']==[]
    poll(tmp_path,'hawk',path,state,NOW+1)
    assert len(ManualLessons(tmp_path).pending())==1
    assert len((tmp_path/'manual_close_reviews.jsonl').read_text().splitlines())==1
    assert path.read_bytes()==before
    assert state['manual_teaching_outbox']==[]

@pytest.mark.parametrize('portfolio',['hawk','bull'])
@pytest.mark.parametrize('choice',['yes','no'])
def test_owner_confirmation_and_preferences_with_separate_financial_file(tmp_path,portfolio,choice):
    state,path=setup(tmp_path,portfolio)
    (tmp_path/'lessons.md').write_text('OLD MEMORY\n')
    (tmp_path/'learning_log.jsonl').write_text('{"ev":"old"}\n')
    poll(tmp_path,portfolio,path,state,NOW)
    data=json.loads((tmp_path/'manual_operator_reviews.json').read_text())
    q=ScopedConfirmations(tmp_path/'manual.confirmations.sqlite3')
    q.submit('a'*32,data['account_id'],data['groups'][0]['group_id'],choice,NOW)
    before=path.read_bytes()
    result=poll(tmp_path,portfolio,path,state,NOW+1000)
    assert result['confirmations']==[{'request_id':'a'*32,'status':'confirmed'}]
    assert len(result['preferences'])==(1 if choice=='yes' else 0)
    assert preferences(tmp_path,portfolio,data['account_id'],NOW)==[]
    assert preferences(tmp_path,'bull' if portfolio=='hawk' else 'hawk',data['account_id'],NOW+1000)==[]
    assert path.read_bytes()==before
    assert (tmp_path/'lessons.md').read_text().startswith('OLD MEMORY\n')
    assert (tmp_path/'learning_log.jsonl').read_text().startswith('{"ev":"old"}\n')
    assert poll(tmp_path,portfolio,path,state,NOW+2000)['confirmations']==[]
    q.close()

def test_failure_after_financial_save_replays_without_closing_again(tmp_path):
    state,path=setup(tmp_path);original=path.read_bytes()
    with patch.object(ManualLessons,'register',side_effect=OSError('offline')):
        with pytest.raises(OSError):poll(tmp_path,'hawk',path,state,NOW)
    assert path.read_bytes()==original
    assert len(state['manual_teaching_outbox'])==1
    assert poll(tmp_path,'hawk',path,state,NOW+1)['status']=='ready'
    assert len(ManualLessons(tmp_path).pending())==1

def test_different_run_rejects_old_confirmation_without_resolving(tmp_path):
    state,path=setup(tmp_path);poll(tmp_path,'hawk',path,state,NOW)
    data=json.loads((tmp_path/'manual_operator_reviews.json').read_text())
    q=ScopedConfirmations(tmp_path/'manual.confirmations.sqlite3')
    q.submit('a'*32,data['account_id'],data['groups'][0]['group_id'],'yes',NOW)
    state['run_no']=9;path.write_text(json.dumps(state))
    assert poll(tmp_path,'hawk',path,state,NOW+1)['confirmations'][0]['status']=='rejected_account'
    assert len(ManualLessons(tmp_path).pending())==1
    q.close()

def test_interrupted_confirmation_never_replays(tmp_path):
    q=ScopedConfirmations(tmp_path/'manual.confirmations.sqlite3')
    q.submit('a'*32,'desk-hawk-paper-run-8','b'*16,'yes',NOW)
    calls=[]
    def uncertain(text,at):
        calls.append(text);raise OSError('uncertain')
    assert q.consume('desk-hawk-paper-run-8',uncertain,NOW)[0]['status']=='needs_reconciliation'
    assert q.consume('desk-hawk-paper-run-8',uncertain,NOW+1)==[]
    assert len(calls)==1
    q.close()

def test_real_manual_close_survives_broken_teaching_then_recovers(tmp_path):
    from backend.tests.test_desk import _sandbox,_state_with_two_positions,_frozen_clock,NOW as START
    with _sandbox() as (folder,calls):
        state=_state_with_two_positions()
        cli.fetch_candles=lambda *a,**k:[[START,101,103,100,102.,1.]]
        from pathlib import Path
        root=Path(folder)
        (root/'close_position.flag').write_text(json.dumps({'symbols':['BTC'],'ts':START+1000}))
        with _frozen_clock(START+1000),patch.object(ManualLessons,'register',side_effect=OSError('offline')):
            assert cli._check_close_position_flag(state)
        before=Path(cli.STATE_FILE).read_bytes()
        assert 'BTC' not in cli.make_account(state).positions
        assert json.loads(before)['manual_teaching_outbox']
        poll(root,cli.PORTFOLIO.name,cli.STATE_FILE,state,START+2000)
        assert len(ManualLessons(root).pending())==1
        assert Path(cli.STATE_FILE).read_bytes()==before

def test_bad_teaching_evidence_does_not_block_a_financial_close():
    from backend.tests.test_desk import _sandbox,_state_with_two_positions,_frozen_clock,NOW as START
    from pathlib import Path
    with _sandbox() as (folder,calls):
        state=_state_with_two_positions()
        cli.fetch_candles=lambda *a,**k:[[START,101,103,100,102.,1.]]
        (Path(folder)/'close_position.flag').write_text(json.dumps({'symbols':['BTC'],'ts':START+1000}))
        with _frozen_clock(START+1000),patch('desk.manual_teaching_service.queue_close',side_effect=ValueError('invalid evidence')):
            assert cli._check_close_position_flag(state)
        assert 'BTC' not in cli.make_account(state).positions

def test_confirmed_examples_reach_optional_ai_context_without_rule_changes():
    from backend.tests.test_desk import _sandbox,_frozen_clock,_cut_stub,NOW as START
    seen=[];inner=_cut_stub()
    def capture(system,user,*args,**kwargs):
        seen.append(user);return inner(system,user,*args,**kwargs)
    with _sandbox(capture),_frozen_clock(START),patch.dict(os.environ,{'DESK_MANUAL_TEACHING':'on'}):
        state={'manual_operator_preferences':[{'event_id':'OBSERVATION_MARKER','training_applied':False}]}
        cli.run_cycle(state,START)
    assert seen and 'OBSERVATION_MARKER' in seen[0]
    assert 'non regole o TP obbligatori' in seen[0]

