"""Bounded, causal projection of operator-confirmed examples; never rules."""
import json
import math
from pathlib import Path

def confirmed_preferences(root, account_id, now_ms):
    if type(now_ms) is not int or now_ms<=0:return []
    try:
        path=Path(root)/'manual_close_reviews.jsonl'
        if path.is_symlink():return []
        with path.open('rb') as f:
            data=f.read(2000001)
        if len(data)>2000000:return []
        pending={};resolved={}
        for line in data.splitlines():
            row=json.loads(line)
            if row.get('event')=='pending':pending[row['event_id']]=row['data']
            elif row.get('event')=='resolved':resolved[row['event_id']]=row
        out=[]
        for eid,r in resolved.items():
            d=pending.get(eid,{})
            t=r.get('at_ms');closed=d.get('close_ms')
            if (r.get('choice')!='yes' or type(t) is not int or type(closed) is not int
                    or not 0<closed<=t<=now_ms or d.get('account_id')!=account_id
                    or d.get('source')!='manual_user' or d.get('paper') is not True
                    or d.get('side') not in ('LONG','SHORT')):continue
            keys=('pnl_usd','margin','pnl_pct_margin','duration_min')
            if any(type(d.get(k)) not in (int,float) or not math.isfinite(d[k]) for k in keys):continue
            if d['pnl_usd']<=0 or d['margin']<=0:continue
            symbol=d.get('symbol')
            if not isinstance(symbol,str) or not symbol.isascii() or not symbol.isalnum():continue
            out.append({'event_id':eid,'symbol':symbol,'side':d['side'],
                        'close_ms':closed,'confirmed_ms':t,
                        **{k:d[k] for k in keys},
                        'interpretation':'user_confirmed_profit_exit_example',
                        'authority':'observational_only','training_applied':False})
        return sorted(out,key=lambda r:(r['confirmed_ms'],r['event_id']))[-5:]
    except (OSError,ValueError,KeyError,TypeError):return []

def project_preferences(rows,account_id,now_ms):
    # Reuse the strict schema at the context boundary, without arbitrary text.
    if not isinstance(rows,list):return []
    out=[]
    for r in rows[-5:]:
        if not isinstance(r,dict):continue
        try:
            if (r.get('authority')!='observational_only' or r.get('training_applied') is not False
                    or r.get('interpretation')!='user_confirmed_profit_exit_example'
                    or r.get('side') not in ('LONG','SHORT')
                    or not isinstance(r.get('event_id'),str) or len(r['event_id'])!=64
                    or any(c not in '0123456789abcdef' for c in r['event_id'])
                    or not isinstance(r.get('symbol'),str) or not r['symbol'].isascii()
                    or not r['symbol'].isalnum()
                    or type(r.get('close_ms')) is not int or type(r.get('confirmed_ms')) is not int
                    or not 0<r['close_ms']<=r['confirmed_ms']<=now_ms):continue
            keys=('pnl_usd','margin','pnl_pct_margin','duration_min')
            if any(type(r.get(k)) not in (int,float) or not math.isfinite(r[k]) for k in keys):continue
            if r['pnl_usd']<=0 or r['margin']<=0:continue
            out.append({k:r[k] for k in ('event_id','symbol','side','close_ms','confirmed_ms',*keys,
                'interpretation','authority','training_applied')})
        except (TypeError,ValueError):continue
    return out
