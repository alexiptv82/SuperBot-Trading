"""Offline-only shadow replay. No exchange access, orders, or bot integration.

Input snapshots must be chronological and independently collected. Prices are
observations, not executable quotes; simulated fills use conservative slippage.
A shadow exit is terminal: subsequent baseline ticks cannot reopen it.
"""
from dataclasses import dataclass
from typing import Optional

try:
    from .profit_manager_shadow import ProfitConfig, assess
except ImportError:
    from profit_manager_shadow import ProfitConfig, assess


@dataclass(frozen=True)
class Snapshot:
    trade_id: str
    timestamp_ms: int
    side: int
    entry: float
    mark: float
    qty: float
    allocated_margin: float
    open_ms: int
    funding_paid_usdt: float = 0.0  # signed: negative means received
    open_fee_usdt: Optional[float] = None


@dataclass(frozen=True)
class ReplayEvent:
    trade_id: str
    timestamp_ms: int
    action: str
    reason: str
    roi_net_pct: float
    peak_roi_net_pct: float
    estimated_net_usdt: float


class ShadowReplay:
    """One independent PM-A counterfactual per trade.

    Rejects duplicate/out-of-order ticks and changes in position economics:
    partial closes and DCA require a separately audited accounting model.
    """

    def __init__(self, config: ProfitConfig = ProfitConfig()):
        self.config = config
        self._state = {}

    def observe(self, snap: Snapshot) -> ReplayEvent:
        if not snap.trade_id or not isinstance(snap.timestamp_ms, int) or not isinstance(snap.open_ms, int):
            raise ValueError("Missing trade identity or invalid timestamps")
        if snap.timestamp_ms < snap.open_ms:
            raise ValueError("Snapshot precedes opening")
        prev = self._state.get(snap.trade_id)
        if prev is not None:
            if snap.timestamp_ms <= prev["timestamp_ms"]:
                raise ValueError("Duplicate or out-of-order snapshot")
            if (snap.side, snap.entry, snap.qty, snap.allocated_margin, snap.open_ms) != prev["identity"]:
                raise ValueError("Position changed: partial/DCA requires explicit ledger")
            if prev["exit"] is not None:
                self._state[snap.trade_id]["timestamp_ms"] = snap.timestamp_ms
                return prev["exit"]
        peak = prev["peak"] if prev is not None else -1e12
        d = assess(
            side=snap.side, entry=snap.entry, mark=snap.mark, qty=snap.qty,
            margin=snap.allocated_margin, peak_roi_net_pct=peak,
            held_seconds=(snap.timestamp_ms - snap.open_ms) / 1000,
            config=self.config, funding_usdt=snap.funding_paid_usdt,
            open_fee_usdt=snap.open_fee_usdt,
        )
        event = ReplayEvent(snap.trade_id, snap.timestamp_ms, d.action,
                            d.reason, d.roi_net_pct, d.peak_roi_net_pct,
                            d.estimated_net_usdt)
        self._state[snap.trade_id] = {
            "timestamp_ms": snap.timestamp_ms,
            "identity": (snap.side, snap.entry, snap.qty, snap.allocated_margin, snap.open_ms),
            "peak": d.peak_roi_net_pct,
            "exit": event if d.action == "SHADOW_EXIT" else None,
        }
        return event
