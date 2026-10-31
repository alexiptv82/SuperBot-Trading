"""I7: dual PAPER dashboard snapshot, with no worker or provider attached.

Caller must invoke publish_if_due after committed ticks. SQLite remains the
authoritative ledger and snapshot output is read-only.
"""
import json
import os
from pathlib import Path
import tempfile

INTERVAL_MS=5000
IDS={'hawk':'brain-scalp-hawk-paper','bull':'brain-scalp-bull-paper'}


def project_wallet(state,name,now,*,spec=None):
    expected=IDS[name] if spec is None else spec.account_id
    initial=1000. if spec is None else spec.start_cash
    if state.get('mode')!='paper' or state.get('account_id')!=expected:
        raise ValueError('foreign_wallet')
    metrics=state.get('metrics') or {}
    positions=[{'symbol':sym,'side':'LONG' if p['side']==1 else 'SHORT',
                'entry':p['entry'],'qty':p['qty'],'margin':p['margin'],
                'leverage':p['leverage'],'stop':p['stop'],
                'target':p.get('target'),'open_ms':p['open_ms']}
               for sym,p in sorted(state['positions'].items())]
    for item in positions:
        item['notional']=item['entry']*item['qty']
        item['age_minutes']=max(0.,(now-item['open_ms'])/60000)
        item['net_close_estimate']=None  # snapshots never invent a fresh mark
    pending=[{'symbol':sym,'side':'LONG' if p['side']==1 else 'SHORT',
              'trigger':p['trigger'],'price':p['trigger_price'],
              'expires_ms':p['expires_ms'],'margin_reserved':p['margin']}
             for sym,p in sorted((state.get('plans') or {}).items())]
    margin=sum(p['margin'] for p in state['positions'].values())
    capacity=state.get('runtime_capacity') or {}
    return {'status':'ok','available':True,'paper':True,'name':name,
            'account_id':state['account_id'],'heartbeat_ms':state.get('heartbeat_ms'),
            'metrics':metrics,'equity':metrics.get('equity'),
            'net_pnl_vs_initial':(
                metrics['equity']-initial if metrics.get('equity') is not None else None),
            'cash':state['cash'],'margin':margin,
            'margin_limit':capacity.get('max_margin'),
            'max_slots':capacity.get('max_slots'),
            'initial_cash':initial,'positions':positions,
            'pending':pending,'paused':bool(state.get('paused')),
            'coverage_gaps':state.get('coverage_gaps',[]),
            'ai_spend':{'status':'not_connected_to_provider_metering'},
            'trades_summary_only':True}


def build_snapshot(hawk,bull,now):
    if type(now)!=int or now<=0: raise ValueError('invalid_time')
    return {'schema_version':1,'paper':True,'read_only':True,'ts_ms':now,
            'profiles':{'hawk':project_wallet(hawk,'hawk',now),
                        'bull':project_wallet(bull,'bull',now)}}


def atomic_write(path,snapshot):
    path=Path(path).absolute()
    if not path.parent.is_dir() or path.is_symlink() or path.parent.is_symlink():
        raise ValueError('invalid_snapshot_path')
    payload=json.dumps(snapshot,allow_nan=False,sort_keys=True).encode('utf-8')
    if len(payload)>2000000: raise ValueError('snapshot_too_large')
    temp=None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent,prefix='.scalp_',
                                         delete=False) as f:
            temp=f.name
            os.fchmod(f.fileno(),0o600)
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp,path)
        temp=None
    finally:
        if temp is not None:
            os.unlink(temp)
    return path


class SnapshotPublisher:
    def __init__(self,path,interval_ms=INTERVAL_MS):
        if type(interval_ms)!=int or interval_ms<1000:
            raise ValueError('invalid_interval')
        self.path=Path(path)
        self.interval_ms=interval_ms
        self.last=None

    def publish_if_due(self,pair,now):
        if self.last is not None and 0<=now-self.last<self.interval_ms:
            return False
        snapshot=build_snapshot(pair.hawk.store.load(),
                                pair.bull.store.load(),now)
        atomic_write(self.path,snapshot)
        self.last=now
        return True


def read_snapshot(path,now,stale_after_ms=60000):
    path=Path(path)
    if path.is_symlink() or not path.is_file():
        return {'status':'not_started','available':False,'profiles':{}}
    try:
        if path.stat().st_size>2000000: raise ValueError('too_large')
        snapshot=json.loads(path.read_text(encoding='utf-8'))
        if (not isinstance(snapshot,dict) or
            snapshot.get('schema_version')!=1 or
            snapshot.get('paper') is not True or
            snapshot.get('read_only') is not True or
            not isinstance(snapshot.get('profiles'),dict) or
            set(snapshot.get('profiles',{}))!=set(IDS)):
            raise ValueError('bad_schema')
        for name,p in snapshot['profiles'].items():
            if (not isinstance(p,dict) or
                p.get('account_id')!=IDS[name] or p.get('paper') is not True):
                raise ValueError('foreign_wallet')
        age=now-snapshot['ts_ms']
        if type(age) not in (int,float) or age<0:
            raise ValueError('bad_age')
        stale=age>stale_after_ms
        snapshot.update(status='stale' if stale else 'ok',
                        available=True,stale=stale,age_ms=age)
        for profile in snapshot['profiles'].values():
            heartbeat=profile.get('heartbeat_ms')
            profile['online']=bool(not stale and isinstance(heartbeat,int)
                                   and 0<=now-heartbeat<60000)
            profile['snapshot_stale']=stale
        return snapshot
    except (OSError,ValueError,TypeError,KeyError,RecursionError):
        return {'status':'unavailable','available':False,'profiles':{}}



def build_account_snapshot(account,now,markets=None,*,position_actions=None):
    """v2 single account: readable PAPER positions and bounded actual close history.

    Mark estimates require a timely quote; no stale, absent or fabricated P&L.
    The authoritative SQLite event history is read only, not modified.
    """
    from dataclasses import replace
    import math
    from director.brain_free.execution import fresh
    from .config import PROTECT_PRICE_AGE_MS
    if type(now)!=int or now<=0:raise ValueError('invalid_time')
    engine=account.wallets.get('brain')
    if engine is None:raise ValueError('single_account_required')
    state=engine.store.load()
    if state.get('account_id')!='brain-scalp-single-paper' or state.get('mode')!='paper':
        raise ValueError('foreign_wallet')
    value=project_wallet(state,'brain',now,spec=engine.spec)
    markets=markets if isinstance(markets,dict) else {}
    cfg=replace(engine.spec.brain_config(),price_age_ms=PROTECT_PRICE_AGE_MS)
    for row in value['positions']:
        quote=(markets.get(row['symbol']) or {}).get('quote')
        if not fresh(quote,now,cfg):
            row.update(mark_price=None,mark_ts_ms=None,price_status='unavailable',
                       net_close_estimate=None,pnl_pct_margin=None)
            continue
        position=state['positions'][row['symbol']]
        px=quote['price']
        fill=px*(1-position['side']*cfg.slippage)
        fee=position['qty']*fill*cfg.fee_rate
        gross=position['side']*(fill-position['entry'])*position['qty']
        estimate=gross-position['entry_fees']-fee-position['funding']
        if not math.isfinite(estimate):
            row.update(mark_price=None,mark_ts_ms=None,price_status='unavailable',
                       net_close_estimate=None,pnl_pct_margin=None)
            continue
        row.update(mark_price=px,mark_ts_ms=quote['ts_ms'],
                   price_status='fresh',net_close_estimate=round(estimate,4),
                   pnl_pct_margin=(round(estimate/row['margin']*100,2)
                                   if row['margin']>0 else None))
    rows=engine.store.db.execute(
        "SELECT body FROM events WHERE kind='trade_closed' ORDER BY seq DESC LIMIT 50").fetchall()
    latest=[]
    for (body,) in rows:
        try:
            e=json.loads(body)
            if e.get('kind')!='trade_closed':continue
            trade={'symbol':e['symbol'],'side':'LONG' if e['side']==1 else 'SHORT',
                   'position_id':e['position_id'],'entry':e['entry'],
                   'exit':(e.get('segment') or {}).get('exit'),
                   'leverage':e['leverage'],'net':e['net'],
                   'close_ms':e['close_ms'],'open_ms':e['open_ms'],
                   'duration_minutes':e.get('duration_minutes'),
                   'reason':str(e.get('reason') or '')[:160],
                   'source':str(e.get('source') or '')[:40]}
            if (not isinstance(trade['symbol'],str) or
                any(type(trade[k]) not in (float,int) or not math.isfinite(trade[k])
                    for k in ('entry','net','leverage','close_ms','open_ms'))):
                continue
            if trade['exit'] is not None and (
                type(trade['exit']) not in (int,float) or not math.isfinite(trade['exit'])):
                trade['exit']=None
            latest.append(trade)
        except (ValueError,TypeError,KeyError,OverflowError):continue
    value['trades']=latest
    value['trades_summary_only']=False
    value['trades_shown']=len(latest)
    value['closed_total']=engine.store.db.execute(
        "SELECT COUNT(*) FROM events WHERE kind='trade_closed'").fetchone()[0]
    value['recent_closed_wins']=sum(t['net']>0 for t in latest)
    value['recent_closed_losses']=sum(t['net']<0 for t in latest)
    value['recent_closed_net_usd']=round(sum(t['net'] for t in latest),4)
    review={'mode':position_actions if position_actions in ('off','paper') else 'unknown',
            'status':'none','last':None}
    row=engine.store.db.execute("SELECT ts,body FROM events WHERE kind='ai_position_review_observed' ORDER BY seq DESC LIMIT 1").fetchone()
    if row:
        try:
            event=json.loads(row[1])
            if type(row[0])!=int or not 0<row[0]<=now:
                raise ValueError('invalid_review_time')
            proposals=[{'symbol':str(r['symbol'])[:20],
                        'action':r['action'],'reason':str(r.get('reason',''))[:220]}
                       for r in event['reviews'][:10]
                       if r.get('action') in ('HOLD','SUGGEST_CLOSE','SUGGEST_REDUCE','SUGGEST_TIGHTEN')]
            executed=[{'symbol':str(r['symbol'])[:20],'action':r['action']}
                      for r in event.get('executed',[])[:10]
                      if r.get('action') in ('closed','reduced','stop_tightened')]
            review.update(status='recorded',last={'ts_ms':row[0],
                'reviewer_checked':event.get('reviewed') is True,
                'proposals':proposals,'executed':executed})
        except (ValueError,TypeError,KeyError,AttributeError):
            review.update(status='unavailable')
    value['position_review']=review
    attempt=state.get('last_ai_attempt')
    if isinstance(attempt,dict):
        value['ai_attempt']={k:attempt.get(k) for k in
            ('ts_ms','purpose','status','provider','failure_code')}
    return {'schema_version':2,'paper':True,'read_only':True,'ts_ms':now,
            'account':value}
