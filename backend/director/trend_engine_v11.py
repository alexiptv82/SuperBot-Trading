"""Trend Engine v1.1 adapted from user's ZIP, as an INDICATOR ONLY.

Pure CPU, closed contiguous 1-minute Bitget V2 OHLCV. No HTTP, orders,
score adjustment, candidate filtering, stop/target edits, or authority to trade.
The two production-facing integrations must use an *asynchronous* caller.
"""
from collections import deque
from dataclasses import dataclass
from math import isfinite

MINUTE=60000
MAX_BARS=1000
WARMUP=50


def _clip(v):
    return max(-1.0,min(1.0,v))


@dataclass(frozen=True)
class _Candle:
    ts:int
    op:float
    hi:float
    lo:float
    cl:float
    vol:float

    def validate(self):
        if (type(self.ts)!=int or self.ts<0 or self.ts%60 or
            any(not isfinite(v) for v in (self.op,self.hi,self.lo,self.cl,self.vol)) or
            min(self.op,self.hi,self.lo,self.cl)<=0 or self.vol<0 or
            not self.lo<=min(self.op,self.cl)<=max(self.op,self.cl)<=self.hi):
            raise ValueError('untrusted_ohlcv')


class _Frame:
    def __init__(self):
        self.bars=deque(maxlen=50)
        self.n=0
        self.fast=self.slow=self.atr=None
        self.swing_high=self.swing_low=None
        self.structure=self.score=0.0
        self.reasons=()

    def add(self,c):
        prev=self.bars[-1].cl if self.bars else c.op
        tr=max(c.hi-c.lo,abs(c.hi-prev),abs(c.lo-prev))
        old_fast=self.fast if self.fast is not None else c.cl
        self.fast=old_fast+2/10*(c.cl-old_fast)
        self.slow=c.cl if self.slow is None else self.slow+2/22*(c.cl-self.slow)
        self.atr=tr if self.atr is None else self.atr+(tr-self.atr)/14
        unit=max(self.atr,c.cl*1e-10)
        reasons=[]
        self.structure*=0.8
        if self.swing_high is not None and c.cl>self.swing_high+0.10*unit:
            self.structure=1.0;self.swing_high=None
            reasons.append('confirmed_high_break')
        if self.swing_low is not None and c.cl<self.swing_low-0.10*unit:
            self.structure=-1.0;self.swing_low=None
            reasons.append('confirmed_low_break')
        slope=_clip((self.fast-old_fast)/unit*3)
        spread=_clip((self.fast-self.slow)/unit)
        impulse=_clip((c.cl-prev)/unit)
        volumes=[b.vol for b in list(self.bars)[-20:]]
        avg=sum(volumes)/len(volumes) if volumes else 0
        vol_impulse=impulse*_clip(max(0,c.vol/avg-1)) if avg else 0
        # Bitget row[6] is quote turnover, NOT taker-buy base volume.
        # We never fabricate the optional signed taker delta.
        self.score=_clip(0.35*slope+0.25*spread+
                         0.25*self.structure+0.10*vol_impulse)
        self.bars.append(c);self.n+=1
        if len(self.bars)>=5:
            window=list(self.bars)[-5:]
            pivot=window[2]
            rest=window[:2]+window[3:]
            if all(pivot.hi>b.hi for b in rest):self.swing_high=pivot.hi
            if all(pivot.lo<b.lo for b in rest):self.swing_low=pivot.lo
        self.reasons=tuple(reasons)


def _parse(rows,now_ms):
    if (type(now_ms)!=int or now_ms<=0 or
        not isinstance(rows,(list,tuple)) or not 1<=len(rows)<=MAX_BARS):
        raise ValueError('invalid_input')
    seen={};candles=[];previous=None
    for row in rows:
        if not isinstance(row,(list,tuple)) or len(row)<6:
            raise ValueError('invalid_shape')
        raw=[float(x) if not isinstance(x,bool) else float('nan') for x in row[:6]]
        if not all(isfinite(x) for x in raw):
            raise ValueError('invalid_number')
        ms=int(raw[0])
        if raw[0]!=ms or ms<0 or ms%MINUTE:
            raise ValueError('invalid_timestamp')
        c=_Candle(ms//1000,*raw[1:6])
        c.validate()
        if ms+MINUTE>now_ms:continue  # Unclosed current bar has no authority.
        fingerprint=(c.op,c.hi,c.lo,c.cl,c.vol)
        if ms in seen:
            if seen[ms]!=fingerprint:raise ValueError('conflicting_revision')
            continue
        if previous is not None and ms!=previous+MINUTE:
            raise ValueError('noncausal_gap_or_out_of_order')
        seen[ms]=fingerprint
        candles.append(c);previous=ms
    return candles


def read_bitget_closed_1m(symbol,rows,*,now_ms):
    """A fresh, bounded, no-score-delta observation for Brain and classics.

    UNKNOWN is not a SHORT, HOLD, NO_TRADE, or bot gate: it is *no opinion*.
    All state is recomputed from bounded public history for deterministic replay.
    """
    if not isinstance(symbol,str) or not symbol.isascii() or not symbol.isalnum() or len(symbol)>20:
        raise ValueError('invalid_symbol')
    candles=_parse(rows,now_ms)
    if not candles:
        return {'symbol':symbol,'quality':'WARMUP','state':'NEUTRAL',
                'observed_ms':None,'ready':False,'bias':0.0,
                'five_minute_ready':False}
    last_ms=candles[-1].ts*1000+MINUTE
    if now_ms-last_ms>90000:
        return {'symbol':symbol,'quality':'STALE','state':'UNKNOWN',
                'observed_ms':last_ms,'ready':False,'bias':0.0,
                'five_minute_ready':False}
    one=_Frame();five=_Frame();bucket=[]
    state='NEUTRAL';candidate=0;count=quiet=0
    for c in candles:
        one.add(c)
        if c.ts%300==0:bucket=[c]
        elif bucket and c.ts==bucket[-1].ts+60:bucket.append(c)
        else:bucket=[]
        if len(bucket)==5:
            five.add(_Candle(bucket[0].ts,bucket[0].op,max(b.hi for b in bucket),
                             min(b.lo for b in bucket),bucket[-1].cl,
                             sum(b.vol for b in bucket)))
            bucket=[]
        if one.n<50:continue
        raw=0.75*one.score+0.25*five.score if five.n>=50 else one.score
        direction=1 if raw>=0.45 else -1 if raw<=-0.45 else 0
        current=1 if state=='BULLISH' else -1 if state=='BEARISH' else 0
        quiet=quiet+1 if abs(raw)<0.18 else 0
        if direction:
            count=count+1 if direction==candidate else 1
            candidate=direction
            if count>=2:state='BULLISH' if direction>0 else 'BEARISH'
            elif direction!=current:
                state='TRANSITION_UP' if direction>0 else 'TRANSITION_DOWN'
        else:
            candidate=count=0
            if current and raw*current<0.18:
                state='TRANSITION_DOWN' if current>0 else 'TRANSITION_UP'
            if quiet>=3:state='NEUTRAL'
    ready=one.n>=50
    bias=(0.75*one.score+0.25*five.score if five.n>=50 else one.score) if ready else 0.0
    return {'symbol':symbol,'quality':'OK' if ready else 'WARMUP',
            'state':state,'observed_ms':last_ms,'ready':ready,
            'bias':round(bias,6),'five_minute_ready':five.n>=50}


def safe_indicator(symbol,rows,*,now_ms):
    """Fail-open for trade decisions: malformed/incomplete data yields no opinion."""
    try:
        result=read_bitget_closed_1m(symbol,rows,now_ms=now_ms)
        quality=result['quality']
    except Exception:
        result={'symbol':symbol,'quality':'UNAVAILABLE','state':'UNKNOWN',
                'observed_ms':None,'ready':False,'bias':0.,
                'five_minute_ready':False}
        quality='UNAVAILABLE'
    return {
        'kind':'trend_engine_v11',
        'source':'user_trend_engine_v1_1_adapted',
        'authority':'advisory_only',
        'may_authorize_entry':False,
        'may_block_entry':False,
        'may_modify_scores':False,
        'symbol':symbol,
        'observed_ms':result['observed_ms'],
        'state':result['state'],'quality':quality,
        'ready':result['ready'],'bias':result['bias'],
        'five_minute_ready':result['five_minute_ready'],
        'strength_is_probability':False,
    }


def read_many(series,now_ms):
    if not isinstance(series,dict) or type(now_ms)!=int:return {}
    return {symbol:safe_indicator(symbol,rows,now_ms=now_ms)
            for symbol,rows in list(series.items())[:50]
            if isinstance(symbol,str) and symbol.isascii() and symbol.isalnum()}
