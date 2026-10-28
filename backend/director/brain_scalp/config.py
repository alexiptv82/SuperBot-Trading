"""Separate immutable PAPER mandates; never inherit classical portfolio state."""
from dataclasses import dataclass, replace
from director.brain_free.config import Config as BrainConfig


@dataclass(frozen=True)
class WalletSpec:
    name: str
    account_id: str
    slots: int
    min_margin: float
    max_margin_trade: float
    start_cash: float = 1000.0
    max_margin_total: float = 950.0
    risk_trade_usd: float = 50.0
    risk_portfolio_usd: float = 150.0
    daily_stop_pct: float = 0.20
    kill_equity: float = 450.0
    max_plan_age_ms: int = 90000
    max_plan_lifetime_ms: int = 300000

    def brain_config(self) -> BrainConfig:
        return replace(BrainConfig(), start_cash=self.start_cash,
                       max_margin=self.max_margin_total, max_slots=self.slots)


HAWK = WalletSpec('hawk', 'brain-scalp-hawk-paper', 10, 100, 250)
BULL = WalletSpec('bull', 'brain-scalp-bull-paper', 3, 150, 350)
SPECS = {'hawk': HAWK, 'bull': BULL}
