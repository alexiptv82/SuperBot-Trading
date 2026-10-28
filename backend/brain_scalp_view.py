"""Read-only, authenticated-dashboard projection for two isolated PAPER wallets.

Never creates, upgrades, repairs or writes a ledger. Missing wallet != $1000.
"""
import json
import math
from pathlib import Path
import sqlite3
import time

IDS={'hawk':'brain-scalp-hawk-paper','bull':'brain-scalp-bull-paper'}
CAPACITY={'hawk':10,'bull':3}


def _number(x):
    if isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x):
        raise ValueError('invalid_number')
    return float(x)


def read_wallet(base,name,now=None):
    if name not in IDS: raise ValueError('unknown_wallet')
    now=int(time.time()*1000) if now is None else now
    base=Path(base).absolute()
    root=base/name;file=root/'brain_scalp.sqlite3'
    if root.is_symlink() or file.is_symlink() or not file.is_file():
        return {'status':'not_started','available':False,'name':name}
    db=None
    try:
        db=sqlite3.connect(file.resolve().as_uri()+'?mode=ro',uri=True,timeout=.15)
        db.execute('PRAGMA query_only=ON')
        deadline=time.monotonic()+.3
        db.set_progress_handler(lambda:int(time.monotonic()>deadline),1000)
        db.execute('BEGIN')
        row=db.execute('SELECT body FROM state WHERE id=1').fetchone()
        if not row or len(row[0])>2_000_000: raise ValueError('bad_state')
        s=json.loads(row[0])
        if s.get('account_id')!=IDS[name] or s.get('mode')!='paper':
            raise ValueError('foreign_account')
        cash=_number(s['cash'])
        if cash<0: raise ValueError('negative_cash')
        margin=0.;gross=0.;complete=True;positions=[]
        quotes=s.get('last_prices',{})
        for sym,p in s['positions'].items():
            qty=_number(p['qty']);entry=_number(p['entry'])
            mar=_number(p['margin']);lev=_number(p['leverage'])
            if qty<=0 or entry<=0 or mar<=0 or lev<=0 or p['side'] not in (-1,1):
                raise ValueError('invalid_position')
            margin+=mar
            q=quotes.get(sym) or {}
            px=q.get('price');ts=q.get('ts_ms')
            valid=(isinstance(px,(int,float)) and not isinstance(px,bool) and
                   math.isfinite(px) and px>0 and isinstance(ts,(int,float)) and
                   not isinstance(ts,bool) and 0<=now-ts<=30000)
            net=None
            if valid:
                gross+=p['side']*(px-entry)*qty
                fill=px*(1-p['side']*.0002)
                net=p['side']*(fill-entry)*qty-_number(p['entry_fees'])-_number(p.get('funding',0))-qty*fill*.0006
            else:complete=False
            positions.append({'symbol':sym,'side':'LONG' if p['side']==1 else 'SHORT',
                'margin':mar,'leverage':lev,'notional':qty*entry,'entry':entry,
                'stop':p['stop'],'target':p.get('target'),'age_minutes':max(0,(now-p['open_ms'])/60000),
                'net_close_estimate':net,'reason':str(p.get('reason',''))[:500],
                'invalidation':str(p.get('invalidation',''))[:300], 'stale_price':not valid})
        pending=[{'symbol':sym,'side':'LONG' if p['side']==1 else 'SHORT',
                  'trigger':p['trigger'],'price':p['trigger_price'],'expires_ms':p['expires_ms'],
                  'margin_reserved':p['margin']} for sym,p in s.get('plans',{}).items()]
        trades=[json.loads(row[0]) for row in db.execute(
            "SELECT body FROM events WHERE kind='trade_closed' ORDER BY seq DESC LIMIT 10")]
        rejected=[json.loads(row[0]) for row in db.execute(
            "SELECT body FROM events WHERE kind='plan_rejected' ORDER BY seq DESC LIMIT 10")]
        latest=[dict(kind=k,ts=ts,body=json.loads(body)) for k,ts,body in db.execute(
            "SELECT kind,ts,body FROM events ORDER BY seq DESC LIMIT 20")]
        capacity=s.get('runtime_capacity') or {}
        return {'status':'ok','available':True,'name':name,'account_id':s['account_id'],
          'paper':True,'online':0<=now-s.get('heartbeat_ms',0)<60000,
          'heartbeat_ms':s.get('heartbeat_ms'),'cash':cash,'margin':margin,
          'equity':cash+margin+gross if complete else None,
          'net_pnl_vs_initial':cash+margin+gross-1000 if complete else None,
          'initial_cash':1000.,'margin_limit':capacity.get('max_margin'),
          'max_slots':capacity.get('max_slots',CAPACITY[name]),
          'positions':positions,'pending':pending,'trades':trades,'rejections':rejected,
          'latest_events':latest,'paused':bool(s.get('paused')),
          'daily':s.get('daily'),'coverage_gaps':s.get('coverage_gaps',[]),
          'ai_spend':{'status':'not_connected_to_provider_metering'}}
    except (OSError,TypeError,ValueError,KeyError,sqlite3.Error,IndexError):
        return {'status':'unavailable','available':False,'name':name}
    finally:
        if db is not None:db.close()


def read_all(base,now=None):
    return {'paper':True,'read_only':True,
            'profiles':{n:read_wallet(base,n,now) for n in ('hawk','bull')}}
