"""Independent adversarial review: Brain F2 R1.8.
Expected to PASS against the patched engine.
"""
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from backend.v3.brain_f2.analyst import Analyst, MockDeepSeekAnalyst
from backend.v3.brain_f2.contracts import BrainDecision, DecisionKind, MarketContext, ProposalStatus
from backend.v3.brain_f2.engine import BrainEngine, BrainPortfolioSnapshot, _policy_hash
from backend.v3.brain_f2.reviewer import MockClaudeReviewer
from backend.v3.events import EventJournal
from backend.v3.risk import RiskPolicy

CTX=MarketContext('BTCUSDT',Decimal('50000'),1700000000000,'TRENDING')
POL=RiskPolicy(Decimal('.02'),Decimal('.05'),Decimal('.1'),Decimal('.3'),Decimal('450'),Decimal('16'),Decimal('.5'))
SNAP=BrainPortfolioSnapshot(Decimal('1000'),Decimal('1000'),Decimal('0'),Decimal('0'))
MP=dict(exchange_leverage_limit=10,quantity_step=Decimal('.001'),minimum_notional=Decimal('5'),
        maintenance_fraction=Decimal('.004'),market_data_fresh=True,paused=False,daily_loss_latched=False)

class FnAnalyst(Analyst):
    def __init__(self,fn): self.fn=fn
    def analyze(self,c,positions): return self.fn(c,positions)

def launch(fn, *, verifier=None, mandate=None):
    with TemporaryDirectory() as td:
        j=EventJournal(Path(td)/'journal.sqlite');j.init_schema()
        m=dict(portfolio_id='brain',run_id='r18',version='v1',approved=True,approved_by='operator',policy_hash=_policy_hash(POL)) if mandate is None else mandate
        e=BrainEngine(FnAnalyst(fn),MockClaudeReviewer(always_approve=True),risk_policy=POL,
            portfolio_snapshot=SNAP,market_params=MP,journal=j,run_id='r18',
            policy_mandate=m,policy_verifier=verifier)
        d=e.step(CTX)
        return d,repr(e.memory)

def patch_prop(mutator):
    def fn(c,p):
        d=MockDeepSeekAnalyst().analyze(c,p)
        d.proposal=mutator(d.proposal)
        return d
    return fn

def test_no_trade_after_invalid_origin_removes_proposal():
    d,mem=launch(patch_prop(lambda p:replace(p,originating_ai={'bad':'object'})))
    assert d.kind==DecisionKind.NO_TRADE and d.proposal is None

def test_no_trade_after_wrong_symbol_drops_untrusted_content():
    secret='SYNTHETIC_SECRET_SYMBOL_XYZ'
    d,mem=launch(patch_prop(lambda p:replace(p,symbol=secret)))
    assert d.kind==DecisionKind.NO_TRADE and d.proposal is None
    assert secret not in repr(d) and secret not in mem

def test_no_trade_after_invalid_confidence_removes_proposal():
    d,mem=launch(patch_prop(lambda p:replace(p,confidence=float('nan'))))
    assert d.kind==DecisionKind.NO_TRADE and d.proposal is None

def test_no_trade_untrusted_risk_quote_is_stripped():
    secret='SYNTHETIC_SECRET_RISK_QUOTE_999'
    def fn(c,p):
        return BrainDecision(kind=DecisionKind.NO_TRADE,risk_quote={'token':secret},
                             occurred_at_ms=c.timestamp_ms)
    d,mem=launch(fn)
    assert d.kind==DecisionKind.NO_TRADE and d.risk_quote is None
    assert secret not in repr(d) and secret not in mem

def test_open_bad_proposal_type_drops_all_untrusted_content():
    secret='SYNTHETIC_SECRET_FAKE_PROPOSAL_999'
    def fn(c,p):return BrainDecision(kind=DecisionKind.OPEN,proposal={'token':secret},occurred_at_ms=c.timestamp_ms)
    d,mem=launch(fn)
    assert d.kind==DecisionKind.NO_TRADE and d.proposal is None
    assert secret not in repr(d) and secret not in mem

def test_invalid_AI_status_type_is_normalized():
    def fn(c,p):
        return BrainDecision(kind=DecisionKind.HOLD,status={'forged':'APPROVED'},
                             occurred_at_ms=c.timestamp_ms)
    d,mem=launch(fn)
    assert isinstance(d.status,ProposalStatus) and d.status!=ProposalStatus.APPROVED

def test_truthy_non_boolean_policy_verifier_fails_closed():
    fn=lambda c,p:MockDeepSeekAnalyst().analyze(c,p)
    d,mem=launch(fn,verifier=lambda m,p:'yes')
    assert d.status!=ProposalStatus.APPROVED

def test_missing_external_verifier_rejects():
    fn=lambda c,p:MockDeepSeekAnalyst().analyze(c,p)
    d,mem=launch(fn)
    assert d.status!=ProposalStatus.APPROVED

def test_valid_injected_verifier_allows_proposal_only_not_execution():
    fn=lambda c,p:MockDeepSeekAnalyst().analyze(c,p)
    d,mem=launch(fn,verifier=lambda m,p:m['policy_hash']==_policy_hash(p) and m['approved'] is True)
    assert d.status==ProposalStatus.APPROVED and d.status!=ProposalStatus.EXECUTED_PAPER

def test_scope_mismatched_mandate_does_not_approve():
    fn=lambda c,p:MockDeepSeekAnalyst().analyze(c,p)
    m=dict(version='v1',approved=True,approved_by='operator',policy_hash=_policy_hash(POL),
           portfolio_id='hawk',run_id='unrelated')
    d,mem=launch(fn,verifier=lambda m,p:True,mandate=m)
    assert d.status!=ProposalStatus.APPROVED
