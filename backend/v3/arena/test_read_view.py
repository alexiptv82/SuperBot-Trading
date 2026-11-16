"""Offline synthetic verification for independent Arena PAPER wallet read views."""
from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from unittest import TestCase, main

from backend.v3.arena.read_view import read_wallet, read_arena
from backend.v3.arena.trial_plan import build_trial_plan
from backend.v3.events import Event, EventJournal


NOW = 1_795_000_000_000
START = NOW - 300_000


def _prepared(plan, *, with_journal=True, with_heartbeat=True):
    plan.folder.mkdir(parents=True)
    (plan.folder / "arena_manifest.json").write_text(json.dumps({
        "schema": "brain_arena_trial_v1",
        "provider": plan.provider,
        "run_id": plan.run_id,
        "initial_capital": "2000",
        "mode": "paper",
        "model": plan.model,
        "experiment": "independent",
        "trial_start_ms": START,
    }), encoding="utf-8")
    if with_journal:
        EventJournal(plan.journal).init_schema()
    if with_heartbeat:
        plan.heartbeat.write_text(json.dumps({
            "run_id": plan.run_id, "ts_ms": NOW - 15_000,
            "cycle": 0, "state": "running",
        }), encoding="utf-8")


def _append(plan, kind, event_id, payload):
    return EventJournal(plan.journal).append(Event(
        event_id=event_id, portfolio_id="brain", run_id=plan.run_id,
        kind=kind, source="arena_test", occurred_at_ms=NOW - 10_000,
        payload=payload,
    ))


def _open(plan, *, originating_ai=None):
    _append(plan, "brain_decision", "decision.proposal0", {
        "kind": "OPEN", "status": "APPROVED", "symbol": "BTCUSDT",
        "regime": "TREND_DOWN",
    })
    _append(plan, "paper_open", "paper_open.pos0", {
        "position_id": "pos0", "symbol": "BTCUSDT", "side": -1,
        "fill_price": "100", "quantity": "10", "margin_used": "50",
        "leverage": 20, "stop_price": "101",
        "originating_ai": originating_ai or plan.provider,
        "decision_event_id": "decision.proposal0",
    })


class ReadViewTests(TestCase):
    def test_missing_data_never_claims_trading_or_profits(self):
        with TemporaryDirectory() as tmp:
            p = build_trial_plan(date(2026, 11, 16),
                                 root=Path(tmp) / "trial")[1]
            result = read_wallet(p, NOW)
            self.assertEqual(result["state"], "not_started")
            self.assertIsNone(result["equity"])
            self.assertIsNone(result["realized_pnl"])
            self.assertIsNone(result["open_positions"])
            self.assertFalse(result["trial_comparable"])
            self.assertFalse(Path(tmp, "trial").exists())

    def test_missing_journal_or_manifest_remains_unknown(self):
        with TemporaryDirectory() as tmp:
            plan = build_trial_plan(date(2026, 11, 16),
                                    root=Path(tmp) / "trial")[1]
            _prepared(plan, with_journal=False)
            value = read_wallet(plan, NOW)
            self.assertEqual(value["data_status"], "JOURNAL_NOT_AVAILABLE")
            self.assertIsNone(value["settled_equity"])
            (plan.folder / "arena_manifest.json").unlink()
            value = read_wallet(plan, NOW)
            self.assertEqual(value["data_status"], "NOT_CONFIGURED")

    def test_clean_started_wallet_has_2000_and_no_trades(self):
        with TemporaryDirectory() as tmp:
            plan = build_trial_plan(date(2026, 11, 16),
                                    root=Path(tmp) / "trial")[1]
            _prepared(plan)
            result = read_wallet(plan, NOW)
            self.assertEqual(result["data_status"], "VERIFIED")
            self.assertEqual(result["state"], "running")
            self.assertEqual(result["equity"], "2000")
            self.assertEqual(result["realized_pnl"], "0")
            self.assertEqual(result["open_positions"], [])
            self.assertEqual(result["closed_trades"], [])
            self.assertTrue(result["trial_comparable"])
            self.assertEqual(result["trial_start_ms"], START)

    def test_live_open_is_not_counted_as_realized_profit(self):
        with TemporaryDirectory() as tmp:
            plan = build_trial_plan(date(2026, 11, 16),
                                    root=Path(tmp) / "trial")[1]
            _prepared(plan)
            _open(plan)
            result = read_wallet(plan, NOW)
            self.assertEqual(result["data_status"], "VERIFIED")
            self.assertEqual(result["open_count"], 1)
            self.assertEqual(result["margin_in_use"], "50")
            self.assertEqual(result["settled_equity"], "2000")
            self.assertIsNone(result["equity"])
            self.assertEqual(result["equity_basis"], "open_unmarked")
            self.assertIsNone(result["unrealized_pnl"])
            self.assertIsNone(result["open_positions"][0]["unrealized_pnl"])

    def test_wrong_ai_cannot_impersonate_qwen(self):
        with TemporaryDirectory() as tmp:
            plan = build_trial_plan(date(2026, 11, 16),
                                    root=Path(tmp) / "trial")[1]
            _prepared(plan)
            _open(plan, originating_ai="deepseek")
            result = read_wallet(plan, NOW)
            self.assertEqual(result["data_status"], "UNVERIFIED_JOURNAL")
            self.assertIsNone(result["realized_pnl"])
            self.assertFalse(result["trial_comparable"])

    def test_other_run_in_same_db_cannot_generate_fake_zero_pnl(self):
        with TemporaryDirectory() as tmp:
            plan = build_trial_plan(date(2026, 11, 16),
                                    root=Path(tmp) / "trial")[1]
            _prepared(plan)
            EventJournal(plan.journal).append(Event(
                event_id="foreign.decision", portfolio_id="brain",
                run_id="brain-deepseek-paper20261116", kind="brain_decision",
                source="arena_test", occurred_at_ms=NOW - 20_000,
                payload={"kind":"NO_TRADE", "status":"DRAFT"},
            ))
            data = read_wallet(plan, NOW)
            self.assertEqual(data["data_status"], "UNVERIFIED_JOURNAL")
            self.assertIsNone(data["equity"])

    def test_missing_heartbeat_and_empty_journal_cannot_claim_started(self):
        with TemporaryDirectory() as tmp:
            plan = build_trial_plan(date(2026, 11, 16),
                                    root=Path(tmp) / "trial")[1]
            _prepared(plan, with_heartbeat=False)
            result = read_wallet(plan, NOW)
            self.assertEqual(result["data_status"], "UNVERIFIED_JOURNAL")
            self.assertIsNone(result["settled_equity"])

    def test_corrupt_hash_chain_is_not_displayed(self):
        with TemporaryDirectory() as tmp:
            plan = build_trial_plan(date(2026, 11, 16),
                                    root=Path(tmp) / "trial")[1]
            _prepared(plan)
            _open(plan)
            con = sqlite3.connect(plan.journal)
            try:
                con.execute("DROP TRIGGER v3_no_update")
                con.execute("UPDATE v3_events SET payload_json='{}' WHERE seq=1")
                con.commit()
            finally:
                con.close()
            self.assertEqual(read_wallet(plan, NOW)["data_status"], "UNVERIFIED_JOURNAL")

    def test_all_three_are_independent_and_not_assumed_started(self):
        with TemporaryDirectory() as tmp:
            plan = build_trial_plan(date(2026, 11, 16),
                                    root=Path(tmp) / "arena")
            _prepared(plan[1])
            result = read_arena(plan, NOW)
            self.assertEqual(set(result["portfolios"]),
                             {"deepseek","qwen","minimax"})
            self.assertEqual(result["portfolios"]["qwen"]["equity"], "2000")
            self.assertIsNone(result["portfolios"]["deepseek"]["equity"])
            self.assertIsNone(result["portfolios"]["minimax"]["equity"])

    def test_symlink_folder_does_not_leak_unrelated_journal(self):
        with TemporaryDirectory() as tmp:
            plan = build_trial_plan(date(2026, 11, 16),
                                    root=Path(tmp) / "arena")
            _prepared(plan[1])
            plan[2].folder.parent.mkdir(parents=True, exist_ok=True)
            plan[2].folder.symlink_to(plan[1].folder, target_is_directory=True)
            self.assertEqual(read_wallet(plan[2], NOW)["data_status"], "INVALID_SCOPE")


if __name__ == "__main__":
    main()
