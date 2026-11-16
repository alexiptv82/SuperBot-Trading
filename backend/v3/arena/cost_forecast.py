"""Offline budget feasibility for Arena PAPER API calls; no secrets/network.

Rates were observed on VPS OpenRouter catalog 2026-11-16. They are *not*
guarantees of future prices or actual token usage, especially with reasoning.
The OpenRouter account's actual prepaid/promotional balance is UNKNOWN until
the operator checks Credits; an API key's $2 limit is not account credit.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

PRICES = {
    "qwen": (Decimal("0.32"), Decimal("1.28")),
    "minimax": (Decimal("0.15"), Decimal("0.60")),
}
KEY_LIMIT_USD = Decimal("2")
RESERVE_USD = Decimal("0.20")


@dataclass(frozen=True)
class CostForecast:
    provider: str
    request_count: int
    estimated_total_usd: Decimal
    usable_key_budget_usd: Decimal
    under_key_limit: bool
    account_credit_verified: bool = False


def estimate_paper_api(
    provider: str, *,
    days: int = 14, symbols: int = 8, decisions_per_day_per_symbol: int = 24,
    input_tokens_per_call: int = 3000, output_tokens_per_call: int = 1000,
    key_limit_usd: Decimal = KEY_LIMIT_USD,
    reserve_usd: Decimal = RESERVE_USD,
) -> CostForecast:
    """Predict inference costs; Never treat under-limit as spend approval.

    Token counts are scenario inputs, not observations; no rounding makes
    forecasts falsely precise. Calls that use more reasoning tokens can
    exhaust the account or key before their forecasted date.
    """
    vals = (days, symbols, decisions_per_day_per_symbol,
            input_tokens_per_call, output_tokens_per_call)
    if (provider not in PRICES
            or any(type(v) is not int or v < 1 or v > 100_000 for v in vals)
            or type(key_limit_usd) is not Decimal
            or type(reserve_usd) is not Decimal
            or not key_limit_usd.is_finite() or not reserve_usd.is_finite()
            or not Decimal(0) < key_limit_usd <= KEY_LIMIT_USD
            or not Decimal(0) <= reserve_usd < key_limit_usd):
        raise ValueError("invalid_arena_cost_assumptions")
    calls = days * symbols * decisions_per_day_per_symbol
    input_usd, output_usd = PRICES[provider]
    unit = (input_usd * input_tokens_per_call
            + output_usd * output_tokens_per_call) / Decimal(1_000_000)
    estimated = unit * calls
    usable = key_limit_usd - reserve_usd
    return CostForecast(
        provider=provider,
        request_count=calls,
        estimated_total_usd=estimated,
        usable_key_budget_usd=usable,
        under_key_limit=estimated <= usable,
    )
