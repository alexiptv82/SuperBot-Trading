#!/usr/bin/env python3
"""Pre-registered, read-only historical Bitget 1m regime replay.

No credentials, orders, portfolio state, signal tuning, or fallback synthetic
data. The output is an *indicator diagnostic*, NOT a trading backtest.
"""
import csv
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import random
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from director.trend_engine_v11 import safe_indicator

START=1792108800000  # 2026-10-16 00:00 UTC
END=1792713600000    # 2026-10-23 00:00 UTC (exclusive)
MINUTE=60000
SYMBOLS=('BTC','ETH','SOL','DOGE')
HORIZON=90
BARRIER=.0035
PAGE=200
EXPECTED=(END-START)//MINUTE
API='https://api.bitget.com/api/v2/mix/market/history-candles'


def fetch(path,opener=urllib.request.urlopen):
    query=urllib.parse.urlencode(path)
    url=API+'?'+query
    request=urllib.request.Request(url,headers={'User-Agent':'SuperBot-PAPER-Research/1.0',
                                                 'Accept':'application/json'})
    last=None
    for attempt in range(3):
        try:
            with opener(request,timeout=12) as response:
                payload=json.loads(response.read(1000000))
            if payload.get('code')!='00000' or not isinstance(payload.get('data'),list):
                raise ValueError('bitget_error_'+str(payload.get('code','missing')))
            return payload['data']
        except (urllib.error.URLError,TimeoutError,ValueError,json.JSONDecodeError) as exc:
            last=exc
            if attempt<2:time.sleep(.5*(attempt+1))
    raise ValueError('public_api_unavailable:'+type(last).__name__) from None


def check_row(row):
    if not isinstance(row,list) or len(row)<6:
        raise ValueError('invalid_ohlcv_shape')
    values=[float(x) for x in row[:6]]
    if not all(math.isfinite(x) for x in values):
        raise ValueError('nonfinite_ohlcv')
    t=int(values[0])
    if values[0]!=t or t%MINUTE or t<0:
        raise ValueError('bad_timestamp')
    _,op,hi,lo,cl,v=values
    if min(op,hi,lo,cl)<=0 or lo>min(op,cl) or hi<max(op,cl) or v<0:
        raise ValueError('bad_prices')
    return [t,op,hi,lo,cl,v]


def gather(symbol,loader=fetch,delay=.09):
    rows={}; calls=0
    for start in range(START,END,PAGE*MINUTE):
        end=min(END,start+PAGE*MINUTE)
        params={'symbol':symbol+'USDT','productType':'USDT-FUTURES',
                'granularity':'1m','startTime':start,'endTime':end-1,
                'limit':PAGE}
        received=loader(params)
        calls+=1
        for raw in received:
            r=check_row(raw)
            t=r[0]
            if not start<=t<end:continue
            prior=rows.get(t)
            if prior is not None and prior!=r:
                raise ValueError('conflicting_bitget_revision')
            rows[t]=r
        if delay:time.sleep(delay)
    wanted=list(range(START,END,MINUTE))
    missing=[t for t in wanted if t not in rows]
    if missing:
        # The V2 paginator can omit one boundary minute per 200-row page.
        # Query that minute explicitly; only accept a genuinely returned,
        # independently validated Bitget candle, never interpolation.
        print('REAL_REPLAY_PAGINATION_GAPS '+symbol+' '+str(len(missing))+
              ' first='+str(missing[:3]),flush=True)
        for t in missing:
            params={'symbol':symbol+'USDT','productType':'USDT-FUTURES',
                    'granularity':'1m','startTime':t-3*MINUTE,
                    'endTime':t+4*MINUTE,'limit':10}
            received=loader(params);calls+=1
            for raw in received:
                item=check_row(raw)
                if item[0]!=t:continue
                existing=rows.get(t)
                if existing is not None and existing!=item:
                    raise ValueError('conflicting_bitget_repair')
                rows[t]=item
            if delay:time.sleep(delay)
        remaining=[t for t in missing if t not in rows]
        if remaining:
            raise ValueError('history_gap_'+str(len(remaining))+'_of_'+str(len(wanted))+
                             '_first_'+str(remaining[:3]))
    ordered=[rows[t] for t in wanted]
    digest=hashlib.sha256(json.dumps(ordered,separators=(',',':')).encode()).hexdigest()
    return ordered,{'symbol':symbol,'minutes':len(ordered),'requests':calls,
                    'coverage_pct':100.,'sha256':digest,
                    'first_ms':ordered[0][0],'last_ms':ordered[-1][0]}


def first_barrier(bars,ix,side):
    if ix+HORIZON>=len(bars):
        return {'outcome':'censored','minutes':None}
    entry=bars[ix][4]
    hi=entry*(1+BARRIER*side)
    lo=entry*(1-BARRIER*side)
    for wait in range(1,HORIZON+1):
        r=bars[ix+wait]
        hit_f=(r[2]>=hi if side==1 else r[3]<=hi)
        hit_a=(r[3]<=lo if side==1 else r[2]>=lo)
        if hit_a:return {'outcome':'adverse_first','minutes':wait}
        if hit_f:return {'outcome':'favorable_first','minutes':wait}
    return {'outcome':'no_barrier','minutes':None}


def event_summary(events):
    count=len(events)
    counts={k:sum(e['outcome']==k for e in events)
            for k in ('favorable_first','adverse_first','no_barrier','censored')}
    observed=counts['favorable_first']+counts['adverse_first']
    success=counts['favorable_first']
    ratio=success/observed if observed else None
    # Wilson 95%, conditional on a barrier being reached.
    if observed:
        z=1.96
        denominator=1+z*z/observed
        center=(ratio+z*z/(2*observed))/denominator
        half=z*math.sqrt(ratio*(1-ratio)/observed+z*z/(4*observed**2))/denominator
        interval=[round(max(0,center-half),3),round(min(1,center+half),3)]
    else:interval=None
    mins=[e['minutes'] for e in events if e['outcome']=='favorable_first']
    return {'events':count,'outcomes':counts,
            'favorable_first_pct_given_barrier':round(ratio*100,2) if ratio is not None else None,
            'wilson_95_pct': [round(v*100,1) for v in interval] if interval else None,
            'median_min_to_favorable_barrier':statistics.median(mins) if mins else None}


def replay(symbol,bars):
    """Signals use current/past closes; barriers are labelled only afterwards."""
    stable=None
    last_emitted={1:-100000,-1:-100000}
    signals=[]
    states={'BULLISH':0,'BEARISH':0,'NEUTRAL':0,'TRANSITION_UP':0,
            'TRANSITION_DOWN':0,'UNKNOWN':0}
    for ix in range(299,len(bars)):
        t=bars[ix][0]+MINUTE
        observation=safe_indicator(symbol,bars[max(0,ix-299):ix+1],now_ms=t)
        if observation['quality']!='OK':continue
        state=observation['state']
        states[state]=states.get(state,0)+1
        if state in ('BULLISH','BEARISH'):
            stable=(1 if state=='BULLISH' else -1,ix)
        for transition,side in (('TRANSITION_UP',1),('TRANSITION_DOWN',-1)):
            if (state==transition and stable is not None and stable[0]==-side
                and ix-stable[1]<=180 and ix-last_emitted[side]>=120):
                item={'symbol':symbol,'ts_ms':t,'direction':'UP' if side==1 else 'DOWN',
                      'state':state,'price_close':bars[ix][4],
                      'minutes_since_last_opposing_trend':ix-stable[1]}
                item.update(first_barrier(bars,ix,side))
                signals.append(item);last_emitted[side]=ix
    # Fixed deterministic non-trading baseline: one point per 120 minutes.
    rng=random.Random(20261030+len(symbol))
    baseline=[]
    for ix in range(299+45,len(bars),120):
        side=rng.choice((-1,1))
        label=first_barrier(bars,ix,side)
        baseline.append({'direction':'UP' if side==1 else 'DOWN',**label})
    by_direction={d:event_summary([s for s in signals if s['direction']==d])
                  for d in ('UP','DOWN')}
    return signals,{'symbol':symbol,'state_counts':states,
                    'events_per_day':round(len(signals)/7,3),
                    'total':event_summary(signals),
                    'up':by_direction['UP'],'down':by_direction['DOWN'],
                    'descriptive_random_baseline':event_summary(baseline)}


def run(outdir='research-results'):
    destination=Path(outdir);destination.mkdir(parents=True,exist_ok=True)
    (destination/'validated_candles').mkdir(exist_ok=True)
    summary={'status':'started','provenance':'Bitget V2 public USDT-FUTURES',
             'window_start_utc':'2026-10-16T00:00:00Z',
             'window_end_exclusive_utc':'2026-10-23T00:00:00Z',
             'symbols':list(SYMBOLS),'method':'preregistered_0.35pct_first_barrier_90m',
             'outcomes':{},'unavailable':{},'integrity':{}}
    all_events=[]
    for symbol in SYMBOLS:
        try:
            rows,integrity=gather(symbol)
            summary['integrity'][symbol]=integrity
            with gzip.open(destination/'validated_candles'/(symbol+'USDT-1m.csv.gz'),'wt') as f:
                writer=csv.writer(f)
                writer.writerow(['open_ms','open','high','low','close','base_volume'])
                writer.writerows(rows)
            events,metrics=replay(symbol,rows)
            all_events.extend(events)
            summary['outcomes'][symbol]=metrics
            print('REAL_REPLAY_SYMBOL '+json.dumps({'symbol':symbol,
                         'count':len(events),'metrics':metrics['total']},sort_keys=True),flush=True)
        except Exception as exc:
            # Never silently synthesize or substitute a ticker.
            summary['unavailable'][symbol]=str(exc)[:160]
            print('REAL_REPLAY_UNAVAILABLE '+symbol+' '+type(exc).__name__+
                  ': '+str(exc)[:110],flush=True)
    summary['status']='real_data' if summary['outcomes'] else 'no_verifiable_real_data'
    summary['eligible_symbols']=len(summary['outcomes'])
    summary['eligible_observed_minutes']=sum(v['minutes'] for v in summary['integrity'].values()
                                                if v['symbol'] in summary['outcomes'])
    summary['all_real_events']=event_summary(all_events)
    (destination/'summary.json').write_text(json.dumps(summary,indent=2,sort_keys=True))
    with (destination/'trend_events.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=[
            'symbol','ts_ms','direction','state','price_close',
            'minutes_since_last_opposing_trend','outcome','minutes'])
        writer.writeheader();writer.writerows(all_events)
    print('REAL_REPLAY_FINAL '+json.dumps(summary,sort_keys=True),flush=True)
    # Do not turn API/data failure into a green validation.
    if len(summary['outcomes'])!=len(SYMBOLS):
        raise SystemExit('REPLAY_INCOMPLETE: missing real data for one or more fixed symbols')
    return summary


if __name__=='__main__':
    run(sys.argv[1] if len(sys.argv)>1 else 'research-results')
