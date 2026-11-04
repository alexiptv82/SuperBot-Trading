"""Independent adversarial Brain F2 R1.3 tests.
Expected to PASS against the patched engine.
"""
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.v3.brain_f2.analyst import Analyst, MockDeepSeekAnalyst
from backend.v3.brain_f2.contracts import BrainDecision, DecisionKind, MarketContext, ProposalStatus
from backend.v3.brain_f2.engine import BrainEngine, BrainPortfolioSnapshot
from backend.v3.brain_f2.reviewer import MockClaudeReviewer
from backend.v3.events import EventJournal
from backend.v3.risk import RiskPolicy

CTX = MarketContext("BTCUSDT", Decimal("50000"), 1700000000000, "TRENDING")

def policy():
    return RiskPolicy(Decimal(".02"), Decimal(".05"), Decimal(".1"), Decimal(".3"),
                      Decimal("450"), Decimal("16"), Decimal(".5"))

def params():
    return dict(exchange_leverage_limit=10, quantity_step=Decimal(".001"),
                minimum_notional=Decimal("5"), maintenance_fraction=Decimal(".004"),
                market_data_fresh=True, paused=False, daily_loss_latched=False)

def engine(journal=None, analyst=None, reviewer=None, **kw):
    args=dict(analyst=analyst or MockDeepSeekAnalyst(),
              reviewer=reviewer or MockClaudeReviewer(always_approve=True),
              risk_policy=policy(),
              portfolio_snapshot=BrainPortfolioSnapshot(Decimal("1000"),Decimal("1000"),
                                                       Decimal("0"), Decimal("0")),
              market_params=params(), journal=journal, run_id="audited-run")
    args.update(kw)
    args.setdefault('policy_verifier', lambda m,p: True)
    args.setdefault('policy_mandate', {'version':'r15-test','approved_by':'operator','approved':True,'policy_hash':'c31ad48159749a03'})
    return BrainEngine(**args)

class InertJournal:
    def append(self, event):
        return None

class CustomAnalyst(Analyst):
    def __init__(self, change): self.change=change
    def analyze(self, context, open_positions):
        return self.change(MockDeepSeekAnalyst().analyze(context, open_positions))

def test_noop_journal_does_not_approve():
    d=engine(journal=InertJournal()).step(CTX)
    assert d.status != ProposalStatus.APPROVED

def test_symbol_mismatch_does_not_approve():
    with TemporaryDirectory() as td:
        j=EventJournal(Path(td)/"j.sqlite");j.init_schema()
        a=CustomAnalyst(lambda d:replace(d,proposal=replace(d.proposal,symbol="ETHUSDT",confidence=.99)))
        assert engine(journal=j,analyst=a).step(CTX).status != ProposalStatus.APPROVED

def test_nonfinite_confidence_does_not_skip_reviewer():
    with TemporaryDirectory() as td:
        j=EventJournal(Path(td)/"j.sqlite");j.init_schema()
        a=CustomAnalyst(lambda d:replace(d,proposal=replace(d.proposal,confidence=float("nan"))))
        d=engine(journal=j,analyst=a,reviewer=MockClaudeReviewer(always_approve=False)).step(CTX)
        assert d.status != ProposalStatus.APPROVED

def test_no_trade_cannot_claim_executed():
    class Forged(Analyst):
        def analyze(self, context, positions):
            return BrainDecision(kind=DecisionKind.NO_TRADE,
                                 status=ProposalStatus.EXECUTED_PAPER,
                                 rationale="forged",occurred_at_ms=context.timestamp_ms)
    assert engine(analyst=Forged()).step(CTX).status != ProposalStatus.EXECUTED_PAPER

def test_untrusted_sources_not_persisted():
    with TemporaryDirectory() as td:
        j=EventJournal(Path(td)/"j.sqlite");j.init_schema()
        a=CustomAnalyst(lambda d:replace(d,sources=["Bearer synthetic-secret-123"],
                                         proposal=replace(d.proposal,confidence=.99)))
        engine(journal=j,analyst=a).step(CTX)
        records=j.list_run("brain","audited-run")
        assert "synthetic-secret-123" not in str([r.event.payload for r in records])

def test_restart_cannot_reapprove_separate_requests_on_one_event():
    with TemporaryDirectory() as td:
        path=Path(td)/"j.sqlite"
        j=EventJournal(path);j.init_schema()
        d1=engine(journal=j).step(CTX)
        d2=engine(journal=EventJournal(path)).step(CTX)
        count=len(j.list_run("brain","audited-run"))
        assert not (d1.status==ProposalStatus.APPROVED and d2.status==ProposalStatus.APPROVED and count==1)

def test_nonpositive_market_price_does_not_approve():
    class UsesSeparateQuote(Analyst):
        def analyze(self, context, positions):
            return MockDeepSeekAnalyst().analyze(CTX,positions)
    with TemporaryDirectory() as td:
        j=EventJournal(Path(td)/"j.sqlite");j.init_schema()
        d=engine(journal=j,analyst=UsesSeparateQuote()).step(replace(CTX,price=Decimal("-1")))
        assert d.status != ProposalStatus.APPROVED

def test_no_tautological_independence_assertion():
    p=Path(__file__).with_name("test_brain_f2.py")
    assert "or True" not in p.read_text()

def test_no_placeholder_close_stop_assertion():
    p=Path(__file__).with_name("test_brain_f2_safety_contract.py")
    assert "assert True" not in p.read_text()
