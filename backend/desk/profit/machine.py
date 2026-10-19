"""Pure state transition. Floors protect TOTAL lifecycle net USD, not ROI.

One transition per distinct closed bar. A new floor takes effect on the next
bar: never apply a newly tightened level retroactively to the same candle.
"""
from dataclasses import dataclass, replace
from .liquidable import finite

STATES = ("OSSERVA", "ARMATO", "PROTETTO", "STRETTO", "USCITA", "CONGELATO")


@dataclass(frozen=True)
class State:
    name: str = "OSSERVA"
    resume: str = "OSSERVA"
    floor_usd: float | None = None
    peak_usd: float | None = None
    peak_ms: int = 0
    last_bar_ms: int = -1
    confirmations: int = 0
    partial_proposed: bool = False

    def __post_init__(self):
        if self.name not in STATES or self.resume not in STATES[:-1] or self.confirmations < 0:
            raise ValueError("invalid machine state")
        finite(*(x for x in (self.floor_usd, self.peak_usd) if x is not None))


@dataclass(frozen=True)
class Decision:
    state: State
    action: str
    reasons: tuple[str, ...]
    fraction: float = 0.0


def step(state, *, features, liquidation, qty, reversal, policy):
    finite(qty)
    if qty <= 0:
        raise ValueError("positive residual quantity required")
    if state.name == "USCITA":
        return Decision(state, "HOLD", ("exit already proposed",))
    if not features.valid:
        resume = state.resume if state.name == "CONGELATO" else state.name
        return Decision(replace(state, name="CONGELATO", resume=resume), "HOLD", (features.reason,))
    finite(liquidation.net_usd, features.atr, reversal.score)
    if features.bar_close_ms < state.last_bar_ms:
        raise ValueError("time reversal")
    if features.bar_close_ms == state.last_bar_ms:
        return Decision(state, "HOLD", ("bar already evaluated",))
    s = replace(state, name=state.resume) if state.name == "CONGELATO" else state
    net = liquidation.net_usd
    if s.peak_usd is None or net > s.peak_usd:
        s = replace(s, peak_usd=net, peak_ms=features.bar_close_ms)
    s = replace(s, last_bar_ms=features.bar_close_ms)
    credible = reversal.score >= policy.reversal_threshold and len(set(reversal.families)) >= 2
    if (s.floor_usd is not None and net <= s.floor_usd) or (s.name != "OSSERVA" and credible):
        return Decision(replace(s, name="USCITA"), "ESCI", ("existing floor breached" if s.floor_usd is not None and net <= s.floor_usd else "independent reversal evidence",))
    if s.name == "OSSERVA":
        threshold = liquidation.close_fee + liquidation.spread_cost + liquidation.slippage_cost + policy.arm_atr * features.atr * qty
        count = s.confirmations+1 if net >= threshold else 0
        s = replace(s, confirmations=count)
        if count >= policy.confirmations:
            return Decision(replace(s, name="ARMATO"), "ARMA", ("cost and ATR threshold confirmed",))
        return Decision(s, "HOLD", ("awaiting confirmed profit",))
    entering = s.name == "ARMATO"
    deteriorated = bool(reversal.families) or features.bar_close_ms-s.peak_ms >= policy.no_peak_ms
    name = "STRETTO" if s.name == "STRETTO" or (not entering and deteriorated) else "PROTETTO"
    factor = {"trend": policy.trend_multiplier, "range": policy.range_multiplier, "high_volatility": policy.high_vol_multiplier}.get(features.regime)
    if factor is None:
        return Decision(replace(state, name="CONGELATO", resume=state.resume if state.name == "CONGELATO" else state.name), "HOLD", ("unknown regime",))
    distance = (policy.tight_atr if name == "STRETTO" else policy.giveback_atr) * factor * features.atr * qty
    candidate = s.peak_usd-distance
    floor = max(s.floor_usd, candidate) if s.floor_usd is not None else candidate
    tightened = s.floor_usd is None or floor > s.floor_usd
    s = replace(s, name=name, floor_usd=floor)
    if entering and policy.partial_fraction and not s.partial_proposed:
        return Decision(replace(s, partial_proposed=True), "PARZIALE", ("research proposal only; no execution",), policy.partial_fraction)
    return Decision(s, "STRINGI" if tightened else "HOLD", ("monotone net USD floor",))
