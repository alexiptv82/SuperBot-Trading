"""Test SINTETICI del collegamento decisione -> snapshot v2 (nessun dato reale, nessuna rete).

Il journal e' sintetico ma ha la forma reale (`v3_events`, `seq` crescente, hash per evento): quello che si prova e' che
la regola di ammissione usi l'ORDINE DI SCRITTURA e non l'orologio dichiarato, e che nulla di non provato entri nel training.
"""
import hashlib
import json
import os
import sqlite3
import unittest

import test_training as T
import snapshot_link as SL
import eligibility as EL
import schema as S

H = T.H


def ehash(eid):
    return hashlib.sha256(eid.encode()).hexdigest()


def make_journal(path, events, hashes=None, hash_column=True):
    """events: (event_id, kind, ts, payload[, run]) nell'ORDINE DI SCRITTURA (= seq). `hashes`: {event_id: hash} da imporre;
    `hash_column=False`: journal di un formato senza colonna event_hash."""
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE v3_events(seq INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT, portfolio_id TEXT, run_id TEXT,"
                " kind TEXT, occurred_at_ms INTEGER, source TEXT, payload_json TEXT, previous_hash TEXT"
                + (", event_hash TEXT)" if hash_column else ")"))
    for e in events:
        eid, kind, ts, payload = e[:4]
        run = e[4] if len(e) > 4 else "runA"
        h = (hashes or {}).get(eid, ehash(eid))
        if hash_column:
            con.execute("INSERT INTO v3_events(event_id,portfolio_id,run_id,kind,occurred_at_ms,source,payload_json,previous_hash,"
                        "event_hash) VALUES(?,?,?,?,?,?,?,?,?)", (eid, "brain", run, kind, ts, "s", json.dumps(payload), "0" * 64, h))
        else:
            con.execute("INSERT INTO v3_events(event_id,portfolio_id,run_id,kind,occurred_at_ms,source,payload_json,previous_hash)"
                        " VALUES(?,?,?,?,?,?,?,?)", (eid, "brain", run, kind, ts, "s", json.dumps(payload), "0" * 64))
    con.commit()
    con.close()


def snap(decision_id, ts, *, symbol="ETHUSDT", action="OPEN", status="APPROVED", captured=None, asof=None, features=None,
         risk=None, **over):
    p = {"schema_version": 2, "decision_event_id": decision_id, "decision_event_hash": ehash(decision_id), "decision_ts_ms": ts,
         "snapshot_captured_at_ms": ts - 1000 if captured is None else captured,
         "feature_asof_ms": ts - 60_000 if asof is None else asof, "symbol": symbol, "action": action, "status": status,
         "regime": "TRENDING", "strategy_id": "S07", "reason_code": "x",
         "features": {"rsi_1h": "55.5", "atr_pct": "0.0123"} if features is None else features,
         "risk": {"daily_loss_fraction": "0.05"} if risk is None else risk,
         "feature_source": "unverified_snapshot", "inputs_verified": False, "eligible_for_training": False}
    p.update(over)
    return p


def dec(symbol="ETHUSDT", kind="OPEN", status="APPROVED"):
    return {"kind": kind, "status": status, "symbol": symbol, "regime": "TRENDING", "strategy_id": "S07", "strategy_origin": "library"}


def opn(pid, decision_id, symbol="ETHUSDT"):
    return {"position_id": pid, "symbol": symbol, "side": 1, "fill_price": "100", "quantity": "10", "stop_price": "99", "leverage": 30,
            "originating_ai": "deepseek", "decision_event_id": decision_id}


def cls(pid):
    return {"position_id": pid, "realized_pnl": "-12.5", "fees": "1.2", "reason": "stop", "held_ms": 2 * H, "loss_exceeds_margin": False}


class Snap(T.BuilderBase):
    """Base: sostituisce il journal V3 della BuilderBase con uno proprio e rifa' l'attestazione."""

    def journal(self, events, **kw):
        os.remove(self.v3)
        make_journal(self.v3, events, **kw)
        self.anchors.clear()
        self.spec["inputs"][0]["attestation"] = T.make_attestation(
            self.p("att"), [self.p("hawk", "learning_log.jsonl"), self.p("hawk", "trade_history.jsonl")], name="b1", anchors=self.anchors)
        self.spec["inputs"][1]["attestation"] = T.make_attestation(self.p("att"), [self.v3], name="b2", anchors=self.anchors)
        return self.build()

    def row(self, res, key):
        rows = [r for r in res["rows"] if r["source_system"] == "arena_minimax" and r["example_id"] == S.example_id(
            "arena_minimax", "runA", *key)]
        self.assertEqual(len(rows), 1, key)
        return rows[0]

    def executed_events(self, **snap_kw):
        t = self.base + 2 * H
        return t, [("d2", "brain_decision", t, dec()),
                   ("s2", SL.KIND, t, snap("d2", t, **snap_kw)),
                   ("o2", "paper_open", t + 1000, opn("pos2", "d2")),
                   ("c2", "paper_close", t + 2 * H, cls("pos2"))]


class AdmissionTests(Snap):
    def test_a_valid_snapshot_written_before_the_open_gives_logged_features_but_stays_ineligible(self):
        t, ev = self.executed_events()
        r = self.row(self.journal(ev), ("executed", "pos2"))
        self.assertEqual(r["feature_source"], "logged_at_decision")
        self.assertEqual(r["features"], {"rsi_1h": 55.5, "atr_pct": 0.0123, "risk_daily_loss_fraction": 0.05})
        self.assertEqual(r["feature_asof_ms"], t - 60_000)
        self.assertEqual((r["provenance"]["snapshot_status"], r["provenance"]["link_status"]), ("admitted", "linked"))
        self.assertIn("snapshot_unverified", r["quality_flags"])
        self.assertFalse(r["eligible_for_training"])
        self.assertIn("snapshot_unverified", r["ineligible_reasons"])
        self.assertEqual(S.validate_row(r), [])

    def test_no_snapshot_keeps_the_candle_reconstruction_unchanged(self):
        t = self.base + 2 * H
        r = self.row(self.journal([("d2", "brain_decision", t, dec()), ("o2", "paper_open", t + 1000, opn("pos2", "d2")),
                                   ("c2", "paper_close", t + 2 * H, cls("pos2"))]), ("executed", "pos2"))
        self.assertEqual(r["feature_source"], "reconstructed_from_candles")
        self.assertEqual(r["provenance"]["snapshot_status"], "none")
        self.assertNotIn("snapshot_unverified", r["quality_flags"])
        self.assertNotIn("snapshot_unverified", r["ineligible_reasons"])

    def test_a_no_trade_decision_gets_its_snapshot_too(self):
        t = self.base + H
        res = self.journal([("d1", "brain_decision", t, dec(kind="NO_TRADE", status="REJECTED")),
                            ("s1", SL.KIND, t, snap("d1", t, action="NO_TRADE", status="REJECTED"))])
        r = self.row(res, ("no_trade", "d1"))
        self.assertEqual((r["feature_source"], r["provenance"]["snapshot_status"]), ("logged_at_decision", "admitted"))

    def test_a_rejected_open_decision_gets_its_snapshot_too(self):
        t = self.base + H
        res = self.journal([("d4", "brain_decision", t, dec(status="RISK_REJECTED")),
                            ("s4", SL.KIND, t, snap("d4", t, status="RISK_REJECTED"))])
        r = self.row(res, ("candidate_rejected", "d4"))
        self.assertEqual(r["provenance"]["snapshot_status"], "admitted")

    def test_snapshot_claims_of_verification_or_eligibility_are_ignored(self):
        t, ev = self.executed_events(inputs_verified=True, eligible_for_training=True, feature_source="verified")
        r = self.row(self.journal(ev), ("executed", "pos2"))
        self.assertFalse(r["eligible_for_training"])
        self.assertIn("snapshot_unverified", r["ineligible_reasons"])

    def test_the_build_is_deterministic(self):
        t, ev = self.executed_events()
        a = self.journal(ev)
        b = self.build()
        self.assertEqual([r["example_id"] for r in a["rows"]], [r["example_id"] for r in b["rows"]])
        self.assertEqual(json.dumps(a["rows"], sort_keys=True), json.dumps(b["rows"], sort_keys=True))


class LeakageTests(Snap):
    """Ogni caso e' una forma di informazione dal futuro o di legame non provato: deve essere RIFIUTATA con il codice giusto
    e le feature devono tornare alla ricostruzione da candele chiuse (mai usare lo snapshot)."""

    def rejected(self, events, key, code):
        r = self.row(self.journal(events), key)
        self.assertEqual((r["provenance"]["snapshot_status"], r["provenance"].get("snapshot_reject")), ("rejected", code))
        self.assertEqual(r["feature_source"], "reconstructed_from_candles")
        self.assertIn("snapshot_rejected", r["quality_flags"])
        self.assertNotIn("snapshot_unverified", r["ineligible_reasons"])
        self.assertNotIn("rsi_1h", r["features"])
        return r

    def test_snapshot_written_after_the_open_even_if_backdated(self):
        t = self.base + 2 * H
        ev = [("d2", "brain_decision", t, dec()), ("o2", "paper_open", t + 1000, opn("pos2", "d2")),
              ("s2", SL.KIND, t, snap("d2", t))]                                    # istante dichiarato = decisione, ma scritto dopo l'apertura
        self.rejected(ev, ("executed", "pos2"), "snapshot_after_open")

    def test_snapshot_written_after_the_outcome_is_known(self):
        t = self.base + 2 * H
        ev = [("d2", "brain_decision", t, dec()), ("o2", "paper_open", t + 1000, opn("pos2", "d2")),
              ("c2", "paper_close", t + 2 * H, cls("pos2")), ("s2", SL.KIND, t, snap("d2", t))]
        self.rejected(ev, ("executed", "pos2"), "snapshot_after_open")

    def test_no_trade_snapshot_written_after_a_later_event_is_late(self):
        t = self.base + H
        ev = [("d1", "brain_decision", t, dec(kind="NO_TRADE", status="REJECTED")),
              ("d9", "brain_decision", t + H, dec(symbol="BTCUSDT", kind="NO_TRADE", status="REJECTED")),
              ("s1", SL.KIND, t, snap("d1", t, action="NO_TRADE", status="REJECTED"))]
        self.rejected(ev, ("no_trade", "d1"), "snapshot_written_late")

    def test_a_late_event_inside_the_grace_window_does_not_reject(self):
        t = self.base + H
        ev = [("d1", "brain_decision", t, dec(kind="NO_TRADE", status="REJECTED")),
              ("x1", "paper_close", t + SL.WRITE_GRACE_MS - 1, cls("posZ")),
              ("s1", SL.KIND, t, snap("d1", t, action="NO_TRADE", status="REJECTED"))]
        r = self.row(self.journal(ev), ("no_trade", "d1"))
        self.assertEqual(r["provenance"]["snapshot_status"], "admitted")

    def test_a_late_event_just_past_the_grace_window_rejects(self):
        t = self.base + H
        ev = [("d1", "brain_decision", t, dec(kind="NO_TRADE", status="REJECTED")),
              ("x1", "paper_close", t + SL.WRITE_GRACE_MS + 1, cls("posZ")),
              ("s1", SL.KIND, t, snap("d1", t, action="NO_TRADE", status="REJECTED"))]
        self.rejected(ev, ("no_trade", "d1"), "snapshot_written_late")

    def test_snapshot_before_its_decision_in_write_order(self):
        t = self.base + 2 * H
        ev = [("s2", SL.KIND, t, snap("d2", t)), ("d2", "brain_decision", t, dec()),
              ("o2", "paper_open", t + 1000, opn("pos2", "d2")), ("c2", "paper_close", t + 2 * H, cls("pos2"))]
        self.rejected(ev, ("executed", "pos2"), "snapshot_before_decision")

    def test_snapshot_captured_after_the_decision(self):
        t, ev = self.executed_events(captured=self.base + 2 * H + 5)
        self.rejected(ev, ("executed", "pos2"), "snapshot_time_order")

    def test_features_computed_after_capture(self):
        t, ev = self.executed_events(asof=self.base + 2 * H - 500)                    # asof > captured (t - 1000)
        self.rejected(ev, ("executed", "pos2"), "snapshot_time_order")

    def test_features_without_an_asof_instant(self):
        t, ev = self.executed_events(asof=None)
        ev[1][3]["feature_asof_ms"] = None
        self.rejected(ev, ("executed", "pos2"), "snapshot_time_order")

    def test_non_integer_and_non_positive_times(self):
        for bad in ("1", 0, -5, 1.5, True):
            with self.subTest(bad=bad):
                t, ev = self.executed_events()
                ev[1][3]["snapshot_captured_at_ms"] = bad
                self.rejected(ev, ("executed", "pos2"), "snapshot_time_order")

    def test_hash_of_another_decision_is_not_accepted(self):
        t, ev = self.executed_events(decision_event_hash=ehash("other"))
        self.rejected(ev, ("executed", "pos2"), "snapshot_hash_mismatch")

    def test_missing_or_malformed_hash(self):
        for bad in (None, "", "abc", "Z" * 64, 5):
            with self.subTest(bad=bad):
                t, ev = self.executed_events(decision_event_hash=bad)
                self.rejected(ev, ("executed", "pos2"), "snapshot_hash_mismatch")

    def test_a_malformed_decision_hash_is_never_a_binding_even_when_the_snapshot_repeats_it(self):
        for bad in ("abc", "G" * 64, "A" * 64, "a" * 63):
            with self.subTest(bad=bad):
                t, ev = self.executed_events(decision_event_hash=bad)
                r = self.row(self.journal(ev, hashes={"d2": bad}), ("executed", "pos2"))
                self.assertEqual(r["provenance"].get("snapshot_reject"), "snapshot_hash_mismatch")

    def test_a_journal_without_event_hashes_cannot_bind_any_snapshot(self):
        t, ev = self.executed_events(decision_event_hash=None)
        r = self.row(self.journal(ev, hash_column=False), ("executed", "pos2"))
        self.assertEqual((r["provenance"]["snapshot_status"], r["provenance"]["snapshot_reject"]),
                         ("rejected", "snapshot_hash_mismatch"))
        self.assertEqual(r["feature_source"], "reconstructed_from_candles")

    def test_a_snapshot_event_is_not_evidence_of_time_for_other_snapshots(self):
        """Un altro snapshot (retrodatato) non fa da prova di tempo: solo gli eventi di mercato e di decisione."""
        t = self.base + H
        ev = [("d1", "brain_decision", t, dec(kind="NO_TRADE", status="REJECTED")),
              ("s9", SL.KIND, t + 3 * H, snap("ghost", t + 3 * H)),
              ("s1", SL.KIND, t, snap("d1", t, action="NO_TRADE", status="REJECTED"))]
        r = self.row(self.journal(ev), ("no_trade", "d1"))
        self.assertEqual(r["provenance"]["snapshot_status"], "admitted")

    def test_out_of_order_event_times_use_the_earliest_write_after_the_threshold(self):
        t = self.base + H
        ev = [("d1", "brain_decision", t, dec(kind="NO_TRADE", status="REJECTED")),
              ("x2", "paper_close", t + 5 * H, cls("posZ")),                              # scritto presto ma con istante lontano
              ("x1", "paper_close", t + SL.WRITE_GRACE_MS + 10, cls("posY")),            # scritto dopo, istante piu' vicino
              ("s1", SL.KIND, t, snap("d1", t, action="NO_TRADE", status="REJECTED"))]
        self.rejected(ev, ("no_trade", "d1"), "snapshot_written_late")

    def test_timestamp_symbol_and_decision_must_match(self):
        for kw, code in ((dict(decision_ts_ms=self.base + 2 * H - 1), "snapshot_ts_mismatch"),
                         (dict(symbol="BTCUSDT"), "snapshot_symbol_mismatch"),
                         (dict(action="NO_TRADE"), "snapshot_decision_mismatch"),
                         (dict(status="REJECTED"), "snapshot_decision_mismatch")):
            with self.subTest(kw=kw):
                t, ev = self.executed_events(**kw)
                self.rejected(ev, ("executed", "pos2"), code)

    def test_other_run_and_other_schema(self):
        t, ev = self.executed_events()
        ev[1] = ev[1] + ("runB",)
        self.rejected(ev, ("executed", "pos2"), "snapshot_run_mismatch")
        t, ev = self.executed_events(schema_version=1)
        self.rejected(ev, ("executed", "pos2"), "snapshot_schema")

    def test_two_snapshots_for_one_decision_are_a_conflict_and_none_is_trusted(self):
        t, ev = self.executed_events()
        ev.insert(2, ("s2b", SL.KIND, t, snap("d2", t, features={"rsi_1h": "10"})))
        self.rejected(ev, ("executed", "pos2"), "snapshot_conflict")

    def test_invalid_feature_values_are_rejected_whole(self):
        for feats in ({"rsi_1h": "NaN"}, {"rsi_1h": "inf"}, {"rsi_1h": "abc"}, {"Rsi": "1"}, {"rsi_1h": 5},
                      {"rsi_1h": "1e3"}, {"x" * 40: "1"}, {"a": "1", "b": "TESTO"}):
            with self.subTest(feats=feats):
                t, ev = self.executed_events(features=feats)
                self.rejected(ev, ("executed", "pos2"), "snapshot_features_invalid")

    def test_too_many_values_and_risk_key_collision(self):
        t, ev = self.executed_events(features={"f%d" % i: "1" for i in range(SL.MAX_VALUES + 1)})
        self.rejected(ev, ("executed", "pos2"), "snapshot_features_invalid")
        t, ev = self.executed_events(features={"risk_daily_loss_fraction": "1"}, risk={"daily_loss_fraction": "0.1"})
        self.rejected(ev, ("executed", "pos2"), "snapshot_features_invalid")

    def test_an_open_that_belongs_to_the_decision_but_precedes_the_snapshot_blocks_all_its_positions(self):
        t = self.base + 2 * H
        ev = [("d2", "brain_decision", t, dec()), ("o2", "paper_open", t + 1000, opn("pos2", "d2")),
              ("s2", SL.KIND, t, snap("d2", t)), ("o2b", "paper_open", t + 2000, opn("pos2b", "d2"))]
        self.rejected(ev, ("executed", "pos2"), "snapshot_after_open")

    def test_a_snapshot_for_an_unknown_decision_is_ignored_and_counted(self):
        t = self.base + H
        res = self.journal([("d1", "brain_decision", t, dec(kind="NO_TRADE", status="REJECTED")),
                            ("s9", SL.KIND, t, snap("ghost", t))])
        r = self.row(res, ("no_trade", "d1"))
        self.assertEqual(r["provenance"]["snapshot_status"], "none")
        st = res["per_input"]["arena_minimax"]["stats"]
        self.assertEqual(st["reader:snapshots"], 1)


class UnitTests(unittest.TestCase):
    def test_timeline_first_seq_after(self):
        tl = SL.Timeline()
        for ts, seq in ((100, 1), (300, 5), (200, 3), (300, 4)):
            tl.add("r", ts, seq)
        self.assertEqual([tl.first_seq_after("r", x) for x in (50, 100, 150, 200, 299, 300)], [1, 3, 3, 4, 4, None])
        self.assertIsNone(tl.first_seq_after("other", 0))
        tl.add("r", 400, 2)                                                           # aggiunta dopo la prima interrogazione
        self.assertEqual(tl.first_seq_after("r", 300), 2)
        ooo = SL.Timeline()                                                           # istanti non monotoni rispetto alla scrittura
        ooo.add("r", 100, 9)
        ooo.add("r", 200, 3)
        self.assertEqual((ooo.first_seq_after("r", 50), ooo.first_seq_after("r", 100), ooo.first_seq_after("r", 200)), (3, 3, None))

    def test_eligibility_vocabulary_knows_the_new_reason(self):
        self.assertIn("snapshot_unverified", EL.REASONS)
        row = {"provenance": {"input_id": "i"}, "is_synthetic": False, "features": {"a": 1}, "label_complete": True,
               "outcome": {"status": "closed"}, "quality_flags": ["snapshot_unverified"]}
        self.assertEqual(EL.reasons(row, {"i"}), ["snapshot_unverified"])
        row["quality_flags"] = []
        self.assertEqual(EL.reasons(row, {"i"}), [])


if __name__ == "__main__":
    unittest.main()
