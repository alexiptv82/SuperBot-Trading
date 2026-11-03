"""R1.7 independent failure reproducers on R1.6, synthetic data only.
Use alongside the full downloadable ChatGPT audit ZIP with seven tests.
Untrusted policy mandate must fail closed without an external verifier.
"""
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.v3.brain_f2.analyst import Analyst, MockDeepSeekAnalyst
from backend.v3.brain_f2.contracts import BrainDecision, DecisionKind, MarketContext, OpenProposal, ProposalStatus
from backend.v3.brain_f2.engine import BrainEngine, BrainPortfolioSnapshot, _policy_hash
from backend.v3.brain_f2.reviewer import MockClaudeReviewer
from backend.v3.risk import RiskPolicy
from backend.v3.events import EventJournal

CTX = MarketContext('BTCUSDT',Decimal('50000'),1700000000000,'TRENDING')
POL = RiskPolicy(Decimal('.02'),Decimal('.05'),Decimal('.1'),Decimal('.3'),Decimal('450'),Decimal('16'),Decimal('.5'))
SNAP = BrainPortfolioSnapshot(Decimal('1000'),Decimal('1000'),Decimal('0'),Decimal('0'))
MP = dict(exchange_leverage_limit=10, quantity_step=Decimal('.001'),minimum_notional=Decimal('5'),
          maintenance_fraction=Decimal('.004'),market_data_fresh=True,paused=False,daily_loss_latched=False)

class AnalystFn(Analyst):
    def __init__(self, fn): self.fn=fn
    def analyze(self, context, open_positions): return self.fn(context,open_positions)

def run(fn=None):
    with TemporaryDirectory() as td:
        j=EventJournal(Path(td)/'j.sqlite');j.init_schema()
        analyst=AnalystFn(fn) if fn is not None else MockDeepSeekAnalyst()
        mandate=dict(version='self-claimed', approved=True, approved_by='operator', policy_hash=_policy_hash(POL))
        e=BrainEngine(analyst,MockClaudeReviewer(always_approve=True),risk_policy=POL,
                      portfolio_snapshot=SNAP,market_params=MP,journal=j,
                      run_id='r17-synthetic',policy_mandate=mandate)
        d=e.step(CTX)
        return d,str(e.memory)

def test_untrusted_policy_self_attestation_rejected():
    d,_=run()
    assert d.status != ProposalStatus.APPROVED

def test_untrusted_proposal_context_hash_removed():
    secret='SYNTHETIC_SECRET_47329'
    def fn(c,p):
        d=MockDeepSeekAnalyst().analyze(c,p)
        d.proposal=replace(d.proposal,context_hash=secret,confidence=.9)
        return d
    d,mem=run(fn)
    assert secret not in str(d) and secret not in mem

def test_dict_proposal_rationale_removed():
    secret='SYNTHETIC_SECRET_63719'
    def fn(c,p):
        d=MockDeepSeekAnalyst().analyze(c,p)
        d.proposal=replace(d.proposal,rationale={'token':secret},confidence=.9)
        return d
    d,mem=run(fn)
    assert secret not in str(d) and secret not in mem

def test_no_trade_does_not_retain_open_proposal():
    proposal=OpenProposal('BTCUSDT',1,Decimal('50000'),Decimal('49000'),2,
                          'SYNTHETIC_SECRET',.9,'deepseek','untrusted')
    def fn(c,p):return BrainDecision(kind=DecisionKind.NO_TRADE,proposal=proposal,
                                    occurred_at_ms=c.timestamp_ms)
    d,mem=run(fn)
    assert d.kind == DecisionKind.NO_TRADE and d.proposal is None
    assert 'SYNTHETIC_SECRET' not in mem

def test_malformed_origin_dict_returns_no_trade_not_exception():
    def fn(c,p):
        d=MockDeepSeekAnalyst().analyze(c,p)
        d.proposal=replace(d.proposal,originating_ai={'unexpected':'dict'})
        return d
    d,_=run(fn)
    assert d.kind==DecisionKind.NO_TRADE and d.status!=ProposalStatus.APPROVED
