import contextlib
import hashlib
import io
import json
from pathlib import Path
import random
import tempfile
import unittest

from desk.engine import PaperAccount
from desk.profit.features import Bar
from desk.profit.liquidable import evaluate
from desk.profit_sidecar import roi_variants
from desk.profit_sidecar.accounting import snapshot
from desk.profit_sidecar.candles import INTERVAL_MS, fetch_bars
from desk.profit_sidecar.common import Freeze
from desk.profit_sidecar.journal import Journal
from desk.profit_sidecar.reader import read_consistent
from desk.profit_sidecar.runner import poll_once, process_cycle

BASE = 1_800_000_000_000          # multiple of 15 minutes
T_EVAL = BASE + 5 * 60_000        # five minutes into a candle
HOUR = 3_600_000


def write_source(root, account, *, cycles=2, price=110.0, price_ms=T_EVAL, run_no=3, run_started=BASE - 10 * HOUR,
                 end_offset=35_000, running=False, symbol_prices=None):
    root = Path(root)
    root.mkdir(exist_ok=True)
    state = {"run_no": run_no, "run_started_ms": run_started,
             "last_prices": symbol_prices or {"BTC": price}, "last_prices_ms": price_ms, "main": account.to_dict()}
    hb = {"started_ms": 1, "cycles": cycles, "last_start_ms": price_ms, "last_end_ms": price_ms + end_offset,
          "cycle_running": running, "exec_mode": "paper", "portfolio": "hawk", "last_ok": True,
          "open_positions": len(account.positions), "version": "botsha", "ts": (price_ms + end_offset) / 1000}
    (root / "state_v2.json").write_text(json.dumps(state))
    (root / "heartbeat.json").write_text(json.dumps(hb))
    return price_ms + end_offset + 20_000      # a plausible "now"


def bars_for(price_path):
    """Closed bars ending at the last full candle before T_EVAL plus the forming one, as fetch_bars returns them."""
    def make(symbol, asof_ms):
        out, p = [], price_path
        containing = asof_ms - asof_ms % INTERVAL_MS
        for i in range(24, -1, -1):
            opened = containing - i * INTERVAL_MS
            c = p + (24 - i) * 0.1
            out.append(Bar(opened + INTERVAL_MS, c - 0.05, c + 0.3, c - 0.3, c))
        return tuple(out)
    return make


def engine_account(side, dca=True):
    acc = PaperAccount()
    t0 = BASE - 5 * HOUR
    adverse = 98.0 if side == 1 else 102.0
    pos, msg = acc.open("BTC", side, 100, 10, 100.0, 95.0 if side == 1 else 105.0, None, t0, {"BTC": 100.0})
    assert pos, msg
    if dca:
        pos2, msg = acc.add_dca("BTC", 94.0 if side == 1 else 106.0, None, t0 + HOUR, {"BTC": adverse})
        assert pos2, msg
    assert acc.partial_close("BTC", 105.0 if side == 1 else 95.0, t0 + 2 * HOUR, .4)
    return acc


class GoldenAgainstEngine(unittest.TestCase):
    def check(self, side, mark):
        with tempfile.TemporaryDirectory() as tmp:
            acc = engine_account(side)
            now = write_source(tmp, acc, price=mark)
            obs = read_consistent(tmp, "hawk", now)
            pos = obs.state["main"]["positions"]["BTC"]
            snap, view, costs, _ = snapshot(obs, pos)
            predicted = evaluate(view, mark, costs)
            rec = acc.close("BTC", mark, T_EVAL, "golden")
            lifecycle = sum(r["net"] for r in acc.closed)
            self.assertAlmostEqual(predicted.net_usd, lifecycle, places=3)
            self.assertAlmostEqual(view.funding_paid, rec["funding"], places=3)
            self.assertAlmostEqual(snap["reference_margin"], 100 + obs.state["main"]["positions"]["BTC"]["dca_levels"][0]["margin"])

    def test_long_with_dca_and_partial_matches_engine_close(self):
        self.check(1, 110.0)
        self.check(1, 96.0)

    def test_short_with_dca_and_partial_matches_engine_close(self):
        self.check(-1, 90.0)
        self.check(-1, 104.0)


class RoiVariants(unittest.TestCase):
    P = roi_variants.RoiPolicy()

    def run_path(self, path):
        s, out = roi_variants.RoiState(), []
        for i, roi in enumerate(path):
            s, d = roi_variants.step(s, roi=roi, eval_ms=1000 + i, credible_reversal=False, features_valid=True, policy=self.P)
            out.append((s, d))
        return out

    def test_user_scenario_floor_exit_and_checkpoint(self):
        out = self.run_path([10, 16, 21, 15.9, 30])
        self.assertFalse(out[0][0].armed)
        self.assertEqual(out[1][1]["floor_roi"], 11.0)
        self.assertEqual(out[2][1]["floor_roi"], 16.0)
        self.assertEqual(out[3][1]["a"], "EXIT_FLOOR")       # 15.9 <= floor 16 known BEFORE this evaluation
        self.assertEqual(out[3][1]["b"], "EXIT_FLOOR")
        self.assertEqual(out[4][1]["checkpoint"], "LASCIA_CORRERE")
        self.assertEqual(sum(1 for _, d in out if d["checkpoint"]), 1)   # checkpoint only once

    def test_checkpoint_fires_once_even_if_roi_stays_above(self):
        out = self.run_path([26, 28, 30])
        self.assertEqual([d["checkpoint"] for _, d in out], ["LASCIA_CORRERE", None, None])

    def test_new_floor_is_not_retroactive(self):
        out = self.run_path([16, 30])      # 30 raises the floor to 25; same evaluation is not judged by it
        self.assertEqual(out[1][1]["a"], "HOLD")
        self.assertEqual(out[1][1]["floor_roi"], 25.0)

    def test_variant_b_target_exit_while_a_keeps_running(self):
        out = self.run_path([16, 26])
        self.assertEqual(out[1][1]["b"], "EXIT_TARGET")
        self.assertEqual(out[1][1]["a"], "HOLD")

    def test_checkpoint_reports_reversal_and_invalid_data(self):
        s, d = roi_variants.step(roi_variants.RoiState(), roi=27, eval_ms=1, credible_reversal=True, features_valid=True, policy=self.P)
        self.assertEqual(d["checkpoint"], "CHIUDI_O_PARZIALE")
        s, d = roi_variants.step(roi_variants.RoiState(), roi=27, eval_ms=1, credible_reversal=False, features_valid=False, policy=self.P)
        self.assertEqual(d["checkpoint"], "DATI_NON_VALIDI")
        self.assertEqual(s, roi_variants.RoiState())          # congelato: niente e' stato consumato o aggiornato
        _, d = roi_variants.step(s, roi=27, eval_ms=2, credible_reversal=False, features_valid=True, policy=self.P)
        self.assertEqual(d["checkpoint"], "LASCIA_CORRERE")   # il checkpoint scatta al primo istante con dati validi

    def test_floor_is_monotone_on_random_paths(self):
        rng = random.Random(7)
        for _ in range(200):
            floors = [d["floor_roi"] for _, d in self.run_path([rng.uniform(-20, 45) for _ in range(30)]) if d["floor_roi"] is not None]
            self.assertEqual(floors, sorted(floors))

    def test_repeated_evaluation_and_bad_policy_rejected(self):
        s, _ = roi_variants.step(roi_variants.RoiState(), roi=20, eval_ms=5, credible_reversal=False, features_valid=True, policy=self.P)
        again, d = roi_variants.step(s, roi=99, eval_ms=5, credible_reversal=False, features_valid=True, policy=self.P)
        self.assertEqual(again, s)
        with self.assertRaises(ValueError): roi_variants.RoiPolicy(first_floor_roi=20, arm_roi=15)
        with self.assertRaises(ValueError): roi_variants.RoiPolicy(giveback_pp=float("nan"))


class InvalidFeaturesFreeze(unittest.TestCase):
    P = roi_variants.RoiPolicy()

    def test_invalid_features_do_not_trigger_floor_exit_or_move_state(self):
        # controesempio riprodotto da ChatGPT (20/10): pavimento 25, ROI 20, dati non validi => prima dava EXIT_FLOOR
        st = roi_variants.RoiState(peak_roi=30, armed=True, floor_roi=25, last_eval_ms=1)
        after, d = roi_variants.step(st, roi=20, eval_ms=2, credible_reversal=False, features_valid=False, policy=self.P)
        self.assertEqual((d["a"], d["b"], d["frozen"]), ("HOLD", "HOLD", "features_invalid"))
        self.assertEqual(after, st)
        _, d = roi_variants.step(after, roi=20, eval_ms=3, credible_reversal=False, features_valid=True, policy=self.P)
        self.assertEqual(d["a"], "EXIT_FLOOR")                # con dati validi il pavimento torna a valere

    def test_invalid_features_never_lower_or_raise_peak(self):
        st = roi_variants.RoiState(peak_roi=18, armed=True, floor_roi=13, last_eval_ms=1)
        after, _ = roi_variants.step(st, roi=40, eval_ms=2, credible_reversal=True, features_valid=False, policy=self.P)
        self.assertEqual(after.peak_roi, 18)


class FetchBars(unittest.TestCase):
    def opener(self, rows, code="00000"):
        body = json.dumps({"code": code, "data": rows}).encode()

        class Response(io.BytesIO):
            def __enter__(self): return self
            def __exit__(self, *a): return False
        return lambda request, timeout: Response(body)

    def rows(self, newest_open):
        return [[str(newest_open - i * INTERVAL_MS), "100", "101", "99", "100.5", "1", "1"] for i in range(5, -1, -1)]

    def test_open_time_semantics_ok_and_converted(self):
        containing = T_EVAL - T_EVAL % INTERVAL_MS
        bars = fetch_bars("BTC", asof_ms=T_EVAL, opener=self.opener(self.rows(containing)))
        self.assertEqual(bars[-1].close_ms, containing + INTERVAL_MS)

    def test_close_time_semantics_would_freeze(self):
        containing = T_EVAL - T_EVAL % INTERVAL_MS
        with self.assertRaisesRegex(Freeze, "candle_clock_mismatch"):
            fetch_bars("BTC", asof_ms=T_EVAL, opener=self.opener(self.rows(containing + INTERVAL_MS)))
        with self.assertRaisesRegex(Freeze, "candle_clock_mismatch"):
            fetch_bars("BTC", asof_ms=T_EVAL, opener=self.opener(self.rows(containing - 3 * INTERVAL_MS)))

    def test_rejections(self):
        with self.assertRaisesRegex(Freeze, "candles_rejected"):
            fetch_bars("BTC", asof_ms=T_EVAL, opener=self.opener([], code="40001"))
        with self.assertRaisesRegex(Freeze, "candles_malformed"):
            fetch_bars("BTC", asof_ms=T_EVAL, opener=self.opener([["x", "1", "1", "1", "1"]]))
        with self.assertRaisesRegex(Freeze, "candles_unavailable"):
            fetch_bars("BTC", asof_ms=T_EVAL, opener=lambda *a, **k: (_ for _ in ()).throw(OSError("net")))


class Cycle(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "hawk"
        self.out = self.root / "out"

    def tree(self):
        return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.source.iterdir()}

    def test_cycle_is_shadow_deduplicated_restart_safe_and_source_untouched(self):
        acc = engine_account(1, dca=False)
        now = write_source(self.source, acc, price=110.0, cycles=2)
        before = self.tree()
        with Journal(self.out) as j:
            self.assertTrue(process_cycle(j, read_consistent(self.source, "hawk", now), portfolio="hawk",
                                          bars_for=bars_for(100.0), code_version="t"))
            self.assertFalse(process_cycle(j, read_consistent(self.source, "hawk", now), portfolio="hawk",
                                           bars_for=bars_for(100.0), code_version="t"))
        self.assertEqual(before, self.tree())
        line = json.loads(next(self.out.glob("events-*.jsonl")).read_text().splitlines()[0])["body"]
        self.assertEqual((line["mode"], line["applied"]), ("ombra", False))
        rec = line["positions"][0]
        self.assertEqual(rec["pm_eval"]["mode"], "ombra")
        self.assertFalse(rec["pm_eval"]["applied"])
        self.assertIn("a", rec["roi"])
        self.assertTrue(rec["snapshot"]["funding_source"].startswith("modello del motore"))
        # restart: cache restored, same cycle not re-journaled, next cycle continues the per-position state
        with Journal(self.out) as j:
            self.assertFalse(process_cycle(j, read_consistent(self.source, "hawk", now), portfolio="hawk",
                                           bars_for=bars_for(100.0), code_version="t"))
            later = write_source(self.source, acc, price=112.0, cycles=3, price_ms=T_EVAL + 1_800_000)
            self.assertTrue(process_cycle(j, read_consistent(self.source, "hawk", later), portfolio="hawk",
                                          bars_for=bars_for(100.0), code_version="t"))
            body = json.loads(list(self.out.glob("events-*.jsonl"))[0].read_text().splitlines()[-1])["body"]
            self.assertEqual(body["cycles_skipped"], 0)
            self.assertGreater(body["positions"][0]["roi"]["peak_roi"] or -1e9, -1e9)

    def test_ambiguous_dca_and_partial_freeze_the_evaluation_but_keep_the_state(self):
        acc = engine_account(1)                                    # DCA e parziale: l'ordine non e' dimostrabile
        now = write_source(self.source, acc, price=110.0, cycles=2)
        with Journal(self.out) as j:
            self.assertTrue(process_cycle(j, read_consistent(self.source, "hawk", now), portfolio="hawk",
                                          bars_for=bars_for(100.0), code_version="t"))
            body = json.loads(next(self.out.glob("events-*.jsonl")).read_text().splitlines()[0])["body"]
        rec = body["positions"][0]
        self.assertEqual(rec["frozen"], "ambiguous_order")
        self.assertNotIn("pm_eval", rec)
        self.assertNotIn("roi", rec)
        self.assertTrue(rec["snapshot"]["ambiguous_order"])
        self.assertEqual(body["freezes"][0]["reason"], "ambiguous_order")

    def test_stale_or_foreign_mark_price_freezes_position_not_the_bot(self):
        acc = engine_account(1, dca=False)
        now = write_source(self.source, acc, price=110.0, price_ms=T_EVAL)
        state = json.loads((self.source / "state_v2.json").read_text())
        state["last_prices_ms"] = T_EVAL - 600_000      # price older than this cycle (download failed)
        (self.source / "state_v2.json").write_text(json.dumps(state))
        with Journal(self.out) as j:
            self.assertTrue(process_cycle(j, read_consistent(self.source, "hawk", now), portfolio="hawk",
                                          bars_for=bars_for(100.0), code_version="t"))
            body = json.loads(next(self.out.glob("events-*.jsonl")).read_text().splitlines()[0])["body"]
        self.assertEqual(body["positions"], [])
        self.assertEqual(body["freezes"][0]["reason"], "mark_price_not_from_this_cycle")

    def test_bad_candles_congela_the_pm_but_still_logs_the_snapshot(self):
        acc = engine_account(1, dca=False)
        now = write_source(self.source, acc, price=110.0)

        def broken(symbol, asof):
            raise Freeze("candles_unavailable")
        with Journal(self.out) as j:
            process_cycle(j, read_consistent(self.source, "hawk", now), portfolio="hawk", bars_for=broken, code_version="t")
            body = json.loads(next(self.out.glob("events-*.jsonl")).read_text().splitlines()[0])["body"]
        rec = body["positions"][0]
        self.assertEqual(rec["pm_eval"]["state"]["to"]["name"], "CONGELATO")
        self.assertEqual(rec["pm_eval"]["inputs"]["reason"], "candles_unavailable")
        self.assertIsNotNone(rec["liquidable_now"]["roi_pct"])

    def test_new_run_resets_cache_and_closed_outcomes_are_journaled(self):
        acc = engine_account(1, dca=False)
        now = write_source(self.source, acc, price=110.0)
        with Journal(self.out) as j:
            process_cycle(j, read_consistent(self.source, "hawk", now), portfolio="hawk", bars_for=bars_for(100.0), code_version="t")
            acc.close("BTC", 110.0, T_EVAL + 1_800_000, "x")
            now2 = write_source(self.source, acc, cycles=3, price_ms=T_EVAL + 1_800_000)
            process_cycle(j, read_consistent(self.source, "hawk", now2), portfolio="hawk", bars_for=bars_for(100.0), code_version="t")
            lines = [json.loads(x)["body"] for x in next(self.out.glob("events-*.jsonl")).read_text().splitlines()]
            first, last = lines[0], lines[-1]
            self.assertEqual([o["partial"] for o in first["outcomes"]], [True])     # partial already in the account at cycle 1
            self.assertEqual([o["partial"] for o in last["outcomes"]], [False])     # the final close arrives exactly once, later
            self.assertAlmostEqual(last["outcomes"][0]["lifecycle_net_usd"], first["outcomes"][0]["lifecycle_net_usd"] + last["outcomes"][0]["record"]["net"])
            self.assertEqual(last["positions"], [])
            fresh = PaperAccount()
            now3 = write_source(self.source, fresh, cycles=4, price_ms=T_EVAL + 3_600_000, run_no=4, run_started=T_EVAL + 3_000_000)
            process_cycle(j, read_consistent(self.source, "hawk", now3), portfolio="hawk", bars_for=bars_for(100.0), code_version="t")
            self.assertEqual(j.cache["hawk"]["closed_hashes"], [])
            self.assertTrue(j.cache["hawk"]["run_key"].endswith(str(T_EVAL + 3_000_000)))

    def test_poll_reports_transient_freeze_once_and_writes_only_its_own_directory(self):
        acc = engine_account(1, dca=False)
        now = write_source(self.source, acc, price=110.0, running=True)
        before = self.tree()
        memo = {}
        with Journal(self.out) as j:
            for k in range(3):
                reason = poll_once(self.source, j, portfolio="hawk", now_ms=now + k, bars_for=bars_for(100.0), code_version="t", memo=memo)
            self.assertEqual(reason, "cycle_unfinished_or_failed")
            self.assertEqual(j.sequence, 1)                    # journaled once, not every minute
            self.assertEqual(json.loads((self.out / "status.json").read_text())["freeze"], reason)
        self.assertEqual(before, self.tree())

    def test_unexpected_exception_is_reported_by_class_only(self):
        acc = engine_account(1, dca=False)
        now = write_source(self.source, acc, price=110.0)
        memo = {}

        def boom(symbol, asof):
            raise RuntimeError("secret detail")
        with Journal(self.out) as j:
            with unittest.mock.patch("desk.profit_sidecar.runner._evaluate_position", side_effect=RuntimeError("secret detail")):
                reason = poll_once(self.source, j, portfolio="hawk", now_ms=now, bars_for=boom, code_version="t", memo=memo)
            self.assertEqual(reason, "unexpected_RuntimeError")
            self.assertNotIn("secret", next(self.out.glob("events-*.jsonl")).read_text())


import unittest.mock  # noqa: E402

if __name__ == "__main__":
    unittest.main()
