"""Independent regression checks against Grok F2 R1.9.
Expected to PASS against the patched engine.
"""
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
import pytest
from backend.v3.events import EventJournal
from backend.v3.risk import RiskPolicy
from backend.v3.brain_f2.analyst import MockDeepSeekAnalyst
from backend.v3.brain_f2.reviewer import MockClaudeReviewer
from backend.v3.brain_f2.contracts import MarketContext, DecisionKind, ProposalStatus
from backend.v3.brain_f2.engine import BrainEngine, BrainPortfolioSnapshot, _policy_hash

CTX=MarketContext('BTCUSDT',Decimal('50000'),1700000000000,'TRENDING')
POL=RiskPolicy(Decimal('.02'),Decimal('.05'),Decimal('.1'),Decimal('.3'),Decimal('450'),Decimal('16'),Decimal('.5'))
SNAP=BrainPortfolioSnapshot(Decimal('1000'),Decimal('1000'),Decimal('0'),Decimal('0'))
MP=dict(exchange_leverage_limit=10,quantity_step=Decimal('.001'),minimum_notional=Decimal('5'),
        maintenance_fraction=Decimal('.004'),market_data_fresh=True,paused=False,daily_loss_latched=False)

def mandate(**overrides):
    m=dict(version='v1',approved=True,approved_by='operator',policy_hash=_policy_hash(POL))
    m.update(overrides)
    return m

def engine(j, m=None, **kwargs):
    args=dict(analyst=MockDeepSeekAnalyst(),reviewer=MockClaudeReviewer(always_approve=True),
              risk_policy=POL,portfolio_snapshot=SNAP,market_params=MP,
              journal=j,run_id='r19',policy_mandate=mandate() if m is None else m,
              policy_verifier=lambda m,p: True)
    args.update(kwargs)
    return BrainEngine(**args)

def real_journal(td):
    j=EventJournal(Path(td)/'events.sqlite');j.init_schema();return j

@pytest.mark.parametrize('fields', [dict(),dict(portfolio_id='brain'),dict(run_id='r19')],
                         ids=['missing_both','missing_run','missing_portfolio'])
def test_policy_mandate_requires_explicit_scope(fields):
    with TemporaryDirectory() as td:
        d=engine(real_journal(td),m=mandate(**fields)).step(CTX)
        assert d.status != ProposalStatus.APPROVED, 'Missing mandated scope must fail closed'

def test_missing_operator_identity_rejected_even_with_verifier():
    with TemporaryDirectory() as td:
        m=mandate(portfolio_id='brain',run_id='r19');del m['approved_by']
        d=engine(real_journal(td),m=m).step(CTX)
        assert d.status != ProposalStatus.APPROVED

def test_missing_journal_denial_has_no_proposal_or_risk_quote():
    # journal=None now raises ValueError at constructor (fail-closed: no journal = no engine)
    with pytest.raises(ValueError, match='journal is required'):
        engine(None, m=mandate(portfolio_id='brain', run_id='r19'))

class BrokenJournal(EventJournal):
    def append(self,e): raise OSError('synthetic-failure')

def test_journal_failure_denial_has_no_proposal_or_risk_quote():
    with TemporaryDirectory() as td:
        j=BrokenJournal(Path(td)/'events.sqlite');j.init_schema()
        d=engine(j,m=mandate(portfolio_id='brain',run_id='r19')).step(CTX)
        assert d.kind==DecisionKind.NO_TRADE and d.status != ProposalStatus.APPROVED
        assert d.proposal is None and d.risk_quote is None

def test_context_none_fails_closed_without_exception():
    with TemporaryDirectory() as td:
        d=engine(real_journal(td),m=mandate(portfolio_id='brain',run_id='r19')).step(None)
        assert d.kind==DecisionKind.NO_TRADE

def test_invalid_context_symbol_type_fails_closed():
    with TemporaryDirectory() as td:
        bad=replace(CTX,symbol=123)
        d=engine(real_journal(td),m=mandate(portfolio_id='brain',run_id='r19')).step(bad)
        assert d.kind==DecisionKind.NO_TRADE and d.status != ProposalStatus.APPROVED

def test_good_policy_proof_with_explicit_scope_produces_approval():
    with TemporaryDirectory() as td:
        d=engine(real_journal(td),m=mandate(portfolio_id='brain',run_id='r19')).step(CTX)
        assert d.kind==DecisionKind.OPEN and d.status==ProposalStatus.APPROVED
