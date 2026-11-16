"""Offline deterministic checks for shadow-only selective AI collaboration."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from unittest import TestCase, main

from backend.v3.arena.selective_advisors import (
    AdvisorAllowance, MarketDecision, THRESHOLD, projected_usd, triggers,
    plan_first_opinion, plan_second_opinion, advisory_result_policy,
)


def candidate(**kwargs):
    defaults = dict(
        provider="deepseek", symbol="BTCUSDT", action="SHORT",
        confidence=Decimal("0.86"), regime="TREND_DOWN",
        trend_4h="DOWN", trend_1h="DOWN",
        market_data_fresh=True, risk_eligible=True,
        timestamp_ms=1795000000000,
    )
    return MarketDecision(**{**defaults, **kwargs})


def caps(name, *, calls=5, daily="0.05", key="1.50", worst="0.004"):
    return AdvisorAllowance(
        name, calls, Decimal(daily), Decimal(key), Decimal(worst),
    )


class SelectiveAdvisorTests(TestCase):
    def test_disabled_initially_no_advisory_inference(self):
        d = candidate(action="LONG", trend_4h="DOWN")
        result = plan_first_opinion(d, (caps("qwen"), caps("minimax")))
        self.assertEqual(result.reason, "NOT_ENABLED")
        self.assertEqual(result.consult, ())
        self.assertFalse(result.can_change_trade)

    def test_clear_trend_no_consult_cost(self):
        d = candidate()
        p = plan_first_opinion(
            d, (caps("qwen"), caps("minimax")), enabled=True
        )
        self.assertEqual(p.reason, "NO_TRIGGER")
        self.assertEqual(p.consult, ())
        self.assertEqual(triggers(d), ())

    def test_long_against_downtrend_selects_one_affordable_advisor(self):
        d = candidate(action="LONG", confidence=Decimal("0.80"))
        p = plan_first_opinion(d, (caps("qwen"), caps("minimax")),
                               enabled=True)
        self.assertEqual(p.consult, ("qwen",))
        self.assertEqual(p.triggers, ("AGAINST_4H_TREND",))
        self.assertEqual(p.mode, "SHADOW_ONLY")

    def test_low_confidence_and_mtf_conflict(self):
        d = candidate(
            confidence=Decimal("0.50"), trend_4h="DOWN", trend_1h="UP"
        )
        self.assertEqual(
            triggers(d),
            ("PRIMARY_LOW_CONFIDENCE", "MTF_CONFLICT"),
        )
        borderline = candidate(confidence=THRESHOLD)
        self.assertEqual(triggers(borderline), ())

    def test_expansion_alone_not_an_automatic_short_veto(self):
        p = plan_first_opinion(
            candidate(regime="EXPANSION"),
            (caps("qwen"), caps("minimax")), enabled=True,
        )
        self.assertEqual(p.reason, "NO_TRIGGER")
        self.assertEqual(p.consult, ())

    def test_shock_is_a_reason_to_consult_not_to_execute(self):
        p = plan_first_opinion(
            candidate(regime="SHOCK"),
            (caps("qwen"), caps("minimax")), enabled=True,
        )
        self.assertEqual(p.consult, ("qwen",))
        self.assertFalse(p.can_change_trade)
        self.assertIn("SHOCK_REGIME", p.triggers)

    def test_no_trade_stays_no_trade_without_advisor_expense(self):
        d = candidate(action="NO_TRADE", confidence=Decimal("0.2"))
        p = plan_first_opinion(d, (caps("qwen"), caps("minimax")),
                               enabled=True)
        self.assertEqual(p.reason, "NO_TRIGGER")
        self.assertEqual(p.consult, ())

    def test_stale_or_risk_rejected_no_external_calls(self):
        for change, error in (
            ({"market_data_fresh": False}, "STALE_MARKET_NO_INFERENCE"),
            ({"risk_eligible": False}, "RISK_INELIGIBLE_NO_INFERENCE"),
        ):
            p = plan_first_opinion(
                candidate(**change), (caps("qwen"), caps("minimax")),
                enabled=True,
            )
            self.assertEqual(p.reason, error)
            self.assertEqual(p.consult, ())

    def test_qwen_budget_ended_can_select_minimax(self):
        d = candidate(action="LONG")
        p = plan_first_opinion(
            d, (caps("qwen", calls=0), caps("minimax")),
            enabled=True,
        )
        self.assertEqual(p.consult, ("minimax",))
        p = plan_first_opinion(
            d, (caps("qwen", daily="0.001"), caps("minimax", calls=0)),
            enabled=True,
        )
        self.assertEqual(p.reason, "NO_BUDGET_OR_ADVISOR")
        self.assertEqual(p.consult, ())

    def test_missing_primary_preference_always_uses_distinct_provider(self):
        d = candidate(provider="qwen", action="LONG")
        p = plan_first_opinion(
            d, (caps("qwen"), caps("minimax"), caps("deepseek")),
            enabled=True,
        )
        self.assertEqual(p.consult, ("minimax",))

    def test_first_agrees_then_no_second_request(self):
        d = candidate(action="LONG")
        p = plan_second_opinion(
            d, "qwen", "LONG", (caps("minimax"),), enabled=True,
        )
        self.assertEqual(p.reason, "FIRST_AGREES_NO_SECOND_CALL")
        self.assertEqual(p.consult, ())

    def test_first_disagrees_second_only_when_budgeted(self):
        d = candidate(action="LONG")
        p = plan_second_opinion(
            d, "qwen", "NO_TRADE", (caps("minimax"),),
            enabled=True,
        )
        self.assertEqual(p.consult, ("minimax",))
        self.assertIn("FIRST_DISAGREES", p.triggers)
        denied = plan_second_opinion(
            d, "qwen", "SHORT", (caps("minimax", key="0.002"),),
            enabled=True,
        )
        self.assertEqual(denied.reason, "NO_BUDGET_FOR_SECOND")

    def test_conflicting_opinions_do_not_override_leader_or_risk(self):
        summary = advisory_result_policy(
            lead_decision="LONG",
            opinions=("SHORT", "NO_TRADE"),
        )
        self.assertEqual(summary["final_action"], "OBSERVE_ONLY")
        self.assertTrue(summary["advisor_disagreement"])
        self.assertFalse(summary["trading_authority"])
        self.assertFalse(summary["risk_override"])

    def test_prices_from_verified_catalog(self):
        self.assertEqual(
            projected_usd("qwen", input_tokens=3000, output_tokens=1000),
            Decimal("0.00224"),
        )
        self.assertEqual(
            projected_usd("minimax", input_tokens=3000, output_tokens=1000),
            Decimal("0.00105"),
        )
        with self.assertRaises(ValueError):
            projected_usd("deepseek", input_tokens=3000, output_tokens=1000)
        with self.assertRaises(ValueError):
            projected_usd("qwen", input_tokens=-2, output_tokens=0)


if __name__ == "__main__":
    main()
