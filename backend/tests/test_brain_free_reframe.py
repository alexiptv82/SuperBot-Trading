"""V1->V2 controlled single-account migration: preservation, refusal and report isolation."""
import json,sqlite3
from pathlib import Path
import pytest
from director.brain_free.store import Store
from director.brain_free.reframe import migrate
from director.brain_free.runtime import Runtime
from director.brain_free import reports

OLD_SHA='a'*40
NEW_SHA='b'*40
T=1800000000000


def prepared(tmp_path,with_position=False):
    root=tmp_path/'v1';st=Store(root,True,'old-hash',T-900000)
    s=st.load()
    s['build_sha']=OLD_SHA
    s['verified_start_ms']=T-900000
    s['paused']=True
    s['cash']=1905.5
    if with_position:
        s['positions']={'BTC':{'symbol':'BTC','side':1,'margin':100.0}}
    st.commit(s,[('legacy-open','open',T-800000,{'kind':'open','fee_paid':2,'symbol':'ETH'}),
                 ('legacy-close','trade_closed',T-700000,{'kind':'trade_closed','net':-4,
                  'fees':1,'fee_paid':1,'gross':-3,'funding':0,'duration_minutes':4,'side':1})])
    st.record_request('legacy-request',T-800000,{'kind':'full'})
    st.finish_request('legacy-request','complete',{'billing':{'cost':.01}})
    st.enqueue('legacy-telegram','[BRAIN] historical')
    st.close()
    (root/'pause.flag').write_text('1')
    return root


def test_guarded_reframe_preserves_v1_events_memory_and_real_paper_cash(tmp_path,monkeypatch):
    root=prepared(tmp_path)
    out=migrate(root,tmp_path/'backup',OLD_SHA,NEW_SHA,T)
    assert out['status']=='migrated_paused' and out['cash']==1905.5
    assert (tmp_path/'backup'/'brain-before-v2.sqlite3').is_file()
    with sqlite3.connect(tmp_path/'backup'/'brain-before-v2.sqlite3') as backup:
        before=json.loads(backup.execute('SELECT body FROM state WHERE id=1').fetchone()[0])
        assert before['cash']==1905.5 and before['build_sha']==OLD_SHA
        assert backup.execute('SELECT COUNT(*) FROM events').fetchone()[0]==2
    monkeypatch.setenv('BRAIN_FREE_CODE_SHA',NEW_SHA)
    r=Runtime(root,api_key='synthetic')
    st=r.store.load()
    assert st['paused'] and st['cash']==1905.5
    assert st['build_sha']==NEW_SHA and st['previous_run_id']==before['experiment_id']
    assert st['positions']=={} and st['verified_start_ms']==T
    assert r.store.db.execute('SELECT COUNT(*) FROM requests').fetchone()[0]==1
    assert r.store.db.execute('SELECT COUNT(*) FROM events').fetchone()[0]==3
    assert r.store.db.execute('SELECT COUNT(*) FROM outbox').fetchone()[0]==2
    assert r.store.recent()[0]['net']==-4  # V1 remains useful to V2 memory
    # V1 PnL never contaminates V2's 168-hour measurement.
    report=reports.build(r.store,st,T+1000)
    assert report['closed']==0 and report['realized_net']==0 and report['fees']==0
    assert report['slot_occupancy']==0
    r.close()


def test_migration_refuses_existing_open_trade(tmp_path):
    root=prepared(tmp_path,True)
    with pytest.raises(ValueError,match='positions_must_close'):
        migrate(root,tmp_path/'backup',OLD_SHA,NEW_SHA,T)
    assert not (tmp_path/'backup').exists()
    with sqlite3.connect(root/'brain.sqlite3') as db:
        assert json.loads(db.execute('SELECT body FROM state WHERE id=1').fetchone()[0])['build_sha']==OLD_SHA


def test_migration_refuses_unpaused_or_running_writer(tmp_path):
    root=prepared(tmp_path)
    (root/'pause.flag').unlink()
    with pytest.raises(ValueError,match='paused_flag_required'):
        migrate(root,tmp_path/'backup',OLD_SHA,NEW_SHA,T)
    (root/'pause.flag').write_text('1')
    writer=Store(root,False,'old-hash')
    try:
        with pytest.raises(ValueError,match='running_writer_must_stop_first'):
            migrate(root,tmp_path/'backup',OLD_SHA,NEW_SHA,T)
    finally:writer.close()
    assert not (tmp_path/'backup').exists()


def test_migration_is_not_idempotent_and_never_reinitializes_database(tmp_path):
    root=prepared(tmp_path)
    migrate(root,tmp_path/'backup',OLD_SHA,NEW_SHA,T)
    with pytest.raises(ValueError,match='unexpected_old_build|already_reframed'):
        migrate(root,tmp_path/'another_backup',OLD_SHA,NEW_SHA,T+1000)
    assert not (tmp_path/'another_backup').exists()
