"""Offline: compare existing Brain's real 8-symbol runner with 25-market Arena.

No network, no writes, no provider API and no orders. Reuse actual RunnerConfig
and the existing 25-market common indicator packet test fixture.
"""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path
import unittest

from backend.v3.arena.test_comparison_packet import _shared_fixture
from backend.v3.arena.trial_universe_bridge import (
    VerifiedMarketIdentity, review_equal_universe,
)
from backend.v3.runner.config import load_runner_config


def base_config():
    path = Path(__file__).resolve().parents[1] / "runner" / "runner_config_brain2000_paper.json"
    return load_runner_config(path.read_bytes())


def mappings(packet):
    identities = []
    for i, symbol in enumerate(packet.symbols):
        metal = symbol in {"XAUUSDT", "XAGUSDT"}
        identities.append(VerifiedMarketIdentity(
            symbol=symbol, category="metal" if metal else "crypto_native",
            coingecko_id="" if metal else f"coin-id-{i}",
            market_cap_rank=None if metal else i + 1,
            bitget_contract_symbol=symbol,
            contract_status="normal", quote_asset="USDT",
            exchange_max_leverage=50, identity_reviewed=True,
        ))
    return tuple(identities)


class ArenaTrialUniverseBridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, cls.market = _shared_fixture()
        cls.config = base_config()
        cls.identities = mappings(cls.market)
        cls.asof = cls.market.asof_ms

    def review(self, *, identities="default", **kw):
        ids = self.identities if identities == "default" else identities
        return review_equal_universe(
            self.market, self.config, now_ms=self.asof + 60_000,
            identities=ids, **kw,
        )

    def test_actual_2000_brain_config_has_old_eight(self):
        self.assertEqual(self.config.symbols, (
            "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT",
            "DOGEUSDT", "ADAUSDT", "LINKUSDT",
        ))
        self.assertEqual(self.config.initial_equity, Decimal("2000"))
        self.assertEqual(self.config.risk_policy.minimum_equity, Decimal("450"))

    def test_all_three_receive_exact_same_proposed_25_universe(self):
        plan = self.review()
        self.assertEqual(len(plan.candidates), 25)
        self.assertEqual(len(plan.per_ai), 3)
        self.assertEqual(tuple(x[0] for x in plan.per_ai),
                         ("deepseek", "qwen", "minimax"))
        self.assertTrue(all(x[1] == plan.candidates for x in plan.per_ai))
        self.assertTrue({"XAUUSDT", "XAGUSDT"}.issubset(plan.candidates))

    def test_risk_ready_is_not_executable_and_does_not_change_baseline(self):
        original = self.config.symbols
        plan = self.review()
        self.assertTrue(plan.ready_for_further_integration)
        self.assertFalse(plan.executable)
        self.assertEqual(self.config.symbols, original)
        self.assertNotEqual(plan.candidates, original)

    def test_provisional_data_without_independent_identity_review_blocked(self):
        plan = self.review(identities=None)
        self.assertIn("ASSET_IDENTITY_AND_CONTRACTS_NOT_REVIEWED", plan.issues)
        self.assertFalse(plan.ready_for_further_integration)
        self.assertFalse(plan.executable)

    def test_old_snapshot_rejected_for_next_integration_gate(self):
        plan = review_equal_universe(
            self.market, self.config, now_ms=self.asof + 15*60_000 + 1,
            identities=self.identities)
        self.assertIn("STALE_RESEARCH_SNAPSHOT", plan.issues)

    def test_exact_time_limit_is_allowed_to_plan_only(self):
        plan = review_equal_universe(
            self.market, self.config, now_ms=self.asof + 15*60_000,
            identities=self.identities)
        self.assertTrue(plan.ready_for_further_integration)
        self.assertFalse(plan.executable)

    def test_incomplete_identity_roster_blocked(self):
        plan = self.review(identities=self.identities[:-1])
        self.assertIn("INCOMPLETE_ASSET_IDENTITY_SET", plan.issues)

    def test_unverified_identity_and_wrong_exchange_contract_blocked(self):
        items = list(self.identities)
        items[0] = replace(items[0], identity_reviewed=False)
        self.assertIn("UNVERIFIED_OR_UNTRADEABLE_CONTRACT",
                      self.review(identities=tuple(items)).issues)
        items[0] = replace(items[0], identity_reviewed=True, bitget_contract_symbol="BADUSDT")
        self.assertIn("UNVERIFIED_OR_UNTRADEABLE_CONTRACT",
                      self.review(identities=tuple(items)).issues)

    def test_exchange_leverage_below_brain_minimum_is_blocked(self):
        items = list(self.identities)
        items[0] = replace(items[0], exchange_max_leverage=6)
        self.assertIn("UNVERIFIED_OR_UNTRADEABLE_CONTRACT",
                      self.review(identities=tuple(items)).issues)

    def test_stablecoin_or_wrapped_asset_cannot_be_called_native(self):
        items = list(self.identities)
        idx = next(i for i, x in enumerate(items) if x.category == "crypto_native")
        items[idx] = replace(items[idx], category="wrapped")
        self.assertIn("CRYPTO_IDENTITY_OR_RANK_AMBIGUOUS",
                      self.review(identities=tuple(items)).issues)

    def test_duplicate_coin_rank_refused(self):
        items = list(self.identities)
        native = [i for i,x in enumerate(items) if x.category == "crypto_native"]
        items[native[1]] = replace(items[native[1]],
                                   market_cap_rank=items[native[0]].market_cap_rank)
        self.assertIn("CRYPTO_IDENTITY_OR_RANK_AMBIGUOUS",
                      self.review(identities=tuple(items)).issues)

    def test_metal_mapped_as_crypto_blocked(self):
        items = list(self.identities)
        idx = next(i for i,x in enumerate(items) if x.symbol == "XAUUSDT")
        items[idx] = replace(items[idx], category="crypto_native")
        self.assertIn("METAL_IDENTITY_MISMATCH",
                      self.review(identities=tuple(items)).issues)

    def test_baseline_capital_mismatch_blocked(self):
        changed = replace(self.config, initial_equity=Decimal("1000"))
        plan = review_equal_universe(
            self.market, changed, now_ms=self.asof + 60_000,
            identities=self.identities)
        self.assertIn("BASELINE_CAPITAL_MISMATCH", plan.issues)

    def test_no_future_asof_is_allowed(self):
        with self.assertRaisesRegex(ValueError, "ARENA_UNIVERSE_INVALID_TIME"):
            review_equal_universe(self.market, self.config,
                                  now_ms=self.asof - 1,
                                  identities=self.identities)


if __name__ == "__main__":
    unittest.main()
