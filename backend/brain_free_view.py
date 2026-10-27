"""Bounded, authenticated read-only projection of the independent PAPER account."""
import json,math,os,sqlite3,time
from datetime import datetime,timezone
from pathlib import Path


def read(root,now=None):
    now=int(time.time()*1000) if now is None else now
    root=Path(root);path=root/'brain.sqlite3'
    if (root/'retired.flag').exists():return {'available':False,'status':'retired'}
    if root.is_symlink() or path.is_symlink() or not path.is_file():return {'available':False,'status':'not_started'}
    db=None
    try:
        db=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=.1)
        db.execute('PRAGMA query_only=ON');deadline=time.monotonic()+.2
        db.set_progress_handler(lambda:int(time.monotonic()>deadline),1000);db.execute('BEGIN')
        raw=db.execute('SELECT body FROM state WHERE id=1').fetchone()[0]
        if len(raw)>2_000_000:raise ValueError('oversize_state')
        s=json.loads(raw)
        if s.get('mode')!='paper' or s.get('account_id')!='brain-free-paper':raise ValueError('foreign_account')
        if s.get('verified_start_ms') is None:return {'available':False,'status':'not_started'}
        positions=[];
        if isinstance(s['cash'],bool):raise ValueError('invalid_cash')
        cash=float(s['cash']);total_margin=0;floating=0;prices_fresh=True
        for sym,p in s['positions'].items():
            for key in ('qty','entry','margin','leverage','stop','liquidation'):
                value=p[key]
                if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<=0:raise ValueError('invalid_position')
            if p['side'] not in (-1,1) or not isinstance(p['reason'],str):raise ValueError('invalid_position')
            q=s.get('last_prices',{}).get(sym,{})
            valid=0<=now-q.get('ts_ms',0)<=30000
            gross=p['side']*(q['price']-p['entry'])*p['qty'] if valid else None
            if not valid:prices_fresh=False
            else:floating+=gross
            total_margin+=p['margin']
            positions.append({'symbol':sym,'side':'LONG' if p['side']==1 else 'SHORT',
                'margin':p['margin'],'leverage':p['leverage'],'qty':p['qty'],'notional':p['entry']*p['qty'],
                'entry':p['entry'],'stop':p['stop'],'target':p['target'],'liquidation_estimate':p['liquidation'],
                'floating_gross':gross,'net_close_estimate':gross-p.get('entry_fees',0)-p.get('funding',0)-q['price']*p['qty']*(.0006+.0002) if valid else None,'reason':p['reason'],'invalidation':p['invalidation'],
                'age_minutes':max(0,(now-p['open_ms'])/60000),'source':p['source']})
        today=datetime.fromtimestamp(now/1000,timezone.utc).strftime('%Y-%m-%d')
        daily=total=0.;unknown=0
        for ts,body in db.execute('SELECT ts,body FROM requests'):
            b=json.loads(body);cost=(b.get('billing')or{}).get('cost')
            if cost is None:unknown+=1;continue
            if not math.isfinite(cost) or cost<0:raise ValueError('invalid_cost')
            total+=cost
            if datetime.fromtimestamp(ts/1000,timezone.utc).strftime('%Y-%m-%d')==today:daily+=cost
        trades=[json.loads(x[0]) for x in db.execute("SELECT body FROM events WHERE kind='trade_closed' ORDER BY seq DESC LIMIT 10")]
        rejections=[json.loads(x[0]) for x in db.execute("SELECT body FROM events WHERE kind='execution_rejected' ORDER BY seq DESC LIMIT 10")]
        latest=db.execute("SELECT body FROM events WHERE kind='daily_report' ORDER BY seq DESC LIMIT 1").fetchone()
        eq=cash+total_margin+floating if prices_fresh else None
        if not math.isfinite(cash) or cash<0 or not math.isfinite(total_margin):raise ValueError('invalid_account')
        return {'available':True,'status':'ok','paper':True,'account_id':s['account_id'],
            'online':0<=now-s.get('heartbeat_ms',0)<60000,'heartbeat_ms':s.get('heartbeat_ms'),
            'equity':eq,'cash':cash,'margin':total_margin,'margin_limit':1600,'max_slots':10,
            'pnl':eq-2000 if eq is not None else None,'positions':positions,'trades':trades,
            'execution_rejections':rejections,'decision':s.get('last_decision'),'provider_status':s.get('provider_status'),
            'spend':{'today_usd':daily,'total_usd':total,'uncertain_requests':unknown,'today_utc':today,'budget_gate':False},
            'market_context':s.get('context',{}),'paused':s.get('paused',False),'coverage_gaps':s.get('coverage_gaps',[]),
            'experiment_start_ms':s['verified_start_ms'],'elapsed_hours':(now-s['verified_start_ms'])/3600000,
            'config_hash':s['config_hash'],'build_sha':s.get('build_sha'),'latest_report':json.loads(latest[0]) if latest else None}
    except (OSError,ValueError,TypeError,KeyError,sqlite3.Error,IndexError):return {'available':False,'status':'unavailable','message':'Brain AI libero non leggibile; nessun saldo ricostruito.'}
    finally:
        if db is not None:db.close()
