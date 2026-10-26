"""Optional public futures context; timestamped, cached and restart-persistent.

No exchange keys. Caller persists state in its own atomic brain snapshot. A
bounded network budget and round-robin cursor prevent slow feeds blocking AI.
"""
import copy
import json
import math
import time
import urllib.request

BASE="https://api.bitget.com/api/v2/mix/market/"
FNG="https://api.alternative.me/fng/?limit=1"
HOUR=3600000


def finite(value):
    if isinstance(value,bool):raise ValueError("boolean")
    value=float(value)
    if not math.isfinite(value):raise ValueError("nonfinite")
    return value


def fetch_json(url):
    request=urllib.request.Request(url,headers={"User-Agent":"SuperBot-Brain-PAPER"})
    with urllib.request.urlopen(request,timeout=2) as response:
        return json.loads(response.read(262144))


def _bitget(payload):
    if not isinstance(payload,dict) or payload.get("code")!="00000":raise ValueError("unavailable")
    return payload["data"]


def _point(rows,point,now_ms):
    # One observation per 15m bucket, including repeated model attempts/restarts.
    rows=[r for r in rows if 0<=now_ms-r["ts_ms"]<=8*HOUR]
    if not rows or rows[-1]["ts_ms"]//900000!=now_ms//900000:
        rows.append(point)
    return rows[-40:]


def view(state,symbols,now_ms):
    result={"as_of_ms":now_ms,"symbols":{},"btc_macro":{
        "fear_greed":None,"source":"Alternative.me — https://alternative.me/crypto/fear-and-greed-index/",
        "availability":"non disponibile"}}
    fng=state.get("fear_greed")
    if fng and 0<=now_ms-fng["ts_ms"]<=48*HOUR:
        result["btc_macro"].update(fear_greed=copy.deepcopy(fng),availability="available")
    for symbol in sorted(symbols):
        record=state.get("symbols",{}).get(symbol,{})
        row={"funding_recent_samples":[],"funding_settled":[],"funding_interpretation":None,
             "oi_quantity":None,"oi_change_4h_pct":None,"oi_reference_ts_ms":None,"oi_elapsed_ms":None,
             "availability":"non disponibile"}
        samples=[p for p in record.get("funding",[]) if 0<=now_ms-p["ts_ms"]<=2*HOUR]
        if samples and now_ms-samples[-1]["ts_ms"]<=1800000:
            row["funding_recent_samples"]=copy.deepcopy(samples[-3:])
            if len(samples)>=3:
                rates=[p["rate"] for p in samples[-3:]]
                if min(rates)>.0005:row["funding_interpretation"]="persistent_positive_long_payment_pressure_not_reversal_proof"
                elif max(rates)<-.0005:row["funding_interpretation"]="persistent_negative_short_payment_pressure_not_reversal_proof"
        if 0<=now_ms-record.get("settled_fetched_ms",-100*HOUR)<=4*HOUR:
            row["funding_settled"]=copy.deepcopy(record.get("settled",[]))
        oi=[p for p in record.get("oi",[]) if 0<=now_ms-p["ts_ms"]<=8*HOUR]
        if oi and now_ms-oi[-1]["ts_ms"]<=1800000:
            latest=oi[-1];row["oi_quantity"]=copy.deepcopy(latest)
            # Compare quantities (not dollar values, which move with price).
            candidates=[p for p in oi[:-1] if abs(latest["ts_ms"]-p["ts_ms"]-4*HOUR)<=900000]
            if candidates:
                ref=min(candidates,key=lambda p:abs(latest["ts_ms"]-p["ts_ms"]-4*HOUR))
                row.update(oi_change_4h_pct=100*(latest["quantity"]/ref["quantity"]-1),oi_reference_ts_ms=ref["ts_ms"],
                           oi_elapsed_ms=latest["ts_ms"]-ref["ts_ms"])
        if row["oi_quantity"] or row["funding_recent_samples"] or row["funding_settled"]:
            row["availability"]="available_or_partial"
        result["symbols"][symbol+"USDT"]=row
    return result


class ContextCollector:
    def __init__(self,fetch=fetch_json,clock=time.monotonic,max_seconds=10):
        self.fetch=fetch;self.clock=clock;self.max_seconds=max_seconds

    def collect(self,symbols,now_ms,state):
        # Only requests initiated inside the budget; final request <=2s timeout.
        deadline=self.clock()+self.max_seconds
        def get(url):
            if self.clock()>=deadline:raise TimeoutError("context_budget")
            return self.fetch(url)
        if now_ms>=state.get("fng_next_ms",0):
            try:
                data=get(FNG)["data"][0]
                value=finite(data["value"]);stamp=finite(data["timestamp"])*1000
                if not 0<=value<=100 or not 0<=now_ms-stamp<=48*HOUR:raise ValueError("invalid_fng")
                state["fear_greed"]={"value":value,"ts_ms":stamp,"observed_ms":now_ms,
                                      "classification":str(data.get("value_classification",""))[:60]}
                wait=finite(data.get("time_until_update",3600))
                state["fng_next_ms"]=now_ms+min(86400,max(300,wait))*1000
            except Exception:
                state["fng_next_ms"]=now_ms+900000
        names=sorted(set(symbols));n=len(names)
        if not n:return view(state,names,now_ms)
        cursor=int(state.get("cursor",0))%n
        for i in range(n):
            if self.clock()>=deadline:break
            symbol=names[(cursor+i)%n]
            if not symbol.isalnum():continue
            record=state.setdefault("symbols",{}).setdefault(symbol,{})
            suffix="?symbol="+symbol+"USDT&productType=USDT-FUTURES"
            if now_ms-record.get("observed_ms",-100*HOUR)<900000:continue
            try:
                payload=_bitget(get(BASE+"current-fund-rate"+suffix))
                data=payload[0] if isinstance(payload,list) else payload
                rate=finite(data["fundingRate"])
                record["funding"]=_point(record.get("funding",[]),{"rate":rate,"ts_ms":now_ms,"kind":"observed_current"},now_ms)
            except Exception:pass
            try:
                data=_bitget(get(BASE+"open-interest"+suffix))["openInterestList"]
                match=next(p for p in data if p.get("symbol")==symbol+"USDT")
                quantity=finite(match["size"])
                if quantity<=0:raise ValueError("invalid_oi")
                record["oi"]=_point(record.get("oi",[]),{"quantity":quantity,"ts_ms":now_ms,"unit":"base_asset_quantity"},now_ms)
            except Exception:pass
            if now_ms-record.get("settled_fetched_ms",-100*HOUR)>=4*HOUR:
                try:
                    rows=_bitget(get(BASE+"history-fund-rate"+suffix+"&pageSize=3"))
                    settled={}
                    for p in rows:
                        stamp=finite(p["fundingTime"])
                        rate=finite(p["fundingRate"])
                        if 0<stamp<=now_ms:settled[stamp]={"rate":rate,"ts_ms":stamp,"kind":"settled_payment"}
                    record["settled"]=[settled[t] for t in sorted(settled)][-3:]
                    record["settled_fetched_ms"]=now_ms
                except Exception:pass
            record["observed_ms"]=now_ms
            state["cursor"]=(cursor+i+1)%n
        return view(state,names,now_ms)
