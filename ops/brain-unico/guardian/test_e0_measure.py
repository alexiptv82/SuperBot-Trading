#!/usr/bin/env python3
"""Test SINTETICI di e0_measure (nessun dato reale). Uso: python3 -I test_e0_measure.py"""
import contextlib
import io
import json
import os
import random
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import e0_measure as E  # noqa: E402

MIN = 60_000
H = 3_600_000


def utc(y, mo, d, h=0, mi=0):
    return int(datetime(y, mo, d, h, mi, tzinfo=timezone.utc).timestamp() * 1000)


def row(stream, sym, side, opened, closed, r=None, pnl=None, **kw):
    o = {"status": kw.pop("status", "closed"), "net_pnl": pnl if pnl is not None else (r if r is not None else None),
         "opened_ms": opened, "closed_ms": closed, "net_r": r, "is_manual": kw.pop("manual", False)}
    src, run = stream.split("|")
    base = {"record_kind": "executed", "is_synthetic": False, "provenance": {"input_id": "x"}, "ineligible_reasons": [],
            "outcome": o, "source_system": src, "source_run": run, "symbol": sym, "side": side}
    for k, v in kw.items():
        if k == "prov":
            base["provenance"].update(v)
        else:
            base[k] = v
    return base


def gen_sessions(n_days, decay=True, seed=1, stream="arena_qwen|r1", start=None):
    """Una sessione al giorno (dalle 09:00 Rome circa), 8 trade sequenziali da 30 min su simboli diversi.
    Con `decay`: dopo +4R realizzati nella sessione la probabilita' di vincita scende da 0,45 a 0,10."""
    rng = random.Random(seed)
    rows = []
    t0 = start or utc(2026, 1, 5, 8, 0)
    for d in range(n_days):
        t = t0 + d * 24 * H
        cum = 0.0
        for k in range(8):
            p = 0.10 if (decay and cum >= 4) else 0.45
            r = 2.0 if rng.random() < p else -1.0
            rows.append(row(stream, "S%d" % k, 1 if k % 2 else -1, t, t + 30 * MIN, r))
            cum += r
            t += 31 * MIN
    return rows


class SelectionTests(unittest.TestCase):
    def test_only_attested_closed_unique_real_trades_are_used_and_exclusions_counted(self):
        t = utc(2026, 1, 5, 9)
        rows = [row("falco|run1", "A", 1, t, t + H, 1.0),
                row("falco|run1", "A", 1, t, t + H, 1.0, prov={"duplicate_of": "e1"}),
                row("falco|run1", "A", 1, t, t + H, 1.0, ineligible_reasons=["provenance_not_anchored"]),
                row("falco|run1", "A", 1, t, t + H, 1.0, ineligible_reasons=["input_not_attested"]),
                row("falco|run1", "A", 1, t, None, None, status="open_censored"),
                row("falco|run1", "A", 1, t, t + H, None, status="closed_unknown_pnl"),
                row("falco|run1", "A", 1, t, t + H, 1.0, is_synthetic=True),
                {**row("falco|run1", "A", 0, t, t + H, 1.0), "record_kind": "no_trade"}]
        used, excl = E.select(rows)
        self.assertEqual(len(used), 1)
        self.assertEqual(dict(excl), {"duplicate": 1, "not_attested": 2, "not_closed_or_unknown_pnl": 2, "synthetic": 1,
                                      "not_executed": 1})
        used2, _ = E.select(rows, allow_unattested=True)
        self.assertEqual(len(used2), 3)
        self.assertEqual(E.analyze(rows, boot=200, allow_unattested=True)["certification"], "NOT_CERTIFIED_unattested_allowed")

    def test_r_proxy_from_median_loss_when_net_r_missing(self):
        t = utc(2026, 1, 5, 9)
        rows = [row("toro|run1", "A", 1, t + i * H, t + i * H + MIN, None, pnl=p) for i, p in enumerate((-10.0, -30.0, 40.0))]
        used, _ = E.select(rows)
        info = E.assign_r(used)
        self.assertEqual([u["r"] for u in used], [-0.5, -1.5, 2.0])                   # unita' = mediana perdite = 20
        self.assertEqual(info["toro|run1"]["r_proxy_trades"], 3)
        only_wins = [row("toro|run2", "A", 1, t, t + MIN, None, pnl=5.0)]
        rep = E.analyze(only_wins, boot=200)
        self.assertEqual((rep["trades_used"], rep["excluded"].get("no_r_unit")), (0, 1))


class SessionAndCausalityTests(unittest.TestCase):
    def test_session_boundary_at_08_rome_across_dst(self):
        # inverno (UTC+1): 08:00 Rome = 07:00 UTC; estate (UTC+2): 08:00 Rome = 06:00 UTC
        self.assertEqual(E.session_key(utc(2026, 1, 10, 6, 59), "Europe/Rome", 8), "2026-01-09")
        self.assertEqual(E.session_key(utc(2026, 1, 10, 7, 0), "Europe/Rome", 8), "2026-01-10")
        self.assertEqual(E.session_key(utc(2026, 7, 10, 5, 59), "Europe/Rome", 8), "2026-07-09")
        self.assertEqual(E.session_key(utc(2026, 7, 10, 6, 0), "Europe/Rome", 8), "2026-07-10")
        # notte del cambio (29/03/2026): la sessione del 28 dura 23 ore
        self.assertEqual(E.session_key(utc(2026, 3, 29, 5, 59), "Europe/Rome", 8), "2026-03-28")
        self.assertEqual(E.session_key(utc(2026, 3, 29, 6, 0), "Europe/Rome", 8), "2026-03-29")
        # mezzanotte come alternativa
        self.assertEqual(E.session_key(utc(2026, 1, 10, 22, 59), "Europe/Rome", 0), "2026-01-10")
        self.assertEqual(E.session_key(utc(2026, 1, 10, 23, 0), "Europe/Rome", 0), "2026-01-11")

    def test_session_pnl_uses_only_trades_closed_before_the_open(self):
        t = utc(2026, 1, 5, 9)
        rows = [row("arena_qwen|r1", "A", 1, t, t + 2 * H, 5.0),             # chiude DOPO l'apertura del 2o: non conta
                row("arena_qwen|r1", "B", 1, t + H, t + 3 * H, -1.0),
                row("arena_qwen|r1", "C", 1, t + 4 * H, t + 5 * H, 1.0)]       # vede +5 e -1
        used, _ = E.select(rows)
        E.assign_r(used)
        E.annotate(used, "Europe/Rome", 8, 12)
        by = {u["symbol"]: u for u in used}
        self.assertEqual((by["A"]["sess_pnl_before"], by["B"]["sess_pnl_before"], by["C"]["sess_pnl_before"]), (0.0, 0.0, 4.0))
        self.assertEqual((by["C"]["sess_peak_before"], by["B"]["open_concurrent"], by["C"]["open_concurrent"]), (5.0, 1, 0))

    def test_previous_session_profit_does_not_carry_over(self):
        t = utc(2026, 1, 5, 9)
        rows = [row("arena_qwen|r1", "A", 1, t, t + H, 6.0), row("arena_qwen|r1", "B", 1, t + 24 * H, t + 25 * H, 1.0)]
        used, _ = E.select(rows)
        E.assign_r(used)
        E.annotate(used, "Europe/Rome", 8, 12)
        self.assertEqual(used[1]["sess_pnl_before"], 0.0)

    def test_streams_never_mix(self):
        t = utc(2026, 1, 5, 9)
        rows = [row("arena_qwen|r1", "A", 1, t, t + H, 6.0), row("arena_minimax|r1", "A", 1, t + 2 * H, t + 3 * H, 1.0)]
        used, _ = E.select(rows)
        E.assign_r(used)
        E.annotate(used, "Europe/Rome", 8, 12)
        mm = next(u for u in used if u["stream"].startswith("arena_minimax"))
        self.assertEqual((mm["sess_pnl_before"], mm["reentry"]), (0.0, 1))


class ReentryTests(unittest.TestCase):
    def annotate(self, rows, window=12):
        used, _ = E.select(rows)
        E.assign_r(used)
        E.annotate(used, "Europe/Rome", 8, window)
        return sorted(used, key=lambda u: u["opened"])

    def test_index_window_opposite_side_and_prev_outcome(self):
        t = utc(2026, 1, 5, 9)
        s = "falco|run1"
        u = self.annotate([row(s, "A", 1, t, t + H, 2.0), row(s, "A", 1, t + 2 * H, t + 3 * H, -1.0),
                           row(s, "A", 1, t + 4 * H, t + 5 * H, 2.0),
                           row(s, "B", 1, t + 4 * H + MIN, t + 5 * H, 1.0),              # altro simbolo: nuova tesi
                           row(s, "A", -1, t + 6 * H, t + 7 * H, 1.0),                    # lato opposto: nuova tesi SHORT
                           row(s, "A", 1, t + 8 * H, t + 9 * H, 1.0),                     # opposto in mezzo: reset LONG
                           row(s, "A", 1, t + 30 * H, t + 31 * H, 1.0)])                  # oltre la finestra: reset
        self.assertEqual([x["reentry"] for x in u], [1, 2, 3, 1, 1, 1, 1])
        self.assertEqual([x["prev_outcome"] for x in u], ["none", "tp", "sl", "none", "none", "none", "none"])

    def test_prev_outcome_ignores_entries_still_open(self):
        t = utc(2026, 1, 5, 9)
        s = "falco|run1"
        u = self.annotate([row(s, "A", 1, t, t + 5 * H, 2.0), row(s, "A", 1, t + H, t + 2 * H, -1.0),
                           row(s, "A", 1, t + 3 * H, t + 4 * H, 1.0)])
        self.assertEqual([x["reentry"] for x in u], [1, 2, 3])
        self.assertEqual([x["prev_outcome"] for x in u], ["none", "none", "sl"])          # il 1o e' ancora aperto

    def test_window_is_measured_from_previous_entry_of_the_thesis(self):
        t = utc(2026, 1, 5, 9)
        s = "falco|run1"
        u = self.annotate([row(s, "A", 1, t, t + H, 1.0), row(s, "A", 1, t + 10 * H, t + 11 * H, 1.0),
                           row(s, "A", 1, t + 20 * H, t + 21 * H, 1.0)], window=12)
        self.assertEqual([x["reentry"] for x in u], [1, 2, 3])
        u = self.annotate([row(s, "A", 1, t, t + H, 1.0), row(s, "A", 1, t + 13 * H, t + 14 * H, 1.0)], window=12)
        self.assertEqual([x["reentry"] for x in u], [1, 1])


class ContrastTests(unittest.TestCase):
    def test_planted_post_profit_decay_is_detected(self):
        rep = E.analyze(gen_sessions(400, decay=True), boot=400)
        h1 = rep["primary"]["H1_after_session_profit"]
        self.assertEqual(h1["verdict"], "worse", h1)
        self.assertLess(h1["ci95"][1], 0)
        self.assertGreaterEqual(h1["n_a"], E.MIN_TRADES)
        b = rep["exploratory"]["session_pnl_buckets"]
        self.assertEqual((h1["n_a"], h1["n_b"]), (b[">=4"]["n"], b["[-1,1)"]["n"]))          # gruppi pre-registrati

    def test_no_decay_gives_no_evidence_not_better_or_worse(self):
        rep = E.analyze(gen_sessions(400, decay=False, seed=3), boot=400)
        h1 = rep["primary"]["H1_after_session_profit"]
        self.assertEqual(h1["verdict"], "no_evidence", h1)
        self.assertLessEqual(h1["ci95"][0], 0)
        self.assertGreaterEqual(h1["ci95"][1], 0)

    def test_small_sample_is_inconclusive(self):
        rep = E.analyze(gen_sessions(12, decay=True), boot=200)
        self.assertEqual(rep["primary"]["H1_after_session_profit"]["verdict"], "inconclusive_small_sample")
        self.assertIsNone(rep["primary"]["H1_after_session_profit"]["p"])

    def test_planted_reentry_decay_is_detected(self):
        rng = random.Random(5)
        rows, t = [], utc(2026, 1, 5, 8)
        for d in range(300):
            base = t + d * 24 * H
            for j, sym in enumerate(("A", "B")):
                for k in range(4):                                   # 4 ingressi della stessa tesi, a 2 ore di distanza
                    p = 0.5 if k == 0 else (0.4 if k == 1 else 0.1)
                    r = 2.0 if rng.random() < p else -1.0
                    o = base + j * 10 * MIN + k * 2 * H
                    rows.append(row("arena_deepseek|r1", sym, 1, o, o + H, r))
        rep = E.analyze(rows, boot=400)
        h2 = rep["primary"]["H2_reentry_3plus_vs_first"]
        self.assertEqual(h2["verdict"], "worse", h2)
        self.assertEqual(rep["exploratory"]["reentry_index"]["3+"]["n"], 1200)
        self.assertEqual((h2["n_a"], h2["n_b"]), (1200, rep["exploratory"]["reentry_index"]["1"]["n"]))   # 3+ contro 1

    def test_stream_fixed_effect_removes_spurious_effect(self):
        """Un flusso forte (molte sessioni sopra +4R) e uno debole, SENZA decadimento dentro ciascuno: niente effetto."""
        rng = random.Random(9)
        rows = []
        for stream, p, seed in (("arena_qwen|r1", 0.7, 1), ("arena_minimax|r1", 0.25, 2)):
            t0 = utc(2026, 1, 5, 8)
            for d in range(300):
                t = t0 + d * 24 * H
                for k in range(8):
                    r = 2.0 if rng.random() < p else -1.0
                    rows.append(row(stream, "S%d" % k, 1 if k % 2 else -1, t, t + 30 * MIN, r))
                    t += 31 * MIN
        rep = E.analyze(rows, boot=400)
        h1 = rep["primary"]["H1_after_session_profit"]
        self.assertNotEqual(h1["verdict"], "better", h1)          # senza effetto fisso il flusso forte sembrerebbe "better"
        self.assertLess(abs(h1["diff_r"]), 0.3, h1)

    def test_holm_adjusts_and_never_lowers_p(self):
        res = {"a": {"p": 0.01, "ci95": [-1, -0.1]}, "b": {"p": 0.04, "ci95": [-1, -0.1]}}
        E.holm(res)
        self.assertEqual((res["a"]["p_holm"], res["b"]["p_holm"]), (0.02, 0.04))
        self.assertEqual((res["a"]["verdict"], res["b"]["verdict"]), ("worse", "worse"))
        res = {"a": {"p": 0.03, "ci95": [-1, -0.1]}, "b": {"p": 0.04, "ci95": [0.1, 1]}}
        E.holm(res)
        self.assertEqual((res["a"]["p_holm"], res["b"]["p_holm"]), (0.06, 0.06))      # Holm: 2*0.03, poi max(0.06, 0.04)
        self.assertEqual((res["a"]["verdict"], res["b"]["verdict"]), ("no_evidence", "no_evidence"))
        res = {"a": {"p": 0.001, "ci95": [-1, -0.1]}, "b": {"p": 0.03, "ci95": [0.1, 1]}}
        E.holm(res)
        self.assertEqual((res["a"]["verdict"], res["b"]["verdict"]), ("worse", "better"))

    def test_manual_close_sensitivity_and_giveback_reported(self):
        rows = gen_sessions(200, decay=True)
        for r in rows[::7]:
            r["outcome"]["is_manual"] = True
        rep = E.analyze(rows, boot=200)
        self.assertIn("sensitivity_without_manual_closes", rep)
        gb = rep["exploratory"]["giveback"]
        self.assertGreater(gb["sessions_armed"], 0)
        self.assertLessEqual(gb["sessions_below_75pct_of_peak"], gb["sessions_armed"])

    def test_deterministic_and_numbers_only(self):
        rows = gen_sessions(60, decay=True)
        a, b = E.analyze(rows, boot=200, seed=4), E.analyze(rows, boot=200, seed=4)
        self.assertEqual(a, b)
        txt = json.dumps(a)
        self.assertNotIn("S1", txt)                                   # nessun simbolo nel rapporto
        self.assertNotIn("arena_qwen", txt)                           # nessun nome di flusso


class CliTests(unittest.TestCase):
    def test_cli_writes_new_private_file_outside_git_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as d:
            ex = os.path.join(d, "examples.jsonl")
            with open(ex, "w") as fh:
                fh.write("".join(json.dumps(r) + "\n" for r in gen_sessions(40)))
            out = os.path.join(d, "e0.json")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(E.main(["--examples", ex, "--out", out, "--boot", "200"]), 0)
                self.assertEqual(E.main(["--examples", ex, "--out", out, "--boot", "200"]), 1)
                self.assertEqual(E.main(["--examples", ex, "--out", out + "2", "--session-hour", "25"]), 2)
            self.assertEqual(oct(os.stat(out).st_mode & 0o777), "0o600")
            with open(out) as fh:
                self.assertEqual(json.load(fh)["kind"], "e0_measure_v1")
            g = os.path.join(d, "repo")
            os.mkdir(g)
            subprocess.run(["git", "init", "-q", g], check=True)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(E.main(["--examples", ex, "--out", os.path.join(g, "e0.json")]), 1)
            self.assertFalse(os.path.exists(os.path.join(g, "e0.json")))


if __name__ == "__main__":
    unittest.main()
