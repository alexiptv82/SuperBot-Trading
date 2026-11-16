"""Offline regression: Arena AI origins are bound to the matching PAPER run.

Current DeepSeek behavior must remain unchanged unless arena_provider is
explicitly passed. These tests do not contact providers or execute trades.
"""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, main

from backend.v3.brain_f2.contracts import (
    BrainDecision, DecisionKind, MarketContext, OpenProposal, ProposalStatus,
)
from backend.v3.brain_f2.engine import BrainEngine, _ALLOWED_ORIGINS
from backend.v3.events import EventJournal

TS = 1_795_000_000_000


def mk_engine(*, run_id: str, provider: str | None = None, journal=None) -> BrainEngine:
    return BrainEngine(
        analyst=object(), reviewer=object(),
        risk_policy=object(), portfolio_snapshot=object(),
        journal=journal if journal is not None else object(),
        portfolio_id="brain", run_id=run_id, arena_provider=provider,
    )


def decision(origin: str) -> BrainDecision:
    return BrainDecision(
        kind=DecisionKind.OPEN,
        proposal=OpenProposal(
            symbol="BTCUSDT", side=-1,
            entry_price=Decimal("100"), stop_price=Decimal("101"),
            leverage=20, rationale=origin + ":analysis",
            confidence=0.82, originating_ai=origin,
            context_hash="a"*64,
        ),
        rationale=origin + ":analysis", sources=[origin + ":analysis"],
        occurred_at_ms=TS, status=ProposalStatus.DRAFT,
    )


CTX = MarketContext(symbol="BTCUSDT", price=Decimal("100"),
                    timestamp_ms=TS, regime="TREND_DOWN")


class TestArenaEngineOrigins(TestCase):
    def test_historical_default_allowlist_remains_identical(self):
        b = mk_engine(run_id="brain-v3-paper20261111")
        self.assertIsNone(b.arena_provider)
        self.assertEqual(b.allowed_origins, _ALLOWED_ORIGINS)
        self.assertNotIn("qwen", b.allowed_origins)
        self.assertEqual(b._sanitize_rationale("deepseek:analysis"), "deepseek:analysis")
        self.assertEqual(b._sanitize_rationale("qwen:analysis"), "sanitized")

    def test_explicit_arena_provider_rejects_wrong_run_binding(self):
        for case in (
            ("brain-deepseek-paper20261116", "qwen"),
            ("brain-v3-paper20261111", "qwen"),
            ("brain-qwen-paper20261116", "minimax"),
            ("brain-qwen-paper20261116", "foo"),
        ):
            with self.subTest(case=case), self.assertRaisesRegex(
                ValueError, "invalid_arena_provider_scope"
            ):
                mk_engine(run_id=case[0], provider=case[1])

    def test_legacy_engine_will_still_reject_qwen_open(self):
        b = mk_engine(run_id="brain-v3-paper20261111")
        result = b._validate_decision(decision("qwen"), CTX)
        self.assertEqual(result.kind, DecisionKind.NO_TRADE)
        self.assertEqual(result.status, ProposalStatus.REJECTED)

    def test_qwen_run_accepts_only_qwen_provenance(self):
        b = mk_engine(run_id="brain-qwen-paper20261116", provider="qwen")
        good = b._validate_decision(decision("qwen"), CTX)
        self.assertEqual(good.kind, DecisionKind.OPEN)
        self.assertEqual(good.proposal.originating_ai, "qwen")
        self.assertEqual(good.rationale, "qwen:analysis")
        self.assertEqual(good.sources, ["qwen:analysis"])
        bad = b._validate_decision(decision("minimax"), CTX)
        self.assertEqual(bad.kind, DecisionKind.NO_TRADE)
        self.assertEqual(bad.status, ProposalStatus.REJECTED)

    def test_minimax_run_accepts_only_minimax(self):
        b = mk_engine(run_id="brain-minimax-paper20261116", provider="minimax")
        good = b._validate_decision(decision("minimax"), CTX)
        self.assertEqual(good.kind, DecisionKind.OPEN)
        other = b._validate_decision(decision("qwen"), CTX)
        self.assertEqual(other.kind, DecisionKind.NO_TRADE)

    def test_new_arena_journal_has_provider_stamp_without_changing_legacy(self):
        with TemporaryDirectory() as tmp:
            for provider, runid in (
                ("qwen", "brain-qwen-paper20261116"),
                (None, "brain-v3-paper20261111"),
            ):
                path = Path(tmp) / (provider or "old") / "journal.db"
                path.parent.mkdir()
                journal = EventJournal(path)
                journal.init_schema()
                b = mk_engine(run_id=runid, provider=provider, journal=journal)
                d = BrainDecision(
                    kind=DecisionKind.NO_TRADE,
                    occurred_at_ms=TS,
                    status=ProposalStatus.DRAFT,
                    rationale="qwen:analysis" if provider else "deepseek:analysis",
                    sources=["qwen:analysis"] if provider else ["deepseek:analysis"],
                )
                self.assertIsNotNone(b._append_durable(d, CTX))
                stored = journal.list_run("brain", runid)
                self.assertEqual(len(stored), 1)
                self.assertEqual(stored[0].event.payload.get("originating_ai"), provider)


if __name__ == "__main__":
    main()
