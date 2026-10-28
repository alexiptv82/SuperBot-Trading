import importlib.util,json,sqlite3
from pathlib import Path
import pytest
from director.brain_free.store import Store
from director.brain_free.execution import apply
from director.brain_free.config import Config
spec=importlib.util.spec_from_file_location('cutover',Path(__file__).parents[2]/'deploy/scripts/brain_free_v2_cutover.py')
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
T=1800000000000

def setup(root):
    store=Store(root,True,'old',T-10000);s=store.load();s['build_sha']=mod.OLD;s['verified_start_ms']=T-10000
    c={'status':'normal','max_leverage':45,'qty_step':.001,'min_qty':.001,'min_notional':1,'price_step':.01}
    d={'symbol':'BTC','action':'open_long','margin':120,'leverage':12,'stop':97,'target':110,'reason':'AI: sample','invalidation':'below 97'}
    s,events=apply(s,d,{'BTC':{'ts_ms':T,'price':100}},{'BTC':c},T,Config());s['paused']=True
    store.commit(s,[('old-open','open',T,events[0])]);store.close();(root/'pause.flag').touch()
    return s

def test_authorized_close_keeps_history_charges_costs_and_migrates(tmp_path):
    root=tmp_path/'account';before=setup(root)
    mod.backup(root,tmp_path/'backup')
    after=mod.flatten(root,mod.OLD,{'BTC':{'ts_ms':T+1000,'price':101}},T+1000)
    assert not after['positions'] and after['cash']>before['cash']
    with sqlite3.connect(root/'brain.sqlite3') as db:
        rows=db.execute('select kind,body from events order by seq').fetchall()
    assert rows[0][0]=='open' and rows[-1][0]=='trade_closed'
    close=json.loads(rows[-1][1]);assert close['source']=='operator' and close['fees']>0
    assert close['net']==pytest.approx(close['gross']-close['fees']-close['funding'])
    from director.brain_free.reframe import migrate
    result=migrate(root,tmp_path/'migration',mod.OLD,mod.NEW,T+2000)
    assert result['cash']==after['cash'] and result['old_events_preserved']
    mod.preserved(tmp_path/'backup/brain.sqlite3',root/'brain.sqlite3')

def test_stale_quote_or_running_writer_never_discards_position(tmp_path):
    root=tmp_path/'account';setup(root)
    with pytest.raises(AssertionError,match='fresh_quote_required'):
        mod.flatten(root,mod.OLD,{'BTC':{'ts_ms':T-31000,'price':101}},T)
    assert mod.read_state(root/'brain.sqlite3')['positions']
    with sqlite3.connect(root/'brain.sqlite3') as db:assert db.execute('select count(*) from events').fetchone()[0]==1
    writer=Store(root)
    try:
        with pytest.raises(ValueError,match='writer_already_active'):mod.flatten(root,mod.OLD,{},T)
    finally:writer.close()
