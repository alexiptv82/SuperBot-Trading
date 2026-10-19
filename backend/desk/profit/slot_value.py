"""Net EV inputs must share horizon, currency and estimation convention."""
from dataclasses import dataclass
from .liquidable import finite


@dataclass(frozen=True)
class SwapDecision:
    action: str
    advantage_usd: float | None
    reason: str


def compare(new_net_ev, residual_net_ev, replacement_cost, safety_margin, *, comparable=False):
    if not comparable or any(x is None for x in (new_net_ev, residual_net_ev, replacement_cost, safety_margin)):
        return SwapDecision("HOLD", None, "missing or incomparable estimates")
    finite(new_net_ev, residual_net_ev, replacement_cost, safety_margin)
    if min(replacement_cost, safety_margin) < 0:
        raise ValueError("negative replacement costs/margin")
    advantage = new_net_ev-residual_net_ev-replacement_cost-safety_margin
    return SwapDecision("PROPONI_SOSTITUZIONE" if advantage > 0 else "HOLD", advantage, "strict incremental net EV comparison")
