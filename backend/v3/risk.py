"""Pure PAPER risk quotation for V3 design tests (NOT an order executor).

No strategy rules, market connector, credentials, wallet writes or AI calls.
All risk limits MUST be supplied by a versioned, user-approved policy:
this module does not set or approve production percentages.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN, InvalidOperation


def _d(value: object) -> Decimal:
    try:
        out = Decimal(str(value))
        if not out.is_finite():
            raise ValueError("non_finite")
        return out
    except (InvalidOperation, TypeError) as exc:
        raise ValueError("invalid_number") from exc


@dataclass(frozen=True)
class RiskPolicy:
    max_loss_fraction: Decimal
    max_open_risk_fraction: Decimal
    max_position_margin_fraction: Decimal
    max_total_margin_fraction: Decimal
    minimum_equity: Decimal
    estimated_roundtrip_cost_bp: Decimal
    liquidation_buffer_fraction: Decimal
    # Optional PAPER profile: none/1x..125x preserves historical behavior.
    # 75 USDT risk on 350 USDT margin = 0.214285714285... of actual margin.
    max_loss_margin_fraction: Decimal | None = None
    min_leverage: int = 1
    max_leverage: int = 125


@dataclass(frozen=True)
class RiskRequest:
    equity: Decimal
    available_cash: Decimal
    margin_used: Decimal
    existing_open_risk: Decimal
    entry_price: Decimal
    stop_price: Decimal
    side: int  # +1 LONG, -1 SHORT
    requested_leverage: int
    exchange_leverage_limit: int
    quantity_step: Decimal
    minimum_notional: Decimal
    maintenance_fraction: Decimal
    market_data_fresh: bool
    paused: bool
    daily_loss_latched: bool


@dataclass(frozen=True)
class RiskQuote:
    allowed: bool
    reason: str
    quantity: Decimal = Decimal("0")
    notional: Decimal = Decimal("0")
    margin: Decimal = Decimal("0")
    worst_case_loss_estimate: Decimal = Decimal("0")
    risk_budget: Decimal = Decimal("0")


def _rejected(reason: str) -> RiskQuote:
    return RiskQuote(False, reason)


def quote_paper_risk(policy: RiskPolicy, request: RiskRequest) -> RiskQuote:
    """Return a conservative quote, not an order.

    The stop-loss estimate includes a configurable round-trip cost buffer;
    execution gaps and market liquidation can still exceed that estimate.
    """
    if request.paused or request.daily_loss_latched:
        return _rejected("portfolio_locked")
    if not request.market_data_fresh:
        return _rejected("stale_market_data")
    if type(request.side) is not int or request.side not in (-1, 1):
        return _rejected("invalid_side")
    if (type(policy.min_leverage) is not int or type(policy.max_leverage) is not int
            or not 1 <= policy.min_leverage <= policy.max_leverage <= 125):
        return _rejected("invalid_policy_or_market")
    if (type(request.requested_leverage) is not int
            or type(request.exchange_leverage_limit) is not int
            or request.requested_leverage <= 0
            or request.exchange_leverage_limit <= 0
            or request.requested_leverage > request.exchange_leverage_limit):
        return _rejected("invalid_leverage")
    if not policy.min_leverage <= request.requested_leverage <= policy.max_leverage:
        return _rejected("leverage_outside_profile")

    try:
        if policy.max_loss_margin_fraction is not None:
            loss_per_margin = _d(policy.max_loss_margin_fraction)
            if not Decimal("0") < loss_per_margin <= Decimal("1"):
                return _rejected("invalid_policy_or_market")
        else:
            loss_per_margin = None
        p = [_d(x) for x in (
            policy.max_loss_fraction, policy.max_open_risk_fraction,
            policy.max_position_margin_fraction, policy.max_total_margin_fraction,
            policy.minimum_equity, policy.estimated_roundtrip_cost_bp,
            policy.liquidation_buffer_fraction)]
        q = [_d(x) for x in (
            request.equity, request.available_cash, request.margin_used,
            request.existing_open_risk, request.entry_price, request.stop_price,
            request.quantity_step, request.minimum_notional,
            request.maintenance_fraction)]
    except ValueError:
        return _rejected("invalid_numeric_input")
    (per_trade, total_risk, position_margin, total_margin,
     floor, costs_bp, buffer) = p
    (equity, cash, used_margin, used_risk, price, stop, step, minimum,
     maintenance) = q
    if (not (Decimal("0") < per_trade <= total_risk <= Decimal("1"))
        or not (Decimal("0") < position_margin <= total_margin <= Decimal("1"))
        or not (Decimal("0") < buffer <= Decimal("1"))
        or floor < 0 or costs_bp < 0 or price <= 0 or stop <= 0
        or step <= 0 or minimum < 0 or cash < 0 or used_risk < 0
        or used_margin < 0 or not (Decimal("0") <= maintenance < Decimal("1"))):
        return _rejected("invalid_policy_or_market")

    if equity <= floor:
        return _rejected("equity_floor_reached")
    if ((request.side == 1 and stop >= price)
            or (request.side == -1 and stop <= price)):
        return _rejected("stop_wrong_side")

    leverage = Decimal(request.requested_leverage)
    cost_fraction = costs_bp / Decimal("10000")
    stop_fraction = abs(price - stop) / price
    liquid_dist = Decimal("1") / leverage - maintenance - cost_fraction
    if liquid_dist <= 0 or stop_fraction >= liquid_dist * buffer:
        return _rejected("stop_near_liquidation")
    # This is a bound on loss vs ACTUAL filled margin, not only equity.
    # Downsizing alone cannot change this ratio: a shorter stop or a lower
    # leverage is necessary. The Brain can try a safer leverage before veto.
    if loss_per_margin is not None and leverage * (stop_fraction + cost_fraction) > loss_per_margin:
        return _rejected("margin_loss_ratio_exceeded")

    risk_budget = min(
        equity * per_trade,
        equity * total_risk - used_risk,
        equity - floor - used_risk,
    )
    if risk_budget <= 0:
        return _rejected("risk_budget_exhausted")

    # Cash reserves include the configured cost buffer; this is deliberately
    # stricter than reserving only the opening fee.
    cash_margin = cash / (Decimal("1") + leverage * cost_fraction)
    margin_budget = min(
        equity * position_margin,
        equity * total_margin - used_margin,
        cash_margin,
    )
    if margin_budget <= 0:
        return _rejected("margin_budget_exhausted")

    estimated_loss_per_unit = abs(price - stop) + price * cost_fraction
    quantity_by_risk = risk_budget / estimated_loss_per_unit
    quantity_by_margin = margin_budget * leverage / price
    max_qty = min(quantity_by_risk, quantity_by_margin)
    steps = (max_qty / step).to_integral_value(rounding=ROUND_DOWN)
    quantity = steps * step
    if quantity <= 0 or quantity * price < minimum:
        return _rejected("below_minimum_size")

    notional = quantity * price
    margin = notional / leverage
    loss = quantity * estimated_loss_per_unit
    if (loss > risk_budget or margin > margin_budget or
            (loss_per_margin is not None and loss > margin * loss_per_margin)):
        return _rejected("internal_risk_invariant")
    return RiskQuote(True, "quote_only", quantity, notional, margin,
                     loss, risk_budget)
