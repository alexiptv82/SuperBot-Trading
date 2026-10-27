"""Read-only view of isolated Brain Hawk/Bull plus the previous Brain account.

Never import a trading runtime, initialize a directory or query an exchange.
Only fixed profile paths and allowlisted scalar fields leave this module.
"""
from contextlib import closing
import json
import os
import re
from pathlib import Path
import sqlite3
import time
from .brain_view import Unavailable, _number, _positive_optional, _text, _json, _check, _trade, read_status

VERSION='classical-adaptive-v1'
FRESH_MS=180000


def _unavailable(profile,reason,status='unavailable'):
    return {'status':status,'reason':reason,'mode':'paper','read_only':True,'runtime':VERSION,'profile':profile}


def read_profile(parent,profile,now,deadline):
    if profile not in ('hawk','bull'):
        return _unavailable(profile,'unknown_profile')
    root=Path(parent)/('brain-'+profile)
    path=root/'brain.sqlite3'
    try:
        _check(deadline)
        if any(p.is_symlink() for p in (root,*root.parents)) or path.is_symlink():
            raise Unavailable('invalid_profile_path')
        if not path.is_file():return _unavailable(profile,'missing_database','not_started')
        with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=max(0,deadline-time.monotonic()),check_same_thread=False)) as db:
            db.set_progress_handler(lambda:int(time.monotonic()>=deadline),100)
            db.execute('PRAGMA query_only=ON');db.execute('BEGIN')
            row=db.execute('SELECT body FROM state WHERE id=1').fetchone()
            if row is None:raise Unavailable('missing_state')
            state=_json(row[0]);desk=state['desk'];a=desk['main']
            if state.get('version')!=VERSION or state.get('profile')!=profile or a.get('name')!='brain-'+profile:
                raise Unavailable('unsupported_profile_state')
            if not isinstance(state.get('method'),str) or not re.fullmatch(r'[a-f0-9]{64}',state['method']):
                raise Unavailable('invalid_method_identity')
            groups={};realized=0.;trades=[]
            for body, in db.execute("SELECT body FROM events WHERE kind='trade' ORDER BY seq"):
                _check(deadline);r=_json(body)
                if r.get('account')!='brain-'+profile or r.get('profile')!=profile or r.get('mode')!='paper':
                    raise Unavailable('foreign_trade')
                t=_trade(r);key=(r['id'],r['open_ms'],r['symbol'],r['side'])
                if type(r['id']) is not int or r['id']<1 or not isinstance(r.get('partial',False),bool) or _number(r['open_ms'])>t['closed_ms']:
                    raise Unavailable('invalid_trade')
                g=groups.setdefault(key,{'net':0.,'closed':False});g['net']+=r['net'];g['closed']|=not r.get('partial',False)
                realized+=r['net']
                t.update(margin=_positive_optional(r.get('margin')),leverage=_positive_optional(r.get('leverage')),
                         decision_source=_text(r.get('exit_decision_source')))
                trades.append(t)
                if len(trades)>20:trades.pop(0)
            advice=None;cycle=None;last_input=None
            for body, in db.execute("SELECT body FROM events WHERE kind='journal' ORDER BY seq DESC LIMIT 128"):
                _check(deadline);r=_json(body)
                if cycle is None and r.get('kind')=='adaptive_cycle':cycle=r
                if last_input is None and r.get('kind')=='adaptive_input':last_input=r.get('ts_ms')
                if advice is None and r.get('kind')=='adaptive_advice':
                    decisions=r.get('decisions',[])
                    if not isinstance(decisions,list):raise Unavailable('invalid_advice')
                    advice={'ts_ms':r.get('ts_ms'),'meaning':'proposal_not_execution','decisions':[
                        {k:_text(d.get(k)) for k in ('symbol','action','reason')} for d in decisions[:30] if isinstance(d,dict)]}
        positions=[];floating=0.;margin=0.;times=[];priced=True
        prices=desk.get('last_prices',{});price_times=desk.get('last_price_times',{})
        limits=a['limits']
        for symbol,p in sorted(a['positions'].items()):
            _check(deadline)
            entry,qty,side,mar,opened=(_number(p[k]) for k in ('entry','qty','side','total_margin','open_ms'))
            if entry<=0 or qty<=0 or mar<0 or side not in (-1,1) or opened>now+5000:
                raise Unavailable('invalid_position')
            price=prices.get(symbol);stamp=price_times.get(symbol)
            if stamp is not None:stamp=_number(stamp);times.append(stamp)
            stale=stamp is None or not -5000<=now-stamp<=FRESH_MS
            pnl=None;net=None
            if price is None:priced=False
            else:
                price=_number(price)
                if price<=0:raise Unavailable('invalid_price')
                pnl=side*(price-entry)*qty;floating+=pnl
                fill=price*(1-side*_number(limits['slip_bp_side'])/10000)
                funding=qty*entry*_number(limits['funding_bp_8h_long'])/10000*max(0,now-opened)/28800000 if side==1 else 0.
                net=side*(fill-entry)*qty-_number(p['fee_open'])-qty*fill*_number(limits['fee_bp_side'])/10000-funding
            margin+=mar
            positions.append({'symbol':symbol,'side':'LONG' if side==1 else 'SHORT','entry':entry,'price':price,
                              'margin':mar,'leverage':_positive_optional(p.get('leverage')),'notional_entry':entry*qty,
                              'floating_pnl':pnl,'floating_margin_roi_pct':pnl/mar*100 if pnl is not None and mar else None,
                              'net_close_estimate':net,'net_margin_roi_pct':net/mar*100 if net is not None and mar else None,
                              'valued_ms':stamp,'stale':stale,'age_minutes':max(0,now-opened)/60000,
                              'stop':_positive_optional(p.get('sl')),'target':_positive_optional(p.get('tp')),
                              'decision_source':_text(p.get('source')),'entry_reason':_text(p.get('reason'))})
        cash=_number(a['cash']);start=_number(limits['start_equity'])
        if start<=0:raise Unavailable('invalid_start_equity')
        equity=cash+margin+floating if priced else None
        last_step=_number(state['last_step_ms'])
        valued=min(times) if times else last_step if not positions else None
        stale=valued is None or not -5000<=now-valued<=FRESH_MS
        if any(p['stale'] for p in positions):stale=True
        day=a.get('day');today=time.strftime('%Y-%m-%d',time.gmtime(now/1000));current=day==today
        limit=_number(limits['daily_stop'])*100;daily_start=_number(a['day_start_equity'])
        if not 0<limit<=100 or daily_start<=0:raise Unavailable('invalid_daily_policy')
        dd=max(0.,(1-equity/daily_start)*100) if current and equity is not None else None
        beat=None;budget={};provider=_text((cycle or {}).get('last_provider_status'))
        try:
            status_path=root/'status.json'
            if status_path.is_symlink():raise ValueError()
            with status_path.open() as f:status=_json(f.read(2*1024*1024+1))
            if (status.get('mode'),status.get('profile'),status.get('version'),status.get('method_version'))==('paper',profile,VERSION,state.get('method')):
                beat=_number(status['ts_ms'])
                for k in ('daily_reserved','monthly_reserved','profile_reserved','shared_daily_cap','shared_monthly_cap'):
                    v=status.get('api_budget',{}).get(k)
                    if v is not None:budget[k]=_number(v)
        except (OSError,ValueError,TypeError,KeyError):pass
        closed=[g['net'] for g in groups.values() if g['closed']]
        result={'status':'ok','mode':'paper','read_only':True,'runtime':VERSION,'profile':profile,
                'portfolio':{'equity':equity,'cash':cash,'starting_equity':start,'margin_in_use':margin,
                             'pnl':equity-start if equity is not None else None,'pnl_pct':(equity/start-1)*100 if equity is not None else None,
                             'cycles':state.get('steps_completed'),'valued_ms':valued,'stale':stale},
                'positions':positions,'trades':list(reversed(trades)),'trades_coverage':'sqlite_last_20_realizations',
                'stats':{'closed_trades':len(closed),'win_rate_pct':100*sum(n>0 for n in closed)/len(closed) if closed else None,
                         'average_pnl':sum(closed)/len(closed) if closed else None,'realized_pnl':realized,'partial_records_included':True},
                'daily_stop':{'limit_pct':limit,'day':day,'state':'current' if current else 'awaiting_utc_rollover',
                              'stopped':dd>=limit if dd is not None else None,'drawdown_pct':dd,'used_limit_pct':dd/limit*100 if dd is not None else None},
                'reasoning':{'last_call_ms':last_input,'advice':advice,'note':'Ultima proposta AI: non certifica esecuzione. Le posizioni mostrano gli ingressi effettivi.'},
                'execution':{'last_cycle_ms':_number(cycle['ts_ms']) if cycle else None,
                             'decision_source':_text((cycle or {}).get('decision_source')),'provider_status':provider,
                             'fresh_fast_data':(cycle or {}).get('fresh_fast_data') is True,
                             'coverage_unresolved':state.get('coverage_unresolved') is True,
                             'note':'Supervisione prevista a un minuto; segnali classici su 15m. Dati osservati, non prezzi tick garantiti.'},
                'api_budget':budget,'system':{'container':None,'health':'unknown','sha':None,'uptime_seconds':None,
                  'method_version':_text(state.get('method')),'heartbeat_ms':beat,
                  'heartbeat':('fresh' if -5000<=now-beat<=FRESH_MS else 'stale') if beat is not None else 'unknown',
                  'note':'Heartbeat del profilo PAPER; salute Docker, SHA e uptime non attestati dal reader.'}}
        _check(deadline);json.dumps(result,allow_nan=False);return result
    except Unavailable as exc:return _unavailable(profile,str(exc))
    except sqlite3.OperationalError as exc:
        msg=str(exc).lower();reason='query_timeout' if 'interrupted' in msg else 'locked' if 'locked' in msg or 'busy' in msg else 'database_unavailable'
        return _unavailable(profile,reason)
    except (OSError,ValueError,KeyError,TypeError,AttributeError,OverflowError,sqlite3.DatabaseError):
        return _unavailable(profile,'invalid_or_unreadable_data')


def read_profiles(parent=None,legacy_dir=None,*,now_ms=None):
    now=int(time.time()*1000) if now_ms is None else now_ms
    parent=parent or os.getenv('BRAIN_ADAPTIVE_DATA_DIR','/opt/superbot-brain-adaptive')
    deadline=time.monotonic()+2
    profiles={p:read_profile(parent,p,now,deadline) for p in ('hawk','bull')}
    legacy=read_status(legacy_dir,now_ms=now)
    return {'status':'ok','mode':'paper','read_only':True,'profiles':profiles,'legacy':legacy,
            'note':'Conti PAPER distinti; capitale e risultati non vengono sommati.'}
