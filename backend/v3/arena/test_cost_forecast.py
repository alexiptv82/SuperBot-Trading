"""Offline test scenarios for $2 OpenRouter key caps and 14-day trials."""
from __future__ import annotations

from decimal import Decimal
from unittest import TestCase, main

from backend.v3.arena.cost_forecast import estimate_paper_api


class CostForecastTests(TestCase):
    def test_hourly_eight_symbols_cannot_fit_two_dollar_keys(self):
        q = estimate_paper_api("qwen")
        m = estimate_paper_api("minimax")
        self.assertEqual(q.request_count, 2688)
        self.assertEqual(q.estimated_total_usd, Decimal("6.02112"))
        self.assertEqual(m.estimated_total_usd, Decimal("2.82240"))
        self.assertFalse(q.under_key_limit)
        self.assertFalse(m.under_key_limit)
        self.assertFalse(q.account_credit_verified)
        self.assertFalse(m.account_credit_verified)

    def test_less_frequent_common_schedule_is_possible_in_scenario_not_proven(self):
        q = estimate_paper_api(
            "qwen", decisions_per_day_per_symbol=4,
            output_tokens_per_call=2000,
        )
        m = estimate_paper_api(
            "minimax", decisions_per_day_per_symbol=4,
            output_tokens_per_call=2000,
        )
        self.assertEqual(q.request_count, 448)
        self.assertEqual(q.estimated_total_usd, Decimal("1.57696"))
        self.assertEqual(m.estimated_total_usd, Decimal("0.73920"))
        self.assertTrue(q.under_key_limit)
        self.assertTrue(m.under_key_limit)
        self.assertEqual(q.usable_key_budget_usd, Decimal("1.80"))
        self.assertFalse(q.account_credit_verified)

    def test_invalid_cost_scenario_rejected(self):
        for data in (
            {"provider": "deepseek"},
            {"provider": "qwen", "input_tokens_per_call": 0},
            {"provider": "qwen", "days": 0},
            {"provider": "minimax", "key_limit_usd": Decimal("50")},
            {"provider": "minimax", "reserve_usd": Decimal("2")},
        ):
            with self.subTest(data=data), self.assertRaises(ValueError):
                estimate_paper_api(**data)


if __name__ == "__main__":
    main()
