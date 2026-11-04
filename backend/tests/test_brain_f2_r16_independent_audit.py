"""Independent R1.6 acceptance checks.
Expected to PASS against the patched engine.
"""
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.v3.brain_f2.analyst import Analyst, MockDeepSeekAnalyst
from backend.v3.brain_f2.contracts import MarketContext, ProposalStatus
from backend.v3.brain_f2.engine import BrainEngine, BrainPortfolioSnapshot
from backend.v3.brain_f2.reviewer import MockClaudeReviewer
from backend.v3.events import EventJournal
from backend.v3.risk import RiskPolicy

CTX=MarketContext("BTCUSDT", Decimal("50000"), 1700000000000, "TRENDING")
POL=RiskPolicy(Decimal(".02"),Decimal(".05"),Decimal(".1"),Decimal(".3"),Decimal("450"),Decimal("16"),Decimal(".5"))
MP=dict(exchange_leverage_limit=10,quantity_step=Decimal(".001"),
        minimum_notional=Decimal("5"),maintenance_fraction=Decimal(".004"),
        market_data_fresh=True,paused=False,daily_loss_latched=False)
SNAP=BrainPortfolioSnapshot(Decimal("1000"),Decimal("1000"),Decimal("0"),Decimal("0"))
# Hash computed for the standard policy above
MANDATE=dict(portfolio_id='brain',run_id='r16-synthetic',version="signed-v1",approved_by="operator",approved=True,policy_hash="c31ad48159749a03")

class EditedAnalyst(Analyst):
    def __init__(self,f): self.f=f
    def analyze(self,ctx,positions): return self.f(MockDeepSeekAnalyst().analyze(ctx,positions))

def journal(td):
    j=EventJournal(Path(td)/"journal.sqlite");j.init_schema();return j

def make(j,analyst=None,**changes):
    args=dict(analyst=analyst or MockDeepSeekAnalyst(),reviewer=MockClaudeReviewer(always_approve=True),
              risk_policy=POL,portfolio_snapshot=SNAP,market_params=MP,
              journal=j,run_id="r16-synthetic",policy_verifier=lambda m,p: m.get('approved') is True and m.get('approved_by') in ('operator','system-admin'),policy_mandate=MANDATE)
    args.update(changes)
    return BrainEngine(**args)

def test_proposal_text_not_exposed_return_or_memory():
    secret="TOKEN_NOT_FOR_LOGS_SYNTHETIC_1234"
    a=EditedAnalyst(lambda d:replace(d,proposal=replace(d.proposal,
        rationale="API_KEY="+secret,confidence=Decimal(".9"))))
    with TemporaryDirectory() as td:
        e=make(journal(td),a)
        d=e.step(CTX)
        assert d.status == ProposalStatus.APPROVED
        assert secret not in str(d)
        assert secret not in str(e.memory)

def test_unverified_ai_origin_not_approved():
    a=EditedAnalyst(lambda d:replace(d,proposal=replace(d.proposal,
        originating_ai="external_unverified_provider",confidence=.9)))
    with TemporaryDirectory() as td:
        assert make(journal(td),a).step(CTX).status != ProposalStatus.APPROVED

def test_stale_ai_decision_timestamp_not_approved():
    a=EditedAnalyst(lambda d:replace(d,occurred_at_ms=CTX.timestamp_ms-86400000,
        proposal=replace(d.proposal,confidence=.9)))
    with TemporaryDirectory() as td:
        assert make(journal(td),a).step(CTX).status != ProposalStatus.APPROVED

def test_mandate_binds_to_policy_values():
    with TemporaryDirectory() as td:
        j=journal(td)
        original=make(j).step(CTX)
        changed=replace(POL,max_loss_fraction=Decimal(".01"))
        altered=make(j,risk_policy=changed,run_id="new-run").step(CTX)
        assert original.status == ProposalStatus.APPROVED
        assert altered.status != ProposalStatus.APPROVED

def test_self_attested_untrusted_approver_not_accepted():
    with TemporaryDirectory() as td:
        mandate=dict(version="random",approved_by="unverified-stranger",approved=True,policy_hash="c31ad48159749a03")
        assert make(journal(td),policy_verifier=lambda m,p: m.get('approved') is True and m.get('approved_by') in ('operator','system-admin'),policy_mandate=mandate).step(CTX).status != ProposalStatus.APPROVED

def test_string_review_threshold_rejected():
    with TemporaryDirectory() as td:
        assert make(journal(td)).step(CTX,complexity_threshold="0.7").status != ProposalStatus.APPROVED

def test_no_approved_open_when_run_id_omitted():
    with TemporaryDirectory() as td:
        e=BrainEngine(MockDeepSeekAnalyst(),MockClaudeReviewer(always_approve=True),
             risk_policy=POL,portfolio_snapshot=SNAP,market_params=MP,
             journal=journal(td),policy_verifier=lambda m,p: m.get('approved') is True and m.get('approved_by') in ('operator','system-admin'),policy_mandate=MANDATE)
        assert e.step(CTX).status != ProposalStatus.APPROVED

def test_unapproved_mandate_rejected():
    with TemporaryDirectory() as td:
        assert make(journal(td),policy_verifier=lambda m,p: m.get('approved') is True and m.get('approved_by') in ('operator','system-admin'),policy_mandate=dict(version="v1",approved_by="operator",approved=False,policy_hash="c31ad48159749a03")).step(CTX).status != ProposalStatus.APPROVED

def test_approved_is_not_executed_paper():
    with TemporaryDirectory() as td:
        d=make(journal(td)).step(CTX)
        assert d.status == ProposalStatus.APPROVED
        assert d.status != ProposalStatus.EXECUTED_PAPER
