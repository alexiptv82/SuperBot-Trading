"""AI conditional proposal contract. A plan is not an order."""
from dataclasses import dataclass
import math
from director.brain_free.config import max_leverage
from .config import ENTRY_PRICE_AGE_MS


def finite(value, minimum=None, maximum=None):
    if isinstance(value,bool) or not isinstance(value,(float,int)) or not math.isfinite(value):
        raise ValueError('nonfinite_plan_number')
    if minimum is not None and value<minimum or maximum is not None and value>maximum:
        raise ValueError('plan_number_outside_bounds')
    return float(value)


@dataclass(frozen=True)
class Plan:
    plan_id: str
    symbol: str
    side: int
    created_ms: int
    expires_ms: int
    trigger: str
    trigger_price: float
    stop: float
    target: float
    margin: float
    leverage: int
    hold_max_ms: int
    protect_after_usd: float
    take_net_usd: float
    reason: str
    invalidation: str
    breakeven_after_usd: float | None = None
    trail_bps: int | None = None
    scale_out: list | None = None
    invalidate_price: float | None = None


def parse_plan(raw,spec,now,whitelist):
    if not isinstance(raw,dict): raise ValueError('plan_not_object')
    symbol=raw.get('symbol')
    if symbol not in whitelist or not isinstance(symbol,str): raise ValueError('unknown_symbol')
    plan_id=raw.get('plan_id')
    if not isinstance(plan_id,str) or not 8<=len(plan_id)<=100 or any(ch.isspace() for ch in plan_id):
        raise ValueError('invalid_plan_id')
    created=int(finite(raw.get('created_ms'),0))
    expires=int(finite(raw.get('expires_ms'),0))
    if created>now or now-created>spec.max_plan_age_ms or not now<expires<=created+spec.max_plan_lifetime_ms:
        raise ValueError('stale_or_overlong_plan')
    side=int(finite(raw.get('side'),-1,1))
    if side not in (-1,1): raise ValueError('invalid_side')
    trigger=raw.get('trigger')
    if trigger not in ('break_above','break_below','touch'): raise ValueError('invalid_trigger')
    px=finite(raw.get('trigger_price'),1e-12)
    stop=finite(raw.get('stop'),1e-12)
    target=finite(raw.get('target'),1e-12)
    if side*(px-stop)<=0 or side*(target-px)<=0: raise ValueError('stop_target_wrong_side')
    if (side==1 and trigger=='break_below') or (side==-1 and trigger=='break_above'):
        raise ValueError('contradictory_trigger')
    margin=finite(raw.get('margin'),spec.min_margin,spec.max_margin_trade)
    lev=int(finite(raw.get('leverage'),1,max_leverage(symbol)))
    hold=int(finite(raw.get('hold_max_ms'),60000,14400000))
    protect=finite(raw.get('protect_after_usd'),0,500)
    take=finite(raw.get('take_net_usd'),0,1000)
    reason,invalidation=raw.get('reason'),raw.get('invalidation')
    if not isinstance(reason,str) or len(reason.strip())<12 or not isinstance(invalidation,str) or len(invalidation.strip())<8:
        raise ValueError('missing_thesis_or_invalidation')
    breakeven=raw.get('breakeven_after_usd')
    if breakeven is not None:
        breakeven=finite(breakeven,0,500)
    trail=raw.get('trail_bps')
    if trail is not None:
        trail_int=int(finite(trail,1,1000))
        if trail_int!=trail: raise ValueError('trail_bps_not_integer')
        trail=trail_int
    invalidate=raw.get('invalidate_price')
    if invalidate is not None:
        invalidate=finite(invalidate,1e-12)
        if side*(px-invalidate)<=0:
            raise ValueError('invalid_invalidation_side')
    steps=raw.get('scale_out')
    if steps is not None:
        if not isinstance(steps,list) or len(steps)>3:
            raise ValueError('invalid_scale_out')
        checked=[]
        total=0.
        previous=0.
        for step in steps:
            if not isinstance(step,dict) or set(step)!={'net_usd','fraction'}:
                raise ValueError('invalid_scale_out_step')
            net=finite(step['net_usd'],0.01,1000)
            fraction=finite(step['fraction'],1e-8,1)
            if net<=previous:
                raise ValueError('scale_out_requires_increasing_thresholds')
            total+=fraction
            if total>1+1e-9:
                raise ValueError('scale_out_exceeds_one')
            checked.append({'net_usd':net,'fraction':fraction})
            previous=net
        steps=checked
    return Plan(plan_id,symbol,side,created,expires,trigger,px,stop,target,margin,lev,
                hold,protect,take,reason.strip(),invalidation.strip(),
                breakeven,trail,steps,invalidate)


def triggered(plan,quote,now):
    if now>=plan.expires_ms: return False
    try: price,ts=finite(quote['price'],1e-12),int(finite(quote['ts_ms'],0))
    except (KeyError,ValueError,TypeError): return False
    if not 0<=now-ts<=ENTRY_PRICE_AGE_MS: return False
    if plan.trigger=='break_above': return price>=plan.trigger_price
    if plan.trigger=='break_below': return price<=plan.trigger_price
    return abs(price/plan.trigger_price-1)<=0.001
