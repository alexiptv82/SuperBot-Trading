"""Asynchronous DeepSeek adapter for the classical JSON decision contract.

Only the worker calls the model. The sole account writer never waits for it;
protection/fallback continue. Results require fresh time, unchanged exposure,
valid schema and bounded price drift before reaching the classical controls.
"""
from concurrent.futures import ThreadPoolExecutor
import copy
import hashlib
import json
import math
from dataclasses import replace
from director.ai_shadow import deepseek


class Unavailable(RuntimeError):
    pass


def fingerprint(state):
    a=state.get("main",{})
    fields=("id","side","entry","qty","total_margin","leverage","sl","tp","dca_count","pending_split")
    positions={s:{k:p.get(k) for k in fields} for s,p in a.get("positions",{}).items()}
    return hashlib.sha256(json.dumps({"cash":a.get("cash"),"positions":positions},sort_keys=True,allow_nan=False).encode()).hexdigest()


def validate(text, symbols, key):
    text=text.replace(key,"[redacted]") if key else text
    data=json.loads(text,parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite_response")))
    if not isinstance(data,dict) or not isinstance(data.get("decisions"),list) or len(data["decisions"])>30:
        raise ValueError("invalid_response")
    actions={"open_long","open_short","open_long_split","open_short_split","hold","close","partial_close","dca","skip"}
    numeric={"confidence","leverage","margin_usd","stop_loss_pct","take_profit_pct","partial_close_fraction","partial_close_tp2_pct","dca_sl_pct","dca_tp_pct","split_retrace_pct"}
    allowed=numeric|{"symbol","action","trade_type","reason"}
    out=[];seen=set()
    for raw in data["decisions"]:
        if not isinstance(raw,dict) or raw.get("symbol") not in symbols or raw.get("action") not in actions or raw["symbol"] in seen:
            raise ValueError("invalid_or_duplicate_decision")
        d={k:v for k,v in raw.items() if k in allowed}
        if not isinstance(d.get("reason"),str) or not d["reason"].strip():
            raise ValueError("missing_reason")
        for k in numeric & d.keys():
            v=d[k]
            if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not 0<=v<=1e6:
                raise ValueError("invalid_number")
        if d.get("trade_type","scalp") not in ("scalp","medio"):
            raise ValueError("invalid_trade_type")
        if d["action"].startswith("open_"):
            if not 0<d.get("stop_loss_pct",0)<1 or not 0<d.get("take_profit_pct",0)<1 or not 1<=d.get("leverage",0)<=45 or not 0<=d.get("confidence",-1)<=100 or d.get("margin_usd",0)<=0:
                raise ValueError("invalid_entry")
        for k in ("dca_sl_pct","dca_tp_pct","partial_close_tp2_pct"):
            if d.get(k,0)>=1:raise ValueError("invalid_price_fraction")
        if "partial_close_fraction" in d and not .05<=d["partial_close_fraction"]<=.95:
            raise ValueError("invalid_close_fraction")
        d["reason"]=d["reason"][:300]
        out.append(d);seen.add(d["symbol"])
    return {"decisions":out,"note":str(data.get("note",""))[:200]}


class Provider:
    def __init__(self, profile, cfg, key, budget, call=deepseek.call):
        self.profile,self.cfg,self.key,self.budget,self.call=profile,cfg,key,budget,call
        self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix="brain-model")
        self.pending=None
        self.last_status="not_requested"

    def close(self):
        self.pool.shutdown(wait=True,cancel_futures=True)

    def request(self, system, user, state, readings, now_ms, symbols):
        current=fingerprint(state)
        if self.pending:
            job=self.pending
            if not job["future"].done():
                self.last_status="model_pending";raise Unavailable(self.last_status)
            self.pending=None
            if not 0<=now_ms-job["ts"]<=120000 or job["fingerprint"]!=current:
                self.last_status="stale_model_result";raise Unavailable(self.last_status)
            try:
                result=job["future"].result()
                data=validate(result["content"],symbols,self.key)
                for d in data["decisions"]:
                    if d["action"].startswith("open_"):
                        old=job["prices"].get(d["symbol"]);new=readings.get(d["symbol"])
                        if not old or not new or abs(new/old-1)>min(.005,d["stop_loss_pct"]*.5):
                            raise ValueError("price_drift")
                self.last_status="adaptive_ai"
                return json.dumps(data),{"brain_reserved_cost":job["cost"],"stop_reason":"stop"}
            except Exception:
                self.last_status="invalid_or_failed_model_result"
                raise Unavailable(self.last_status) from None
        if not self.key:
            self.last_status="missing_model_key";raise Unavailable(self.last_status)
        allowed,why,cost=self.budget.reserve(self.profile,now_ms,len(system.encode())+len(user.encode()),self.cfg.max_tokens)
        if not allowed:
            self.last_status=why;raise Unavailable(why)
        self.pending={"future":self.pool.submit(self.call,replace(self.cfg),self.key,system,user),
                      "ts":now_ms,"fingerprint":current,"prices":copy.deepcopy(readings),"cost":cost,"id":why}
        self.last_status="model_pending"
        raise Unavailable(self.last_status)
