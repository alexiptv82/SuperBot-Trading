"""Offline tests: the snapshot adapter refuses a snapshot the journal can show was NOT written at decision time.

Real V3 EventJournal on a temporary SQLite file. No exchange, no VPS, no network.
A timestamp alone proves nothing (the writer supplies it): what is checked is WRITE ORDER (journal seq).
"""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

from backend.v3.events import Event, EventConflict, EventJournal
from backend.v3.decision_snapshot_v2 import (
    SNAPSHOT_KIND, WRITE_GRACE_MS, DecisionSnapshotV2, append_snapshot, assess_link, make_snapshot_event,
)

D = Decimal
T = 1_800_000_000_000
RUN = "brain-paper"


class WriteOrderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.j = EventJournal(Path(self.tmp.name) / "journal.db")
        self.j.init_schema()
        self.decide("decision-001", T)

    def decide(self, eid, ts, symbol="BTCUSDT"):
        return self.j.append(Event(eid, "brain", RUN, "brain_decision", ts, "brain_f2_engine",
                                   {"symbol": symbol, "kind": "OPEN", "status": "APPROVED", "regime": "TREND"}))

    def open_for(self, eid, ts, pid="p1"):
        return self.j.append(Event("open-" + pid, "brain", RUN, "paper_open", ts, "paper",
                                   {"position_id": pid, "symbol": "BTCUSDT", "side": 1, "decision_event_id": eid}))

    def other(self, eid, ts, kind="paper_close"):
        return self.j.append(Event(eid, "brain", RUN, kind, ts, "paper", {"position_id": "zz"}))

    def snap(self, decision="decision-001", ts=T, **kw):
        args = dict(decision_event_id=decision, decision_ts_ms=ts, captured_at_ms=ts - 1_000, feature_asof_ms=ts - 60_000,
                    features={"rsi_15m": D("48.2")}, risk={"equity_usd": D("2000")})
        args.update(kw)
        return DecisionSnapshotV2(**args)

    def count(self):
        return len(self.j.list_run("brain", RUN))

    def refused(self, code, **kw):
        before = self.count()
        with self.assertRaisesRegex(ValueError, "^" + code + "$"):
            append_snapshot(journal=self.j, run_id=RUN, snapshot=self.snap(**kw))
        self.assertEqual(self.count(), before)                       # nothing written

    def test_snapshot_before_the_open_is_accepted(self):
        append_snapshot(journal=self.j, run_id=RUN, snapshot=self.snap())
        self.open_for("decision-001", T + 1_000)
        kinds = [r.event.kind for r in self.j.list_run("brain", RUN)]
        self.assertEqual(kinds, ["brain_decision", SNAPSHOT_KIND, "paper_open"])

    def test_backdated_snapshot_written_after_the_open_is_refused(self):
        self.open_for("decision-001", T + 1_000)
        self.refused("snapshot_after_open")                          # declared time = decision time, written later

    def test_backdated_snapshot_written_after_the_outcome_is_refused(self):
        self.open_for("decision-001", T + 1_000)
        self.other("close-1", T + 3_600_000)
        self.refused("snapshot_after_open")

    def test_an_open_of_another_decision_does_not_block(self):
        self.decide("decision-002", T + 60_000, "ETHUSDT")                          # inside the grace window
        self.open_for("decision-002", T + 61_000, "p2")
        append_snapshot(journal=self.j, run_id=RUN, snapshot=self.snap())

    def verdict(self, decision="decision-001"):
        dec = self.j.get(decision)
        snaps = [r for r in self.j.list_run("brain", RUN) if r.event.kind == SNAPSHOT_KIND
                 and r.event.payload.get("decision_event_id") == decision]
        return assess_link(dec, snaps, [], lambda t: self.j.first_seq_stamped_after("brain", RUN, t, SNAPSHOT_KIND))

    # Lateness is no longer refused at write time (20/11/2026): the snapshot is written and the canonical rule
    # (same as the dataset builder) makes it inadmissible. Refusing would turn a quality fact into a missing record.
    def test_a_later_event_beyond_the_grace_window_makes_the_snapshot_late(self):
        self.other("late-1", T + WRITE_GRACE_MS + 1)
        append_snapshot(journal=self.j, run_id=RUN, snapshot=self.snap())
        self.assertEqual(self.verdict(), "snapshot_written_late")

    def test_a_later_event_inside_or_exactly_at_the_grace_window_is_tolerated(self):
        self.other("ok-1", T + WRITE_GRACE_MS)                                      # strictly greater is late
        append_snapshot(journal=self.j, run_id=RUN, snapshot=self.snap())
        self.assertEqual(self.verdict(), "valid")

    def test_a_later_decision_event_beyond_the_grace_window_is_the_evidence_of_lateness(self):
        self.decide("decision-009", T + 5_000_000)
        append_snapshot(journal=self.j, run_id=RUN, snapshot=self.snap("decision-009", T + 5_000_000))
        # the decision-009 EVENT (not its snapshot) is a later event with a far time, so decision-001 is late
        append_snapshot(journal=self.j, run_id=RUN, snapshot=self.snap())
        self.assertEqual(self.verdict(), "snapshot_written_late")

    def test_a_snapshot_event_with_a_far_time_is_not_evidence_of_time_for_others(self):
        # a foreign snapshot (unknown decision cannot be appended through the adapter): write the raw event instead
        self.j.append(Event("raw-snap", "brain", RUN, SNAPSHOT_KIND, T + 9_000_000, "x", {"decision_event_id": "ghost"}))
        append_snapshot(journal=self.j, run_id=RUN, snapshot=self.snap())
        self.assertEqual(self.verdict(), "valid")

    def test_an_event_stamped_beyond_the_window_before_the_decision_makes_the_decision_late(self):
        # Aligned with the dataset builder (Timeline): if another writer had already stamped a time beyond
        # decision_ts + grace, the decision itself was written late; the write is allowed, the link is not valid.
        j2 = EventJournal(Path(self.tmp.name) / "j2.db")
        j2.init_schema()
        j2.append(Event("early", "brain", RUN, "paper_close", T + 10_000_000, "paper", {"position_id": "e"}))
        j2.append(Event("decision-001", "brain", RUN, "brain_decision", T, "brain_f2_engine",
                        {"symbol": "BTCUSDT", "kind": "OPEN", "status": "APPROVED"}))
        append_snapshot(journal=j2, run_id=RUN, snapshot=self.snap())
        snaps = [r for r in j2.list_run("brain", RUN) if r.event.kind == SNAPSHOT_KIND]
        verdict = assess_link(j2.get("decision-001"), snaps, [],
                              lambda t: j2.first_seq_stamped_after("brain", RUN, t, SNAPSHOT_KIND))
        self.assertEqual(verdict, "decision_written_late")

    def test_reappending_the_identical_snapshot_after_later_events_is_idempotent(self):
        first = append_snapshot(journal=self.j, run_id=RUN, snapshot=self.snap())
        self.open_for("decision-001", T + 1_000)
        self.other("late-1", T + 3_600_000)
        again = append_snapshot(journal=self.j, run_id=RUN, snapshot=self.snap())
        self.assertEqual(first.event_hash, again.event_hash)

    def test_rewriting_different_content_after_later_events_is_still_a_conflict(self):
        append_snapshot(journal=self.j, run_id=RUN, snapshot=self.snap())
        self.open_for("decision-001", T + 1_000)
        with self.assertRaises(EventConflict):
            append_snapshot(journal=self.j, run_id=RUN, snapshot=self.snap(features={"rsi_15m": D("73")}))

    def test_the_pure_builder_also_refuses_and_writes_nothing(self):
        self.open_for("decision-001", T + 1_000)
        before = self.count()
        with self.assertRaisesRegex(ValueError, "^snapshot_after_open$"):
            make_snapshot_event(journal=self.j, run_id=RUN, snapshot=self.snap())
        self.assertEqual(self.count(), before)

    def test_grace_window_matches_the_dataset_builder(self):
        self.assertEqual(WRITE_GRACE_MS, 120_000)


if __name__ == "__main__":
    unittest.main()
