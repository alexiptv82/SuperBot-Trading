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
    return dict(m.PROTOCOL, schema=2, status="approved",
                oos_start_utc="2026-10-23T00:00:00Z", baseline_version="4aabeb8",
                reviewed_versions=["4aabeb8", "fa3e220"],
                baseline_config_sha256={"hawk": "a"*64, "bull": "b"*64})


def ledger(p=None, end=None):
    p = p or plan()
    end = end or START+56*m.DAY
    return {"schema": 1, "source": "reviewed_deployment_config_ledger", "bots": {
        bot: [{"from_ms": START, "to_ms": end, "code_version": p["baseline_version"],
               "config_sha256": p["baseline_config_sha256"][bot], "paper": True,
               "source_sha256": "c"*64}] for bot in ("hawk", "bull")}}


def paired(i, opened=None, side=1, delta=None):
    at = OPEN+i*2*m.DAY if opened is None else opened
    value = i/10 if delta is None else delta
    return dict(opened=at, closed=at+m.BAR, base=-1., alt=-1.+value,
                delta=value, changed=True, side=side, leverage=2., r_dist=.01, cost_R=.1)


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
        pairs = [paired(i) for i in range(30)]
        a = m.summarize(pairs)
        self.assertEqual(a, m.summarize(pairs))
        self.assertEqual(a["episodes"], 30)
        pairs[0]["closed"] = pairs[-1]["closed"]
        a = m.summarize(pairs)
        self.assertEqual(a["episodes"], 1)
        self.assertIsNone(a["episode_ci975_delta_R"])

    def test_prospective_gate_requires_sample_and_complete_coverage(self):
        events, index = [], {"PRIVATE_TEST_SYMBOL": {}}
        for i in range(100):
            t, rows = trade(opened=START+(i//3)*m.DAY, ident=i+1)
            events.extend(rows)
            index[t["symbol"]].update({b[0]: b for b in bars(t)})
        by_bot = {"hawk": events, "bull": [dict(r, portfolio="bull") for r in events]}
        report = m.analyze(by_bot, index, START+56*m.DAY, plan(), START-1, ledger())
        hawk = report["bots"]["hawk"]
        self.assertEqual(hawk["hypothesis_gate"], "supports_further_shadow_review")
        self.assertEqual(hawk["groups"]["prospective"]["slip2bp_delay0bar"]["n"], 100)
        del index["PRIVATE_TEST_SYMBOL"][START+m.BAR]
        report = m.analyze(by_bot, index, START+56*m.DAY, plan(), START-1, ledger())
        self.assertEqual(report["bots"]["hawk"]["hypothesis_gate"], "inconclusive_sample_or_coverage")
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

    def test_workflow_isolation_and_no_bot_mutation(self):
        workflow = (ROOT/".github/workflows/desk-step6-economic.yml").read_text()
        for guard in ("--network none", "--read-only", "--cap-drop ALL", ":/data:ro",
                      ":/market:ro", "BOT_CONTAINER_INVARIANCE=PASS", "DESK_MODE=paper",
                      "actions/upload-artifact@v4", "registered_ms", "StrictHostKeyChecking=yes"):
            self.assertIn(guard, workflow)
        for mutation in ("docker restart", "docker stop", "docker rm", "workflow_dispatch"):
            self.assertNotIn(mutation, workflow)

    def test_plan_lifecycle_does_not_oblige_delivery_draft(self):
        proposal = json.loads((ROOT/"deploy/step6-plan.json").read_text())
        # A future approved registration must pass the same suite as draft.
        registered = m.utc_ms(proposal["oos_start_utc"])-1 if proposal["status"] == "approved" else START-1
        m.validate_plan(proposal, registered, allow_draft=True)
        approved = plan()
        self.assertEqual(m.validate_plan(approved, START-1), START)
        draft = dict(approved, status="draft", oos_start_utc=None,
                     baseline_config_sha256={"hawk": None, "bull": None})
        self.assertIsNone(m.validate_plan(draft, START-1, allow_draft=True))
        with self.assertRaises(m.Invalid): m.validate_plan(draft, START-1)

    def final_fixture(self):
        events, index = [], {"PRIVATE_TEST_SYMBOL": {}}
        for i in range(100):
            t, event = trade(opened=START+(i//3)*m.DAY, ident=i+1)
            events.extend(event)
            index[t["symbol"]].update({b[0]: b for b in bars(t)})
        return {"hawk": events, "bull": [dict(r, portfolio="bull") for r in events]}, index

    def test_no_prospective_effects_or_activation_before_final(self):
        events, index = self.final_fixture()
        with patch.object(m, "replay", side_effect=AssertionError("must not inspect OOS")):
            report = m.analyze(events, index, START+55*m.DAY, plan(), START-1, ledger())
        result = report["bots"]["hawk"]
        self.assertEqual(result["groups"]["prospective"], {"effects_withheld": True})
        self.assertEqual(result["hypothesis_gate"], "pending_fixed_final")
        self.assertEqual(result["cohort_by_direction"]["long"]["opened_events"], 100)
        self.assertNotIn("mean_delta_R", json.dumps(result["groups"]["prospective"]))

    def test_nontrade_version_changes_and_missing_versions_invalidate(self):
        events, index = self.final_fixture()
        for version in ("fa3e220", None):
            changed = dict(events["hawk"][0], ev="claude_call", code_version=version)
            altered = dict(events, hawk=events["hawk"]+[changed])
            report = m.analyze(altered, index, START+m.DAY, plan(), START-1)
            self.assertEqual(report["bots"]["hawk"]["version_gate"], "invalidated_baseline_change")

    def test_runtime_gap_change_missing_and_attestation(self):
        p = plan(); cutoff = START+56*m.DAY
        self.assertEqual(m.continuity_gate(None, "hawk", START, cutoff, p), "missing_runtime_ledger")
        evidence = ledger()
        self.assertEqual(m.continuity_gate(evidence, "hawk", START, cutoff, p),
                         "attested_continuity_manual_review_required")
        evidence["bots"]["hawk"][0]["from_ms"] += 1
        self.assertEqual(m.continuity_gate(evidence, "hawk", START, cutoff, p), "incomplete_runtime_ledger")
        for field, value in (("config_sha256", "f"*64), ("code_version", "fa3e220"), ("paper", False)):
            evidence = ledger(); evidence["bots"]["hawk"][0][field] = value
            self.assertEqual(m.continuity_gate(evidence, "hawk", START, cutoff, p), "invalidated_runtime_change")
        events, index = self.final_fixture()
        report = m.analyze(events, index, cutoff, p, START-1)
        self.assertEqual(report["bots"]["hawk"]["hypothesis_gate"], "inconclusive_runtime_evidence")

    def test_many_trades_in_one_episode_are_inconclusive(self):
        pairs = [paired(i, opened=START+i*m.BAR, delta=1) for i in range(100)]
        for row in pairs: row["closed"] = START+40*m.DAY
        summary = m.summarize(pairs)
        self.assertEqual(summary["episodes"], 1)
        self.assertIsNone(summary["episode_ci975_delta_R"])
        # A naturally clustered fixture keeps its closed trades without asserting failure.
        clustered, idx = [], {"PRIVATE_TEST_SYMBOL": {}}
        for i in range(100):
            t, row = trade(opened=START, ident=i+1)
            clustered.extend(row); idx[t["symbol"]].update({b[0]: b for b in bars(t)})
        report = m.analyze({"hawk": clustered, "bull": [dict(r, portfolio="bull") for r in clustered]},
                           idx, START+56*m.DAY, plan(), START-1, ledger())
        self.assertEqual(report["bots"]["hawk"]["sample_gate"], "inconclusive_at_final")
        self.assertEqual(report["bots"]["hawk"]["hypothesis_gate"], "inconclusive_sample_or_coverage")

    def test_final_cutoff_keeps_open_positions_censored_and_does_not_extend(self):
        events, index = self.final_fixture()
        t, extra = trade(opened=START+41*m.DAY, ident=101)
        extra[1].update(ts=START+57*m.DAY, close_ms=START+57*m.DAY)
        for bot in events: events[bot].extend(dict(r, portfolio=bot) for r in extra)
        a = m.analyze(events, index, START+56*m.DAY, plan(), START-1, ledger())
        b = m.analyze(events, index, START+90*m.DAY, plan(), START-1, ledger())
        self.assertEqual(a["bots"], b["bots"])
        self.assertEqual(a["bots"]["hawk"]["cohort_by_direction"]["long"]["not_uniquely_closed_by_cutoff"], 1)
        self.assertEqual(a["bots"]["hawk"]["hypothesis_gate"], "inconclusive_sample_or_coverage")

    def test_directional_summaries_share_whole_episodes_and_profit_factor_null(self):
        pairs = [paired(i, opened=OPEN+(i//2)*2*m.DAY, side=1 if i%2 else -1, delta=2.)
                 for i in range(60)]
        result = m.summarize(pairs)
        self.assertEqual(result["episodes"], 30)
        for side in ("long", "short"):
            self.assertEqual(result["by_direction"][side]["episodes"], 30)
            self.assertEqual(result["by_direction"][side]["n"], 30)
            candidate = result["by_direction"][side]["candidate"]
            self.assertIsNone(candidate["profit_factor_R"])
            self.assertTrue(candidate["profit_factor_denominator_zero"])
        json.dumps(result, allow_nan=False)

    def test_quantile_convention_and_influential_episode(self):
        values = list(range(2000))
        self.assertEqual(m.empirical_quantile(values, .0125), 24)
        self.assertEqual(m.empirical_quantile(values, .9875), 1974)
        pairs = [paired(i, delta=-.1) for i in range(30)]
        pairs[0]["delta"] = 10
        result = m.summarize(pairs)
        self.assertGreater(result["mean_delta_R"], 0)
        self.assertLess(result["min_leave_one_episode_out_mean_delta_R"], 0)
        with patch.object(m, "bootstrap_ci", side_effect=[[.1, .2], [.13, .23]]):
            self.assertFalse(m.summarize(pairs)["bootstrap_stable"])

    def test_plan_preflight_before_ssh_accepts_approved_rejects_draft(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"plan.json"
            for status, rc in (("approved", 0), ("draft", 2)):
                p = plan()
                if status == "draft":
                    p.update(status="draft", oos_start_utc=None,
                             baseline_config_sha256={"hawk": None, "bull": None})
                path.write_text(json.dumps(p))
                result = subprocess.run(["python", str(ROOT/"deploy/scripts/step6_economic_replay.py"),
                    "--check-plan", "--plan", str(path), "--registered-ms", str(START-1)],
                    capture_output=True, text=True)
                self.assertEqual(result.returncode, rc, result.stderr)

    def test_loaded_workflow_mismatch_is_blocked_before_checkout_or_ssh(self):
        workflow = (ROOT/".github/workflows/desk-step6-economic.yml").read_text()
        begin = workflow.index('          SHA="$(sed')
        block = workflow[begin:workflow.index('      - name: Read-only analysis', begin)]
        block = "\n".join(line[10:] for line in block.splitlines())
        prefix = r'''
        set -euo pipefail
        sed() { printf '%040d\n' 0 | tr 0 a; }
        git() {
          if [ "$1" = rev-parse ]; then
            if [[ "$2" == b* ]] && [ "$MISMATCH" = 1 ]; then echo different; else echo same; fi
          elif [ "$1" = show ]; then echo 1700000000;
          elif [ "$1" = checkout ]; then echo CHECKOUT_REACHED; fi
        }
        python() { return 0; }
        '''
        import os
        with tempfile.TemporaryDirectory() as tmp:
            for mismatch in ("0", "1"):
                result = subprocess.run(["bash", "-c", prefix+block], text=True, capture_output=True,
                    env=dict(os.environ, LOADED_WORKFLOW_SHA="b"*40, MISMATCH=mismatch,
                             GITHUB_OUTPUT=str(Path(tmp)/"output")))
                self.assertEqual(result.returncode, int(mismatch), result.stderr)
                self.assertEqual("CHECKOUT_REACHED" in result.stdout, mismatch == "0")

    def test_final_negative_result_is_distinct_from_inconclusive(self):
        events, index = self.final_fixture()
        def negative_variant(t, bars_, slip, delay):
            base=m.liquidation(t,t['baseline_ref'],t['closed'],slip)/t['risk']
            return base,base-.5,True
        with patch.object(m, "replay", side_effect=negative_variant):
            report = m.analyze(events, index, START+56*m.DAY, plan(), START-1, ledger())
        self.assertEqual(report["bots"]["hawk"]["hypothesis_gate"], "not_supported")
        with patch.object(m, "bootstrap_ci", side_effect=lambda c, n, seed:
                          [.1, .2] if seed == 20261022 else [.13, .23]):
            report = m.analyze(events, index, START+56*m.DAY, plan(), START-1, ledger())
        self.assertEqual(report["bots"]["hawk"]["hypothesis_gate"], "inconclusive_bootstrap_precision")

    def test_entries_after_enrollment_and_versions_after_final_do_not_change_effects(self):
        events, index = self.final_fixture()
        reference = m.analyze(events, index, START+56*m.DAY, plan(), START-1, ledger())
        t, late = trade(opened=START+43*m.DAY, ident=101)
        for bot in events:
            events[bot].extend(dict(r, portfolio=bot) for r in late)
            events[bot].append(dict(late[0], portfolio=bot, ev="claude_call",
                                    ts=START+57*m.DAY, code_version="fa3e220"))
        index[t["symbol"]].update({b[0]: b for b in bars(t)})
        report = m.analyze(events, index, START+90*m.DAY, plan(), START-1, ledger())
        for bot in events:
            self.assertEqual(report["bots"][bot]["groups"]["prospective"],
                             reference["bots"][bot]["groups"]["prospective"])
            self.assertEqual(report["bots"][bot]["version_gate"], "unchanged_in_recorded_events")
            self.assertEqual(report["bots"][bot]["cohort_by_direction"]["long"]["opened_after_enrollment_end"], 1)

    def test_later_candles_cannot_rescue_coverage_beyond_fixed_deadline(self):
        events, index = self.final_fixture()
        # A baseline close precisely at the final deadline requires the next
        # complete candle under window(); later data must not rescue that gap.
        final = START+56*m.DAY
        opened = START+41*m.DAY
        t, last = trade(opened=opened, ident=101)
        t["closed"] = final
        c = last[1]
        c.update(ts=final, close_ms=final)
        c["funding"] = round(200*m.FUND*(final-opened)/28800000, 4)
        c["net"] = round(m.liquidation(t, t["baseline_ref"], final, 2), 4)
        c["net_r"] = round(c["net"]/2, 4)
        for bot in events: events[bot].extend(dict(r, portfolio=bot) for r in last)
        index[t["symbol"]].update({at: (at, 100., 100.2, 99.8, 100.)
                                  for at in range(opened, final+m.BAR, m.BAR)})
        a = m.analyze(events, index, final, plan(), START-1, ledger())
        b = m.analyze(events, index, final+2*m.DAY, plan(), START-1, ledger())
        self.assertEqual(a["bots"], b["bots"])
        self.assertEqual(a["bots"]["hawk"]["coverage_gate"], "missing_prospective_candles")
        self.assertEqual(a["bots"]["hawk"]["excluded_by_cohort_and_direction"]["prospective"]["long"]["missing_candle_coverage"], 1)

    def test_two_half_accounting_against_independent_cashflows(self):
        t, _ = trade()
        first = t["opened"]+m.DAY
        second = t["opened"]+2*m.DAY
        # Qty 1 per half: gross +2-1; entry fee .12; exit fees .0612+.0594;
        # long PAPER funding .03+.06. No cash amounts from operational data.
        actual = .5*m.liquidation(t, 102., first, 0)+.5*m.liquidation(t, 99., second, 0)
        self.assertAlmostEqual(actual, .6694)
        t, _ = trade(-1)
        actual = .5*m.liquidation(t, 98., first, 0)+.5*m.liquidation(t, 101., second, 0)
        self.assertAlmostEqual(actual, .7606)

    def test_entry_regime_and_exclusion_audit_use_open_information(self):
        t, events = trade(opened=START)
        events[0]["features"] = {"btc_roc24h": -2.}
        events[1]["features"] = {"btc_roc24h": 2.}
        clean, _ = m.clean_trades(events, "hawk", START+m.DAY, plan())
        self.assertEqual(clean[0]["entry_btc_regime"], "down")
        events[1]["side"] = -1  # Exclusion must stay attributed to the long opening.
        audit = m.exclusion_audit(events, "hawk", START+m.DAY, plan(), START, START+42*m.DAY)
        self.assertEqual(audit["prospective"]["long"]["identity_or_time_mismatch"], 1)
        self.assertEqual(audit["prospective"]["short"], {})

    def test_reference_C_full_quantity_trailing_next_open_and_mirror(self):
        for side in (1,-1):
            t,_=trade(side)
            closes=[100,102,103,101.9,100,99,99,99,99]
            if side==-1:closes=[200-v for v in closes]
            series=bars(t,closes)
            base,alt,changed=m.replay_C(t,series,2,0)
            self.assertTrue(changed)
            self.assertAlmostEqual(alt,m.liquidation(t,series[4][1],series[4][0],2)/t['risk'])
            self.assertAlmostEqual(base,m.replay(t,series,2,0)[0])

    def test_reference_C_never_arms_on_intrabar_high(self):
        t,_=trade();series=bars(t,[100]*9)
        series[1]=(series[1][0],100,200,99,100)
        base,alt,changed=m.replay_C(t,series,2,0)
        self.assertEqual(base,alt);self.assertFalse(changed)

    def test_reference_C_terminal_boundary_and_delay(self):
        t,_=trade();series=bars(t,[100,102,103,101.9,100,99,99,99,99])
        self.assertNotEqual(m.replay_C(t,series,2,0)[1],m.replay_C(t,series,2,1)[1])
        t['closed']=t['opened']+5*m.BAR
        base,alt,changed=m.replay_C(t,series,2,0)
        self.assertFalse(changed);self.assertEqual(base,alt)

    def test_reference_C_descriptive_has_no_gate_or_CI(self):
        rows=[dict(opened=START,closed=START+2*m.DAY,side=1,delta=.2,changed=True),
              dict(opened=START,closed=START+m.BAR,side=-1,delta=-.1,changed=True)]
        result=m.summarize_C(rows)
        self.assertAlmostEqual(result['delta_R_C_minus_baseline']['mean'],.05)
        self.assertEqual(result['by_direction_and_baseline_duration']['long']['24h_plus']['n'],1)
        self.assertNotIn('episode_ci975_delta_R',result)
        self.assertNotIn('hypothesis_gate',result)

    def test_reference_C_cannot_change_primary_hypothesis_family_or_gate(self):
        events,index=self.final_fixture()
        ordinary=m.analyze(events,index,START+56*m.DAY,plan(),START-1,ledger())
        original=m.replay_C
        def bad_C(t,bars_,slip,delay):
            base,_,_=original(t,bars_,slip,delay)
            return base,base-999,True
        with patch.object(m,'replay_C',side_effect=bad_C):
            terrible=m.analyze(events,index,START+56*m.DAY,plan(),START-1,ledger())
        self.assertEqual(terrible['primary_family'],'two_pooled_bot_means_bonferroni')
        for bot in ('hawk','bull'):
            self.assertEqual(ordinary['bots'][bot]['hypothesis_gate'],terrible['bots'][bot]['hypothesis_gate'])
            for cohort in ('historical_exploratory','prospective'):
                for key,value in ordinary['bots'][bot]['groups'][cohort].items():
                    other=terrible['bots'][bot]['groups'][cohort][key]
                    self.assertEqual({k:v for k,v in value.items() if k!='reference_C'},
                                     {k:v for k,v in other.items() if k!='reference_C'})

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
            if [ "$BAD_PAPER_AFTER" = 1 ] && [ "$(cat "$COUNT_FILE")" -ge 2 ]; then echo DESK_MODE=live; else echo DESK_MODE=paper; fi
          else
            echo sha256:fake
          fi
        }
        '''
        with tempfile.TemporaryDirectory() as tmp:
            import os
            for fail, change, paper, rc, marker in (("0", "0", "0", 0, "PASS"), ("1", "0", "0", 9, "PASS"), ("0", "1", "0", 1, "FAIL"), ("0", "0", "1", 1, "PASS")):
                counter = Path(tmp)/"counter"
                counter.unlink(missing_ok=True)
                result = subprocess.run(["bash", "-c", prefix+block], text=True, capture_output=True,
                                        env=dict(os.environ, FAIL_RUN=fail, CHANGE=change, BAD_PAPER_AFTER=paper, COUNT_FILE=str(counter)))
                self.assertEqual(result.returncode, rc, result.stderr)
                self.assertIn("BOT_CONTAINER_INVARIANCE="+marker, result.stdout)


if __name__ == "__main__":
    unittest.main()
