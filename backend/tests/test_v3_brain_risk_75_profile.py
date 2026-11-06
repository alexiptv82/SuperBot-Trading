"""Explicit approved PAPER 75-on-350 profile; old portfolios remain untouched."""
from dataclasses import replace
from decimal import Decimal as D
from pathlib import Path
import json

import pytest

from backend.v3.risk import RiskRequest, quote_paper_risk
from backend.v3.runner.config import load_default_config, load_runner_config
from backend.v3.brain_f2.engine import BrainEngine, BrainPortfolioSnapshot, _policy_hash
from backend.v3.brain_f2.analyst import MockDeepSeekAnalyst
from backend.v3.brain_f2.reviewer import MockClaudeReviewer
from backend.v3.brain_f2.contracts import BrainDecision, DecisionKind, ProposalStatus, OpenProposal, MarketContext
from backend.v3.events import EventJournal

PROFILE = Path(__file__).resolve().parents[1] / 'v3' / 'runner' / 'runner_config_brain2000_paper.json'


def profile():
    return load_runner_config(PROFILE.read_bytes()).risk_policy


def request(**changes):
    d=dict(equity=D('2000'),available_cash=D('2000'),margin_used=D(0),existing_open_risk=D(0),
           entry_price=D(100),stop_price=D('99.1'),side=1,requested_leverage=20,
           exchange_leverage_limit=50,quantity_step=D('.0001'),minimum_notional=D(5),
           maintenance_fraction=D('.005'),market_data_fresh=True,paused=False,daily_loss_latched=False)
    d.update(changes)
    return RiskRequest(**d)


def test_profile_is_fixed_to_approved_capital_and_limits():
    config=load_runner_config(PROFILE.read_bytes())
    p=config.risk_policy
    assert config.initial_equity==D('2000')
    assert p.max_loss_fraction==D('0.042857142857142857')
    assert p.max_loss_margin_fraction==D('0.214285714285714285')
    assert p.max_open_risk_fraction==D('.05')
    assert p.max_position_margin_fraction==D('.20')
    assert p.max_total_margin_fraction==D('.40')
    assert (p.min_leverage,p.max_leverage)==(20,50)
    assert p.minimum_equity==D(450)
    assert config.daily_loss_warn==D('.35') and config.daily_loss_halt==D('.50')


def test_actual_350_margin_never_risks_over_75():
    p=profile();lev=D(20);money=D(350)
    # Quote uses initial_cash / (1 + leverage*fees) to cap margin at 350.
    cash=money * (1+lev*D('0.0016'))
    # Stop adjusted to make $75 worst-case loss at 350 margin, incl costs.
    stop=D(100)*(1-((p.max_loss_margin_fraction-D('0.000000001'))/lev-D('.0016')))
    q=quote_paper_risk(p,request(available_cash=cash,stop_price=stop))
    assert q.allowed,q.reason
    assert D('349.9')<q.margin<=D(350)
    assert q.worst_case_loss_estimate<=D(75)
    assert q.worst_case_loss_estimate<=q.margin*p.max_loss_margin_fraction


def test_actual_400_margin_never_risks_over_8572():
    p=profile();lev=D(20);money=D(400)
    stop=D(100)*(1-((p.max_loss_margin_fraction-D('0.000000001'))/lev-D('.0016')))
    q=quote_paper_risk(p,request(stop_price=stop))
    assert q.allowed,q.reason
    assert q.margin<=D(400)
    assert q.worst_case_loss_estimate<=D('85.72')
    assert q.worst_case_loss_estimate<=q.margin*p.max_loss_margin_fraction


def test_leverage_is_between_20_and_50_without_exception():
    p=profile()
    assert quote_paper_risk(p,request(requested_leverage=19)).reason=='leverage_outside_profile'
    assert quote_paper_risk(p,request(requested_leverage=51,exchange_leverage_limit=75)).reason=='leverage_outside_profile'
    assert quote_paper_risk(p,request(requested_leverage=50,stop_price=D('99.85'))).allowed


def test_wide_stop_must_not_be_disguised_by_smaller_margin():
    q=quote_paper_risk(profile(), request(stop_price=D('98.5')))
    assert not q.allowed and q.reason=='margin_loss_ratio_exceeded'


def test_open_risk_5_percent_remains_portfolio_limit():
    p=profile()
    assert quote_paper_risk(p,request(existing_open_risk=D(100))).reason=='risk_budget_exhausted'
    q=quote_paper_risk(p,request(existing_open_risk=D(75)))
    assert q.allowed
    assert q.worst_case_loss_estimate<=D(25)


def test_old_config_and_mandate_policy_hash_remain_unchanged():
    old=load_default_config().risk_policy
    from hashlib import sha256
    baseline='|'.join(str(getattr(old, attr)) for attr in (
        'max_loss_fraction','max_open_risk_fraction','max_position_margin_fraction',
        'max_total_margin_fraction','minimum_equity','estimated_roundtrip_cost_bp','liquidation_buffer_fraction'))
    assert _policy_hash(old)==sha256(baseline.encode()).hexdigest()[:16]
    assert _policy_hash(profile())!=_policy_hash(old)
    assert old.max_loss_margin_fraction is None
    assert old.min_leverage==1 and old.max_leverage==125


def test_config_requires_entire_new_profile_not_partial():
    parsed=json.loads(PROFILE.read_text())
    parsed['risk_policy'].pop('min_leverage')
    with pytest.raises(ValueError,match='invalid_config'):
        load_runner_config(json.dumps(parsed).encode())
    parsed=json.loads(PROFILE.read_text())
    parsed['risk_policy']['max_leverage']=20.5
    with pytest.raises(ValueError,match='invalid_config'):
        load_runner_config(json.dumps(parsed).encode())


def make_decision(lev=50, stop=D('99.5')):
    prop=OpenProposal('BTCUSDT',1,D(100),stop,lev,'sanitized',.8,'deepseek:mock','a'*32)
    return BrainDecision(kind=DecisionKind.OPEN,proposal=prop,occurred_at_ms=1800000000000,
                         status=ProposalStatus.DRAFT,rationale='sanitized',sources=['risk:quote'])


def make_engine(tmp_path):
    journal=EventJournal(str(tmp_path/'journal.db'))
    journal.init_schema()
    return BrainEngine(MockDeepSeekAnalyst(force_no_trade=True),MockClaudeReviewer(),
        risk_policy=profile(),
        portfolio_snapshot=BrainPortfolioSnapshot(D(2000),D(2000),D(0),D(0)),
        market_params={'exchange_leverage_limit':50,'quantity_step':D('.0001'),
                       'minimum_notional':D(5),'maintenance_fraction':D('.005'),
                       'market_data_fresh':True,'paused':False,'daily_loss_latched':False},
        journal=journal,run_id='paper_profile_test')


def test_engine_adapts_leverage_down_before_rejecting(tmp_path):
    engine=make_engine(tmp_path)
    decision=make_decision(50,D('99.5'))
    result=engine._apply_risk_gate(decision,MarketContext('BTCUSDT',D(100),1800000000000,'TREND_UP'))
    assert result.status == ProposalStatus.APPROVED
    assert result.proposal.leverage == 32
    assert 'risk:leverage_adjusted' in result.sources
    assert result.risk_quote.allowed
    assert result.risk_quote.worst_case_loss_estimate<=result.risk_quote.margin*profile().max_loss_margin_fraction


def test_engine_clamps_above_50_and_below_20_after_risk_recheck(tmp_path):
    eng=make_engine(tmp_path)
    for suggested in (10,60):
        d=make_decision(suggested,D('99.85'))
        out=eng._apply_risk_gate(d,MarketContext('BTCUSDT',D(100),1800000000000,'TREND_UP'))
        assert out.status==ProposalStatus.APPROVED
        assert 20<=out.proposal.leverage<=50


def test_engine_rejects_if_even_20x_not_safe(tmp_path):
    eng=make_engine(tmp_path)
    d=make_decision(50,D('98.5'))
    out=eng._apply_risk_gate(d,MarketContext('BTCUSDT',D(100),1800000000000,'TREND_UP'))
    assert out.kind==DecisionKind.NO_TRADE
    assert out.status==ProposalStatus.RISK_REJECTED
