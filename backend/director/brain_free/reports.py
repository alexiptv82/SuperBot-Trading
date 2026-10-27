"""Descriptive experiment report; reporting never changes trading behaviour."""
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
import json,math
from .execution import equity,margin
from .spend import view

def build(store,state,now):
    trades=[json.loads(r[0]) for r in store.db.execute("SELECT body FROM events WHERE kind='trade_closed'")]
    executed=[json.loads(r[0]) for r in store.db.execute("SELECT body FROM events WHERE kind IN ('open','dca','partial_trade','trade_closed')")]
    realized=sum(t.get('segment',t).get('net',0) for t in executed if t['kind'] in ('partial_trade','trade_closed'))
    paid_fees=sum(t.get('fee_paid',0) for t in executed)
    prices=state.get('last_prices',{});eq,complete=equity(state,prices)
    wins=[t['net'] for t in trades if t['net']>0];losses=[t['net'] for t in trades if t['net']<0]
    metrics=state['metrics'];duration=sum(t['duration_minutes'] for t in trades)
    today=datetime.fromtimestamp(now/1000,timezone.utc).strftime('%Y-%m-%d')
    today_trades=[t for t in executed if t['kind'] in ('partial_trade','trade_closed') and datetime.fromtimestamp(t['close_ms']/1000,timezone.utc).strftime('%Y-%m-%d')==today]
    open_rows=list(store.db.execute("SELECT ts,body FROM events WHERE kind='open' AND ts>=?",(int(datetime.fromtimestamp(now/1000,timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0).timestamp()*1000),)))
    opens=[json.loads(row[1]) for row in open_rows]
    by_hour={}
    for ts,_ in open_rows:
        hour=datetime.fromtimestamp(ts/1000,timezone.utc).strftime('%Y-%m-%d %H:00 UTC');by_hour[hour]=by_hour.get(hour,0)+1
    rejections={}
    for row in store.db.execute("SELECT body FROM events WHERE kind='execution_rejected'"):
        code=json.loads(row[0]).get('code','unknown');rejections[code]=rejections.get(code,0)+1
    return {'today_utc':today,'opens_today':len(opens),'opens_per_hour_utc':by_hour,'unobserved_minutes':metrics.get('unobserved_ms',0)/60000,'net_closed_today':sum(t.get('segment',t)['net'] for t in today_trades),'rejection_reasons':rejections,'mode':'paper','cash':state['cash'],'equity':eq if complete else None,
      'margin':margin(state),'floating':eq-state['cash']-margin(state) if complete else None,
      'realized_net':realized,'closed':len(trades),
      'fees':paid_fees,'win_rate':len(wins)/len(trades) if trades else None,
      'profit_factor':sum(wins)/-sum(losses) if losses else None,
      'mean_duration_minutes':duration/len(trades) if trades else None,
      'open_long':sum(p['side']==1 for p in state['positions'].values()),'open_short':sum(p['side']==-1 for p in state['positions'].values()),'long':sum(t['side']==1 for t in trades),'short':sum(t['side']==-1 for t in trades),
      'empty_minutes':metrics['empty_ms']/60000,'slot_occupancy':metrics['slot_ms']/max(1,metrics['observed_ms']*10),
      'spend':view(store.db,now),'experiment_start_ms':state['verified_start_ms'],
      'elapsed_hours':(now-state['verified_start_ms'])/3600000 if state['verified_start_ms'] else None,
      'prices_complete':complete,'comparators':state.get('classic_comparison',{'status':'unavailable','note':'No read access configured; not zero performance.'})}

def text(report):
    spend=report['spend'];eq=report['equity']
    return (f"[BRAIN] Report serale PAPER\nEquity: {'non disponibile' if eq is None else f'${eq:.2f}'} · cash ${report['cash']:.2f} · margine ${report['margin']:.2f}"
      f"\nChiusi {report['closed']} · netto ${report['realized_net']:.2f} · fee ${report['fees']:.2f}"
      f"\nLONG/SHORT chiusi {report['long']}/{report['short']} · inattivo {report['empty_minutes']:.1f} min"
      f"\nSpesa oggi UTC ${spend['today_usd']:.4f} · cumulata ${spend['total_usd']:.4f} · costi incerti {spend['uncertain_requests']}"
      f"\nAperture oggi {report['opens_today']} · netto chiuso oggi ${report['net_closed_today']:.2f}"
      f"\nWR {'n/d' if report['win_rate'] is None else format(report['win_rate']*100,'.1f')+'%'} · PF {'n/d' if report['profit_factor'] is None else format(report['profit_factor'],'.2f')} · durata media {'n/d' if report['mean_duration_minutes'] is None else format(report['mean_duration_minutes'],'.1f')+' min'}"
      f"\nSlot medi {report['slot_occupancy']*100:.1f}% · non osservato {report['unobserved_minutes']:.1f} min"
      "\nContatore a tariffa, non fattura provider. Confronto classici descrittivo nel report completo.")

def schedule(store,state,now,cfg):
    d=datetime.fromtimestamp(now/1000,ZoneInfo('Europe/Rome'));date=d.strftime('%Y-%m-%d')
    events=[];messages=[]
    if state['verified_start_ms'] is None:return events,messages
    if d.hour>=cfg.report_hour and state.get('last_report_day')!=date:
        report=build(store,state,now);ident='report:'+date
        events.append((ident,'daily_report',now,report));messages.append((ident,text(report)))
        state['last_report_day']=date
    start=state['verified_start_ms']
    if start and now-start>=cfg.experiment_ms and not state.get('final_report_done'):
        report=build(store,state,now);events.append(('experiment-final','final_report',now,report))
        messages.append(('experiment-final','[BRAIN] Completate 168 ore. '+text(report).replace('[BRAIN] ','')))
        state['final_report_done']=True # No automatic stop or strategy change.
    return events,messages


def classical_comparison(root,now):
    """Optional local PAPER mounts, read-only. Never called by execution."""
    from pathlib import Path
    result={};today=datetime.fromtimestamp(now/1000,timezone.utc).strftime('%Y-%m-%d')
    for profile in ('hawk','bull'):
        try:
            directory=Path(root)/profile
            if directory.is_symlink():raise ValueError('symlink')
            h=json.loads((directory/'heartbeat.json').read_text())
            if h.get('exec_mode')!='paper':raise ValueError('paper_required')
            day_rows=[]
            with (directory/'trade_history.jsonl').open() as stream:
                for line in stream:
                    row=json.loads(line);ts=row.get('close_ms')
                    if ts and datetime.fromtimestamp(ts/1000,timezone.utc).strftime('%Y-%m-%d')==today:day_rows.append(row)
            if not all(isinstance(r.get(k,0),(float,int)) and not isinstance(r.get(k,0),bool) and math.isfinite(r.get(k,0)) for r in day_rows for k in ('net','fees')):raise ValueError('invalid_classic_metrics')
            result[profile]={'status':'available','net_closed_today':sum(r.get('net',0) for r in day_rows),
                'closed_segments':len(day_rows),'fees_today':sum(r.get('fees',0) for r in day_rows),
                'capital_basis':1000,'independent_account':True,'source':'readonly_classic_paper_history'}
        except Exception:result[profile]={'status':'unavailable','note':'No verified PAPER history; not zero performance.'}
    return result
