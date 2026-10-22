"""Synthetic accounting, chronology, isolation and privacy tests; no network."""
from collections import Counter
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("step6", ROOT / "deploy/scripts/step6_economic_replay.py")
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)
START = m.utc_ms("2026-10-23T00:00:00Z")
OPEN = START - 10 * m.DAY


def plan():
    return {"schema": 1, "status": "approved",
            "candidate": "half_after_close_1.5R_then_nonpositive_remainder",
            "oos_start_utc": "2026-10-23T00:00:00Z", "baseline_version": "4aabeb8",
            "reviewed_versions": ["4aabeb8", "fa3e220"],
            "min_days": 42, "min_trades": 100, "min_changed": 50}


def trade(side=1, opened=OPEN, run=1, ident=1):
    closed = opened + 8 * m.BAR
    t = {"opened": opened, "closed": closed, "side": side, "entry": 100.,
         "margin": 100., "leverage": 2., "qty": 2., "r_dist": .01,
         "risk": 2., "risk_plan_usd": 2., "symbol": "PRIVATE_TEST_SYMBOL",
         "baseline_ref": 99. if side == 1 else 101., "why": "stop loss"}
    fill = t["baseline_ref"] * (1 - side * .0002)
    net = m.liquidation(t, t["baseline_ref"], closed, 2)
    gross = side * (fill - 100) * 2
    fees = (100 + fill) * 2 * m.FEE
    funding = 200 * m.FUND * (closed - opened) / 28_800_000 if side == 1 else 0
    common = {"schema": 1, "portfolio": "hawk", "run_no": run, "id": ident,
              "code_version": "4aabeb8", "symbol": t["symbol"], "side": side}
    o = dict(common, ev="open", ts=opened, entry=100., risk_plan_usd=2., r_dist=.01,
             leverage=2., margin_first=100., split_plan=None)
    c = dict(common, ev="close", ts=closed, open_ms=opened, close_ms=closed,
             entry=100., exit=fill, margin=100., leverage=2., risk_plan_usd=2., r_dist=.01,
             net=round(net, 4), net_r=round(net / 2, 4), gross=round(gross, 4),
             fees=round(fees, 4), funding=round(funding, 4), legs=1, dca_count=0,
             why="stop loss")
    return t, [o, c]


def bars(t, closes=None):
    closes = closes or [100., 102., 102., 100., 99., 99., 99., 99., 99.]
    return [(t["opened"] + i*m.BAR, close, close+.2, close-.2, close)
            for i, close in enumerate(closes)]


def encode(value):
    return (json.dumps(value) + "\n").encode()


class Step6Tests(unittest.TestCase):
    def test_jsonl_trailing_newline_and_strict_failures(self):
        self.assertEqual(len(m.rows(b'{"x":1}\n')), 1)
        for raw in (b'', b'\n', b'{"x":1}', b'{"x":1,"x":2}\n',
                    b'{"x":NaN}\n', b'{"x":1e999}\n', b'[]\n'):
            with self.subTest(raw=raw), self.assertRaises(m.Invalid):
                m.rows(raw)

    def test_draft_and_retroactive_registration_rejected(self):
        p = plan()
        p["status"] = "draft"
        with self.assertRaises(m.Invalid): m.validate_plan(p, START-1)
        p["status"] = "approved"
        with self.assertRaises(m.Invalid): m.validate_plan(p, START)
        self.assertEqual(m.validate_plan(p, START-1), START)

    def test_independent_costs_for_long_and_short(self):
        for side in (1, -1):
            _, events = trade(side)
            got, _ = m.clean_trades(events, "hawk", START, plan())
            self.assertEqual(len(got), 1)
            events[-1]["fees"] += .1
            events[-1]["net"] -= .1  # ledger identity still balances: independent costs must reject
            got, excluded = m.clean_trades(events, "hawk", START, plan())
            self.assertEqual(got, [])
            self.assertEqual(excluded["independent_cost_or_risk_reconciliation"], 1)

    def test_runs_not_merged_and_partials_or_splits_excluded(self):
        _, a = trade(run=1)
        _, b = trade(run=2)
        self.assertEqual(len(m.clean_trades(a+b, "hawk", START, plan())[0]), 2)
        a[-1]["partial"] = True
        self.assertEqual(m.clean_trades(a, "hawk", START, plan())[0], [])
        b[0]["split_plan"] = {"private": 1}
        self.assertEqual(m.clean_trades(b, "hawk", START, plan())[0], [])

    def test_missing_open_duplicate_and_bad_times(self):
        _, events = trade()
        for variant in ([events[-1]], events+[events[0]], [dict(events[0], ts=1), events[1]]):
            self.assertEqual(m.clean_trades(variant, "hawk", START, plan())[0], [])

    def test_market_manifest_closed_bars_and_conflicts(self):
        row = {"schema": 1, "symbol": "S", "open_ms": OPEN, "open": 100,
               "high": 101, "low": 99, "close": 100}
        raw = encode(row)
        manifest = {"schema": 1, "source": "bitget_public_15m", "timestamp_semantics": "open_ms",
                    "interval_ms": m.BAR, "asof_ms": OPEN+m.BAR, "bars_sha256": m.digest(raw)}
        self.assertEqual(len(m.candle_index(raw, manifest)[0]["S"]), 1)
        for data, change in ((raw, {"asof_ms": OPEN}), (raw+raw, {"bars_sha256": m.digest(raw+raw)}),
                             (raw, {"bars_sha256": "0"*64})):
            with self.assertRaises(m.Invalid): m.candle_index(data, dict(manifest, **change))

    def test_gap_is_missing_not_a_hold(self):
        t, _ = trade()
        series = bars(t)
        index = {t["symbol"]: {row[0]: row for row in series}}
        self.assertIsNotNone(m.window(t, index))
        del index[t["symbol"]][series[3][0]]
        self.assertIsNone(m.window(t, index))

    def test_next_open_execution_not_signal_close(self):
        t, _ = trade()
        series = bars(t)
        result = m.replay(t, series, 2, 0)
        self.assertTrue(result[2])
        expected = (.5*m.liquidation(t, series[2][1], series[2][0], 2)
                    + .5*m.liquidation(t, series[4][1], series[4][0], 2))/t["risk"]
        self.assertAlmostEqual(result[1], expected)
        series[2] = (series[2][0], 95, 103, 94, 102)  # next-open gap worsens the actual fill
        self.assertLess(m.replay(t, series, 2, 0)[1], result[1])

    def test_delay_and_baseline_exit_boundary(self):
        t, _ = trade()
        series = bars(t)
        self.assertNotEqual(m.replay(t, series, 2, 0)[1], m.replay(t, series, 2, 1)[1])
        t["closed"] = t["opened"] + 3*m.BAR
        # Partial fill exactly at baseline SL-bar start is ambiguous; baseline wins.
        base, alt, changed = m.replay(t, series, 2, 0)
        self.assertFalse(changed)
        self.assertEqual(base, alt)

    def test_entry_bar_prior_extremes_not_used(self):
        t, _ = trade()
        t["opened"] += 1
        series = bars(dict(t, opened=t["opened"]-1), [200]+[100]*8)
        self.assertFalse(m.replay(t, series, 2, 0)[2])

    def test_short_mirror_and_stress_costs(self):
        t, _ = trade(-1)
        series = bars(t, [100, 98, 98, 100, 101, 101, 101, 101, 101])
        b2, a2, change = m.replay(t, series, 2, 0)
        b8, a8, _ = m.replay(t, series, 8, 0)
        self.assertTrue(change)
        self.assertLess(a8, a2)
        self.assertLess(b8, b2)

    def test_chronological_purge_and_version_gate(self):
        t, hawk = trade(opened=START-4*m.BAR)
        bull = [dict(r, portfolio="bull") for r in hawk]
        idx = {t["symbol"]: {b[0]: b for b in bars(t)}}
        report = m.analyze({"hawk": hawk, "bull": bull}, idx, START+10*m.BAR, plan(), START-1)
        self.assertEqual(report["bots"]["hawk"]["excluded"]["crosses_oos_boundary"], 1)
        t, events = trade(opened=START+1*m.DAY)
        events[0]["code_version"] = "fa3e220"
        events[1]["code_version"] = "fa3e220"
        idx = {t["symbol"]: {b[0]: b for b in bars(t)}}
        report = m.analyze({"hawk": events, "bull": [dict(r, portfolio="bull") for r in events]},
                           idx, START+2*m.DAY, plan(), START-1)
        self.assertEqual(report["bots"]["hawk"]["hypothesis_gate"], "invalidated_baseline_change")

    def test_overlap_episodes_and_repeatable_bootstrap(self):
        pairs = [{"opened": OPEN+i*2*m.DAY, "closed": OPEN+i*2*m.DAY+m.BAR,
                  "base": 0, "alt": i/10, "delta": i/10, "changed": True} for i in range(10)]
        a = m.summarize(pairs)
        self.assertEqual(a, m.summarize(pairs))
        self.assertEqual(a["episodes"], 10)
        pairs[0]["closed"] = pairs[-1]["closed"]
        a = m.summarize(pairs)
        self.assertEqual(a["episodes"], 1)
        self.assertIsNone(a["episode_ci975_delta_R"])

    def test_prospective_gate_requires_sample_and_complete_coverage(self):
        events, index = [], {"PRIVATE_TEST_SYMBOL": {}}
        for i in range(100):
            t, rows = trade(opened=START+(i//5)*2*m.DAY, ident=i+1)
            events.extend(rows)
            index[t["symbol"]].update({b[0]: b for b in bars(t)})
        by_bot = {"hawk": events, "bull": [dict(r, portfolio="bull") for r in events]}
        report = m.analyze(by_bot, index, START+42*m.DAY, plan(), START-1)
        hawk = report["bots"]["hawk"]
        self.assertEqual(hawk["hypothesis_gate"], "supports_further_shadow_review")
        self.assertEqual(hawk["groups"]["prospective"]["slip2bp_delay0bar"]["n"], 100)
        del index["PRIVATE_TEST_SYMBOL"][START+m.BAR]
        report = m.analyze(by_bot, index, START+42*m.DAY, plan(), START-1)
        self.assertEqual(report["bots"]["hawk"]["hypothesis_gate"], "pending")
        self.assertEqual(report["bots"]["hawk"]["coverage_gate"], "missing_prospective_candles")

    def test_full_offline_report_privacy_and_changed_source(self):
        t, events = trade()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for bot in ("hawk", "bull"):
                (root/bot).mkdir()
                (root/bot/"learning_log.jsonl").write_bytes(b"".join(encode(dict(r, portfolio=bot)) for r in events))
            market = root/"market"
            market.mkdir()
            raw = b"".join(encode(dict(schema=1, symbol=t["symbol"], open_ms=b[0],
                                        open=b[1], high=b[2], low=b[3], close=b[4])) for b in bars(t))
            (market/"candles.jsonl").write_bytes(raw)
            manifest = {"schema": 1, "source": "bitget_public_15m", "timestamp_semantics": "open_ms",
                        "interval_ms": m.BAR, "asof_ms": t["closed"]+m.BAR, "bars_sha256": m.digest(raw)}
            (market/"manifest.json").write_bytes(encode(manifest))
            p = root/"plan.json"
            p.write_bytes(encode(plan()))
            report = m.run(root, market, p, START-1)
            output = json.dumps(report, allow_nan=False)
            for forbidden in (t["symbol"], "risk_plan_usd", "baseline_ref", '"net"', '"entry"', '"id"'):
                self.assertNotIn(forbidden, output)
            self.assertEqual(report["scope"], m.SCOPE)
            self.assertFalse(report["automatic_promotion"])
            original = m.snapshot
            calls = Counter()
            def mutate(path):
                calls[str(path)] += 1
                return original(path) + (b" " if calls[str(path)] > 1 else b"")
            with patch.object(m, "snapshot", side_effect=mutate), self.assertRaises(m.Invalid):
                m.run(root, market, p, START-1)

    def test_snapshot_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/"file"
            p.write_bytes(b"x")
            link = Path(tmp)/"link"
            link.symlink_to(p)
            with self.assertRaises(OSError): m.snapshot(link)

    def test_workflow_has_no_activation_file_or_bot_mutation(self):
        workflow = (ROOT/".github/workflows/desk-step6-economic.yml").read_text()
        self.assertFalse((ROOT/"deploy/desk-step6.trigger").exists())
        for guard in ("--network none", "--read-only", "--cap-drop ALL", ":/data:ro",
                      ":/market:ro", "BOT_CONTAINER_INVARIANCE=PASS", "DESK_MODE=paper",
                      "actions/upload-artifact@v4", "registered_ms", "StrictHostKeyChecking=yes"):
            self.assertIn(guard, workflow)
        for mutation in ("docker restart", "docker stop", "docker rm", "workflow_dispatch"):
            self.assertNotIn(mutation, workflow)

    def test_plan_shipped_as_non_executable_draft(self):
        proposal = json.loads((ROOT/"deploy/step6-plan.json").read_text())
        self.assertEqual(proposal["status"], "draft")
        self.assertIsNone(proposal["oos_start_utc"])

    def test_workflow_remote_trap_propagates_failure_and_detects_restart(self):
        # Execute the actual remote shell with stubbed git/docker, no SSH/network.
        workflow = (ROOT/".github/workflows/desk-step6-economic.yml").read_text()
        block = workflow.split("<<'REMOTE'\n", 1)[1].split("          REMOTE\n", 1)[0]
        block = "\n".join(line[10:] for line in block.splitlines())
        block = block.replace("SHA_TOKEN", "a"*40).replace("RUN_TOKEN", "1")
        prefix = r'''
        git() {
          case "$1" in
            rev-parse) printf '%040d\n' 0 | tr 0 a ;;
            show) echo 1700000000 ;;
            *) return 0 ;;
          esac
        }
        realpath() { echo "$1"; }
        test() {
          if [ "$1" = -d ] && [ "$2" = /opt/superbot-step6-market ]; then return 0; fi
          builtin test "$@"
        }
        docker() {
          if [ "$1" = run ]; then
            if [ "$FAIL_RUN" = 1 ]; then return 9; fi
            echo '{"schema":1}'
          elif [[ "$*" == *'.Name'* ]]; then
            n=0; [ ! -f "$COUNT_FILE" ] || n=$(cat "$COUNT_FILE")
            echo $((n+1)) > "$COUNT_FILE"
            if [ "$CHANGE" = 1 ] && [ "$n" != 0 ]; then echo changed; else echo same; fi
          elif [[ "$*" == *'.Config.Env'* ]]; then
            echo DESK_MODE=paper
          else
            echo sha256:fake
          fi
        }
        '''
        with tempfile.TemporaryDirectory() as tmp:
            import os
            for fail, change, rc, marker in (("0", "0", 0, "PASS"), ("1", "0", 9, "PASS"), ("0", "1", 1, "FAIL")):
                counter = Path(tmp)/"counter"
                counter.unlink(missing_ok=True)
                result = subprocess.run(["bash", "-c", prefix+block], text=True, capture_output=True,
                                        env=dict(os.environ, FAIL_RUN=fail, CHANGE=change, COUNT_FILE=str(counter)))
                self.assertEqual(result.returncode, rc, result.stderr)
                self.assertIn("BOT_CONTAINER_INVARIANCE="+marker, result.stdout)


if __name__ == "__main__":
    unittest.main()
