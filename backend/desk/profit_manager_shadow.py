"""Profit Manager v0: pure, side-effect-free SHADOW decision engine.

No orders, no file writes, no network access. Never call this as an execution
engine without a separately reviewed integration and paper-only testing.
ROI is NET estimated profit / allocated margin, not price percentage.
"""
from dataclasses import dataclass
from typing import Optional
import math


@dataclass(frozen=True)
class ProfitConfig:
    activation_roi_pct: float = 20.0
    lock_roi_pct: float = 5.0
    trail_drawdown_pct: float = 10.0
    fee_rate_side: float = 0.0006
    slip_rate_side: float = 0.0003
    min_hold_seconds: int = 60


@dataclass(frozen=True)
class ShadowDecision:
    action: str
    reason: str
    roi_net_pct: float
    peak_roi_net_pct: float
    protected_roi_pct: Optional[float]
    estimated_net_usdt: float


def assess(*, side: int, entry: float, mark: float, qty: float, margin: float,
           peak_roi_net_pct: float, held_seconds: float,
           config: ProfitConfig = ProfitConfig(), funding_usdt: float = 0.0,
           open_fee_usdt: Optional[float] = None) -> ShadowDecision:
    """Assess one position on observed mark; caller owns persistent peak tracking.

    Conservative estimated exit: worse execution by configured slippage and
    taker fee; fee_open defaults to assumed taker fee.
    A single current mark cannot prove a historical trailing fill.
    """
    values = (entry, mark, qty, margin, peak_roi_net_pct, held_seconds, funding_usdt)
    if side not in (-1, 1) or not all(math.isfinite(v) for v in values):
        raise ValueError("Invalid position data")
    if min(entry, mark, qty, margin) <= 0 or held_seconds < 0 or funding_usdt < 0:
        raise ValueError("Invalid positive quantities or duration")
    if not (0 <= config.fee_rate_side < 0.1 and 0 <= config.slip_rate_side < 0.1):
        raise ValueError("Invalid cost assumptions")
    if not (0 <= config.lock_roi_pct <= config.activation_roi_pct and
            0 < config.trail_drawdown_pct and config.min_hold_seconds >= 0):
        raise ValueError("Invalid profit thresholds")
    exit_fill = mark * (1 - side * config.slip_rate_side)
    fee_open = (entry * qty * config.fee_rate_side if open_fee_usdt is None
                else open_fee_usdt)
    if not math.isfinite(fee_open) or fee_open < 0:
        raise ValueError("Invalid open fee")
    net = side * (exit_fill - entry) * qty - fee_open - exit_fill * qty * config.fee_rate_side - funding_usdt
    roi = 100 * net / margin
    peak = max(roi, peak_roi_net_pct)
    if held_seconds < config.min_hold_seconds:
        action, reason, floor = "HOLD", "minimum_hold", None
    elif peak < config.activation_roi_pct:
        action, reason, floor = "HOLD", "not_activated", None
    else:
        floor = max(config.lock_roi_pct, peak - config.trail_drawdown_pct)
        if roi <= floor:
            action, reason = "SHADOW_EXIT", "net_roi_below_dynamic_floor"
        else:
            action, reason = "HOLD", "protected_profit_active"
    return ShadowDecision(action, reason, round(roi, 4), round(peak, 4),
                          round(floor, 4) if floor is not None else None,
                          round(net, 4))
