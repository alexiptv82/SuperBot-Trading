"""Offline tests for Brain Unico decision snapshot v2.

Uses actual V3 EventJournal with a temporary synthetic SQLite file.
Never connects to a trading account, an exchange or the VPS.
"""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

from backend.v3.events import Event, EventConflict, EventJournal
from backend.v3.decision_snapshot_v2 import DecisionSnapshotV2, append_snapshot, make_snapshot_event

D = Decimal
T = 1_800_000_000_000


class DecisionSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.journal = EventJournal(Path(self.tmp.name) / "journal.db")
        self.journal.init_schema()
        self.source = self.journal.append(Event(
            event_id="decision-001", portfolio_id="brain", run_id="brain-paper",
            kind="brain_decision", occurred_at_ms=T, source="brain_f2_engine",
            payload={"symbol": "BTCUSDT", "kind": "NO_TRADE", "status": "REJECTED",
                     "rationale": "market_gate", "regime": "RANGING"},
        ))

    def snap(self, **kw):
        args = dict(decision_event_id="decision-001", decision_ts_ms=T,
                    captured_at_ms=T - 1_000, feature_asof_ms=T - 60_000,
                    features={"rsi_15m": D("48.2")}, risk={"equity_usd": D("2000")})
        args.update(kw)
        return DecisionSnapshotV2(**args)

    def test_append_linked_idempotently(self):
        first = append_snapshot(journal=self.journal, run_id="brain-paper", snapshot=self.snap())
        second = append_snapshot(journal=self.journal, run_id="brain-paper", snapshot=self.snap())
        self.assertEqual(first.event_hash, second.event_hash)
        self.assertEqual(len(self.journal.list_run("brain", "brain-paper")), 2)
        self.assertEqual(first.event.payload["decision_event_hash"], self.source.event_hash)
        self.assertFalse(first.event.payload["eligible_for_training"])
        self.assertFalse(first.event.payload["inputs_verified"])

    def test_rewrite_same_decision_is_conflict(self):
        append_snapshot(journal=self.journal, run_id="brain-paper", snapshot=self.snap())
        with self.assertRaises(EventConflict):
            append_snapshot(journal=self.journal, run_id="brain-paper",
                            snapshot=self.snap(features={"rsi_15m": D("73")}))

    def test_future_feature_or_late_capture_rejected(self):
        for snap in (self.snap(feature_asof_ms=T),
                     self.snap(captured_at_ms=T + 1),
                     self.snap(feature_asof_ms=None),
                     self.snap(feature_asof_ms=T - 500)):
            with self.subTest(snap=snap):
                with self.assertRaisesRegex(ValueError, "future|after_decision|asof"):
                    make_snapshot_event(journal=self.journal, run_id="brain-paper", snapshot=snap)

    def test_bad_numbers_and_no_free_text(self):
        for val in (D("NaN"), D("Infinity"), 42, "AI says buy", D("1e+50")):
            with self.subTest(val=val):
                with self.assertRaises(ValueError):
                    make_snapshot_event(journal=self.journal, run_id="brain-paper",
                                        snapshot=self.snap(features={"rsi_15m": val}))
        with self.assertRaisesRegex(ValueError, "invalid_snapshot_key"):
            make_snapshot_event(journal=self.journal, run_id="brain-paper",
                                snapshot=self.snap(features={"api key": D("1")}))

    def test_cannot_mix_runs_or_fake_decision(self):
        with self.assertRaises(ValueError):
            make_snapshot_event(journal=self.journal, run_id="brain-other", snapshot=self.snap())
        with self.assertRaises(ValueError):
            make_snapshot_event(journal=self.journal, run_id="brain-paper",
                                snapshot=self.snap(decision_event_id="decision-002"))

    def test_no_trade_with_missing_features_is_preserved(self):
        evt = make_snapshot_event(journal=self.journal, run_id="brain-paper",
                                  snapshot=self.snap(features={}, feature_asof_ms=None, risk={}))
        self.assertEqual(evt.payload["action"], "NO_TRADE")
        self.assertEqual(evt.payload["feature_source"], "none")
        self.assertFalse(evt.payload["eligible_for_training"])


    def test_real_sqlite_hash_chain_and_external_anchor(self):
        append_snapshot(journal=self.journal, run_id="brain-paper", snapshot=self.snap())
        count, head = self.journal.verify_chain()
        self.assertEqual(count, 2)
        self.assertEqual(self.journal.verify_chain(count, head), (count, head))
        with self.assertRaisesRegex(ValueError, "journal_does_not_match_external_manifest"):
            self.journal.verify_chain(count - 1, head)

    def test_invalid_no_trade_approved_cannot_be_imported(self):
        self.journal.append(Event(
            event_id="decision-002", portfolio_id="brain", run_id="brain-paper",
            kind="brain_decision", occurred_at_ms=T, source="brain_f2_engine",
            payload={"symbol": "BTCUSDT", "kind": "NO_TRADE", "status": "APPROVED"},
        ))
        with self.assertRaisesRegex(ValueError, "source_decision_invalid"):
            make_snapshot_event(journal=self.journal, run_id="brain-paper",
                                snapshot=self.snap(decision_event_id="decision-002"))
        self.assertEqual(self.journal.verify_chain()[0], 2)

    def test_open_approved_remains_unverified_for_training(self):
        self.journal.append(Event(
            event_id="decision-003", portfolio_id="brain", run_id="brain-paper",
            kind="brain_decision", occurred_at_ms=T, source="brain_f2_engine",
            payload={"symbol": "ETHUSDT", "kind": "OPEN", "status": "APPROVED"},
        ))
        evt = make_snapshot_event(journal=self.journal, run_id="brain-paper",
                                  snapshot=self.snap(decision_event_id="decision-003"))
        self.assertEqual((evt.payload["action"], evt.payload["status"]), ("OPEN", "APPROVED"))
        self.assertIs(evt.payload["inputs_verified"], False)
        self.assertIs(evt.payload["eligible_for_training"], False)

    def test_invalid_feature_and_risk_maps_leave_journal_untouched(self):
        invalid = (
            self.snap(features={"api_key": D("NaN")}),
            self.snap(features={"feature_" + str(i): D("1") for i in range(65)}),
            self.snap(risk={"unknown_balance": D("1")}),
            self.snap(risk={"equity_usd": D("-1")}),
        )
        count, head = self.journal.verify_chain()
        for snap in invalid:
            with self.subTest(snap=snap):
                with self.assertRaises(ValueError):
                    append_snapshot(journal=self.journal, run_id="brain-paper", snapshot=snap)
        self.assertEqual(self.journal.verify_chain(), (count, head))

    def test_conflicting_append_preserves_hash_chain(self):
        first = append_snapshot(journal=self.journal, run_id="brain-paper", snapshot=self.snap())
        with self.assertRaises(EventConflict):
            append_snapshot(journal=self.journal, run_id="brain-paper",
                            snapshot=self.snap(risk={"equity_usd": D("999")}))
        self.assertEqual(self.journal.verify_chain(), (2, first.event_hash))


if __name__ == "__main__":
    unittest.main()
