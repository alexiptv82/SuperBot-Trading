"""Separate immutable PAPER mandates; never inherit classical portfolio state."""
from dataclasses import dataclass, replace
from director.brain_free.config import Config as BrainConfig

# Separate scalp quote freshness; never change the active Brain Free config.
ENTRY_PRICE_AGE_MS = 3000
PROTECT_PRICE_AGE_MS = 10000

# Verified official model IDs. This offline module does not call either API.
SCANNER_MODEL = 'deepseek-flash'
SCANNER_REASONING_EFFORT = 'high'
REVIEW_PROVIDER = 'claude'  # Actual model/credentials belong to the existing transport.


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
                       max_margin=self.max_margin_total, max_slots=self.slots,
                       model=SCANNER_MODEL,thinking=SCANNER_REASONING_EFFORT)


# Group 6 option C: slots are upper bounds, not capital allocations.
# Hawk can reserve at most nine minimum-size trades under the 950 budget;
# Bull can reserve 350 + 350 + 250, never three simultaneous 350 margins.
HAWK = WalletSpec('hawk', 'brain-scalp-hawk-paper', 10, 100, 250)
BULL = WalletSpec('bull', 'brain-scalp-bull-paper', 3, 150, 350)
SPECS = {'hawk': HAWK, 'bull': BULL}
