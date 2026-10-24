#!/usr/bin/env python3
"""Read-only paper position & stop audit; no orders, no state writes, no API access.

All mark-to-market figures use the bot's latest persistently saved cycle price.
Exit estimates reproduce position_card.metrics (Fix A) with saved current limits.
An open stop level is NOT proof an exit can execute; stop execution also needs
fresh closed 15m bars and verified journal fills.
"""
from __future__ import annotations
from pathlib import Path
import datetime as dt
import json
import math
import subprocess
import time

NOW=int(time.time()*1000)
BAR_MS=900_000
def finite(x):
    if isinstance(x,bool):return None
    try:
        n=float(x)
        return n if math.isfinite(n) else None
    except (ValueError,TypeError):return None
def ms(v):
    n=finite(v)
    return int(n) if n is not None and n>=0 else None
def tsfmt(m):
    if m is None:return None
    return dt.datetime.fromtimestamp(m/1000,dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
def read(path):
    with open(path,encoding="utf8") as f:
        return json.load(f)
def dock(cmd,*extra):
    x=subprocess.run(["docker",cmd,*extra],capture_output=True,text=True,timeout=12)
    if x.returncode:raise RuntimeError("docker_"+cmd+"_failed")
    return x.stdout
def sample_journal(bot,after_ms):
    f=Path("/opt/superbot-desk-data")/bot/"learning_log.jsonl"
    counts={"new_opens":0,"new_closes":0,"closed_by_stop_loss":0,
            "closed_by_take_profit":0,"closed_by_liquidation":0,
            "closed_by_other":0,"close_samples":[],"first_open_utc":None,"last_open_utc":None}
    if not f.exists():return counts
    with f.open(encoding="utf8") as stream:
        for line in stream:
            try: x=json.loads(line)
            except ValueError:continue
            if not isinstance(x,dict):continue
            event=x.get("ev")
            if event not in ("open","close"):continue
            t=ms(x.get("ts") if event=="open" else x.get("close_ms",x.get("ts")))
            if t is None or t<after_ms:continue
            if event=="open":
                counts["new_opens"]+=1
                if not counts["first_open_utc"]:counts["first_open_utc"]=tsfmt(t)
                counts["last_open_utc"]=tsfmt(t)
            else:
                counts["new_closes"]+=1
                why=str(x.get("why") or x.get("reason") or "").lower()
                cat=("stop_loss" if "stop loss" in why else
                     "take_profit" if "take profit" in why else
                     "liquidation" if "liquidaz" in why else "other")
                counts[{"stop_loss":"closed_by_stop_loss","take_profit":"closed_by_take_profit",
                         "liquidation":"closed_by_liquidation","other":"closed_by_other"}[cat]]+=1
                if len(counts["close_samples"])<8:
                    counts["close_samples"].append({"symbol":x.get("symbol"),"kind":cat,
                      "closed_at_utc":tsfmt(t),"net_usd":round(float(x.get("net") or 0),2)})
    return counts
def metric(p,price,now,closed,lim):
    side=p.get("side");entry=finite(p.get("entry"))
    qty=finite(p.get("qty"));fee_open=finite(p.get("fee_open"));margin=finite(p.get("margin"))
    if side not in (-1,1) or any(x is None for x in (price,entry,qty,fee_open,margin)) or min(price,entry,qty)<=0:return None,None,None
    dcas=p.get("dca_levels") or []
    ref=margin+sum(float(x.get("margin",0)) for x in dcas)
    if ref<=0:return None,None,None
    slip=finite(lim.get("slip_bp_side"));fee_bp=finite(lim.get("fee_bp_side"));fund_bp=finite(lim.get("funding_bp_8h_long"))
    if any(x is None for x in (slip,fee_bp,fund_bp)):return None,None,None
    fill=price*(1-side*slip/10000)
    pos_open=ms(p.get("open_ms")) or now
    funding=qty*entry*fund_bp/10000*max(0,now-pos_open)/28_800_000 if side==1 else 0.
    realized=0.
    for x in closed:
        if (x.get("id")==p.get("id") and x.get("symbol")==p.get("symbol") and
            x.get("open_ms")==p.get("open_ms") and x.get("partial") is True):
            realized+=float(x.get("net") or 0)
    net=realized+side*(fill-entry)*qty-fee_open-qty*fill*fee_bp/10000-funding
    return round(net/ref*100,2),round(net,2),round(ref,2)

for bot in ("hawk","bull"):
    root=Path("/opt/superbot-desk-data")/bot
    h=read(root/"heartbeat.json");st=read(root/"state_v2.json")
    state=json.loads(dock("inspect","superbot-desk-"+bot))[0]
    env={s.split("=",1)[0]:s.split("=",1)[1] for s in state["Config"]["Env"] if "=" in s}
    acc=st.get("main") or {}
    lim=acc.get("limits") or {}
    prices=st.get("last_prices") or {}
    prices_ms=ms(st.get("last_prices_ms"))
    age_minutes=round((NOW-prices_ms)/60000,2) if prices_ms else None
    quote_fresh=bool(age_minutes is not None and 0<=age_minutes<=20)
    closed=acc.get("closed") or []
    open_items=[]
    bad_stops=0
    mark_unknown=0
    missing_stop=0
    total_unrealized=0.
    for sym,p in sorted((acc.get("positions") or {}).items()):
        side=p.get("side")
        price=finite(prices.get(sym))
        sl=finite(p.get("sl"))
        tp=finite(p.get("tp"))
        if sl is None or sl<=0:missing_stop+=1
        if price is None or price<=0:mark_unknown+=1
        executable_mark=price if quote_fresh else None
        roi,net,ref=metric(p,executable_mark,NOW,closed,lim) if executable_mark is not None else (None,None,None)
        risk_dir=None
        if price is not None and sl is not None and price>0 and sl>0:
            dist=(sl/price-1)*100 if side==-1 else (1-sl/price)*100 if side==1 else None
            risk_dir=round(dist,3) if dist is not None else None
            if dist is not None and dist<=0 and quote_fresh:bad_stops+=1
        entry=finite(p.get("entry"))
        qty=finite(p.get("qty"))
        if price is not None and entry is not None and qty is not None:
            total_unrealized+=side*(price-entry)*qty
        last_bar=ms(p.get("last_bar_ms"))
        # Last bar timestamp is the candle OPEN; a closed 15m bar ends 15m later.
        bar_age_minutes=round((NOW-(last_bar+BAR_MS))/60000,1) if last_bar else None
        open_items.append({
          "symbol":sym,"side":"SHORT" if side==-1 else "LONG" if side==1 else "UNKNOWN",
          "entry":entry,"mark":round(price,8) if price is not None else None,
          "mark_fresh":quote_fresh,"roi_net_est_pct":roi,
          "est_exit_net_usd":net,"reference_margin_usd":ref,
          "sl":sl,"tp":tp,"sl_distance_pct_at_mark":risk_dir,
          "sl_present":bool(sl is not None and sl>0),
          "sl_already_crossed_at_mark":bool(risk_dir is not None and risk_dir<=0 and quote_fresh),
          "last_processed_closed_bar_age_min":bar_age_minutes,
          "open_ms":ms(p.get("open_ms")),
          "dca_count":p.get("dca_count"),"pending_split":bool(p.get("pending_split"))
        })
    restart=ms(h.get("started_ms")) or 0
    logs=dock("logs","--since=100m","--tail=220","superbot-desk-"+bot)
    categories=["Traceback","Exception:","[ERROR]","stop loss","take profit","[SLEEP]",
                "[CAPITAL]","liquidazione","[DESK V2] candles ok"]
    errors={p:sum(p in line for line in logs.splitlines()) for p in categories}
    print("STARTUP_POSITION_REPORT",json.dumps({
      "bot":bot,"checked_utc":tsfmt(NOW),
      "docker_running":state["State"].get("Running"),
      "docker_health":(state["State"].get("Health") or {}).get("Status"),
      "docker_started_at_utc":state["State"].get("StartedAt"),
      "runtime_sha_short":h.get("version"),"env_mode":env.get("DESK_MODE"),
      "env_capital_v1":env.get("DESK_CAPITAL_V1"),"heartbeat_capital_v1":h.get("capital_v1"),
      "heartbeat_last_ok":h.get("last_ok"),"heartbeat_cycles":h.get("cycles"),
      "heartbeat_last_error":str(h.get("last_error") or "")[:140],
      "heartbeat_last_cycle_utc":tsfmt(ms(h.get("last_end_ms"))),
      "prices_asof_utc":tsfmt(prices_ms),"prices_age_minutes":age_minutes,
      "prices_fresh_20min":quote_fresh,
      "open_count":len(open_items),"short_count":sum(x["side"]=="SHORT" for x in open_items),
      "long_count":sum(x["side"]=="LONG" for x in open_items),
      "missing_stop_count":missing_stop,"sl_breached_at_fresh_mark_count":bad_stops,
      "unpriced_positions_count":mark_unknown,
      "gross_unrealized_usd_at_marks":round(total_unrealized,2) if quote_fresh and not mark_unknown else None,
      "journal_since_restart":sample_journal(bot,restart),
      "recent_log_categories":errors,"positions":open_items
    },separators=(",",":"),ensure_ascii=False,allow_nan=False),flush=True)
print("STARTUP_POSITION_AUDIT_COMPLETE")
