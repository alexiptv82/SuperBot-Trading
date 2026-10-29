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


def project_wallet(state,name,now):
    if state.get('mode')!='paper' or state.get('account_id')!=IDS[name]:
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
                metrics['equity']-1000 if metrics.get('equity') is not None else None),
            'cash':state['cash'],'margin':margin,
            'margin_limit':capacity.get('max_margin'),
            'max_slots':capacity.get('max_slots'),
            'initial_cash':1000.,'positions':positions,
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
        if (snapshot.get('schema_version')!=1 or
            snapshot.get('paper') is not True or
            snapshot.get('read_only') is not True or
            set(snapshot.get('profiles',{}))!=set(IDS)):
            raise ValueError('bad_schema')
        for name,p in snapshot['profiles'].items():
            if p.get('account_id')!=IDS[name] or p.get('paper') is not True:
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
    except (OSError,ValueError,TypeError,KeyError):
        return {'status':'unavailable','available':False,'profiles':{}}
