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


def validate_spec(spec):
    """Validate explicit mandates before creating files; no financial defaults added."""
    import math
    if not isinstance(spec, WalletSpec):
        raise ValueError('explicit_wallet_spec_required')
    if (not isinstance(spec.name,str) or not spec.name.isascii() or
            not spec.name.isalnum() or not 1<=len(spec.name)<=20 or
            not isinstance(spec.account_id,str) or not 1<=len(spec.account_id)<=80):
        raise ValueError('invalid_wallet_identity')
    for key in ('min_margin','max_margin_trade','start_cash','max_margin_total',
                'risk_trade_usd','risk_portfolio_usd','daily_stop_pct','kill_equity'):
        value=getattr(spec,key)
        if type(value) not in (int,float) or not math.isfinite(value) or value<=0:
            raise ValueError('invalid_wallet_mandate')
    if (type(spec.slots)!=int or not 1<=spec.slots<=100 or
            not spec.min_margin<=spec.max_margin_trade<=spec.max_margin_total<spec.start_cash or
            not spec.risk_trade_usd<=spec.risk_portfolio_usd<=spec.start_cash or
            not 0<spec.daily_stop_pct<1 or not spec.kill_equity<spec.start_cash or
            type(spec.max_plan_age_ms)!=int or type(spec.max_plan_lifetime_ms)!=int or
            not 1000<=spec.max_plan_age_ms<=spec.max_plan_lifetime_ms):
        raise ValueError('invalid_wallet_mandate')
    return spec
