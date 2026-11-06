"""Fresh-risk veto after AI; PAPER synthetic data only."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal as D

import pytest

from backend.tests.test_v3_runner_feed_monitor import _hand
from backend.v3.brain_f2.contracts import DecisionKind, ProposalStatus
from backend.v3.events import EventJournal, Event
from backend.v3.executor.paper import execute_paper
from backend.v3.risk import RiskPolicy, RiskQuote, RiskRequest, quote_paper_risk
from backend.v3.runner.post_ai_guard import recheck_paper_open

NOW=1_800_001_200_000
RUN='paper-post-ai'
RULES={'exchange_leverage_limit':10,'quantity_step':D('0.001'),
       'minimum_notional':D('5'),'maintenance_fraction':D('0.004')}
POL=RiskPolicy(D('.02'),D('.05'),D('.10'),D('.30'),D('450'),D('16'),D('.5'))


def _setup(tmp_path):
    j=EventJournal(tmp_path/'journal.db');j.init_schema()
    d=_hand(side=1,entry='100',stop='99',symbol='BTCUSDT')
    # Test helper gives an approved decision and original quote; bind it to a
    # quote from the actual risk formula rather than a fabricated permissive one.
    d.occurred_at_ms=NOW-1000
    d.risk_quote=quote_paper_risk(POL,RiskRequest(D('1000'),D('1000'),D('0'),D('0'),
          d.proposal.entry_price,d.proposal.stop_price,1,2,10,
          RULES['quantity_step'],RULES['minimum_notional'],RULES['maintenance_fraction'],True,False,False))
    assert d.risk_quote.allowed
    d.journal_event_id='brain-decision-01'
    j.append(Event(d.journal_event_id,'brain',RUN,'brain_decision',NOW-1000,
                   'test',{'symbol':d.proposal.symbol,'kind':'OPEN','status':'APPROVED',
                           'rationale':d.rationale}))
    return j,d


def _args(tmp_path):
    j,d=_setup(tmp_path)
    state={'exit':True,'paused':False,'mandate':None,'budget':None,'loss':False,
           'price':D('100'),'rules':RULES,'now':NOW,'fresh':True}
    def check():
        return recheck_paper_open(decision=d,journal=j,run_id=RUN,
            initial_equity=D('1000'),risk_policy=POL,now_ms=state['now'],
            exit_healthy=lambda t:state['exit'],
            mandate_problem=lambda:state['mandate'],budget_problem=lambda:state['budget'],
            daily_loss_halted=lambda t:state['loss'],paused=lambda:state['paused'],
            market_rules=lambda sym:state['rules'],market_price=lambda sym,t:state['price'],
            market_fresh=lambda sym,t:state['fresh'])
    return j,d,state,check


def test_decision_unjournaled_or_wrong_run_denied(tmp_path):
    j,d,state,run=_args(tmp_path)
    d.journal_event_id='fabricated'
    assert run().code=='decision_unjournaled'


def test_decision_reason_tampering_denied(tmp_path):
    j,d,state,run=_args(tmp_path)
    d.rationale='sanitized'
    assert run().code=='decision_unjournaled'


def test_decision_timestamp_tampering_denied(tmp_path):
    j,d,state,run=_args(tmp_path)
    d.occurred_at_ms=NOW-500
    assert run().code=='decision_unjournaled'


def test_decision_wrong_symbol_denied(tmp_path):
    j,d,state,run=_args(tmp_path)
    d.proposal=replace(d.proposal,symbol='ETHUSDT')
    assert run().code=='decision_unjournaled'


def test_safe_current_snapshot_is_allowed(tmp_path):
    _,_,_,run=_args(tmp_path)
    assert run().allowed is True
    assert run().code=='validated_current_paper_risk'


@pytest.mark.parametrize('field,value,code',[
    ('exit',False,'exit_service_unhealthy'),('paused',True,'brain_paused'),
    ('mandate','revoked','mandate_unavailable'),('budget','cap','budget_unavailable'),
    ('loss',True,'daily_loss_unavailable_or_halted'),('fresh',False,'market_unavailable'),('price',D('108'),'market_price_moved'),
    ('price',D('NaN'),'market_unavailable'),('rules',None,'market_rules_unavailable'),
])
def test_missing_safety_denies(tmp_path,field,value,code):
    _,_,state,run=_args(tmp_path);state[field]=value
    res=run();assert res.allowed is False and res.code==code


def test_new_position_while_ai_waited_denied_if_same_symbol(tmp_path):
    j,d,_,run=_args(tmp_path)
    from copy import deepcopy
    execute_paper(deepcopy(d),portfolio_id='brain',run_id=RUN,journal=j,now_ms=NOW-100)
    assert run().code=='already_open'


def test_occupied_risk_budget_refuses_older_quote(tmp_path):
    j,d,state,run=_args(tmp_path)
    for symbol in ('ETHUSDT','SOLUSDT','XRPUSDT'):
        other=_hand(side=1,entry='100',stop='99',symbol=symbol)
        other.risk_quote=d.risk_quote
        execute_paper(other,portfolio_id='brain',run_id=RUN,journal=j,now_ms=NOW-100)
    assert run().code in ('risk_changed_after_ai','risk_rejected_after_ai')


def test_decision_expired_before_execution(tmp_path):
    _,d,state,run=_args(tmp_path)
    d.occurred_at_ms=NOW-120_001
    assert run().code=='decision_stale'


def test_missing_quote_denied(tmp_path):
    _,d,state,run=_args(tmp_path);d.risk_quote=None
    assert run().code=='decision_not_executable'


def test_new_risk_policy_rejection(tmp_path):
    j,d,state,run=_args(tmp_path)
    state['rules']={**RULES,'exchange_leverage_limit':1}
    assert run().code=='risk_rejected_after_ai'


def test_fail_closed_on_callback_exception(tmp_path):
    j,d,state,_=_args(tmp_path)
    def boom(*_): raise RuntimeError('do not publish internal text')
    res=recheck_paper_open(decision=d,journal=j,run_id=RUN,initial_equity=D('1000'),
        risk_policy=POL,now_ms=NOW,exit_healthy=boom,mandate_problem=lambda:None,
        budget_problem=lambda:None,daily_loss_halted=lambda _:False,
        paused=lambda:False,market_rules=lambda _:RULES,market_price=lambda *_:D('100'),market_fresh=lambda *_:True)
    assert res.allowed is False and res.code=='recheck_failed'


def test_sidecar_becomes_unhealthy_second_check(tmp_path):
    j,d,state,_=_args(tmp_path)
    seen=[]
    def live(_):seen.append(1);return len(seen)==1
    r=recheck_paper_open(decision=d,journal=j,run_id=RUN,initial_equity=D('1000'),
        risk_policy=POL,now_ms=NOW,exit_healthy=live,mandate_problem=lambda:None,
        budget_problem=lambda:None,daily_loss_halted=lambda _:False,
        paused=lambda:False,market_rules=lambda _:RULES,market_price=lambda *_:D('100'),market_fresh=lambda *_:True)
    assert r.code=='safety_changed_after_ai'


def test_does_not_write_to_journal(tmp_path):
    j,d,state,run=_args(tmp_path)
    before=j.verify_chain()
    run()
    assert before==j.verify_chain()


def test_guard_not_transaction_or_execution(tmp_path):
    j,d,state,run=_args(tmp_path)
    assert run().allowed
    assert len(j.list_run('brain',RUN))==1  # only pre-existing decision, no ORDER produced


def test_corrupt_journal_denied_before_quote(tmp_path):
    import sqlite3
    j,d,state,run=_args(tmp_path)
    with sqlite3.connect(j.filename) as db:
        db.execute('DROP TRIGGER v3_no_update')
        db.execute("UPDATE v3_events SET payload_json='{}' WHERE event_id='brain-decision-01'")
    assert run().code=='recheck_failed'
