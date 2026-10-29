"""Read only the published Brain Scalp PAPER snapshot, never SQLite.

Missing snapshot returns None (legacy read-only DB fallback). Corrupt or
foreign snapshot fails closed. A stale snapshot stays visible but NEVER online.
"""
import json
import math
from pathlib import Path

IDS={'hawk':'brain-scalp-hawk-paper','bull':'brain-scalp-bull-paper'}


def _valid_number(value):
    return (isinstance(value,(int,float)) and not isinstance(value,bool)
            and math.isfinite(value))


def read_published_snapshot(path,now):
    path=Path(path)
    if not path.exists() and not path.is_symlink():
        return None
    unavailable={'paper':True,'read_only':True,'source':'snapshot',
                 'status':'unavailable','snapshot_stale':True,
                 'profiles':{n:{'status':'unavailable','available':False,'name':n}
                             for n in IDS}}
    try:
        if path.is_symlink() or path.parent.is_symlink() or path.stat().st_size>2000000:
            raise ValueError('unsafe_snapshot')
        obj=json.loads(path.read_text(encoding='utf-8'))
        if (obj.get('schema_version')!=1 or obj.get('paper') is not True
                or obj.get('read_only') is not True
                or set(obj.get('profiles',{}))!=set(IDS)
                or not _valid_number(obj.get('ts_ms'))):
            raise ValueError('schema')
        age=now-obj['ts_ms']
        if age<0:
            raise ValueError('snapshot_from_future')
        stale=age>60000
        profiles={}
        for name in IDS:
            src=obj['profiles'][name]
            if (src.get('account_id')!=IDS[name] or src.get('paper') is not True
                    or src.get('status')!='ok' or
                    not _valid_number(src.get('cash')) or src['cash']<0):
                raise ValueError('foreign_or_invalid_wallet')
            equity=src.get('equity')
            if equity is not None and not _valid_number(equity):
                raise ValueError('invalid_equity')
            heartbeat=src.get('heartbeat_ms')
            online=(not stale and _valid_number(heartbeat) and
                    0<=now-heartbeat<60000)
            item=dict(src)
            item.update(name=name,status='ok',available=True,online=bool(online),
                        snapshot_stale=stale,snapshot_age_ms=age)
            profiles[name]=item
        return {'paper':True,'read_only':True,'source':'snapshot',
                'status':'stale' if stale else 'ok',
                'snapshot_stale':stale,'snapshot_age_ms':age,
                'snapshot_ts_ms':obj['ts_ms'],'profiles':profiles}
    except (ValueError,TypeError,KeyError,OSError,OverflowError,IndexError):
        return unavailable
