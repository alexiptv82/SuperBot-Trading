"""Final offline safety invariants: synthetic fixtures, no external clients."""
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from concurrent.futures import ThreadPoolExecutor
import pytest
from backend.v3.brain_f2.analyst import Analyst, MockDeepSeekAnalyst
from backend.v3.brain_f2.reviewer import MockClaudeReviewer
from backend.v3.brain_f2.contracts import MarketContext, DecisionKind, ProposalStatus, BrainDecision
from backend.v3.brain_f2.engine import BrainEngine, BrainPortfolioSnapshot, _policy_hash
from backend.v3.events import EventJournal
from backend.v3.risk import RiskPolicy
CTX=MarketContext('BTCUSDT',Decimal('50000'),1700000000000,'TRENDING')
POL=RiskPolicy(Decimal('.02'),Decimal('.05'),Decimal('.1'),Decimal('.3'),Decimal('450'),Decimal('16'),Decimal('.5'))
SNAP=BrainPortfolioSnapshot(Decimal('1000'),Decimal('1000'),Decimal('0'),Decimal('0'))
MP=dict(exchange_leverage_limit=10,quantity_step=Decimal('.001'),minimum_notional=Decimal('5'),maintenance_fraction=Decimal('.004'),market_data_fresh=True,paused=False,daily_loss_latched=False)
def mk(j, *, analyst=None, verifier=None, mandate=None, mp=None, snap=None, run='final-audit'):
    if mandate is None:
        mandate=dict(version='v1', approved=True, approved_by='operator', policy_hash=_policy_hash(POL),portfolio_id='brain',run_id=run)
    return BrainEngine(analyst or MockDeepSeekAnalyst(),MockClaudeReviewer(always_approve=True), risk_policy=POL,
            portfolio_snapshot=snap or SNAP, market_params=MP if mp is None else mp,
            journal=j,run_id=run,policy_mandate=mandate,policy_verifier=verifier)
def make_j(td):
    j=EventJournal(Path(td)/'j.sqlite');j.init_schema();return j

def test_real_verifier_absent_gates_open():
    with TemporaryDirectory() as td:
        j=make_j(td);d=mk(j).step(CTX)
        assert d.kind==DecisionKind.NO_TRADE and d.status!=ProposalStatus.APPROVED
        assert d.proposal is None and d.risk_quote is None

def test_real_sqlite_approval_is_only_one_proposal_event():
    with TemporaryDirectory() as td:
        j=make_j(td);d=mk(j,verifier=lambda m,p: True).step(CTX)
        assert d.kind==DecisionKind.OPEN and d.status==ProposalStatus.APPROVED
        assert d.status!=ProposalStatus.EXECUTED_PAPER
        assert len(j.list_run('brain','final-audit'))==1
        assert j.verify_chain()[0]==1
        assert len(j.list_run('hawk','final-audit'))==0

def test_duplicate_replay_is_not_reapproved():
    with TemporaryDirectory() as td:
        j=make_j(td);ver=lambda m,p: True
        a=mk(j,verifier=ver).step(CTX)
        b=mk(EventJournal(j.filename),verifier=ver).step(CTX)
        assert a.status==ProposalStatus.APPROVED and b.status!=ProposalStatus.APPROVED
        assert len(j.list_run('brain','final-audit'))==1

def test_concurrent_replays_at_most_one_approved():
    with TemporaryDirectory() as td:
        j=make_j(td)
        def work(_):return mk(EventJournal(j.filename),verifier=lambda m,p: True).step(CTX)
        with ThreadPoolExecutor(max_workers=4) as pool:
            ds=list(pool.map(work, range(4)))
        approved=sum(d.status==ProposalStatus.APPROVED for d in ds)
        assert approved<=1 and len(j.list_run('brain','final-audit'))==1

def test_nonfinite_inputs_fail_closed():
    for field in ('margin_used','existing_open_risk'):
        with TemporaryDirectory() as td:
            j=make_j(td)
            corrupt=BrainPortfolioSnapshot(Decimal('1000'),Decimal('1000'),Decimal('0'),Decimal('0'))
            setattr(corrupt, field, Decimal('NaN'))
            d=mk(j,snap=corrupt,verifier=lambda m,p: True).step(CTX)
            assert d.kind==DecisionKind.NO_TRADE and d.proposal is None and d.risk_quote is None

def test_paused_and_stale_inputs_fail_closed():
    for field in ('paused','daily_loss_latched'):
        with TemporaryDirectory() as td:
            j=make_j(td); mp=dict(MP);mp[field]=True
            d=mk(j,mp=mp,verifier=lambda m,p: True).step(CTX)
            assert d.kind==DecisionKind.NO_TRADE
    with TemporaryDirectory() as td:
        mp=dict(MP);mp['market_data_fresh']=False
        assert mk(make_j(td),mp=mp,verifier=lambda m,p: True).step(CTX).kind==DecisionKind.NO_TRADE

class ConfusedAnalyst(Analyst):
    def analyze(self,context,positions):
        return BrainDecision(kind=DecisionKind.NO_TRADE,proposal={'secret':'SYNTHETIC_PRIVATE'},
             risk_quote={'secret':'SYNTHETIC_PRIVATE'}, occurred_at_ms=context.timestamp_ms)

def test_nonactionable_never_leaks_ai_objects():
    with TemporaryDirectory() as td:
        e=mk(make_j(td), analyst=ConfusedAnalyst(),verifier=lambda m,p:True)
        d=e.step(CTX)
        assert d.kind==DecisionKind.NO_TRADE and d.proposal is None and d.risk_quote is None
        assert 'SYNTHETIC_PRIVATE' not in repr(d) and 'SYNTHETIC_PRIVATE' not in repr(e.memory)

def test_wrong_mandate_scope_rejected():
    for changes in ({'portfolio_id':'hawk'},{'run_id':'other'},{'approved_by':''},{'approved':False}):
        with TemporaryDirectory() as td:
            j=make_j(td); m=dict(version='v1',approved=True,approved_by='operator',policy_hash=_policy_hash(POL),portfolio_id='brain',run_id='final-audit');m.update(changes)
            d=mk(j,mandate=m,verifier=lambda m,p:True).step(CTX)
            assert d.kind==DecisionKind.NO_TRADE and d.proposal is None
