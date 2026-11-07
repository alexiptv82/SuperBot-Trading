"""Self-owned integration tests for the optional PAPER split-exit runtime.

No network, no VPS, no live trades. The split mode is explicit and cannot
silently use the legacy direct execute_paper path.
"""
from __future__ import annotations

import dataclasses
from decimal import Decimal as D
from pathlib import Path

import pytest

from backend.tests.test_v3_runner_cycle import (
    _journal, _mandate, _bars, RUN as CYCLE_RUN, NOW as CYCLE_NOW, VIEW, POLICY, RULES,
    ScriptAnalyst, FakeStore,
)
from backend.tests.test_v3_runner_e2e import (
    RUN as E2E_RUN, G, VIEW as E2E_VIEW, FakeModel, _get_json_factory,
    mandate_template,
)
from backend.v3.events import Event, EventJournal
from backend.v3.runner.cycle import CycleBars, MarketEntryAnalyst, run_brain_cycle
from backend.v3.runner.runner import Runner
from backend.v3.runner.open_serial import OpenCommit
from backend.v3.executor.paper import ExecutionReceipt
from backend.v3.runner.exit_service import ExitService
from backend.v3.runner.monitor import MonitorReport
from backend.v3.runner.config import load_default_config
from backend.v3.runner.wiring import build_runner


def _cycle_inputs(j, model, **kw):
    d = dict(
        now_ms=CYCLE_NOW, journal=j, run_id=CYCLE_RUN,
        symbols=("AAAUSDT",), store=FakeStore(), bars_holder=CycleBars(),
        analyst=MarketEntryAnalyst(model), view_params=VIEW, risk_policy=POLICY,
        mandate=_mandate(), policy_verifier=lambda m, p: True,
        market_rules=lambda _: RULES, initial_equity=D("1000"),
        slippage_bps=2, allowed_strategy_ids=("S25",),
    )
    d.update(kw)
    return d


def _events(j, kind):
    return [x.event for x in j.list_run('brain', CYCLE_RUN) if x.event.kind == kind]


def test_legacy_cycle_unmodified_direct_paper_exec():
    j = _journal(); model = ScriptAnalyst()
    result = run_brain_cycle(**_cycle_inputs(j,model))
    assert len(result.opened) == 1 and len(_events(j,'paper_open')) == 1


def test_split_without_commit_refuses_before_model():
    j = _journal(); model = ScriptAnalyst()
    with pytest.raises(ValueError,match='^split_open_commit_required$'):
        run_brain_cycle(**_cycle_inputs(j,model,require_open_commit=True))
    assert not model.calls and not j.list_run('brain',CYCLE_RUN)


def test_split_refuses_callback_without_explicit_mode():
    j = _journal(); model = ScriptAnalyst()
    with pytest.raises(ValueError,match='^open_commit_requires_split_mode$'):
        run_brain_cycle(**_cycle_inputs(j,model,open_commit=lambda _:None))
    assert not model.calls


def test_split_denial_never_calls_direct_executor(monkeypatch):
    j = _journal(); model = ScriptAnalyst()
    import backend.v3.runner.cycle as cycle
    def bomb(*_,**__):raise RuntimeError('direct executor MUST NOT be used')
    monkeypatch.setattr(cycle,'execute_paper',bomb)
    out=run_brain_cycle(**_cycle_inputs(j,model,require_open_commit=True,
        open_commit=lambda d:OpenCommit(False,'exit_service_unhealthy')))
    assert out.opened == ()
    assert out.errors == (("AAAUSDT","exit_service_unhealthy"),)
    assert _events(j,'paper_open') == []
    assert len(_events(j,'brain_decision')) == 1


def test_split_callback_crash_does_not_fallback_to_direct_executor(monkeypatch):
    j = _journal();model=ScriptAnalyst()
    import backend.v3.runner.cycle as cycle
    def bomb(*_,**__):raise RuntimeError('direct path invoked')
    monkeypatch.setattr(cycle,'execute_paper',bomb)
    out=run_brain_cycle(**_cycle_inputs(j,model,require_open_commit=True,
        open_commit=lambda d:1/0))
    assert out.errors==(('AAAUSDT','split_open_failed'),)
    assert _events(j,'paper_open')==[]


def test_split_bad_response_refused_even_when_claimed_success():
    j=_journal();model=ScriptAnalyst()
    r=run_brain_cycle(**_cycle_inputs(j,model,require_open_commit=True,
        open_commit=lambda d:True))
    assert r.opened==() and r.errors==(('AAAUSDT','split_open_result_invalid'),)


def test_split_not_started_without_owner_and_never_runs_commands(tmp_path):
    calls={'monitor':0,'commands':0,'cycles':0}
    def f(*a):calls['cycles']+=1
    r=Runner(run_id='brain-split',data_dir=tmp_path,run_monitor=None,
        run_cycle=f,run_commands=None,exit_mode='sidecar',exit_healthy=lambda _:False,
        fresh_clock_ms=lambda:CYCLE_NOW,
        cycle_delay_ms=0)
    t=r.tick(CYCLE_NOW)
    assert t.state=='halted' and t.last_error=='halted:exit_service_unhealthy'
    assert calls['cycles']==0 and t.monitor is None and t.manual is None


def test_split_allows_cycle_only_after_healthy_check(tmp_path):
    calls=[]
    r=Runner(run_id='brain-split',data_dir=tmp_path,run_monitor=None,
             run_cycle=lambda now,slot: calls.append((now,slot)),
             exit_mode='sidecar',exit_healthy=lambda _:True,fresh_clock_ms=lambda:CYCLE_NOW,cycle_delay_ms=0)
    t=r.tick(CYCLE_NOW)
    assert t.state=='running' and calls == [(CYCLE_NOW,CYCLE_NOW//900_000)]
    assert t.monitor is None and t.manual is None


def test_split_rechecks_health_each_tick(tmp_path):
    status={'alive':True};calls=[]
    r=Runner(run_id='brain-split',data_dir=tmp_path,run_monitor=None,
             run_cycle=lambda now,slot: calls.append(now),
             exit_mode='sidecar',exit_healthy=lambda _:status['alive'],
             fresh_clock_ms=lambda:CYCLE_NOW+900_000,cycle_delay_ms=0)
    r.tick(CYCLE_NOW)
    status['alive']=False
    t=r.tick(CYCLE_NOW+900_000)
    assert t.state=='halted' and t.cycle is None and calls==[CYCLE_NOW]


def test_split_rejects_legacy_callbacks(tmp_path):
    opts=dict(run_id='brain-split',data_dir=tmp_path,run_cycle=lambda *_:None,
              run_monitor=lambda _:None,exit_mode='sidecar',exit_healthy=lambda _:True,
              fresh_clock_ms=lambda:CYCLE_NOW)
    with pytest.raises(ValueError,match='^split_exits_must_have_single_owner$'):
        Runner(**opts)


def test_legacy_runner_rejects_sidecar_heartbeat_injection(tmp_path):
    with pytest.raises(ValueError,match='^legacy_exits_invalid$'):
        Runner(run_id='brain-split',data_dir=tmp_path,run_cycle=lambda *_:None,
               run_monitor=lambda _:None,exit_healthy=lambda _:True)


def test_sidecar_tick_error_reports_halted_not_running(tmp_path,monkeypatch):
    r=Runner(run_id='brain-split',data_dir=tmp_path,run_monitor=None,
             run_cycle=lambda *_:None,exit_mode='sidecar',exit_healthy=lambda _:True,
             fresh_clock_ms=lambda:CYCLE_NOW)
    def bad(_):raise RuntimeError('failure')
    monkeypatch.setattr(r,'tick',bad)
    called=[False]
    def stop():
        if called[0]:return True
        called[0]=True
        return False
    r.run(now_fn=lambda:CYCLE_NOW,sleep_fn=lambda _:None,should_stop=stop)
    import json
    b=json.loads((tmp_path/'heartbeat.json').read_text())
    assert b['state']=='halted' and b['last_error']=='tick_failed'


def test_wiring_split_requires_existing_run_and_budget(tmp_path):
    conf=dataclasses.replace(load_default_config(),symbols=('BTCUSDT',),cycle_minutes=15,
                              thinking='disabled',reasoning_effort='omit',max_tokens=256)
    with pytest.raises(ValueError):
        build_runner(data_dir=tmp_path,run_id=E2E_RUN,config=conf,
                     get_json=_get_json_factory(),inner_transport=FakeModel(),
                     view_params=E2E_VIEW,exit_mode='sidecar',clock_ms=lambda:G+25_000,desk_mode='paper')
    assert not (tmp_path/'journal.db').exists() and not (tmp_path/'budget.db').exists()


def test_wiring_legacy_still_creates_original_journal(tmp_path):
    conf=dataclasses.replace(load_default_config(),symbols=('BTCUSDT',),cycle_minutes=15,
                              thinking='disabled',reasoning_effort='omit',max_tokens=256)
    built=build_runner(data_dir=tmp_path,run_id=E2E_RUN,config=conf,
                       get_json=_get_json_factory(),inner_transport=FakeModel(),view_params=E2E_VIEW)
    assert (tmp_path/'journal.db').is_file() and built.runner._exit_mode=='legacy'


def test_wiring_split_halts_without_actual_exit_owner(tmp_path):
    conf=dataclasses.replace(load_default_config(),symbols=('BTCUSDT',),cycle_minutes=15,
                              thinking='disabled',reasoning_effort='omit',max_tokens=256)
    old=build_runner(data_dir=tmp_path,run_id=E2E_RUN,config=conf,
                     get_json=_get_json_factory(),inner_transport=FakeModel(),view_params=E2E_VIEW)
    old.journal.append(Event('prior-run','brain',E2E_RUN,'startup',G-1000,'test',{'synthetic':True}))
    model=FakeModel()
    split=build_runner(data_dir=tmp_path,run_id=E2E_RUN,config=conf,
                       get_json=_get_json_factory(),inner_transport=model,view_params=E2E_VIEW,
                       exit_mode='sidecar',clock_ms=lambda:G+25_000,desk_mode='paper')
    (tmp_path/'mandate.json').write_text(__import__('json').dumps(dict(
        mandate_template(conf.risk_policy,E2E_RUN),approved=True,approved_by='test')))
    t=split.runner.tick(G+25_000)
    assert t.state=='halted' and t.last_error=='halted:exit_service_unhealthy'
    assert model.payloads==[] and not any(e.event.kind=='paper_open' for e in split.journal.list_run('brain',E2E_RUN))
    assert split.runner._commands is None and split.runner._monitor is None


def test_wiring_split_uses_post_ai_commit_with_real_sidecar(tmp_path):
    conf=dataclasses.replace(load_default_config(),symbols=('BTCUSDT',),cycle_minutes=15,
                              thinking='disabled',reasoning_effort='omit',max_tokens=256)
    old=build_runner(data_dir=tmp_path,run_id=E2E_RUN,config=conf,
                     get_json=_get_json_factory(),inner_transport=FakeModel(),view_params=E2E_VIEW)
    old.journal.append(Event('prior-run','brain',E2E_RUN,'startup',G-1000,'test',{'synthetic':True}))
    model=FakeModel()
    split=build_runner(data_dir=tmp_path,run_id=E2E_RUN,config=conf,
                       get_json=_get_json_factory(),inner_transport=model,view_params=E2E_VIEW,
                       exit_mode='sidecar',clock_ms=lambda:G+25_000,desk_mode='paper')
    (tmp_path/'mandate.json').write_text(__import__('json').dumps(dict(
        mandate_template(conf.risk_policy,E2E_RUN),approved=True,approved_by='test')))
    svc=ExitService(run_id=E2E_RUN,data_dir=tmp_path,run_commands=lambda _:None,
                    run_monitor=lambda _:MonitorReport(0,(),()))
    with svc:
        svc.tick(G+25_000)
        t=split.runner.tick(G+25_000)
        assert t.state=='running'
        assert len(model.payloads) == 1
        assert t.cycle is not None
        assert t.cycle.errors == () and len(t.cycle.opened)==1
        opens=[e.event for e in split.journal.list_run('brain',E2E_RUN) if e.event.kind=='paper_open']
        assert len(opens)==1


def test_split_owner_vanishes_while_ai_waits_no_open_and_halted_heartbeat(tmp_path):
    import json
    conf=dataclasses.replace(load_default_config(),symbols=('BTCUSDT',),cycle_minutes=15,
                              thinking='disabled',reasoning_effort='omit',max_tokens=256)
    getter=_get_json_factory()
    old=build_runner(data_dir=tmp_path,run_id=E2E_RUN,config=conf,get_json=getter,
                     inner_transport=FakeModel(),view_params=E2E_VIEW)
    old.journal.append(Event('prior-run','brain',E2E_RUN,'startup',G-1000,'test',{'synthetic':True}))
    svc=ExitService(run_id=E2E_RUN,data_dir=tmp_path,run_commands=lambda _:None,
                    run_monitor=lambda _:MonitorReport(0,(),()))
    class ModelClosesOwner(FakeModel):
        def __call__(self,payload):
            r=super().__call__(payload)
            svc.stop()  # actual lease disappears during model callback
            return r
    model=ModelClosesOwner()
    built=build_runner(data_dir=tmp_path,run_id=E2E_RUN,config=conf,get_json=getter,
                       inner_transport=model,view_params=E2E_VIEW,
                       exit_mode='sidecar',clock_ms=lambda:G+25_000,desk_mode='paper')
    (tmp_path/'mandate.json').write_text(json.dumps(dict(
        mandate_template(conf.risk_policy,E2E_RUN),approved=True,approved_by='test')))
    with svc:
        svc.tick(G+25_000)
        out=built.runner.tick(G+25_000)
    assert len(model.payloads)==1
    assert out.state=='halted'
    assert 'halted:exit_service_unhealthy' in out.last_error
    assert out.cycle.opened==()
    assert len([e for e in built.journal.list_run('brain',E2E_RUN) if e.event.kind=='paper_open'])==0
    assert json.loads((tmp_path/'heartbeat.json').read_text())['state']=='halted'


def test_split_claimed_open_without_journal_record_is_not_reported():
    j=_journal();model=ScriptAnalyst()
    fake=ExecutionReceipt(position_id='forged', portfolio_id='brain', run_id=CYCLE_RUN,
        symbol='AAAUSDT', side=1,fill_price=D('100'),quantity=D('1'),
        notional=D('100'),margin_used=D('50'),leverage=2,stop_price=D('99'),
        slippage_bps=0,timestamp_ms=CYCLE_NOW,journal_seq=2,
        journal_event_id='paper_open.forged',decision_event_id='fake')
    out=run_brain_cycle(**_cycle_inputs(j,model,require_open_commit=True,
        open_commit=lambda d:OpenCommit(True,'paper_open_committed',fake)))
    assert out.opened==()
    assert out.errors==(('AAAUSDT','split_open_receipt_unverified'),)
    assert _events(j,'paper_open')==[]


def test_split_error_code_cannot_leak_untrusted_callback_text():
    j=_journal();model=ScriptAnalyst()
    out=run_brain_cycle(**_cycle_inputs(j,model,require_open_commit=True,
        open_commit=lambda d:OpenCommit(False,'http://example.net/secret?token=abc')))
    assert out.errors==(('AAAUSDT','split_open_denied'),)


def _setup_live_mutation(tmp_path, mutator, monkeypatch=None):
    """Real runner, analyst, journal and sidecar; only fake market and model."""
    import json
    conf=dataclasses.replace(load_default_config(),symbols=('BTCUSDT',),cycle_minutes=15,
                              thinking='disabled',reasoning_effort='omit',max_tokens=256)
    getter=_get_json_factory()
    old=build_runner(data_dir=tmp_path,run_id=E2E_RUN,config=conf,get_json=getter,
                     inner_transport=FakeModel(),view_params=E2E_VIEW)
    old.journal.append(Event('prior-run','brain',E2E_RUN,'startup',G-1000,'test',{'synthetic':True}))
    state={'mutator':mutator}
    class MutatingModel(FakeModel):
        def __call__(self,payload):
            v=super().__call__(payload)
            state['mutator'](state)
            return v
    model=MutatingModel()
    built=build_runner(data_dir=tmp_path,run_id=E2E_RUN,config=conf,get_json=getter,
                       inner_transport=model,view_params=E2E_VIEW,
                       exit_mode='sidecar',clock_ms=lambda:G+25_000,desk_mode='paper')
    (tmp_path/'mandate.json').write_text(json.dumps(dict(
        mandate_template(conf.risk_policy,E2E_RUN),approved=True,approved_by='test')))
    state.update({'built':built,'model':model,'config':conf,'folder':tmp_path})
    return state


@pytest.mark.parametrize('action,denial,state',[
    ('pause','brain_paused','paused'),
    ('mandate','mandate_unavailable','halted'),
    ('budget','budget_unavailable','halted'),
])
def test_mid_ai_safety_change_is_blocked_and_heartbeat_correct(tmp_path,action,denial,state):
    import json
    def mutate(ctx):
        if action=='pause': (ctx['folder']/'pause.flag').write_text('')
        if action=='mandate': (ctx['folder']/'mandate.json').unlink()
        if action=='budget': ctx['built'].metered.accounting_failed=True
    ctx=_setup_live_mutation(tmp_path,mutate)
    svc=ExitService(run_id=E2E_RUN,data_dir=tmp_path,run_commands=lambda _:None,
                    run_monitor=lambda _:MonitorReport(0,(),()))
    with svc:
        svc.tick(G+25_000)
        r=ctx['built'].runner.tick(G+25_000)
    assert len(ctx['model'].payloads)==1
    assert r.state==state
    assert r.cycle.opened==()
    # Some changes are caught inside BrainEngine before the post-AI committer;
    # both must prevent an OPEN. Do not demand a particular layer catches it.
    assert (any(denial==code for _,code in r.cycle.errors)
            or (r.cycle.decisions and r.cycle.decisions[0][1] != 'OPEN')),(r.cycle.errors,r.cycle.decisions)
    assert not [e for e in ctx['built'].journal.list_run('brain',E2E_RUN) if e.event.kind=='paper_open']
    assert json.loads((tmp_path/'heartbeat.json').read_text())['state']==state


def test_daily_loss_became_halt_in_same_minute_post_ai_guard_rechecks_fresh(tmp_path,monkeypatch):
    from backend.v3.runner.daily_loss import DailyLoss
    import backend.v3.runner.wiring as wiring
    import json
    flag={'after':False,'calls':0}
    original=wiring.evaluate_daily_loss
    def fake_evaluate(**kwargs):
        flag['calls']+=1
        if flag['after']:
            return DailyLoss('halt',D('0.60'),D('600'),(G//86_400_000)*86_400_000)
        return original(**kwargs)
    monkeypatch.setattr(wiring,'evaluate_daily_loss',fake_evaluate)
    ctx=_setup_live_mutation(tmp_path,lambda _:flag.update(after=True))
    svc=ExitService(run_id=E2E_RUN,data_dir=tmp_path,run_commands=lambda _:None,
                    run_monitor=lambda _:MonitorReport(0,(),()))
    with svc:
        svc.tick(G+25_000)
        r=ctx['built'].runner.tick(G+25_000)
    assert flag['calls']>=2  # evaluation before model + fresh recheck after
    assert r.cycle.opened==()
    assert ('BTCUSDT','daily_loss_unavailable_or_halted') in r.cycle.errors
    assert not [e for e in ctx['built'].journal.list_run('brain',E2E_RUN) if e.event.kind=='paper_open']


def test_post_ai_daily_loss_recheck_persists_halt_across_immediate_recovery(tmp_path):
    from backend.v3.runner.daily_loss import DailyLoss, DailyLossGuard
    ms=G+25_000
    values={'level':'ok', 'calls':0}
    def evaluator(t):
        values['calls']+=1
        lvl=values['level']
        return DailyLoss(lvl,D('.55') if lvl=='halt' else D('.1'),D('550') if lvl=='halt' else D('100'),
                         (t//86_400_000)*86_400_000)
    guard=DailyLossGuard(data_dir=tmp_path,evaluate=evaluator,send=None,
                         warn_fraction=D('.35'),halt_fraction=D('.50'))
    assert guard(ms).level=='ok'
    values['level']='halt'
    assert guard.recheck(ms).level=='halt'
    values['level']='ok'
    assert guard.recheck(ms).level=='halt'  # same minute: persistent latch
    rebuilt=DailyLossGuard(data_dir=tmp_path,evaluate=evaluator,send=None,
                           warn_fraction=D('.35'),halt_fraction=D('.50'))
    assert rebuilt(ms+60_000).level=='halt'  # survives service restart
    assert values['calls']==4


def test_post_ai_daily_loss_disk_write_failure_denies_open(tmp_path, monkeypatch):
    from backend.v3.runner.daily_loss import DailyLoss, DailyLossGuard
    ms=G+25_000
    g=DailyLossGuard(data_dir=tmp_path,evaluate=lambda t: DailyLoss('halt',D('.6'),D('600'),
                    (t//86_400_000)*86_400_000),send=None,
                    warn_fraction=D('.35'),halt_fraction=D('.50'))
    monkeypatch.setattr(g,'_save',lambda:None)  # mimic full disk
    with pytest.raises(ValueError,match='^daily_loss_latch_not_persisted$'):
        g.recheck(ms)


def test_split_builder_enforces_explicit_paper_mode_before_any_side_effect(tmp_path):
    conf=load_default_config()
    for mode in (None,'live','PAPER',True):
        with pytest.raises(ValueError,match='^paper_mode_required$'):
            build_runner(data_dir=tmp_path,run_id=E2E_RUN,config=conf,
                         exit_mode='sidecar',desk_mode=mode,clock_ms=lambda:G+25_000)
    assert list(tmp_path.iterdir())==[]


def test_split_post_ai_heartbeat_uses_fresh_clock_not_tick_start(tmp_path):
    import json
    state={'now':CYCLE_NOW,'seen':[]}
    def cycle(now,slot):
        # Synthetic 30-second model wait; sidecar heartbeats have advanced.
        state['now']=CYCLE_NOW+30_000
    def healthy(ts):
        state['seen'].append(ts)
        return ts==state['now']
    r=Runner(run_id='brain-split',data_dir=tmp_path,run_monitor=None,
             run_cycle=cycle,exit_mode='sidecar',exit_healthy=healthy,
             fresh_clock_ms=lambda:state['now'],cycle_delay_ms=0)
    result=r.tick(CYCLE_NOW)
    assert result.state=='running'
    assert state['seen']==[CYCLE_NOW,CYCLE_NOW+30_000]
    beat=json.loads((tmp_path/'heartbeat.json').read_text())
    assert beat['ts_ms']==CYCLE_NOW+30_000 and beat['state']=='running'
