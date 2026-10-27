"""Observed usage ledger projection, never an allowance or entry gate."""
from datetime import datetime,timezone
import json

TARIFF='deepseek-flash-official-2026-10-27'
def price(usage,ts):
    hit=int(usage.get('prompt_cache_hit_tokens',0));total=int(usage['prompt_tokens'])
    miss=int(usage.get('prompt_cache_miss_tokens',total-hit));out=int(usage['completion_tokens'])
    reasoning=int((usage.get('completion_tokens_details') or {}).get('reasoning_tokens',0))
    if min(hit,miss,out,reasoning)<0 or hit+miss!=total or reasoning>out:raise ValueError('invalid_usage')
    d=datetime.fromtimestamp(ts/1000,timezone.utc)
    multiplier=2 if d.weekday()<5 and (1<=d.hour<4 or 6<=d.hour<10) else 1
    # completion_tokens already INCLUDES reasoning: never add reasoning twice.
    cost=(hit*.003+miss*.15+out*.60)*multiplier/1_000_000
    return {'cost':cost,'hit':hit,'miss':miss,'output':out,'reasoning':reasoning,
            'tariff':TARIFF,'estimated_invoice':True,'peak_multiplier':multiplier}

def view(db,now):
    today=datetime.fromtimestamp(now/1000,timezone.utc).strftime('%Y-%m-%d')
    day=total=0.;unknown=0;calls=0
    for ts,status,body in db.execute('SELECT ts,status,body FROM requests'):
        item=json.loads(body);calls+=1
        cost=(item.get('billing') or {}).get('cost')
        if cost is None:unknown+=1;continue
        total+=cost
        if datetime.fromtimestamp(ts/1000,timezone.utc).strftime('%Y-%m-%d')==today:day+=cost
    return {'today_utc':today,'today_usd':day,'total_usd':total,'calls':calls,
            'uncertain_requests':unknown,'accounting':'usage_at_recorded_tariff_not_provider_invoice','budget_gate':False}
