"""Independent adversarial regression tests for Grok Brain F2 R1.2.
Expected to PASS against the patched engine. Synthetic data only.
"""
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
import pytest
from backend.v3.brain_f2.analyst import Analyst, MockDeepSeekAnalyst
from backend.v3.brain_f2.reviewer import MockClaudeReviewer
from backend.v3.brain_f2.contracts import MarketContext, DecisionKind, ProposalStatus
from backend.v3.brain_f2.engine import BrainEngine, BrainPortfolioSnapshot
from backend.v3.risk import RiskPolicy
from backend.v3.events import EventJournal


def context(): return MarketContext('BTCUSDT',Decimal('50000'),1700000000000,'TRENDING')
def policy(floor='450'):
    return RiskPolicy(Decimal('.02'),Decimal('.05'),Decimal('.1'),Decimal('.3'),Decimal(floor),Decimal('16'),Decimal('.5'))
def snapshot(): return BrainPortfolioSnapshot(Decimal('1000'),Decimal('1000'),Decimal('0'),Decimal('0'))
def params():
    return {'exchange_leverage_limit':10,'quantity_step':Decimal('.001'),
            'minimum_notional':Decimal('5'),'maintenance_fraction':Decimal('.004'),
            'market_data_fresh':True, 'paused': False, 'daily_loss_latched': False}
def engine(**kw):
    args={'analyst':MockDeepSeekAnalyst(), 'reviewer':MockClaudeReviewer(always_approve=True),
          'risk_policy':policy(),'portfolio_snapshot':snapshot(),'market_params':params()}
    args.update(kw)
    args.setdefault('policy_verifier', lambda m,p: True)
    args.setdefault('policy_mandate', {'version':'r15-test','approved_by':'operator','approved':True,'policy_hash':'c31ad48159749a03'})
    return BrainEngine(**args)

def test_must_not_approve_without_persistent_journal():
    decision=engine(journal=None).step(context())
    assert not (decision.kind==DecisionKind.OPEN and decision.status==ProposalStatus.APPROVED), 'Approved OPEN without journal'

def test_paused_state_must_be_explicit():
    # market_params lacks paused and daily_loss_latched
    mp = params()
    del mp['paused']
    del mp['daily_loss_latched']
    decision=engine(market_params=mp).step(context())
    assert decision.kind==DecisionKind.NO_TRADE, 'Missing pause state was assumed false'

@pytest.mark.parametrize('floor', ['NaN','Infinity'])
def test_malformed_floor_fails_closed_without_crashing(floor):
    decision=engine(risk_policy=policy(floor)).step(context())
    assert decision.kind==DecisionKind.NO_TRADE

class SensitiveError(Analyst):
    def analyze(self, context, open_positions):
        raise RuntimeError('SensitiveHeader=example-private-credential-value')

def test_provider_exception_text_is_not_reflected():
    decision=engine(analyst=SensitiveError()).step(context())
    assert 'example-private-credential-value' not in decision.rationale

def test_brain_engine_refuses_cross_portfolio_journal_writes():
    with TemporaryDirectory() as td:
        journal=EventJournal(Path(td)/'j.sqlite');journal.init_schema()
        decision=engine(analyst=MockDeepSeekAnalyst(force_no_trade=True),journal=journal,portfolio_id='hawk').step(context())
        assert not journal.list_run('hawk','brain-f2-offline'), 'Brain engine wrote Hawk event'

def test_missing_pause_state_rejected_even_with_real_journal():
    with TemporaryDirectory() as td:
        journal=EventJournal(Path(td)/'j.sqlite');journal.init_schema()
        mp = params()
        del mp['paused']
        del mp['daily_loss_latched']
        decision=engine(journal=journal, market_params=mp).step(context())
        assert decision.kind == DecisionKind.NO_TRADE, 'Missing pause/latch flags approved despite real journal'

class ReturnsNone(Analyst):
    def analyze(self, context, open_positions): return None

def test_malformed_analyst_return_fails_closed_without_crash():
    decision=engine(analyst=ReturnsNone()).step(context())
    assert decision.kind == DecisionKind.NO_TRADE

class InvalidReviewer(MockClaudeReviewer):
    def review(self, decision, complexity_reason): return None

def test_malformed_reviewer_return_fails_closed_without_crash():
    decision=engine(reviewer=InvalidReviewer()).step(context(),complexity_threshold=.9)
    assert decision.kind == DecisionKind.NO_TRADE
