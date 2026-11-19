"""Test SINTETICI dell'audit dei limiti di rischio (nessun dato reale)."""
import decimal
import hashlib
import json
import os
import sqlite3
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import risk_audit as ra  # noqa: E402

DAY = 86_400_000
H = 3_600_000
T0 = 1_795_000_000_000 // DAY * DAY + 3 * H          # un istante UTC comodo (inizio giornata + 3h)
Decimal_ = decimal.Decimal
POLICY = {"initial_equity": "2000", "daily_loss_warn_fraction": "0.35", "daily_loss_halt_fraction": "0.50",
          "risk_policy": {"max_loss_fraction": "0.042857142857142857", "max_open_risk_fraction": "0.12",
                          "max_position_margin_fraction": "0.20", "max_total_margin_fraction": "0.55",
                          "minimum_equity": "450", "estimated_roundtrip_cost_bp": "16",
                          "max_loss_margin_fraction": "0.214285714285714285", "min_leverage": 20, "max_leverage": 50}}


def sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


class Journal:
    def __init__(self, test):
        self.tmp = tempfile.TemporaryDirectory()
        test.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "journal.db")
        self.con = sqlite3.connect(self.path)
        self.con.execute("CREATE TABLE v3_events(seq INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT, portfolio_id TEXT,"
                         " run_id TEXT, kind TEXT, occurred_at_ms INTEGER, source TEXT, payload_json TEXT,"
                         " previous_hash TEXT, event_hash TEXT)")
        self.n = 0

    def add(self, kind, ts, payload):
        self.n += 1
        self.con.execute("INSERT INTO v3_events(event_id,portfolio_id,run_id,kind,occurred_at_ms,source,payload_json,"
                         "previous_hash,event_hash) VALUES(?,?,?,?,?,?,?,?,?)",
                         (f"e{self.n}", "brain", "r", kind, ts, "s", json.dumps(payload), "0" * 64, "0" * 64))
        self.con.commit()

    def open(self, pid, ts, *, risk_loss=30, fill=100, lev=30, margin=None, symbol="BTCUSDT"):
        """Long con stop allo 0,5 %: perdita allo stop = risk_loss (costi esclusi). Con risk_loss=30: rischio incl. costi
        39,6 = 1,98 % di 2000 e 19,8 % del margine (leva 30): DENTRO la politica (tetti 4,29 % del capitale, 21,4 % del margine)."""
        stop = Decimal_(fill) - Decimal_("0.5")
        qty = risk_loss / 0.5
        notional = fill * qty
        self.add("paper_open", ts, {"position_id": pid, "symbol": symbol, "side": 1, "fill_price": str(fill),
                                    "quantity": str(qty), "notional": str(notional),
                                    "margin_used": str(margin if margin is not None else notional / lev),
                                    "leverage": lev, "stop_price": str(stop), "rationale": "testo da non esportare"})

    def close(self, pid, ts, realized, reason="stop", held_ms=H, lem=False):
        self.add("paper_close", ts, {"position_id": pid, "realized_pnl": str(realized), "fees": "1", "reason": reason,
                                     "held_ms": held_ms, "loss_exceeds_margin": lem})

    def decision(self, ts, kind="NO_TRADE", status="REJECTED"):
        self.add("brain_decision", ts, {"kind": kind, "status": status, "symbol": "ETHUSDT", "rationale": "x"})

    def run(self, **kw):
        return ra.analyze_db(self.path, POLICY, **kw)


class RiskAudit(unittest.TestCase):
    def J(self):
        return Journal(self)

    def test_compliant_journal_holds_limits(self):
        j = self.J()
        j.open("a", T0, risk_loss=30)
        j.close("a", T0 + H, -42)
        r = j.run()
        self.assertEqual(r["verdict"]["no_breach_proven"], True)
        self.assertEqual((r["verdict"]["hard_flags"], r["verdict"]["soft_flags"]), ([], []))
        self.assertEqual((r["trades"]["opened"], r["trades"]["closed"], r["trades"]["still_open"]), (1, 1, 0))
        self.assertEqual(r["trades"]["realized_pnl"], "-42.0000")
        self.assertLess(float(r["ratios_vs_limit"]["risk_ratio"]), 1)

    def test_per_position_risk_clearly_over_cap_is_hard_flag(self):
        j = self.J()
        j.open("a", T0, risk_loss=140)                      # ~7,5 % di 2000: ben oltre 4,29 %
        r = j.run()
        self.assertIn("per_position_risk_clearly_over_cap", r["verdict"]["hard_flags"])
        self.assertFalse(r["verdict"]["no_breach_proven"])
        self.assertEqual(r["violations_or_flags"]["risk_over_cap_10pct"], 1)

    def test_margin_loss_cap_is_checked(self):
        j = self.J()
        j.open("a", T0, risk_loss=30, margin=100)           # 39,6/100 = 40 % del margine > 21,4 %
        self.assertIn("per_position_risk_clearly_over_cap", j.run()["verdict"]["hard_flags"])

    def test_aggregate_open_risk_over_limit(self):
        j = self.J()
        for i in range(5):
            j.open(f"p{i}", T0 + i, risk_loss=40)           # 5 x 52,8 = 264 > 12 % di 2000 (e margine 66 % > 55 %)
        r = j.run()
        self.assertGreaterEqual(r["violations_or_flags"]["open_risk_over"], 1)
        self.assertIn("aggregate_risk_or_margin_over_limit_indicative", r["verdict"]["hard_flags"])

    def test_leverage_out_of_range(self):
        for lev in (10, 60):
            j = self.J()
            j.open("a", T0, lev=lev)
            r = j.run()
            self.assertEqual(r["violations_or_flags"]["leverage_out_of_range"], 1, lev)
            self.assertIn("leverage_out_of_policy_range", r["verdict"]["hard_flags"])

    def test_open_at_or_below_equity_floor(self):
        j = self.J()
        j.open("a", T0, risk_loss=30)
        j.close("a", T0 + H, -1600)                         # equity 400 <= 450
        j.open("b", T0 + 2 * H, risk_loss=5)
        r = j.run()
        self.assertEqual(r["violations_or_flags"]["open_below_floor"], 1)
        self.assertIn("open_at_or_below_minimum_equity", r["verdict"]["hard_flags"])

    def test_minus_800_inside_limits_is_not_a_violation(self):
        """-800 (40 %) distribuiti su due giorni UTC, ogni posizione dentro il tetto: i limiti HANNO retto."""
        j = self.J()
        for i in range(20):
            ts = T0 + (i % 10) * 2 * H + (DAY if i >= 10 else 0)
            j.open(f"p{i}", ts, risk_loss=30)
            j.close(f"p{i}", ts + H, -40)                   # 20 stop da 40: sempre sotto il tetto (>= 53 anche a 1240)
        r = j.run()
        self.assertEqual(r["trades"]["realized_pnl"], "-800.0000")
        self.assertEqual(r["equity_realized_only"]["now"], "1200.0000")
        self.assertTrue(r["verdict"]["no_breach_proven"], r["verdict"])
        self.assertEqual(r["daily_guard_lower_bound"]["days_at_or_over_halt"], 0)
        self.assertEqual(r["violations_or_flags"]["realized_loss_over_cap"], 0)

    def test_daily_warn_without_halt_is_allowed_by_design(self):
        j = self.J()
        j.open("a", T0, risk_loss=30)
        j.close("a", T0 + H, -750)                          # 37,5 % del capitale di inizio giornata
        r = j.run()
        g = r["daily_guard_lower_bound"]
        self.assertEqual((g["days_at_or_over_warn"], g["days_at_or_over_halt"]), (1, 0))
        self.assertEqual(r["violations_or_flags"]["opens_after_daily_halt_proof"], 0)

    def test_open_after_daily_halt_is_proven_violation_but_next_day_is_fine(self):
        j = self.J()
        j.open("a", T0, risk_loss=30)
        j.close("a", T0 + H, -1100)                         # 55 % >= 50 % blocco
        j.open("b", T0 + 2 * H, risk_loss=5)                # stesso giorno UTC: vietato
        j.open("c", T0 + DAY, risk_loss=5)                 # giorno dopo: il blocco e' scaduto
        r = j.run()
        self.assertEqual(r["violations_or_flags"]["opens_after_daily_halt_proof"], 1)
        self.assertIn("opens_after_daily_halt_proven_by_realized_only", r["verdict"]["hard_flags"])
        self.assertEqual(r["daily_guard_lower_bound"]["days_at_or_over_halt"], 1)

    def test_realized_loss_over_cap_is_soft_flag_only(self):
        j = self.J()
        j.open("a", T0, risk_loss=30)
        j.close("a", T0 + H, -150)                          # gap/slippage: 150/2000/4,29 % = 1,75
        r = j.run()
        self.assertEqual((r["violations_or_flags"]["realized_loss_over_cap"],
                          r["violations_or_flags"]["realized_loss_over_cap_150pct"]), (1, 1))
        self.assertIn("realized_loss_over_cap_gap_or_slippage", r["verdict"]["soft_flags"])
        self.assertTrue(r["verdict"]["no_breach_proven"])        # il tetto e' una stima: non e' una violazione certa

    def test_orphan_and_duplicate_closes(self):
        j = self.J()
        j.close("ghost", T0, -10)
        j.open("a", T0 + 1)
        j.close("a", T0 + H, -10)
        j.close("a", T0 + 2 * H, -10)
        r = j.run()
        self.assertEqual((r["violations_or_flags"]["orphan_closes"], r["violations_or_flags"]["duplicate_closes"]), (1, 1))
        self.assertIn("journal_consistency_problem", r["verdict"]["hard_flags"])
        self.assertEqual(r["trades"]["closed"], 2)

    def test_open_positions_age_and_status_helper(self):
        j = self.J()
        j.open("a", T0)
        j.open("b", T0 + H)
        j.close("b", T0 + 2 * H, 5)
        j.decision(T0 + 10 * H)
        r = j.run()
        self.assertEqual((r["trades"]["still_open"], r["trades"]["oldest_open_age_hours"]), (1, "10.0000"))
        st = ra.open_positions_status(j.path)
        self.assertEqual((st["opened"], st["closed"], st["open_now"], st["orphan_closes"]), (2, 1, 1, 0))
        self.assertEqual(st["last_event_ms"], T0 + 10 * H)

    def test_manual_close_hold_time_and_reasons(self):
        j = self.J()
        j.open("a", T0)
        j.close("a", T0 + H, -5, reason="manual")
        j.open("b", T0 + 2 * H)
        j.close("b", T0 + 40 * H, -5, reason="timeout", held_ms=38 * H, lem=True)
        r = j.run()
        self.assertEqual(r["trades"]["exit_reasons"], {"manual": 1, "timeout": 1})
        v = r["violations_or_flags"]
        self.assertEqual((v["manual_closes"], v["held_over_max"], v["loss_exceeds_margin"]), (1, 1, 1))
        self.assertIn("positions_held_over_policy_max_hold", r["verdict"]["soft_flags"])

    def test_decisions_counted_including_no_trade(self):
        j = self.J()
        j.decision(T0, "NO_TRADE", "REJECTED")
        j.decision(T0 + 1, "NO_TRADE", "REJECTED")
        j.decision(T0 + 2, "OPEN", "APPROVED")
        self.assertEqual(j.run()["decisions"], {"NO_TRADE:REJECTED": 2, "OPEN:APPROVED": 1})

    def test_empty_or_missing_table_does_not_crash(self):
        j = self.J()
        r = j.run()
        self.assertEqual((r["trades"]["opened"], r["window"]["first_event_ms"], r["verdict"]["no_breach_proven"]), (0, None, True))
        with tempfile.TemporaryDirectory() as t:
            p = os.path.join(t, "x.db")
            sqlite3.connect(p).execute("CREATE TABLE other(a)").connection.close()
            self.assertEqual(ra.read_events(p), [])

    def test_output_is_numbers_only_and_source_untouched(self):
        j = self.J()
        j.open("secret-position-id", T0, symbol="SECRETUSDT")
        j.close("secret-position-id", T0 + H, -5)
        h = sha(j.path)
        text = json.dumps(j.run())
        for leak in ("secret-position-id", "SECRETUSDT", "testo da non esportare", "BTCUSDT"):
            self.assertNotIn(leak, text)
        self.assertEqual(h, sha(j.path))

    def test_exit_policy_hold_hours_is_parametrised(self):
        j = self.J()
        j.open("a", T0)
        j.close("a", T0 + 10 * H, -5, held_ms=10 * H)
        self.assertEqual(j.run(exit_max_hold_hours=24)["violations_or_flags"]["held_over_max"], 0)
        self.assertEqual(j.run(exit_max_hold_hours=2)["violations_or_flags"]["held_over_max"], 1)


class RevisionPr117(unittest.TestCase):
    """Fix della revisione della PR #117 sull'audit."""

    def J(self):
        return Journal(self)

    def test_fully_checked_is_always_false_and_not_checkable_is_declared(self):
        j = self.J()
        j.open("a", T0)
        j.close("a", T0 + H, -10)
        v = j.run()["verdict"]
        self.assertEqual((v["no_breach_proven"], v["fully_checked"]), (True, False))
        self.assertTrue({"unrealized_equity", "guard_block_history", "policy_effectively_loaded_by_run"} <= set(v["not_checkable"]))
        self.assertEqual(self.J().run()["verdict"]["fully_checked"], False)                     # anche con un journal vuoto

    def test_missing_numeric_fields_are_data_gaps_never_zero(self):
        j = self.J()
        j.add("paper_open", T0, {"position_id": "g1", "symbol": "X", "side": 1, "fill_price": "100"})          # niente stop/quantita'...
        j.add("paper_close", T0 + H, {"position_id": "g1", "reason": "stop"})                                  # niente realized_pnl
        j.add("paper_open", T0 + 2 * H, {})                                                                    # payload vuoto/illeggibile
        r = j.run()
        self.assertEqual(r["data_gaps"], {"opens_incomplete": 2, "closes_incomplete": 1, "events_unparsable": 1})
        self.assertEqual(r["equity_realized_only"]["now"], "2000.0000")                                       # nessuno zero inventato
        self.assertFalse(r["verdict"]["no_breach_proven"])
        self.assertIn("data_gaps_present", r["verdict"]["soft_flags"])
        self.assertEqual(r["trades"]["closed"], 1)

    def test_a_clean_journal_has_no_gaps(self):
        j = self.J()
        j.open("a", T0)
        self.assertEqual(j.run()["data_gaps"], {"opens_incomplete": 0, "closes_incomplete": 0, "events_unparsable": 0})

    def test_daily_breakdown_by_utc_day_shows_that_aggregate_loss_is_not_daily_compliance(self):
        j = self.J()
        for i in range(20):
            ts = T0 + (i % 10) * 2 * H + (DAY if i >= 10 else 0)
            j.open(f"p{i}", ts)
            j.close(f"p{i}", ts + H, -40)
        r = j.run()
        by = r["daily_guard_lower_bound"]["by_day_utc"]
        self.assertEqual(len(by), 2)
        self.assertEqual([d["realized"] for d in by], ["-400.0000", "-400.0000"])
        self.assertEqual([d["start_capital"] for d in by], ["2000.0000", "1600.0000"])
        self.assertEqual([d["realized_loss_fraction"] for d in by], ["0.2000", "0.2500"])                     # -40 % totale, max 25 % al giorno
        self.assertEqual(r["equity_realized_only"]["now"], "1200.0000")
        self.assertEqual(sum(d["opens"] for d in by), 20)

    def test_open_positions_age_is_measured_from_now_not_from_the_last_event(self):
        j = self.J()
        j.open("old", T0)
        j.decision(T0 + H)                                                                                       # ultimo evento: 1 h dopo
        stale = j.run()
        self.assertEqual((stale["trades"]["open_overdue"], stale["trades"]["open_age_reference"]), (0, "last_event"))
        now = j.run(now_ms=T0 + 30 * H)
        self.assertEqual((now["trades"]["open_overdue"], now["trades"]["oldest_open_age_hours"], now["trades"]["open_age_reference"]),
                         (1, "30.0000", "now"))
        self.assertIn("open_positions_overdue_for_exit", now["verdict"]["soft_flags"])
        self.assertTrue(now["verdict"]["no_breach_proven"])                                                      # richiede attenzione, non e' una violazione
        self.assertEqual(j.run(now_ms=T0 + 24 * H)["trades"]["open_overdue"], 0)                                 # entro 24 h + 1 h di tolleranza

    def test_policy_is_identified_but_declared_unverified_against_the_run(self):
        j = self.J()
        p = j.run()["policy"]
        self.assertEqual((p["source"], p["verified_against_run"]), ("embedded_copy_of_public_arena_config", False))
        self.assertEqual(p["hash"], ra.policy_hash(POLICY))
        other = json.loads(json.dumps(POLICY))
        other["risk_policy"]["max_leverage"] = 99
        self.assertNotEqual(ra.policy_hash(other), p["hash"])

    def test_no_limits_held_key_is_left_to_be_misread(self):
        self.assertNotIn("limits_held", json.dumps(self.J().run()))


if __name__ == "__main__":
    unittest.main()
