"""Offline contract tests. No API calls, no files, no trading or service changes."""
from __future__ import annotations

from datetime import date
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace as Obj
from unittest import TestCase
from unittest.mock import patch

from backend.v3.arena.trial_plan import PROVIDERS, build_trial_plan
from backend.v3.arena.learning_evidence import collect_arena_learning_evidence
from backend.v3.arena.read_view import _empty


class FakeJournal:
    def __init__(self, plan, *, bad_origin=False, drop_close=False):
        self.plan = plan
        self.bad_origin = bad_origin
        self.drop_close = drop_close
        self.head = sha256(plan.provider.encode()).hexdigest()
        p = "deepseek" if bad_origin else plan.provider
        event_specs = [
            ("brain_decision", {"originating_ai": p, "kind": "OPEN",
                                "status": "APPROVED", "symbol": "BTCUSDT",
                                "reason_code": "MOMENTUM_15M"}),
            ("brain_decision", {"originating_ai": p, "kind": "NO_TRADE",
                                "status": "REJECTED", "symbol": "ETHUSDT",
                                "reason_code": "RANGE_NO_EDGE"}),
            ("paper_open", {"originating_ai": p}),
            ("paper_close", {"originating_ai": p, "position_id": "position-1",
                             "reason": "manual" if plan.provider == "qwen" else "take_profit"}),
        ]
        if drop_close:
            event_specs.pop()
        self.events = [
            Obj(event=Obj(event_id=f"{kind}.{i}", kind=kind,
                          occurred_at_ms=1795000000000+i, source="brain",
                          portfolio_id="brain", run_id=plan.run_id,
                          payload=payload))
            for i, (kind, payload) in enumerate(event_specs)
        ]
        self.probes = []

    def verify_chain(self, expected_count=None, expected_head=None):
        self.probes.append((expected_count, expected_head))
        if expected_count is not None and (expected_count != len(self.events)
                                           or expected_head != self.head):
            raise ValueError("journal_does_not_match_external_manifest")
        return len(self.events), self.head

    def list_run(self, portfolio, run):
        if portfolio != "brain" or run != self.plan.run_id:
            raise ValueError("wrong_scope")
        return self.events


def report(plan, *, manual=False, skipped=()):
    outcome = Obj(run_id=plan.run_id, portfolio_id="brain",
                  originating_ai=plan.provider, link_status="linked",
                  closed_at_ms=1795000000003, is_manual=manual,
                  to_dict=lambda: {
                      "position_id": "position-1", "realized_pnl": "5.25",
                      "exit_reason": "manual" if manual else "take_profit",
                      "decision_event_id": "brain_decision.0",
                      "originating_ai": plan.provider,
                      "symbol": "BTCUSDT",
                  })
    return Obj(portfolio_id="brain", run_id=plan.run_id,
               skipped=skipped, outcomes=(outcome,),
               open_position_ids=())


class ArenaLearningEvidenceTests(TestCase):
    def setUp(self):
        self.plans = build_trial_plan(date(2026, 11, 18),
                                      root=Path("/tmp/superbot-arena-learning-contract"))
        self.journals = {p.journal: FakeJournal(p) for p in self.plans}
        self.reports = {p.run_id: report(p, manual=p.provider == "qwen")
                        for p in self.plans}
        self.t0 = 1794999999000

    def _collect(self, *, t0s=None):
        start_times = t0s or {p.provider: self.t0 for p in self.plans}
        def read(plan, now):
            return {"data_status": "VERIFIED", "trial_comparable": True,
                    "trial_start_ms": start_times[plan.provider]}
        with patch("backend.v3.arena.learning_evidence.read_wallet", side_effect=read), \
             patch("backend.v3.arena.learning_evidence.EventJournal",
                   side_effect=lambda path: self.journals[path]), \
             patch("backend.v3.arena.learning_evidence.extract_outcomes",
                   side_effect=lambda journal, portfolio, run: self.reports[run]):
            return collect_arena_learning_evidence(self.plans, 1795005000000)

    def test_verified_three_journals_preserve_all_decisions_and_manual_outcome(self):
        result = self._collect()
        self.assertEqual(result["provider_order"], list(PROVIDERS))
        self.assertEqual(result["trial_start_ms"], self.t0)
        self.assertEqual(result["status"], "OFFLINE_RESEARCH_ONLY_NOT_APPLIED_TO_MODELS")
        self.assertEqual(len(result["evidence_sha256"]), 64)
        for p in self.plans:
            part = result["providers"][p.provider]
            self.assertEqual(part["source_event_count"], 4)
            self.assertEqual(part["event_kind_counts"]["paper_close"], 1)
            self.assertEqual(len(part["decisions"]), 2)
            self.assertEqual(part["decisions"][1]["kind"], "NO_TRADE")
            self.assertEqual(len(part["closed_outcomes"]), 1)
            self.assertFalse(part["closed_outcomes"][0]["eligible_for_automatic_promotion"])
            self.assertEqual(self.journals[p.journal].probes[-1],
                             (part["source_event_count"], part["chain_head"]))
        qwen = result["providers"]["qwen"]
        self.assertEqual(qwen["manual_closed_count"], 1)
        self.assertEqual(qwen["closed_outcomes"][0]["user_reason_status"],
                         "AWAITING_USER_ANNOTATION")
        self.assertIsNone(qwen["closed_outcomes"][0]["user_reason"])

    def test_human_reason_is_included_only_for_matching_verified_manual_close(self):
        annotation = {
            "schema": "human_close_annotation_v1",
            "provider": "qwen",
            "run_id": self.plans[1].run_id,
            "position_id": "position-1",
            "close_event_id": "paper_close.3",
            "request_id": "req-1234567890123456",
            "reason": "profit_protection",
            "note": "private operator remark",
            "annotated_ms": 1795000000500,
            "source": "human_operator",
            "prev": "0" * 64,
            "hash": "f" * 64,
        }
        def records(plan):
            return [annotation] if plan.provider == "qwen" else []
        with patch("backend.v3.arena.learning_evidence.read_annotations", side_effect=records):
            result = self._collect()
        self.assertEqual(result["schema"], "arena_learning_evidence_v2")
        qwen = result["providers"]["qwen"]
        trade = qwen["closed_outcomes"][0]
        self.assertEqual(trade["user_reason"], "profit_protection")
        self.assertEqual(trade["user_reason_status"], "VERIFIED_HUMAN_ANNOTATION")
        self.assertEqual(trade["user_annotation_sha256"], "f" * 64)
        self.assertFalse(trade["eligible_for_automatic_promotion"])
        self.assertEqual(qwen["verified_human_annotation_count"], 1)
        self.assertNotIn("private operator remark", str(result))
        self.assertIsNone(result["providers"]["deepseek"]["closed_outcomes"][0]["user_reason"])

    def test_annotation_changed_during_read_invalidates_export(self):
        annotation = {
            "schema": "human_close_annotation_v1",
            "provider": "qwen",
            "run_id": self.plans[1].run_id,
            "position_id": "position-1",
            "close_event_id": "paper_close.3",
            "request_id": "req-1234567890123456",
            "reason": "trend_change",
            "note": None,
            "annotated_ms": 1795000000500,
            "source": "human_operator",
            "prev": "0" * 64,
            "hash": "f" * 64,
        }
        reads = {"qwen": 0}
        def records(plan):
            if plan.provider != "qwen":
                return []
            reads["qwen"] += 1
            return [annotation] if reads["qwen"] == 1 else []
        with patch("backend.v3.arena.learning_evidence.read_annotations", side_effect=records):
            with self.assertRaisesRegex(ValueError, "annotation_changed_during_read"):
                self._collect()

    def test_legacy_close_event_without_origin_uses_verified_open_outcome(self):
        # executor.paper_close does not repeat originating_ai on paper_close.
        self.journals[self.plans[0].journal].events[-1].event.payload.pop("originating_ai")
        output = self._collect()
        self.assertEqual(output["providers"]["deepseek"]["closed_outcomes"][0]["originating_ai"],
                         "deepseek")

    def test_t0_must_match(self):
        times = {p.provider: self.t0 for p in self.plans}
        times["minimax"] += 1000
        with self.assertRaisesRegex(ValueError, "t0_mismatch"):
            self._collect(t0s=times)

    def test_wrong_origin_blocks_entire_evidence(self):
        self.journals[self.plans[1].journal] = FakeJournal(self.plans[1],
                                                            bad_origin=True)
        with self.assertRaisesRegex(ValueError, "origin_mismatch"):
            self._collect()

    def test_missing_close_blocks_entire_evidence_instead_of_dropping_trade(self):
        self.journals[self.plans[2].journal] = FakeJournal(self.plans[2],
                                                            drop_close=True)
        with self.assertRaisesRegex(ValueError, "close_count_mismatch"):
            self._collect()

    def test_skipped_outcome_blocks_entire_evidence(self):
        p = self.plans[0]
        self.reports[p.run_id] = report(p, skipped=(Obj(code="corrupt_close"),))
        with self.assertRaisesRegex(ValueError, "skipped_outcomes"):
            self._collect()

    def test_unconfigured_wallet_has_unknown_memory_counts_not_zeros(self):
        row = _empty(self.plans[1], "NOT_CONFIGURED")
        self.assertIsNone(row["decision_count"])
        self.assertIsNone(row["no_trade_count"])
        self.assertIsNone(row["manual_close_count"])
        self.assertIsNone(row["verified_outcome_count"])
        self.assertEqual(row["learning_status"], "NOT_CONFIGURED")

    def test_winner_is_not_auto_selected_or_trained(self):
        result = self._collect()
        self.assertNotIn("winner", result)
        self.assertNotIn("primary_ai", result)
        self.assertNotIn("prompt", result)
