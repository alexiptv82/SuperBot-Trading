"""Offline behavioural contracts for the approved AI-only PAPER experiment."""
import json,sqlite3,time
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import pytest
from director.brain_free.config import Config
from director.brain_free.execution import initial,apply,protect,margin,equity,fingerprint,fresh
from director.brain_free.store import Store
from director.brain_free.runtime import Runtime
from director.brain_free.spend import price,view
from director.brain_free.prompt_builder import build
from director.brain_free.provider import validate,call
from director.brain_free.notifications import event_text
from director.brain_free import reports

NOW=1800000000000
CFG=Config()
def contract():return {'status':'normal','max_leverage':50,'qty_step':.001,'price_step':.01,'min_qty':.001,'min_notional':1.,'maintenance':.005}
def quote(px=100,ts=NOW):return {'price':px,'mark':px,'ts_ms':ts}
def account():
    s=initial(NOW,'hash');s['_version']=0;s['verified_start_ms']=NOW;return s
def decision(action='open_long',**kw):
    return {'symbol':'BTC','action':action,'margin':200,'leverage':5,'stop':95 if action!='open_short' else 105,
            'target':110 if action!='open_short' else 90,'reason':'synthetic evidence','invalidation':'synthetic level fails',**kw}
def execute(s,d,q=None,now=NOW):return apply(s,d,q or {'BTC':quote(ts=now)},{x:contract() for x in CFG.symbols},now)
def market(now=NOW,px=100):
    start=now//60000*60000
    return {'BTC':{'quote':quote(px,now),'bars':{'1m':[[start-i*60000,100,101,99,100,1] for i in (3,2,1,0)]},'summary':{}}}

@pytest.mark.parametrize('action,exit_price',[('open_long',110),('open_short',90)])
def test_net_accounting_with_slippage_and_fees(action,exit_price):
    s,opened=execute(account(),decision(action))
    assert s['cash']+margin(s)<2000
    s,closed=execute(s,decision('close'),{'BTC':quote(exit_price,NOW+1000)},NOW+1000)
    t=closed[0]
    assert s['positions']=={}
    assert s['cash']==pytest.approx(2000+t['net'])
    assert t['gross']-t['fees']-t['funding']==pytest.approx(t['net'])


def test_partial_then_final_is_one_completed_trade_with_full_net():
    s,_=execute(account(),decision())
    s,partial=execute(s,decision('partial_close',fraction=.4),{'BTC':quote(103,NOW+1000)},NOW+1000)
    s,final=execute(s,decision('close'),{'BTC':quote(104,NOW+2000)},NOW+2000)
    assert partial[0]['kind']=='partial_trade' and final[0]['kind']=='trade_closed'
    assert s['cash']==pytest.approx(2000+final[0]['net'])


def test_no_rr_score_atr_regime_or_small_margin_gate():
    s,events=execute(account(),decision(margin=500,leverage=2,stop=90,target=100.1,confidence=0))
    assert events[0]['margin']>499 and margin(s)>100
    assert events[0]['kind']=='open'


def test_stop_feasibility_reduces_leverage_not_stop():
    s,events=execute(account(),decision(leverage=45,stop=90,margin=200))
    assert s['positions']['BTC']['stop']==90
    assert s['positions']['BTC']['leverage']<45 and events[0]['adapted']


def test_dca_has_no_classic_per_trade_cap_but_total_margin_is_physical():
    s,_=execute(account(),decision(margin=900,leverage=2,stop=90))
    s,e=execute(s,decision('dca',margin=900,leverage=2,stop=90))
    assert 1749<margin(s)<=1750 and s['cash']>=0
    assert e[0]['margin_added']<900


def test_slots_and_stale_are_real_execution_limits():
    s=account()
    for sym in CFG.symbols[:CFG.max_slots]:
        s,_=apply(s,decision(symbol=sym,margin=10),{sym:quote()},{sym:contract()},NOW)
    with pytest.raises(ValueError,match='slots_full'):
        apply(s,decision(symbol=CFG.symbols[CFG.max_slots]),{CFG.symbols[CFG.max_slots]:quote()},{CFG.symbols[CFG.max_slots]:contract()},NOW)
    with pytest.raises(ValueError,match='stale_price'):execute(account(),decision(),{'BTC':quote(ts=NOW-31000)})


def test_entry_bar_is_not_used_retroactively_but_fresh_quote_can_stop():
    s,_=execute(account(),decision())
    data=market();data['BTC']['bars']['1m']=[[(NOW//60000)*60000,100,150,50,100,1]]
    updated,events=protect(s,data,{'BTC':contract()},NOW+60000)
    assert not events and updated['positions']
    data=market(NOW+60000,94)
    updated,events=protect(s,data,{'BTC':contract()},NOW+60000)
    assert events[0]['reason']=='stop_observed_quote' and not updated['positions']


def test_gap_marks_incomplete_and_blocks_only_affected_symbol():
    s,_=execute(account(),decision());now=NOW+180000
    m=market(now);m['BTC']['bars']['1m']=m['BTC']['bars']['1m'][-2:]
    updated,_=protect(s,m,{'BTC':contract()},now)
    assert 'BTC' in updated['coverage_gaps']
    assert updated['positions']['BTC']['coverage_complete'] is False
    updated,_=apply(updated,decision(symbol='ETH'),{'ETH':quote(ts=now)},{'ETH':contract()},now)
    assert 'ETH' in updated['positions']


def test_funding_applied_once_and_final_net_matches_cash():
    s,_=execute(account(),decision());now=NOW+60000;m=market(now)
    m['BTC']['funding']=[{'ts_ms':now,'rate':.001,'mark':100}]
    once,_=protect(s,m,{'BTC':contract()},now);twice,_=protect(once,m,{'BTC':contract()},now)
    assert once['cash']==twice['cash']<s['cash']
    done,trades=execute(twice,decision('close'),{'BTC':quote(100,now)},now)
    assert done['cash']==pytest.approx(2000+trades[0]['net'])


def test_restart_never_recreates_account_and_digest_cannot_change(tmp_path):
    root=tmp_path/'account';st=Store(root,True,'hash',NOW)
    s=st.load();s['cash']=1234;st.commit(s);st.close()
    st=Store(root,False,'hash');assert st.load()['cash']==1234;st.close()
    with pytest.raises(ValueError,match='initialization_requires_empty'):Store(root,True,'hash')
    with pytest.raises(ValueError,match='explicit_version_migration'):Store(root,False,'different')


def test_transaction_conflict_and_duplicate_event_are_atomic(tmp_path):
    st=Store(tmp_path/'account',True,'hash',NOW)
    a=st.load();b=deepcopy(a)
    st.commit(a,[('event','decision',NOW,{})])
    with pytest.raises(ValueError,match='stale_writer'):st.commit(b)
    before=st.load();bad=deepcopy(before);bad['cash']=0
    with pytest.raises(sqlite3.IntegrityError):st.commit(bad,[('event','decision',NOW,{})])
    assert st.load()==before;st.close()


def test_only_one_writer_and_verified_backup(tmp_path):
    st=Store(tmp_path/'account',True,'hash',NOW)
    with pytest.raises(ValueError,match='writer_already_active'):Store(tmp_path/'account',False,'hash')
    st.backup(tmp_path/'backup.sqlite3')
    with sqlite3.connect(tmp_path/'backup.sqlite3') as db:assert json.loads(db.execute('SELECT body FROM state').fetchone()[0])['cash']==2000
    st.close()


def test_memory_last_ten_ignores_partial_closes_and_prompt_has_both_contexts(tmp_path):
    st=Store(tmp_path/'account',True,'hash',NOW);s=st.load()
    st.commit(s,[(str(i),'trade_closed' if i%2==0 else 'partial_trade',NOW,{'position_id':i,'net':i-5}) for i in range(30)])
    memory=st.recent();assert len(memory)==10 and [x['position_id'] for x in memory]==list(range(10,30,2))
    _,payload=build(s,{}, {},{'fear_greed':{'status':'unavailable'}},memory,[],'full',NOW)
    assert json.loads(payload)['last_10_completed_trades']==memory
    assert 'last_10_completed_trades' in payload;st.close()


def test_reasoning_tokens_are_not_billed_twice_and_no_budget_cap(tmp_path):
    u={'prompt_tokens':1000,'prompt_cache_hit_tokens':100,'completion_tokens':200,'completion_tokens_details':{'reasoning_tokens':150}}
    p=price(u,NOW);assert p['cost']==pytest.approx((100*.003+900*.15+200*.6)*p['peak_multiplier']/1e6)
    st=Store(tmp_path/'account',True,'hash',NOW);st.record_request('cost',NOW,{})
    st.finish_request('cost','complete',{'billing':{'cost':9000}})
    assert view(st.db,NOW)['total_usd']==9000 and view(st.db,NOW)['budget_gate'] is False;st.close()


def test_timeout_remains_unknown_after_restart(tmp_path):
    root=tmp_path/'account';st=Store(root,True,'hash',NOW);st.record_request('id',NOW,{});st.close()
    st=Store(root,False,'hash');assert view(st.db,NOW)['uncertain_requests']==1
    assert st.db.execute('SELECT status FROM requests').fetchone()[0]=='unknown_after_restart';st.close()


def test_api_failure_does_not_disable_physical_stop_and_does_not_create_rule_trade(tmp_path):
    def model(*args):return {'error':'balance','usage':None}
    r=Runtime(tmp_path/'account',True,model_call=model,api_key='synthetic')
    r.activate(NOW,market());r.step(market(),{'BTC':contract()},{},NOW)
    for _ in range(100):
        if r.pending['future'].done():break
        time.sleep(.001)
    r.step(market(NOW+5000),{'BTC':contract()},{},NOW+5000)
    assert not r.store.load()['positions'] and r.store.load()['provider_status']=='balance'
    assert view(r.store.db,NOW)['uncertain_requests']==1;r.close()


def test_thesis_precedes_execution_and_no_optional_context_blocks(tmp_path):
    d=decision();payload={'summary':'synthetic','decisions':[d]}
    usage={'prompt_tokens':100,'completion_tokens':50}
    r=Runtime(tmp_path/'account',True,model_call=lambda *args:{'content':json.dumps(payload),'usage':usage,'finish_reason':'stop'},api_key='synthetic-key')
    r.activate(NOW,market());r.step(market(),{'BTC':contract()},{'macro':{'status':'unavailable'}},NOW)
    r.pending['future'].result(timeout=2)
    r.step(market(NOW+5000),{'BTC':contract()},{},NOW+5000)
    assert r.store.load()['positions']
    kinds=[x[0] for x in r.store.db.execute('SELECT kind FROM events ORDER BY seq')]
    assert kinds.index('ai_decision')<kinds.index('open')
    assert r.store.db.execute("SELECT body FROM outbox WHERE body LIKE '%[BRAIN] open%'").fetchone();r.close()


def test_daily_report_idempotent_and_168_hours_does_not_reset_or_stop(tmp_path):
    r=Runtime(tmp_path/'account',True,api_key='synthetic');s=r.store.load();s['verified_start_ms']=NOW-168*3600000
    events,messages=reports.schedule(r.store,s,NOW,CFG)
    r.store.commit(s,events,messages)
    assert any(e[1]=='final_report' for e in events)
    assert reports.schedule(r.store,s,NOW,CFG)==([],[])
    assert s['cash']==2000 and not s['paused'];r.close()


def test_invalid_trade_reason_and_nonfinite_values_are_rejected():
    for bad in [dict(decision(),reason=''),dict(decision(),margin=float('nan')),dict(decision(),invalidation='')]:
        with pytest.raises(ValueError):validate(json.dumps({'decisions':[bad]}),CFG.symbols)


def test_real_api_key_never_appears_in_error_and_request_has_thinking():
    observed=[]
    def opener(req,**kwargs):observed.append(json.loads(req.data));raise OSError('synthetic-secret')
    result=call('synthetic-secret','sys','{}',opener=opener)
    assert 'synthetic-secret' not in json.dumps(result)
    assert observed[0]['thinking']=={'type':'enabled'}


def test_no_daily_loss_or_450_equity_gate_and_margin_not_forced():
    s=account();s['cash']=300
    s,e=execute(s,decision(margin=200,leverage=2,stop=90,target=100.1))
    assert e[0]['margin']>199 and s['cash']>=0


def test_expensive_ledger_does_not_stop_an_ai_request(tmp_path):
    calls=[]
    def model(*args):calls.append(True);return {'error':'synthetic','usage':None}
    r=Runtime(tmp_path/'account',True,model_call=model,api_key='synthetic')
    r.store.record_request('past',NOW,{})
    r.store.finish_request('past','complete',{'billing':{'cost':10000}})
    r.activate(NOW,market());r.step(market(),{'BTC':contract()},{},NOW)
    r.pending['future'].result(timeout=2)
    assert calls==[True];r.close()


def test_slow_model_never_delays_observed_stop(tmp_path):
    import threading
    release=threading.Event()
    def model(*args):release.wait(3);return {'error':'synthetic','usage':None}
    r=Runtime(tmp_path/'account',True,model_call=model,api_key='synthetic')
    r.activate(NOW,market());s=r.store.load();s,_=execute(s,decision());r.store.commit(s)
    try:
        r.step(market(),{'BTC':contract()},{},NOW)
        assert r.pending and not r.pending['future'].done()
        r.step(market(NOW+5000,94),{'BTC':contract()},{},NOW+5000)
        assert not r.store.load()['positions']
        assert r.store.db.execute("SELECT kind FROM events WHERE kind='trade_closed'").fetchone()
    finally:release.set();r.close()


def test_funding_chronology_does_not_charge_after_a_stop_but_charges_before_later_stop():
    for funding_at,expected in [(NOW+120000,0),(NOW+60000,1)]:
        s,_=execute(account(),decision());m=market(NOW+180000)
        m['BTC']['bars']['1m']=[[NOW+60000,100,101,94,94,1]]
        m['BTC']['funding']=[{'ts_ms':funding_at,'rate':.001,'mark':100}]
        _,events=protect(s,m,{'BTC':contract()},NOW+180000)
        assert bool(events[0]['funding'])==bool(expected)


def test_bad_model_assessment_cannot_crash_reader_or_ui():
    with pytest.raises(ValueError,match='invalid_assessments'):
        validate(json.dumps({'decisions':[],'assessments':{'malformed':True}}),CFG.symbols)


def test_telegram_failure_does_not_ack_or_modify_account(tmp_path):
    from director.brain_free.notifications import Dispatcher
    r=Runtime(tmp_path/'account',True,api_key='synthetic')
    r.store.enqueue('test','[BRAIN] synthetic')
    before=r.store.load()
    dispatcher=Dispatcher(r.store.root,'token','chat',sender=lambda *args:False)
    dispatcher.flush()
    assert r.store.load()==before
    assert r.store.db.execute('SELECT sent,attempts FROM outbox').fetchone()==(0,1)
    dispatcher.close();r.close()


def test_invalid_optional_context_cannot_prevent_stop_processing(tmp_path):
    r=Runtime(tmp_path/'account',True,api_key='synthetic')
    r.activate(NOW,market());s=r.store.load();s,_=execute(s,decision());r.store.commit(s)
    r.step(market(NOW+5000,94),{'BTC':contract()},{'bad_source':float('nan')},NOW+5000)
    assert not r.store.load()['positions']
    assert r.store.load()['context']['status']=='unavailable_invalid_context';r.close()


def test_model_failure_cost_is_still_recorded_before_schema_rejection(tmp_path):
    result={'content':'not valid JSON','finish_reason':'stop','usage':{'prompt_tokens':100,'completion_tokens':50}}
    r=Runtime(tmp_path/'account',True,model_call=lambda *args:result,api_key='synthetic')
    r.activate(NOW,market());r.step(market(),{'BTC':contract()},{},NOW);r.pending['future'].result(timeout=2)
    r.step(market(NOW+5000),{'BTC':contract()},{},NOW+5000)
    assert view(r.store.db,NOW)['total_usd']>0 and not r.store.load()['positions'];r.close()


def test_report_counts_partial_realization_and_paid_entry_fees_once(tmp_path):
    r=Runtime(tmp_path/'account',True,api_key='synthetic');r.activate(NOW,market())
    s=r.store.load();s,e=execute(s,decision());r.record_events(s,e,NOW,'open')
    report=reports.build(r.store,r.store.load(),NOW)
    assert report['fees']>0 and report['realized_net']==0
    s,e=execute(r.store.load(),decision('partial_close',fraction=.5),{'BTC':quote(103,NOW+1000)},NOW+1000)
    r.record_events(s,e,NOW+1000,'partial');partial_net=e[0]['net']
    assert reports.build(r.store,r.store.load(),NOW+1000)['realized_net']==pytest.approx(partial_net)
    s,e=execute(r.store.load(),decision('close'),{'BTC':quote(104,NOW+2000)},NOW+2000)
    r.record_events(s,e,NOW+2000,'close')
    report=reports.build(r.store,r.store.load(),NOW+2000)
    assert report['realized_net']==pytest.approx(e[0]['net'])
    assert report['fees']==pytest.approx(e[0]['fees']);r.close()


def test_closing_notification_keeps_entry_thesis_and_labels_aggregate_pnl():
    s,_=execute(account(),decision());s,e=execute(s,decision('close'),{'BTC':quote(101,NOW+1000)},NOW+1000)
    text=event_text(e[0])
    assert '[BRAIN]' in text and 'Tesi di apertura: synthetic evidence' in text
    assert 'parziali incluse' in text and 'NETTO' in text


def test_ai_can_close_and_reverse_without_a_symbol_cooldown():
    s,_=execute(account(),decision())
    decisions=validate(json.dumps({'decisions':[decision('close'),decision('open_short')]}),CFG.symbols)['decisions']
    original=s['positions']['BTC']['id']
    for d in decisions:s,_=execute(s,d)
    assert s['positions']['BTC']['side']==-1 and s['positions']['BTC']['id']!=original
    with pytest.raises(ValueError,match='invalid_decision'):
        validate(json.dumps({'decisions':[decision(),decision()]}),CFG.symbols)
