"""Optional context, never imported by the executor and never an entry gate."""
from datetime import datetime,timezone
from email.utils import parsedate_to_datetime
import math,json,urllib.request,xml.etree.ElementTree as ET


def get(url):
    req=urllib.request.Request(url,headers={'User-Agent':'SuperBot-PAPER/brain-free-context'})
    with urllib.request.urlopen(req,timeout=8) as r:return r.read(1_000_001)

def fetch(now,fetcher=get):
    result={}
    sources={
        'btc_dominance':('CoinGecko','https://api.coingecko.com/api/v3/global'),
        'fear_greed':('Alternative.me','https://api.alternative.me/fng/?limit=1'),
        'macro_calendar':('ForexFactory/FairEconomy','https://nfs.faireconomy.media/ff_calendar_thisweek.json'),
        'macro_news':('Federal Reserve','https://www.federalreserve.gov/feeds/press_monetary.xml')}
    for name,(source,url) in sources.items():
        try:
            raw=fetcher(url)
            if len(raw)>1_000_000:raise ValueError('oversize')
            if name=='btc_dominance':
                d=json.loads(raw)['data'];data={'percent':float(d['market_cap_percentage']['btc'])}
                if not math.isfinite(data['percent']) or not 0<=data['percent']<=100:raise ValueError('invalid_dominance')
                updated=int(d['updated_at'])*1000
            elif name=='fear_greed':
                d=json.loads(raw)['data'][0];data={'value':int(d['value']),'classification':str(d['value_classification'])[:100]};updated=int(d['timestamp'])*1000
                if not 0<=data['value']<=100:raise ValueError('invalid_sentiment')
            elif name=='macro_calendar':
                data=[]
                for d in json.loads(raw):
                    ts=int(datetime.fromisoformat(d['date']).timestamp()*1000)
                    if now<=ts<=now+6*3600000:data.append({'title':str(d['title'])[:200],'time_ms':ts,'currency':str(d.get('country',''))[:8],'impact':str(d.get('impact',''))[:20]})
                updated=now # retrieval time; not falsely a provider publication timestamp.
            else:
                data=[]
                for d in ET.fromstring(raw).findall('.//item')[:10]:
                    ts=int(parsedate_to_datetime(d.findtext('pubDate')).timestamp()*1000)
                    if now-24*3600000<=ts<=now:data.append({'title':d.findtext('title','')[:200],'published_ms':ts})
                updated=now
            result[name]={'status':'available','source':source,'url':url,'updated_ms':updated,'retrieved_ms':now,'data':data,'binding':False}
        except Exception:result[name]={'status':'unavailable','source':source,'retrieved_ms':now,'binding':False}
    return result
