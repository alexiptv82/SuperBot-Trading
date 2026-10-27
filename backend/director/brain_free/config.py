"""Approved immutable experiment configuration; no monetary API gate."""
from dataclasses import asdict, dataclass
import hashlib,json

SYMBOLS=tuple('BTC ETH BNB XRP SOL ADA DOGE AVAX DOT LINK UNI ATOM LTC BCH APT ARB OP NEAR FIL INJ SUI TIA RUNE STX XAU XAG'.split())
@dataclass(frozen=True)
class Config:
    version:str='brain-free-v1'
    start_cash:float=2000.0
    max_margin:float=1600.0
    max_slots:int=10
    price_age_ms:int=30000
    bar_age_ms:int=90000
    analysis_ms:int=900000
    management_ms:int=300000
    poll_s:float=5.0
    experiment_ms:int=168*3600000
    model:str='deepseek-flash'
    thinking:str='low'
    max_tokens:int=8192
    timeout_s:int=120
    fee_rate:float=.0006
    slippage:float=.0002
    # Conservative fallback, only if exchange tier data is unavailable.
    maintenance:float=.005
    liquidation_buffer:float=.75
    report_hour:int=22
    symbols:tuple=SYMBOLS
    def digest(self,prompt):
        return hashlib.sha256(json.dumps({'config':asdict(self),'prompt':prompt},sort_keys=True).encode()).hexdigest()

def max_leverage(symbol):return 45 if symbol in ('BTC','XAU','XAG') else 30 if symbol=='ETH' else 25

def number(value,low=0,high=float('inf')):
    import math
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not low<=value<=high:
        raise ValueError('invalid_number')
    return float(value)
