"""Pure optional AI-advisor scheduling for SuperBot Brain AI Arena.

During the 14-day benchmark the three AI wallets must remain independent.
This planner is for a LATER, separate advisor-mode experiment. It does not
call an AI, open or close PAPER positions, change stop/TP/risk, or grant
execution authority. It never turns NO_TRADE into a trade.

The lead AI can be DeepSeek, Qwen or MiniMax. An advisor is asked only for
an OPEN with a specific, causal uncertainty flag and available budgets.
The second advisor is exceptional (first advisor disagreed), never H24.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal
import re

PROVIDERS = ("deepseek", "qwen", "minimax")
SIDE = ("LONG", "SHORT")
REGIMES = frozenset({
    "TREND_UP", "TREND_DOWN", "RANGE", "EXPANSION",
    "SHOCK", "UNCERTAIN",
})
TRENDS = frozenset({"UP", "DOWN", "RANGE", "UNKNOWN"})
SYMBOL = re.compile(r"[A-Z0-9]{3,24}\Z")
THRESHOLD = Decimal("0.65")

# A single request cost is estimated conservatively; actual charges must be
# recorded by the existing budget ledger and provider-key limits as well.
QWEN_IN, QWEN_OUT = Decimal("0.32"), Decimal("1.28")
MINIMAX_IN, MINIMAX_OUT = Decimal("0.15"), Decimal("0.60")


@dataclass(frozen=True)
class MarketDecision:
    provider: str
    symbol: str
    action: Literal["LONG", "SHORT", "NO_TRADE"]
    confidence: Decimal | None
    regime: str
    trend_4h: str
    trend_1h: str
    market_data_fresh: bool
    risk_eligible: bool
    timestamp_ms: int


@dataclass(frozen=True)
class AdvisorAllowance:
    provider: str
    daily_calls_left: int
    daily_usd_left: Decimal
    key_usd_left: Decimal
    estimated_worst_call_usd: Decimal


@dataclass(frozen=True)
class AdvisorPlan:
    consult: tuple[str, ...]
    triggers: tuple[str, ...]
    reason: str
    mode: str = "SHADOW_ONLY"
    can_change_trade: bool = False


def projected_usd(
    provider: str, *, input_tokens: int, output_tokens: int,
) -> Decimal:
    """Price snapshot verified in OpenRouter catalog on 16 Nov 2026.

    Estimates only, not actual billing or a hard per-call cost ceiling.
    DeepSeek is deliberately not priced here because its separate supplier
    uses a different live tariff/budget.
    """
    if (provider not in ("qwen", "minimax")
            or type(input_tokens) is not int or type(output_tokens) is not int
            or not 0 <= input_tokens <= 100_000
            or not 0 <= output_tokens <= 100_000):
        raise ValueError("invalid_cost_projection")
    rates = {
        "qwen": (QWEN_IN, QWEN_OUT),
        "minimax": (MINIMAX_IN, MINIMAX_OUT),
    }
    inp, out = rates[provider]
    return (inp * input_tokens + out * output_tokens) / Decimal(1_000_000)


def _valid(d: MarketDecision) -> bool:
    return (
        type(d) is MarketDecision
        and d.provider in PROVIDERS
        and type(d.symbol) is str and SYMBOL.fullmatch(d.symbol) is not None
        and d.action in SIDE + ("NO_TRADE",)
        and (d.confidence is None or (
            type(d.confidence) is Decimal
            and d.confidence.is_finite()
            and Decimal(0) <= d.confidence <= Decimal(1)))
        and d.regime in REGIMES
        and d.trend_4h in TRENDS and d.trend_1h in TRENDS
        and type(d.market_data_fresh) is bool
        and type(d.risk_eligible) is bool
        and type(d.timestamp_ms) is int and d.timestamp_ms > 0
    )


def _can_spend(allowance: AdvisorAllowance | None) -> bool:
    if type(allowance) is not AdvisorAllowance:
        return False
    amounts = (
        allowance.daily_usd_left,
        allowance.key_usd_left,
        allowance.estimated_worst_call_usd,
    )
    return (
        allowance.provider in PROVIDERS
        and type(allowance.daily_calls_left) is int
        and allowance.daily_calls_left > 0
        and all(type(x) is Decimal and x.is_finite() for x in amounts)
        and Decimal(0) < allowance.estimated_worst_call_usd
        and allowance.daily_usd_left >= allowance.estimated_worst_call_usd
        and allowance.key_usd_left >= allowance.estimated_worst_call_usd
    )


def triggers(d: MarketDecision) -> tuple[str, ...]:
    """Causal *candidate* reasons; never infer from future trade outcomes."""
    if not _valid(d) or not d.market_data_fresh or not d.risk_eligible:
        return ()
    if d.action not in SIDE:
        return ()  # NO_TRADE stays NO_TRADE; no advisor expense.
    reasons = []
    if d.confidence is not None and d.confidence < THRESHOLD:
        reasons.append("PRIMARY_LOW_CONFIDENCE")
    if (
        (d.action == "LONG" and d.trend_4h == "DOWN")
        or (d.action == "SHORT" and d.trend_4h == "UP")
    ):
        reasons.append("AGAINST_4H_TREND")
    if (
        (d.trend_4h, d.trend_1h) in (
            ("UP", "DOWN"), ("DOWN", "UP")
        )
    ):
        reasons.append("MTF_CONFLICT")
    if d.regime == "SHOCK":
        reasons.append("SHOCK_REGIME")
    # EXPANSION alone must never veto the best SHORTs or trigger expensive
    # advisor calls: empirically it also occurs in profitable breakdowns.
    return tuple(reasons)


def plan_first_opinion(
    decision: MarketDecision,
    allowances: tuple[AdvisorAllowance, ...],
    *,
    enabled: bool = False,
    advisor_preference: tuple[str, ...] = ("qwen", "minimax", "deepseek"),
) -> AdvisorPlan:
    """Choose at most one *other* AI, never the primary.

    The output only describes a possible advisory request. Another separately
    approved component must actually send it and log the token cost.
    """
    if enabled is not True:
        return AdvisorPlan((), (), "NOT_ENABLED")
    if not _valid(decision):
        return AdvisorPlan((), (), "INVALID_DECISION")
    if not decision.market_data_fresh:
        return AdvisorPlan((), (), "STALE_MARKET_NO_INFERENCE")
    if not decision.risk_eligible:
        return AdvisorPlan((), (), "RISK_INELIGIBLE_NO_INFERENCE")
    flags = triggers(decision)
    if not flags:
        return AdvisorPlan((), (), "NO_TRIGGER")
    if (
        type(advisor_preference) is not tuple
        or len(set(advisor_preference)) != len(advisor_preference)
        or any(p not in PROVIDERS for p in advisor_preference)
        or any(type(a) is not AdvisorAllowance for a in allowances)
    ):
        return AdvisorPlan((), flags, "INVALID_ALLOWANCES")
    by_provider = {a.provider: a for a in allowances}
    if len(by_provider) != len(allowances):
        return AdvisorPlan((), flags, "INVALID_ALLOWANCES")
    for provider in advisor_preference:
        if provider != decision.provider and _can_spend(by_provider.get(provider)):
            return AdvisorPlan((provider,), flags, "CONSULT_FIRST_ADVISOR")
    return AdvisorPlan((), flags, "NO_BUDGET_OR_ADVISOR")


def plan_second_opinion(
    decision: MarketDecision,
    first_advisor: str,
    first_advice: Literal["LONG", "SHORT", "NO_TRADE"],
    allowances: tuple[AdvisorAllowance, ...],
    *,
    enabled: bool = False,
) -> AdvisorPlan:
    """Optional tie-break study when first advisor differs from the leader.

    No advisor majority vote may create/change an order; the current primary
    remains responsible for final judgment and deterministic risk still gates.
    """
    if enabled is not True:
        return AdvisorPlan((), (), "NOT_ENABLED")
    if not _valid(decision) or not decision.market_data_fresh or not decision.risk_eligible:
        return AdvisorPlan((), (), "INVALID_OR_UNSAFE")
    flags = triggers(decision)
    if not flags or first_advisor not in PROVIDERS or first_advisor == decision.provider:
        return AdvisorPlan((), (), "NOT_ELIGIBLE")
    if first_advice not in SIDE + ("NO_TRADE",):
        return AdvisorPlan((), flags, "INVALID_ADVICE")
    if first_advice == decision.action:
        return AdvisorPlan((), flags, "FIRST_AGREES_NO_SECOND_CALL")
    remaining = tuple(
        p for p in PROVIDERS if p not in (decision.provider, first_advisor)
    )
    if len(remaining) != 1:
        return AdvisorPlan((), flags, "INVALID_PROVIDER_SCOPE")
    second = remaining[0]
    by_provider = {a.provider: a for a in allowances}
    if len(by_provider) != len(allowances) or not _can_spend(by_provider.get(second)):
        return AdvisorPlan((), flags, "NO_BUDGET_FOR_SECOND")
    return AdvisorPlan((second,), flags + ("FIRST_DISAGREES",),
                       "CONSULT_SECOND_ADVISOR")


def advisory_result_policy(*, lead_decision: str, opinions: tuple[str, ...]) -> dict:
    """Shadow-only interpretation; no automatic trade veto or override."""
    if lead_decision not in SIDE + ("NO_TRADE",) or (
        type(opinions) is not tuple or
        any(op not in SIDE + ("NO_TRADE",) for op in opinions)
    ):
        raise ValueError("invalid_advice")
    return {
        "lead_decision": lead_decision,
        "advice_count": len(opinions),
        "advisor_disagreement": any(op != lead_decision for op in opinions),
        "final_action": "OBSERVE_ONLY",
        "trading_authority": False,
        "risk_override": False,
    }
