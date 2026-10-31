"""Read only the published Brain Scalp PAPER snapshot, never SQLite.

Missing snapshot returns None (legacy read-only DB fallback). Corrupt or
foreign snapshot fails closed. A stale snapshot stays visible but NEVER online.
"""
import json
import math
from pathlib import Path

IDS={'hawk':'brain-scalp-hawk-paper','bull':'brain-scalp-bull-paper'}
SINGLE_IDS={'brain':'brain-scalp-single-paper'}


def _valid_number(value):
    return (isinstance(value,(int,float)) and not isinstance(value,bool)
            and math.isfinite(value))


def read_published_snapshot(path,now,layout="auto"):
    if layout not in ("auto","single","dual"):raise ValueError("invalid_layout")
    path=Path(path)
    if not path.exists() and not path.is_symlink():
        return None
    ids=SINGLE_IDS if layout=='single' else IDS
    unavailable={'layout':layout,'paper':True,'read_only':True,'source':'snapshot',
                 'status':'unavailable','snapshot_stale':True,
                 'profiles':{n:{'status':'unavailable','available':False,'name':n}
                             for n in ids}}
    try:
        if path.is_symlink() or path.parent.is_symlink() or path.stat().st_size>2000000:
            raise ValueError('unsafe_snapshot')
        obj=json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(obj,dict):raise ValueError('schema')
        version=obj.get('schema_version')
        if type(version)!=int or version not in (1,2):raise ValueError('schema')
        single=version==2
        ids=SINGLE_IDS if single else IDS
        if ((layout=='single' and not single) or (layout=='dual' and single)):
            raise ValueError('layout_mismatch')
        unavailable.update(layout='single' if single else 'dual',
            profiles={n:{'status':'unavailable','available':False,'name':n} for n in ids})
        if ((layout=='single' and not single) or (layout=='dual' and single)):
            raise ValueError('layout_mismatch')
        if single:
            if 'profiles' in obj or not isinstance(obj.get('account'),dict):
                raise ValueError('schema')
            sources={'brain':obj['account']}
        else:
            if 'account' in obj or not isinstance(obj.get('profiles'),dict) or set(obj['profiles'])!=set(ids):
                raise ValueError('schema')
            sources=obj['profiles']
        if (obj.get('paper') is not True or obj.get('read_only') is not True or
                not _valid_number(obj.get('ts_ms'))):raise ValueError('schema')
        age=now-obj['ts_ms']
        if age<0:
            raise ValueError('snapshot_from_future')
        stale=age>60000
        profiles={}
        for name in ids:
            src=sources[name]
            if (not isinstance(src,dict) or
                    src.get('account_id')!=ids[name] or src.get('paper') is not True
                    or src.get('status')!='ok' or
                    not _valid_number(src.get('cash')) or src['cash']<0):
                raise ValueError('foreign_or_invalid_wallet')
            if src.get('metrics') is not None and not isinstance(src['metrics'],dict):
                raise ValueError('invalid_metrics')
            for key in ('positions','pending','trades','rejections','latest_events'):
                rows=src.get(key,[])
                if not isinstance(rows,list) or any(not isinstance(row,dict) for row in rows):
                    raise ValueError('invalid_wallet_rows')
            if single:
                for key in ('initial_cash','margin_limit','margin'):
                    if not _valid_number(src.get(key)) or src[key]<0:
                        raise ValueError('invalid_account_amount')
                if src['initial_cash']<=0 or type(src.get('max_slots'))!=int or src['max_slots']<=0:
                    raise ValueError('invalid_account_capacity')
                for row in src.get('positions',[]):
                    if not isinstance(row.get('symbol'),str) or row.get('side') not in ('LONG','SHORT'):
                        raise ValueError('invalid_position')
                    for key in ('margin','leverage','notional','entry','stop','age_minutes'):
                        if not _valid_number(row.get(key)):raise ValueError('invalid_position')
                    for key in ('target','net_close_estimate','mark_price','pnl_pct_margin','mark_ts_ms'):
                        if row.get(key) is not None and not _valid_number(row[key]):raise ValueError('invalid_position')
                    price_status=row.get('price_status')
                    if price_status is not None:
                        if price_status not in ('fresh','unavailable'):
                            raise ValueError('invalid_price_status')
                        if price_status=='fresh':
                            if (not _valid_number(row.get('mark_price')) or
                                row['mark_price']<=0 or
                                not _valid_number(row.get('mark_ts_ms')) or
                                not 0<=obj['ts_ms']-row['mark_ts_ms']<=10000 or
                                not _valid_number(row.get('net_close_estimate'))):
                                raise ValueError('unverified_mark')
                        elif any(row.get(k) is not None for k in
                                 ('mark_price','mark_ts_ms','net_close_estimate','pnl_pct_margin')):
                            raise ValueError('stale_mark_claimed_as_fresh')
                for trade in src.get('trades',[]):
                    if (not isinstance(trade.get('symbol'),str) or
                        trade.get('side') not in ('LONG','SHORT') or
                        not _valid_number(trade.get('net')) or
                        not _valid_number(trade.get('entry')) or
                        not _valid_number(trade.get('close_ms'))):
                        raise ValueError('invalid_trade_row')
                for key in ('closed_total','trades_shown','recent_closed_wins','recent_closed_losses'):
                    if key in src and (type(src[key])!=int or src[key]<0):
                        raise ValueError('invalid_trade_counter')
                if ('recent_closed_net_usd' in src and
                    not _valid_number(src['recent_closed_net_usd'])):
                    raise ValueError('invalid_trade_total')
            equity=src.get('equity')
            if equity is not None and not _valid_number(equity):
                raise ValueError('invalid_equity')
            heartbeat=src.get('heartbeat_ms')
            online=(not stale and _valid_number(heartbeat) and
                    0<=now-heartbeat<60000)
            item=dict(src)
            review=src.get('position_review')
            if review is not None:
                try:
                    if (not isinstance(review,dict) or review.get('mode') not in ('off','paper','unknown')
                        or review.get('status') not in ('none','recorded','unavailable')):
                        raise ValueError('review_schema')
                    last=review.get('last')
                    if review['status']=='recorded':
                        if (not isinstance(last,dict) or not _valid_number(last.get('ts_ms'))
                            or not 0<last['ts_ms']<=obj['ts_ms']
                            or type(last.get('reviewer_checked'))!=bool):
                            raise ValueError('review_time')
                        for key,allowed in (('proposals',('HOLD','SUGGEST_CLOSE','SUGGEST_TIGHTEN')),
                                            ('executed',('closed','stop_tightened'))):
                            rows=last.get(key)
                            if (not isinstance(rows,list) or len(rows)>10 or any(
                                not isinstance(r,dict) or not isinstance(r.get('symbol'),str)
                                or len(r['symbol'])>20 or r.get('action') not in allowed
                                or ('reason' in r and (not isinstance(r['reason'],str) or len(r['reason'])>220))
                                for r in rows)):
                                raise ValueError('review_rows')
                    elif last is not None:raise ValueError('review_last')
                except (ValueError,TypeError):
                    item['position_review']={'mode':'unknown','status':'unavailable','last':None}
            if single:
                item['net_pnl_vs_initial']=None if equity is None else equity-src['initial_cash']
            item.update(name=name,status='ok',available=True,online=bool(online),
                        snapshot_stale=stale,snapshot_age_ms=age)
            profiles[name]=item
        return {'schema_version':version,'layout':'single' if single else 'dual',
                'paper':True,'read_only':True,'source':'snapshot',
                'status':'stale' if stale else 'ok',
                'snapshot_stale':stale,'snapshot_age_ms':age,
                'snapshot_ts_ms':obj['ts_ms'],'profiles':profiles}
    except (ValueError,TypeError,KeyError,OSError,OverflowError,IndexError,RecursionError):
        return unavailable

