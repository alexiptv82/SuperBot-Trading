"""Independent R1.5 acceptance regressions for Grok Brain F2 R1.4.
Copy into backend/tests in an isolated R1.4 checkout. No VPS/network/trading.
Failures are intentional until corrected.
"""
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
import pytest

from backend.v3.events import EventJournal
from backend.v3.risk import RiskPolicy
from backend.v3.brain_f2.analyst import Analyst, MockDeepSeekAnalyst
from backend.v3.brain_f2.reviewer import MockClaudeReviewer
from backend.v3.brain_f2.contracts import BrainDecision, DecisionKind, ProposalStatus, MarketContext
from backend.v3.brain_f2.engine import BrainEngine, BrainPortfolioSnapshot

CTX=MarketContext('BTCUSDT',Decimal('50000'),1700000000000,'TRENDING')
POL=RiskPolicy(Decimal('.02'),Decimal('.05'),Decimal('.1'),Decimal('.3'),Decimal('450'),Decimal('16'),Decimal('.5'))
MP={'exchange_leverage_limit':10,'quantity_step':Decimal('.001'),'minimum_notional':Decimal('5'),
    'maintenance_fraction':Decimal('.004'),'market_data_fresh':True,'paused':False,'daily_loss_latched':False}
SNAP=BrainPortfolioSnapshot(Decimal('1000'),Decimal('1000'),Decimal('0'),Decimal('0'))

def engine(j,analyst,reviewer=None):
    return BrainEngine(analyst,reviewer or MockClaudeReviewer(always_approve=True),
        risk_policy=POL,portfolio_snapshot=SNAP,market_params=MP,journal=j,run_id='r15-test')

class Forged(Analyst):
    def __init__(self,k):self.k=k
    def analyze(self,c,p):
        return BrainDecision(kind=self.k,status=ProposalStatus.APPROVED,
                             rationale='fake',occurred_at_ms=c.timestamp_ms)

@pytest.mark.parametrize('kind',[DecisionKind.NO_TRADE,DecisionKind.HOLD])
def test_no_action_not_approved(kind):
    with TemporaryDirectory() as td:
        j=EventJournal(Path(td)/'j.sqlite');j.init_schema()
        d=engine(j,Forged(kind)).step(CTX)
        assert d.status != ProposalStatus.APPROVED

class UntrustedText(Analyst):
    def analyze(self,c,p):
        return BrainDecision(kind=DecisionKind.NO_TRADE,
            rationale='API_KEY=EXAMPLE_PRIVATE_TOKEN_123456789',occurred_at_ms=c.timestamp_ms)

def test_freeform_ai_rationale_not_exposed_or_remembered():
    with TemporaryDirectory() as td:
        j=EventJournal(Path(td)/'j.sqlite');j.init_schema()
        e=engine(j,UntrustedText())
        d=e.step(CTX)
        assert 'EXAMPLE_PRIVATE_TOKEN_123456789' not in d.rationale
        assert 'EXAMPLE_PRIVATE_TOKEN_123456789' not in str(e.memory)

class RejectingReviewer(MockClaudeReviewer):
    def __init__(self):super().__init__(always_approve=False);self.calls=0
    def review(self,d,reason):
        self.calls+=1
        return super().review(d,reason)

def test_nan_review_threshold_cannot_bypass_review():
    with TemporaryDirectory() as td:
        j=EventJournal(Path(td)/'j.sqlite');j.init_schema()
        reviewer=RejectingReviewer()
        d=engine(j,MockDeepSeekAnalyst(),reviewer).step(CTX,complexity_threshold=float('nan'))
        assert d.status != ProposalStatus.APPROVED

class CountingJournal(EventJournal):
    def __init__(self,p):super().__init__(p);self.calls=0
    def append(self,event):
        self.calls+=1
        return super().append(event)

def test_one_approved_open_has_one_append_attempt():
    with TemporaryDirectory() as td:
        j=CountingJournal(Path(td)/'j.sqlite');j.init_schema()
        d=engine(j,MockDeepSeekAnalyst()).step(CTX)
        assert d.status==ProposalStatus.APPROVED
        assert j.calls==1

def test_unapproved_unversioned_policy_cannot_approve():
    # No policy/version approval proof was supplied to F2: F1 RiskPolicy is numeric only.
    with TemporaryDirectory() as td:
        j=EventJournal(Path(td)/'j.sqlite');j.init_schema()
        d=engine(j,MockDeepSeekAnalyst()).step(CTX)
        assert d.status != ProposalStatus.APPROVED

class DictRationale(Analyst):
    def analyze(self,c,p):
        return BrainDecision(kind=DecisionKind.NO_TRADE,rationale={'bad':'type'},
                             occurred_at_ms=c.timestamp_ms)

def test_non_string_rationale_fails_closed_without_exception():
    with TemporaryDirectory() as td:
        j=EventJournal(Path(td)/'j.sqlite');j.init_schema()
        d=engine(j,DictRationale()).step(CTX)
        assert d.kind==DecisionKind.NO_TRADE and d.status!=ProposalStatus.APPROVED

def test_string_review_threshold_fails_closed_without_exception():
    with TemporaryDirectory() as td:
        j=EventJournal(Path(td)/'j.sqlite');j.init_schema()
        d=engine(j,MockDeepSeekAnalyst(),RejectingReviewer()).step(CTX,complexity_threshold='bad')
        assert d.status!=ProposalStatus.APPROVED
