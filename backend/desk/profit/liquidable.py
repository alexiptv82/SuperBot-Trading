"""Immutable accounting VIEW, never a replacement for PaperAccount.

Open fees and funding apply only to residual legs. realized_net already includes
all costs of closed fractions: do not charge those costs a second time.
"""
from dataclasses import dataclass
from math import isfinite


def finite(*values):
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(v) for v in values):
        raise ValueError("finite numeric values required")


@dataclass(frozen=True)
class Leg:
    entry: float
    qty: float
    open_fee: float

    def __post_init__(self):
        finite(self.entry, self.qty, self.open_fee)
        if self.entry <= 0 or self.qty <= 0 or self.open_fee < 0:
            raise ValueError("invalid residual leg")


@dataclass(frozen=True)
class PositionView:
    """Only open residual quantities and their allocated remaining entry fees.

    Exclude fully closed legs. For a partially closed leg pass its remaining
    qty and remaining open_fee, never the original full amounts. funding_paid
    is accrued funding allocated to the residual position, NOT lifecycle
    funding already charged inside realized_net. This pure view cannot infer
    allocation correctness from numbers alone; the source adapter must prove it.
    """
    side: int
    legs: tuple[Leg, ...]
    funding_paid: float
    realized_net: float
    reference_margin: float

    def __post_init__(self):
        finite(self.side, self.funding_paid, self.realized_net, self.reference_margin)
        if self.side not in (-1, 1) or not isinstance(self.legs, tuple) or not self.legs or self.reference_margin <= 0:
            raise ValueError("invalid immutable position view")
        if not all(isinstance(x, Leg) for x in self.legs):
            raise ValueError("Leg objects required")


@dataclass(frozen=True)
class Costs:
    fee_rate: float
    spread_fraction: float
    slippage_fraction: float

    def __post_init__(self):
        finite(self.fee_rate, self.spread_fraction, self.slippage_fraction)
        if min(self.fee_rate, self.spread_fraction, self.slippage_fraction) < 0 or self.fee_rate >= 1 or self.spread_fraction / 2 + self.slippage_fraction >= 1:
            raise ValueError("invalid costs")


@dataclass(frozen=True)
class Liquidation:
    net_usd: float
    roi_pct: float
    fill: float
    close_fee: float
    spread_cost: float
    slippage_cost: float
    funding: float


def evaluate(position: PositionView, mark: float, costs: Costs) -> Liquidation:
    finite(mark)
    if mark <= 0:
        raise ValueError("positive mark required")
    qty = sum(x.qty for x in position.legs)
    spread = mark * qty * costs.spread_fraction / 2
    slip = mark * qty * costs.slippage_fraction
    fill = mark * (1 - position.side * (costs.spread_fraction / 2 + costs.slippage_fraction))
    fee = fill * qty * costs.fee_rate
    gross = sum(position.side * (fill - x.entry) * x.qty - x.open_fee for x in position.legs)
    net = position.realized_net + gross - fee - position.funding_paid
    finite(net, fill, fee)
    return Liquidation(net, 100 * net / position.reference_margin, fill, fee, spread, slip, position.funding_paid)
