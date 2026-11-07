"""Isolated PAPER cooperating-writer tests, no exchange, no AI or VPS."""
from __future__ import annotations

import copy
from decimal import Decimal as D
import fcntl
import multiprocessing
import os
import time
from pathlib import Path

import pytest

from backend.tests.test_v3_post_ai_guard import _args, _setup, NOW, RUN, RULES, POL
from backend.v3.events import EventJournal
from backend.v3.runner.open_serial import commit_paper_open
from backend.v3.brain_f2.contracts import ProposalStatus
from backend.v3.executor.paper import execute_paper
from backend.v3.runner.legacy_exit_fence import LegacyExitFence
from backend.v3.runner.exit_service import ExitService, ExitServiceBusy, exit_service_healthy
from backend.v3.runner.monitor import MonitorReport


def _real_sidecar(folder):
    svc=ExitService(run_id=RUN,data_dir=folder,run_commands=lambda _:None,
                    run_monitor=lambda _:MonitorReport(0,(),()))
    return svc


def _guard_inputs(**state):
    s=dict(exit_ok=True,paused=False,mandate=None,budget=None,loss=False,price=D('100'),fresh=True)
    s.update(state)
    return dict(initial_equity=D('1000'),risk_policy=POL,
        exit_healthy=lambda _:s['exit_ok'], mandate_problem=lambda:s['mandate'],
        budget_problem=lambda:s['budget'],daily_loss_halted=lambda _:s['loss'],
        paused=lambda:s['paused'],market_rules=lambda _:RULES,
        market_price=lambda *_:s['price'],market_fresh=lambda *_:s['fresh'])


def _commit(j, d, folder, *, inputs=None, clock=None, mode='paper'):
    return commit_paper_open(journal=j,data_dir=folder,run_id=RUN,decision=d,
        clock_ms=(lambda:NOW) if clock is None else clock,
        guard_inputs=_guard_inputs() if inputs is None else inputs,
        slippage_bps=0,desk_mode=mode)


def test_authorized_paper_open_is_a_real_executor_event(tmp_path):
    j,d,_,_=_args(tmp_path)
    with _real_sidecar(tmp_path) as sidecar:
        assert sidecar.tick(NOW).state=='healthy'
        result=_commit(j,d,tmp_path)
    assert result.allowed is True and result.code=='paper_open_committed'
    assert result.receipt is not None
    assert d.status == ProposalStatus.EXECUTED_PAPER
    opens=[e for e in j.list_run('brain',RUN) if e.event.kind=='paper_open']
    assert len(opens)==1 and opens[0].event.payload['decision_event_id']==d.journal_event_id
    assert j.verify_chain()[0]==2


def test_idempotent_replay_rejected_even_after_close(tmp_path):
    j,d,_,_=_args(tmp_path)
    original=copy.deepcopy(d)
    with _real_sidecar(tmp_path) as svc:
        svc.tick(NOW)
        assert _commit(j,d,tmp_path).allowed is True
    # An old approved decision object can arrive again, but must not be executed.
    assert _commit(j,original,tmp_path).code=='decision_already_executed'
    from backend.v3.executor.paper_close import close_paper
    close_paper(portfolio_id='brain',run_id=RUN,position_id=d.risk_quote and
        [e.event.payload['position_id'] for e in j.list_run('brain',RUN) if e.event.kind=='paper_open'][0],
        exit_price=D('101'),reason='manual',fee_bps=D('6'),journal=j,now_ms=NOW+60_000)
    assert _commit(j,original,tmp_path).code=='decision_already_executed'
    assert len([e for e in j.list_run('brain',RUN) if e.event.kind=='paper_open'])==1


def test_no_mode_no_lock_and_no_execution(tmp_path):
    j,d,_,_=_args(tmp_path)
    assert _commit(j,d,tmp_path,mode='live').code=='paper_mode_required'
    assert not (tmp_path/'.brain-paper-open.lock').exists()
    assert len(j.list_run('brain',RUN))==1


def test_null_or_mismatched_scope_denied(tmp_path):
    j,d,_,_=_args(tmp_path)
    other=tmp_path/'sub';other.mkdir()
    for folder in (other,Path('.'),tmp_path/'missing'):
        assert _commit(j,d,folder).code=='open_scope_invalid'
    assert len(j.list_run('brain',RUN))==1


def test_decision_without_verified_event_denied(tmp_path):
    j,d,_,_=_args(tmp_path)
    d.journal_event_id='fabricated'
    assert _commit(j,d,tmp_path).code=='decision_unjournaled'
    assert len([e for e in j.list_run('brain',RUN) if e.event.kind=='paper_open'])==0


def test_stale_clock_denied(tmp_path):
    j,d,_,_=_args(tmp_path)
    result=_commit(j,d,tmp_path,clock=lambda:NOW+900_000)
    assert result.code=='decision_stale'


def test_lock_busy_causes_refusal_without_wait(tmp_path):
    j,d,_,_=_args(tmp_path)
    lock=tmp_path/'.brain-paper-open.lock'
    with open(lock,'w') as fd:
        os.chmod(lock,0o600)
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        assert _commit(j,d,tmp_path).code=='open_lease_busy'
        assert len(j.list_run('brain',RUN))==1


def test_unsafe_lock_symlink_rejected(tmp_path):
    j,d,_,_=_args(tmp_path)
    (tmp_path/'.brain-paper-open.lock').symlink_to(tmp_path/'journal.db')
    assert _commit(j,d,tmp_path).code in ('open_scope_invalid','open_lease_invalid')
    assert len(j.list_run('brain',RUN))==1


def test_permissions_of_preexisting_lock_checked(tmp_path):
    j,d,_,_=_args(tmp_path)
    (tmp_path/'.brain-paper-open.lock').write_bytes(b'x')
    os.chmod(tmp_path/'.brain-paper-open.lock',0o666)
    assert _commit(j,d,tmp_path).code=='open_lease_invalid'


def test_failure_between_guard_and_executor_has_no_paper_open(tmp_path,monkeypatch):
    j,d,_,_=_args(tmp_path)
    import backend.v3.runner.open_serial as coordinator
    def fail(*a,**kw):raise RuntimeError('simulated crash')
    monkeypatch.setattr(coordinator,'execute_paper',fail)
    with _real_sidecar(tmp_path) as svc:
        svc.tick(NOW)
        result=_commit(j,d,tmp_path)
    assert result.code=='open_commit_failed'
    assert len(j.list_run('brain',RUN))==1
    assert d.status==ProposalStatus.APPROVED


@pytest.mark.parametrize('change,reason',[
    ({'exit_ok':False},'exit_service_unhealthy'),
    ({'paused':True},'brain_paused'),
    ({'mandate':'revoked'},'mandate_unavailable'),
    ({'budget':'cap'},'budget_unavailable'),
    ({'loss':True},'daily_loss_unavailable_or_halted'),
    ({'fresh':False},'market_unavailable'),
])
def test_post_ai_veto_executed_inside_lock(tmp_path,change,reason):
    j,d,_,_=_args(tmp_path)
    r=_commit(j,d,tmp_path,inputs=_guard_inputs(**change))
    assert r.allowed is False and r.code==reason
    assert len(j.list_run('brain',RUN))==1


def test_bad_input_denied_not_implicitly_accepted(tmp_path):
    j,d,_,_=_args(tmp_path)
    assert _commit(j,d,tmp_path,inputs={}).code=='open_scope_invalid'
    assert _commit(j,d,tmp_path,clock=lambda:True).code=='open_clock_invalid'
    assert _commit(j,d,tmp_path,mode=True).code=='paper_mode_required'


def test_guard_budget_after_prior_open_in_same_run(tmp_path):
    j,d,_,_=_args(tmp_path)
    with _real_sidecar(tmp_path) as svc:
        svc.tick(NOW)
        first=_commit(j,d,tmp_path)
    assert first.allowed
    from dataclasses import replace
    from backend.v3.events import Event
    next_d=copy.deepcopy(d)
    next_d.status=ProposalStatus.APPROVED
    next_d.proposal=replace(next_d.proposal,symbol='ETHUSDT')
    next_d.journal_event_id='brain-decision-02'
    j.append(Event(next_d.journal_event_id,'brain',RUN,'brain_decision',NOW-1000,
                   'test',{'symbol':'ETHUSDT','kind':'OPEN','status':'APPROVED','rationale':next_d.rationale}))
    # Fill synthetic portfolio via existing executor; a stale decision approved
    # before those positions existed must now be vetoed by fresh risk quote.
    for i in range(10):
        other=copy.deepcopy(d)
        other.status=ProposalStatus.APPROVED
        other.proposal=replace(other.proposal,symbol=f'ALT{i}USDT')
        other.journal_event_id=None
        execute_paper(other,portfolio_id='brain',run_id=RUN,journal=j,now_ms=NOW-300)
    r=_commit(j,next_d,tmp_path)
    assert r.code in ('risk_changed_after_ai','risk_rejected_after_ai')
    assert len([e for e in j.list_run('brain',RUN) if e.event.kind=='paper_open'])==11


def _worker_attempt(folder: str, event, q):
    """Independent process; each opens own lock fd and SQLite connections."""
    from backend.tests.test_v3_post_ai_guard import _hand
    from backend.v3.risk import RiskRequest, quote_paper_risk
    from backend.v3.events import EventJournal
    j=EventJournal(Path(folder)/'journal.db')
    d=_hand(side=1,entry='100',stop='99',symbol='BTCUSDT')
    d.occurred_at_ms=NOW-1000
    d.risk_quote=quote_paper_risk(POL,RiskRequest(D('1000'),D('1000'),D('0'),D('0'),
        D('100'),D('99'),1,2,10,RULES['quantity_step'],RULES['minimum_notional'],
        RULES['maintenance_fraction'],True,False,False))
    d.journal_event_id='brain-decision-01'
    try:
        if not event.wait(timeout=8):
            q.put('worker_timeout');return
        result=_commit(j,d,Path(folder))
        q.put(result.code)
    except BaseException:
        q.put('worker_failed')


def test_two_processes_cannot_execute_same_decision_twice(tmp_path):
    j,_,_,_=_args(tmp_path)
    ctx=multiprocessing.get_context('spawn')
    event=ctx.Event();q=ctx.Queue()
    processes=[ctx.Process(target=_worker_attempt,args=(str(tmp_path),event,q)) for _ in range(2)]
    with _real_sidecar(tmp_path) as svc:
        svc.tick(NOW)
        for p in processes:p.start()
        event.set()
        outcomes=[q.get(timeout=10) for _ in processes]
    for p in processes:
        p.join(timeout=10)
        assert p.exitcode==0
    assert outcomes.count('paper_open_committed')==1
    assert sorted(outcomes) in (['open_lease_busy','paper_open_committed'],
                                ['decision_already_executed','paper_open_committed'])
    assert len([e for e in j.list_run('brain',RUN) if e.event.kind=='paper_open'])==1
    assert j.verify_chain()[0]==2


def test_legacy_fence_blocks_sidecar_start(tmp_path):
    first=LegacyExitFence(run_id=RUN,data_dir=tmp_path)
    svc=ExitService(run_id=RUN,data_dir=tmp_path,run_commands=lambda _:None,
                    run_monitor=lambda _:MonitorReport(0,(),()))
    with first:
        with pytest.raises(ExitServiceBusy,match='exit_service_already_running'):
            svc.start()
        # A legacy fence must NEVER masquerade as a healthy sidecar heartbeat.
        assert exit_service_healthy(data_dir=tmp_path,run_id=RUN,now_ms=NOW) is False
    with svc:
        assert svc.tick(NOW).state=='healthy'
        assert exit_service_healthy(data_dir=tmp_path,run_id=RUN,now_ms=NOW) is True
    assert exit_service_healthy(data_dir=tmp_path,run_id=RUN,now_ms=NOW) is False


def test_sidecar_blocks_legacy_fence(tmp_path):
    svc=ExitService(run_id=RUN,data_dir=tmp_path,run_commands=lambda _:None,
                    run_monitor=lambda _:MonitorReport(0,(),()))
    with svc:
        with pytest.raises(ExitServiceBusy,match='exit_service_already_running'):
            LegacyExitFence(run_id=RUN,data_dir=tmp_path).start()


def _legacy_process(folder: str, ready, release):
    with LegacyExitFence(run_id=RUN,data_dir=Path(folder)):
        ready.set()
        release.wait(timeout=10)


def test_two_processes_legacy_fence_prevents_sidecar(tmp_path):
    ctx=multiprocessing.get_context('spawn')
    ready=ctx.Event();release=ctx.Event()
    p=ctx.Process(target=_legacy_process,args=(str(tmp_path),ready,release))
    p.start()
    try:
        assert ready.wait(timeout=6)
        svc=ExitService(run_id=RUN,data_dir=tmp_path,run_commands=lambda _:None,
                        run_monitor=lambda _:MonitorReport(0,(),()))
        with pytest.raises(ExitServiceBusy):svc.start()
    finally:
        release.set();p.join(timeout=10)
    assert p.exitcode==0
    with svc:
        assert svc.tick(NOW).state=='healthy'


def _risk_worker(folder: str, symbol: str, ready, output):
    """Two different decisions compete for the remaining PAPER open-risk budget."""
    from backend.tests.test_v3_post_ai_guard import _hand
    from backend.v3.risk import RiskQuote
    j=EventJournal(Path(folder)/'journal.db')
    d=_hand(side=1,entry='100',stop='95',symbol=symbol)
    d.occurred_at_ms=NOW-1000
    d.risk_quote=RiskQuote(True,'quote_only',D('1'),D('100'),D('20'),D('5.16'),D('20'))
    d.journal_event_id='brain-decision.'+symbol
    if not ready.wait(timeout=8):
        output.put((symbol,'timeout'));return
    res=_commit(j,d,Path(folder))
    output.put((symbol,res.code))


def test_two_distinct_processes_cannot_oversubscribe_near_budget(tmp_path):
    from backend.tests.test_v3_post_ai_guard import _hand
    from backend.v3.risk import RiskQuote
    from backend.v3.events import Event
    j,_,_,_=_args(tmp_path)
    # Existing PAPER positions use 40 out of allowed 50 USDT open risk.
    # These are a synthetic fixture through the real PAPER executor, not live positions.
    for i in range(4):
        d=_hand(side=1,entry='100',stop='90',symbol=f'ALT{i}USDT')
        d.risk_quote=RiskQuote(True,'quote_only',D('1'),D('100'),D('20'),D('10.32'),D('20'))
        execute_paper(d,portfolio_id='brain',run_id=RUN,journal=j,now_ms=NOW-100)
    for symbol in ('ETHUSDT','SOLUSDT'):
        j.append(Event('brain-decision.'+symbol,'brain',RUN,'brain_decision',NOW-1000,
                       'test',{'symbol':symbol,'kind':'OPEN','status':'APPROVED',
                               'rationale':'deepseek:analysis'}))
    ctx=multiprocessing.get_context('spawn')
    ready=ctx.Event();out=ctx.Queue()
    procs=[ctx.Process(target=_risk_worker,args=(str(tmp_path),symbol,ready,out))
           for symbol in ('ETHUSDT','SOLUSDT')]
    with _real_sidecar(tmp_path) as svc:
        svc.tick(NOW)
        for p in procs:p.start()
        ready.set()
        results=dict(out.get(timeout=10) for _ in procs)
    for p in procs:
        p.join(timeout=10)
        assert p.exitcode==0
    assert list(results.values()).count('paper_open_committed')==1, results
    assert set(results.values()) <= {
        'paper_open_committed','open_lease_busy','risk_changed_after_ai','risk_rejected_after_ai'
    }
    # Even if the blocked process retries with a fresh read, budget veto remains.
    failed_symbol=next(s for s,code in results.items() if code!='paper_open_committed')
    from backend.tests.test_v3_post_ai_guard import _hand
    retry=_hand(side=1,entry='100',stop='95',symbol=failed_symbol)
    retry.occurred_at_ms=NOW-1000
    retry.risk_quote=RiskQuote(True,'quote_only',D('1'),D('100'),D('20'),D('5.16'),D('20'))
    retry.journal_event_id='brain-decision.'+failed_symbol
    assert _commit(j,retry,tmp_path).code in ('risk_changed_after_ai','risk_rejected_after_ai')
    assert len([e for e in j.list_run('brain',RUN) if e.event.kind=='paper_open'])==5


def test_callback_cannot_fake_a_real_exit_owner(tmp_path):
    j,d,_,_=_args(tmp_path)
    assert _commit(j,d,tmp_path).code=='exit_service_unhealthy'
    with LegacyExitFence(run_id=RUN,data_dir=tmp_path):
        assert _commit(j,d,tmp_path).code=='exit_service_unhealthy'
    assert len([e for e in j.list_run('brain',RUN) if e.event.kind=='paper_open'])==0
