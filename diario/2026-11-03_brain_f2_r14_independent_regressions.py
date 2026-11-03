"""Independent safety tests for Grok Brain F2 R1.3; expected to fail until R1.4.
Only synthetic fixtures and temporary SQLite; no network, VPS or trading.
"""
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier, Thread

import pytest

from backend.v3.events import EventJournal
from backend.v3.risk import RiskPolicy
from backend.v3.brain_f2.analyst import Analyst, MockDeepSeekAnalyst
from backend.v3.brain_f2.reviewer import MockClaudeReviewer
from backend.v3.brain_f2.contracts import BrainDecision, DecisionKind, ProposalStatus, MarketContext
from backend.v3.brain_f2.engine import BrainEngine, BrainPortfolioSnapshot

CTX = MarketContext("BTCUSDT", Decimal("50000"), 1700000000000, "TRENDING")
P = RiskPolicy(Decimal(".02"),Decimal(".05"),Decimal(".1"),Decimal(".3"),Decimal("450"),Decimal("16"),Decimal(".5"))
MP = dict(exchange_leverage_limit=10,quantity_step=Decimal(".001"),minimum_notional=Decimal("5"),
          maintenance_fraction=Decimal(".004"),market_data_fresh=True,paused=False,daily_loss_latched=False)

class EditingAnalyst(Analyst):
    def __init__(self, mutate): self.mutate=mutate
    def analyze(self,c,p): return self.mutate(MockDeepSeekAnalyst().analyze(c,p))

def make_engine(journal, run="r1", *, analyst=None, policy=P, params=None, snapshot=None):
    return BrainEngine(analyst or MockDeepSeekAnalyst(), MockClaudeReviewer(always_approve=True),
        risk_policy=policy,
        portfolio_snapshot=snapshot or BrainPortfolioSnapshot(Decimal("1000"),Decimal("1000"),Decimal("0"),Decimal("0")),
        market_params=MP if params is None else params, journal=journal, run_id=run)

@pytest.mark.parametrize("field", ["margin_used","existing_open_risk"])
def test_nonfinite_portfolio_field_rejected(field):
    with TemporaryDirectory() as td:
        j=EventJournal(Path(td)/"j.sqlite");j.init_schema()
        data=dict(equity=Decimal("1000"),available_cash=Decimal("1000"),margin_used=Decimal("0"),existing_open_risk=Decimal("0"))
        data[field]=Decimal("NaN")
        d=make_engine(j,snapshot=BrainPortfolioSnapshot(**data)).step(CTX)
        assert d.status != ProposalStatus.APPROVED, "nonfinite input treated as zero risk"

@pytest.mark.parametrize("field", ["maintenance_fraction","minimum_notional"])
def test_nonfinite_market_field_rejected(field):
    with TemporaryDirectory() as td:
        j=EventJournal(Path(td)/"j.sqlite");j.init_schema()
        mp=dict(MP);mp[field]=Decimal("NaN")
        d=make_engine(j,params=mp).step(CTX)
        assert d.status != ProposalStatus.APPROVED, "nonfinite market param treated as zero"

class InertSubclass(EventJournal):
    def append(self,event): return None

def test_inert_journal_subclass_must_not_approve():
    with TemporaryDirectory() as td:
        j=InertSubclass(Path(td)/"j.sqlite");j.init_schema()
        d=make_engine(j).step(CTX)
        assert d.status != ProposalStatus.APPROVED and not j.list_run("brain","r1")

def test_large_entry_price_divergence_must_reject():
    with TemporaryDirectory() as td:
        j=EventJournal(Path(td)/"j.sqlite");j.init_schema()
        a=EditingAnalyst(lambda d: replace(d,proposal=replace(d.proposal,entry_price=Decimal("1000"),
                                                               stop_price=Decimal("980"),confidence=.99)))
        assert make_engine(j,analyst=a).step(CTX).status != ProposalStatus.APPROVED

class InvalidKind(Analyst):
    def analyze(self,c,p): return BrainDecision(kind="not_enum",occurred_at_ms=c.timestamp_ms)

def test_invalid_kind_returns_no_trade():
    with TemporaryDirectory() as td:
        j=EventJournal(Path(td)/"j.sqlite");j.init_schema()
        d=make_engine(j,analyst=InvalidKind()).step(CTX)
        assert d.kind == DecisionKind.NO_TRADE and d.status != ProposalStatus.APPROVED

class InvalidSources(Analyst):
    def analyze(self,c,p): return BrainDecision(kind=DecisionKind.NO_TRADE,
        sources=[{"malformed":"dict"}],occurred_at_ms=c.timestamp_ms)

def test_unhashable_source_fails_closed_not_crash():
    with TemporaryDirectory() as td:
        j=EventJournal(Path(td)/"j.sqlite");j.init_schema()
        d=make_engine(j,analyst=InvalidSources()).step(CTX)
        assert d.kind == DecisionKind.NO_TRADE and d.status != ProposalStatus.APPROVED

class SensitiveRationale(Analyst):
    def analyze(self,c,p): return BrainDecision(kind=DecisionKind.NO_TRADE,
        rationale="Authorization: Bearer synthetic-sensitive-123",occurred_at_ms=c.timestamp_ms)

def test_untrusted_rationale_sanitized_in_return_and_memory():
    with TemporaryDirectory() as td:
        j=EventJournal(Path(td)/"j.sqlite");j.init_schema()
        e=make_engine(j,analyst=SensitiveRationale())
        d=e.step(CTX)
        assert "synthetic-sensitive-123" not in d.rationale
        assert "synthetic-sensitive-123" not in str(e.memory)

class SynchronizingJournal(EventJournal):
    barrier=Barrier(2)
    def __init__(self,path): super().__init__(path);self.first=True
    def list_run(self,portfolio_id,run_id):
        rows=super().list_run(portfolio_id,run_id)
        if self.first:
            self.first=False
            self.barrier.wait(timeout=5)
        return rows

def test_concurrent_duplicate_request_not_twice_approved():
    with TemporaryDirectory() as td:
        path=Path(td)/"j.sqlite";EventJournal(path).init_schema()
        decisions=[];errors=[]
        def worker():
            try: decisions.append(make_engine(SynchronizingJournal(path)).step(CTX))
            except Exception as exc: errors.append(type(exc).__name__)
        threads=[Thread(target=worker) for _ in range(2)]
        for t in threads: t.start()
        for t in threads: t.join(timeout=10)
        assert not errors
        count=len(EventJournal(path).list_run("brain","r1"))
        approvals=sum(d.status == ProposalStatus.APPROVED for d in decisions)
        assert approvals <= count, (approvals,count)
