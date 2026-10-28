"""Public-only Bitget adapters; independent quote and history workers."""
from concurrent.futures import ThreadPoolExecutor
import json,math,time,urllib.request
from .config import Config,max_leverage,number
from .market_context import fetch as fetch_context

BASE='https://api.bitget.com'
def get(path):
    req=urllib.request.Request(BASE+path,headers={'User-Agent':'SuperBot-PAPER/brain-free'})
    with urllib.request.urlopen(req,timeout=8) as r:data=json.loads(r.read(3_000_000))
    if data.get('code')!='00000':raise ValueError('public_market_api')
    return data

def contracts(fetcher=get,symbols=Config().symbols):
    data=fetcher('/api/v2/mix/market/contracts?productType=USDT-FUTURES')['data'];out={}
    for row in data:
        sym=row.get('symbol','').removesuffix('USDT')
        if sym not in symbols:continue
        # Respect exchange precision and minimums; no hardcoded minimum trade size.
        qty_step=float(row.get('sizeMultiplier') or 10**-int(row['volumePlace']))
        out[sym]={'status':row.get('symbolStatus'),'max_leverage':float(row['maxLever']),
          'qty_step':qty_step,'min_qty':float(row['minTradeNum']),
          'min_notional':float(row['minTradeUSDT']),
          'price_step':float(row.get('priceEndStep',1))*10**-int(row['pricePlace']),
          'maintenance':float(row.get('keepMarginRate',Config().maintenance)),
          'maintenance_source':'contract' if 'keepMarginRate' in row else 'paper_conservative_assumption'}
    return out

def quotes(fetcher=get,symbols=Config().symbols):
    data=fetcher('/api/v2/mix/market/tickers?productType=USDT-FUTURES');out={}
    for row in data['data']:
        sym=row.get('symbol','').removesuffix('USDT')
        if sym not in symbols:continue
        try:
            out[sym]={'price':number(float(row['lastPr']),1e-12),
                'mark':number(float(row['markPrice']),1e-12),
                'ts_ms':int(row.get('ts') or data['requestTime'])}
        except (KeyError,ValueError,TypeError):continue
    return out

def candles(symbol,frame,limit=120,fetcher=get):
    payload=fetcher('/api/v2/mix/market/candles?symbol='+symbol+'USDT&productType=USDT-FUTURES&granularity='+frame+'&limit='+str(limit))
    rows=sorted([[float(v) for v in x[:6]] for x in payload['data']],key=lambda b:b[0])
    duration={'1m':60000,'5m':300000,'15m':900000,'1H':3600000,'4H':14400000}[frame]
    previous=None
    for b in rows:
        if len(b)!=6 or not all(math.isfinite(x) for x in b) or b[0]%duration or min(b[1:5])<=0 or b[5]<0 or b[2]<max(b[1],b[4]) or b[3]>min(b[1],b[4]) or previous is not None and b[0]<=previous:raise ValueError('bad_market_bar')
        previous=b[0]
    return rows

def summary(rows,now,duration):
    rows=[b for b in rows if b[0]+duration<=now]
    if not rows:return {'status':'unavailable'}
    close=[b[4] for b in rows];atr=None;rsi=None
    if len(rows)>=15:
        trs=[max(b[2]-b[3],abs(b[2]-rows[i-1][4]),abs(b[3]-rows[i-1][4])) for i,b in enumerate(rows) if i]
        atr=sum(trs[-14:])/14
        delta=[close[i]-close[i-1] for i in range(len(close)-14,len(close))]
        up=sum(max(0,d) for d in delta);down=sum(max(0,-d) for d in delta)
        rsi=50 if up==down==0 else 100 if down==0 else 100-100/(1+up/down)
    recent=rows[-24:]
    total_volume=sum(b[5] for b in recent)
    # OHLCV typical-price proxy, not a real trade-tick VWAP.
    vwap24=(sum(((b[2]+b[3]+b[4])/3)*b[5] for b in recent)/total_volume
            if total_volume>0 else None)
    return {'status':'available','last_close_ms':rows[-1][0]+duration,'atr14':atr,'rsi14':rsi,
            'change_pct':(close[-1]/close[0]-1)*100,'recent_closed':rows[-6:],
            'structure_24_closed_bars':{
                'support_low':min(b[3] for b in recent),
                'resistance_high':max(b[2] for b in recent),
                'typical_price_vwap_approx':vwap24,
                'bars':len(recent),
                'volume_total':total_volume}}

class Feeds:
    def __init__(self,cfg=Config(),fetcher=get,context_fetch=fetch_context):
        self.cfg=cfg;self.fetcher=fetcher;self.context_fetch=context_fetch
        self.fast=ThreadPoolExecutor(1,thread_name_prefix='brain-free-quotes')
        self.slow=ThreadPoolExecutor(1,thread_name_prefix='brain-free-history')
        self.jobs={};self.data={};self.constraints={};self.context={};self.last_slow=0;self.errors={};self.bar_cache={};self.last_context=0;self.context_cache={};self.contract_cache={};self.last_contract=0
    def history(self,positions,now):
        if not self.contract_cache or now-self.last_contract>=3600000:
            self.contract_cache=contracts(self.fetcher,self.cfg.symbols);self.last_contract=now
        limits=self.contract_cache;out={}
        def one(sym):
            row={'bars':{},'summary':{},'funding':[]}
            for frame,duration in (('1m',60000),('5m',300000),('15m',900000),('1H',3600000),('4H',14400000)):
                try:
                    key=(sym,frame);cached=self.bar_cache.get(key)
                    interval=15000 if frame=='1m' and sym in positions else 60000 if frame=='1m' else duration
                    if cached is None or now-cached[0]>=interval or cached[0]//duration!=now//duration:
                        bars=candles(sym,frame,1000 if frame=='1m' and sym in positions else 120,self.fetcher)
                        self.bar_cache[key]=(now,bars)
                    else:bars=cached[1]
                    row['bars'][frame]=bars;row['summary'][frame]=summary(bars,now,duration)
                except Exception:row['summary'][frame]={'status':'unavailable'}
            if sym in positions:
                try:
                    key=(sym,'funding');cached=self.bar_cache.get(key)
                    if cached is None or now-cached[0]>=300000:
                        history=self.fetcher('/api/v2/mix/market/history-fund-rate?symbol='+sym+'USDT&productType=USDT-FUTURES&pageSize=20')['data']
                        self.bar_cache[key]=(now,history)
                    else:history=cached[1]
                    bars=row['bars'].get('1m',[])
                    for f in history:
                        ts=int(f['fundingTime'])
                        match=next((b for b in bars if b[0]+60000==ts),None)
                        if match:row['funding'].append({'ts_ms':ts,'rate':float(f['fundingRate']),'mark':match[4],'mark_source':'paper_trade_bar_estimate'})
                    row['funding_status']='historical_rate_trade_bar_mark_estimate'
                except Exception:row['funding_status']='unavailable_not_assumed_zero'
            return sym,row
        with ThreadPoolExecutor(6) as pool:out=dict(pool.map(one,self.cfg.symbols))
        if not self.context_cache or now-self.last_context>=300000:
            self.context_cache=self.context_fetch(now);self.last_context=now
        return limits,out,self.context_cache
    def poll(self,positions,now):
        for kind in ('quotes','history'):
            job=self.jobs.get(kind)
            if job and job.done():
                try:
                    result=job.result()
                    if kind=='quotes':
                        for sym,q in result.items():self.data.setdefault(sym,{})['quote']=q
                    else:
                        self.constraints,markets,self.context=result
                        for sym,row in markets.items():self.data.setdefault(sym,{}).update(row)
                    self.errors.pop(kind,None)
                except Exception:self.errors[kind]='public_feed_unavailable'
                self.jobs.pop(kind,None)
        if 'quotes' not in self.jobs:self.jobs['quotes']=self.fast.submit(quotes,self.fetcher,self.cfg.symbols)
        if 'history' not in self.jobs and now-self.last_slow>=15000:
            self.last_slow=now;self.jobs['history']=self.slow.submit(self.history,tuple(positions),now)
        return self.data,self.constraints,self.context
    def close(self):
        self.fast.shutdown(wait=False,cancel_futures=True);self.slow.shutdown(wait=False,cancel_futures=True)
