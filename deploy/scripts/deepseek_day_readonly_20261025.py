#!/usr/bin/env python3
"""DeepSeek shadow vs Hawk/Bull daily forensic audit; READS ONLY persistent files.

No internet/API calls, no execution of model decisions, no environment dumps,
no edits, no trading, no service management, no raw saved prompts printed.
"""
import collections
import datetime as dt
import gzip
import json
import math
from pathlib import Path
import subprocess
import time
from zoneinfo import ZoneInfo

TZ=ZoneInfo("Europe/Rome")
UTC=dt.timezone.utc
NOW=int(time.time()*1000)
def at(day,hh,mm=0):
    return int(dt.datetime(2026,10,day,hh,mm,tzinfo=TZ).timestamp()*1000)
DAY_START=at(25,0); DAY_END=min(NOW,at(26,0))
PM_START=at(25,11); PM_END=min(NOW,at(25,15,30))
LAST24_START=NOW-24*3600000
ROOT=Path("/opt/superbot-ai-data/ai")
BASE=Path("/opt/superbot-desk-data")
def when(ts):
    try:return dt.datetime.fromtimestamp(float(ts)/1000,TZ).strftime("%Y-%m-%d %H:%M:%S%z") if ts else None
    except (ValueError,TypeError,OverflowError):return None
def num(v):
    if isinstance(v,bool):return None
    try:
        f=float(v)
        return f if math.isfinite(f) else None
    except (ValueError,TypeError):return None
def rows(path,gz=False):
    if not path.is_file():return [],{"missing":True,"bad":0}
    bad=0;v=[]
    op=gzip.open if gz else open
    with op(path,"rt",encoding="utf8") as f:
        for s in f:
            if not s.strip():continue
            try:
                q=json.loads(s)
                if isinstance(q,dict):v.append(q)
                else:bad+=1
            except (ValueError,EOFError):bad+=1
    return v,{"missing":False,"bad":bad}
def report(name,obj):
    print(name,json.dumps(obj,ensure_ascii=False,separators=(",",":"),allow_nan=False),flush=True)
def inwin(t,lo,hi):return bool(t is not None and lo<=t<hi)
def docker_inspect(c):
    x=subprocess.run(["docker","inspect",c],capture_output=True,text=True,timeout=15)
    if x.returncode:return {"exists":False}
    o=json.loads(x.stdout)[0]
    return {"exists":True,"running":o["State"].get("Running"),"state":o["State"].get("Status"),
            "health":(o["State"].get("Health") or {}).get("Status"),
            "started":o["State"].get("StartedAt"),"image":str(o["Config"].get("Image") or "")[:95]}
def action_counts(rr):return dict(sorted(collections.Counter(z.get("action","?") for z in rr).items()))
def side(z):
    n=z.get("side")
    return "LONG" if str(n)=="1" else "SHORT" if str(n)=="-1" else "UNKNOWN"
def key_of(e):return (e.get("run_no"),e.get("id"),e.get("symbol"))
def snapshot_spend(vals):
    s=[x for x in vals if inwin(num(x.get("ts_ms")),DAY_START,DAY_END)]
    return {"calls_today":len(s),
            "successful_calls_today":sum(x.get("ok") is True for x in s),
            "cost_usd_today":round(sum(num(x.get("cost")) or 0 for x in s),6),
            "avg_cost_usd_per_call":round(sum(num(x.get("cost")) or 0 for x in s)/len(s),7) if s else None,
            "first_today":when(min((x.get("ts_ms") for x in s),default=None)),
            "last_today":when(max((x.get("ts_ms") for x in s),default=None))}
def parse(text):
    text=str(text or "");a=text.find("{");b=text.rfind("}")
    if a<0 or b<=a:return None
    try:j=json.loads(text[a:b+1])
    except ValueError:return None
    return j if isinstance(j,dict) and isinstance(j.get("decisions"),list) else None

report("AUDIT_SCOPE",{"now_local":when(NOW),"window_local_start":when(DAY_START),"window_local_end":when(DAY_END),
  "focus_start":when(PM_START),"focus_end":when(PM_END),
  "day_start_utc":dt.datetime.fromtimestamp(DAY_START/1000,UTC).isoformat(),
  "only_read":True,"source":"saved shadow prompts, cycles, spend and PAPER learning journals"})
report("CONTAINERS",{c:docker_inspect(c) for c in ("superbot-ai","superbot-desk-hawk","superbot-desk-bull")})
status_path=ROOT/"status.json"
status=json.loads(status_path.read_text()) if status_path.exists() else {}
report("SHADOW_STATUS",{"mode":status.get("mode"),"applied":status.get("applied"),
 "last_heartbeat_local":when(status.get("ts_ms")),"last_success_local":when(status.get("last_success_ms")),
 "symbols_ok":status.get("symbols_ok"),"symbols_total":status.get("symbols_total"),
 "model":status.get("algo"),"spend":status.get("spend"),"model_calls":status.get("model")})

all_cycles=[];all_prompts=[];files=[]
for day in ("2026-10-24","2026-10-25"):
    c,cm=rows(ROOT/("cycles-"+day+".jsonl"))
    p,pm=rows(ROOT/("prompts-"+day+".jsonl.gz"),True)
    all_cycles.extend(c);all_prompts.extend(p)
    files.append({"date_utc":day,"cycle_rows":len(c),"prompts_rows":len(p),
                  "bad_cycles":cm["bad"],"bad_prompts":pm["bad"],"has_prompts":not pm["missing"]})
spend,sm=rows(ROOT/"spend.jsonl")
report("SHADOW_FILES",{"dates":files,"spend":snapshot_spend(spend)})

cycles=[c for c in all_cycles if inwin(num(c.get("ts_ms")),DAY_START,DAY_END)]
focus_cycles=[c for c in cycles if inwin(num(c.get("ts_ms")),PM_START,PM_END)]
def summarize_cycles(cs):
    return {"cycles":len(cs),"called":sum((x.get("decision") or {}).get("called") is True for x in cs),
      "empty_model_response":sum((x.get("decision") or {}).get("called") is True and
        (x.get("decision") or {}).get("n_items")==0 for x in cs),
      "skip_system":dict(collections.Counter((x.get("decision") or {}).get("skip")
          for x in cs if (x.get("decision") or {}).get("skip"))),
      "errors":dict(collections.Counter((x.get("decision") or {}).get("error")
          for x in cs if (x.get("decision") or {}).get("error"))),
      "parsed_items":sum(int((x.get("decision") or {}).get("n_items") or 0) for x in cs)}
report("SHADOW_CYCLES_TODAY",summarize_cycles(cycles))
report("SHADOW_CYCLES_11_TO_1530",summarize_cycles(focus_cycles))
cycbybar={x.get("bar_t"):x for x in cycles}
decisions=[]
parse_bad=0
missing_cycle=0
prompts_today=0
for rec in all_prompts:
    bar=rec.get("bar_t")
    cy=cycbybar.get(bar)
    t=(num(cy.get("ts_ms")) if cy else (num(bar)+900000 if num(bar) is not None else None))
    if not inwin(t,DAY_START,DAY_END):continue
    prompts_today+=1
    payload=parse(rec.get("response"))
    if payload is None:parse_bad+=1;continue
    if cy is None:missing_cycle+=1
    result=(cy or {}).get("decision") or {}
    res=result.get("results") or []
    used=set()
    for x in payload["decisions"]:
        if not isinstance(x,dict):continue
        symbol=str(x.get("symbol") or "").upper().replace("USDT","")
        action=str(x.get("action") or "").upper()
        found=None
        for i,z in enumerate(res):
            if i not in used and z.get("symbol")==symbol and z.get("action")==action:
                found=z;used.add(i);break
        decisions.append({"ts":int(t),"when":when(t),"symbol":symbol,"action":action,
                          "conviction":x.get("conviction"),
                          "accepted":found.get("accepted") if found else None,
                          "rejected_reason":(str(found.get("reason") or "")[:90] if found and not found.get("accepted") else None)})
def sums(rr):
    accepted=[x for x in rr if x["accepted"] is True]
    rejected=[x for x in rr if x["accepted"] is False]
    return {"actions":len(rr),"by_action":action_counts(rr),
      "accepted_by_action":action_counts(accepted),
      "rejected_by_reason":dict(collections.Counter(x["rejected_reason"] for x in rejected)),
      "proposals_open_long":sum(x["action"]=="OPEN_LONG" for x in rr),
      "proposals_open_short":sum(x["action"]=="OPEN_SHORT" for x in rr),
      "hold":sum(x["action"]=="HOLD" for x in rr)}
focus_dec=[x for x in decisions if inwin(x["ts"],PM_START,PM_END)]
last75=decisions[-75:]
# Independent virtual-account outcomes, not a simulated switch of the real bots.
vtrades=[];vtfiles=[]
for day in ("2026-10-24","2026-10-25"):
    ts,err=rows(ROOT/("trades-"+day+".jsonl"))
    vtrades.extend(ts)
    vtfiles.append({"utc_day":day,"records":len(ts),"bad":err["bad"]})
vclose=[x for x in vtrades if inwin(num(x.get("close_ms") or x.get("ts")),DAY_START,DAY_END)]
vfocus=[x for x in vclose if inwin(num(x.get("close_ms") or x.get("ts")),PM_START,PM_END)]
def vmetrics(xs):
    net=[num(x.get("net")) or 0 for x in xs]
    return {"close_rows":len(xs),"positive_close_rows":sum(n>0 for n in net),
            "negative_close_rows":sum(n<0 for n in net),
            "net_usd":round(sum(net),2),
            "by_side":dict(collections.Counter(side(x) for x in xs)),
            "by_reason":dict(collections.Counter(str(x.get("why") or "?") for x in xs)),
            "recent_exits":[{"when":when(x.get("close_ms") or x.get("ts")),
               "symbol":x.get("symbol"),"side":side(x),
               "net":round(num(x.get("net")) or 0,2),"why":str(x.get("why") or "")[:60]}
                for x in xs[-12:]]}
virtual_fills=[]
for c in cycles:
    for ev in c.get("events") or []:
        if isinstance(ev,dict) and ev.get("ev")=="fill":
            virtual_fills.append({"when":when(c.get("ts_ms")),"symbol":ev.get("symbol"),
                                  "side":side(ev)})
report("SHADOW_VIRTUAL_PNL_TODAY",{"files":vtfiles,"today":vmetrics(vclose),
   "from_11_to_1530":vmetrics(vfocus),
   "virtual_fills_today":len(virtual_fills),"virtual_fills_by_side":dict(collections.Counter(x["side"] for x in virtual_fills)),
   "virtual_fill_examples":virtual_fills[-15:]})

report("SHADOW_ACTIONS_TODAY",{"prompt_records":prompts_today,"parse_bad":parse_bad,"no_matching_cycle":missing_cycle,**sums(decisions)})
report("SHADOW_ACTIONS_11_TO_1530",sums(focus_dec))
report("SHADOW_LAST_75_ACTIONS",{"count":len(last75),**sums(last75),
   "latest_50_compact":[{"at":x["when"],"symbol":x["symbol"],"action":x["action"],
                        "accepted":x["accepted"],"reject":x["rejected_reason"]} for x in decisions[-50:]]})
# Actual PAPER bot events and exact-key closed realized outcomes
bots={}
for bot in ("hawk","bull"):
    records,errs=rows(BASE/bot/"learning_log.jsonl")
    opens=[x for x in records if x.get("ev")=="open" and inwin(num(x.get("ts")),DAY_START,DAY_END)]
    opens_pm=[x for x in opens if inwin(num(x.get("ts")),PM_START,PM_END)]
    all_close=collections.defaultdict(list)
    for x in records:
        if x.get("ev")=="close":all_close[key_of(x)].append(x)
    by_source=collections.Counter(str(x.get("source","?")) for x in opens)
    sls=[c for c in records if c.get("ev")=="close" and not c.get("partial")
         and inwin(num(c.get("close_ms") or c.get("ts")),PM_START,PM_END)
         and "stop" in str(c.get("why") or "").lower()]
    def brief_open(x):
        cls=all_close.get(key_of(x),[])
        final=any(not z.get("partial") for z in cls)
        return {"at":when(x.get("ts")),"sym":x.get("symbol"),"side":side(x),
                "source":x.get("source"),"trade_type":x.get("trade_type"),
                "confidence":(x.get("features") or {}).get("conf") if isinstance(x.get("features"),dict) else None,
                "closed":final,"realized_net_usd":round(sum(num(z.get("net")) or 0 for z in cls),2) if final else None,
                "close_reason":str(next((z.get("why") for z in cls if not z.get("partial")),""))[:80] if final else None}
    # Compare narrowly in time and same symbol; differences in account state are not controlled.
    match_same=[];match_opposite=[];match_hold=[];no_proposal=[]
    for o in opens:
        tm=num(o.get("ts"));s=o.get("symbol");side_actual=side(o)
        nearby=[z for z in decisions if z["symbol"]==s and abs(z["ts"]-tm)<=15*60000]
        newopen=[z for z in nearby if z["action"] in ("OPEN_LONG","OPEN_SHORT")]
        opposite=[z for z in newopen if z["action"]=="OPEN_LONG" and side_actual=="SHORT" or
                                    z["action"]=="OPEN_SHORT" and side_actual=="LONG"]
        same=[z for z in newopen if z["action"]=="OPEN_SHORT" and side_actual=="SHORT" or
                                z["action"]=="OPEN_LONG" and side_actual=="LONG"]
        holds=[z for z in nearby if z["action"]=="HOLD"]
        bo=brief_open(o)
        if opposite:match_opposite.append({**bo,"deepseek":opposite[-1]["action"],
                                             "deepseek_accepted":opposite[-1]["accepted"],
                                             "deepseek_at":opposite[-1]["when"]})
        elif same:match_same.append({**bo,"deepseek":same[-1]["action"],
                                    "deepseek_accepted":same[-1]["accepted"]})
        elif holds:match_hold.append({**bo,"deepseek":"HOLD_for_virtual_position"})
        else:no_proposal.append(bo)
    cats=collections.Counter()
    closes_total=0
    for o in opens:
        cls=all_close.get(key_of(o),[])
        if not any(not z.get("partial") for z in cls):continue
        closes_total+=1
        net=sum(num(z.get("net")) or 0 for z in cls)
        cats["profit" if net>0 else "loss" if net<0 else "flat"]+=1
    bots[bot]={"opens_today":len(opens),"long":sum(side(x)=="LONG" for x in opens),
      "short":sum(side(x)=="SHORT" for x in opens),"sources":dict(by_source),
      "opens_pm":len(opens_pm),"pm_sl_closures":len(sls),
      "pm_sl_samples":[{"symbol":s.get("symbol"),
                        "closed_at":when(s.get("close_ms") or s.get("ts")),
                        "net_usd":round(num(s.get("net")) or 0,2)} for s in sls[-12:]],
      "trade_type_opens":dict(collections.Counter(str(x.get("trade_type") or "?") for x in opens)),
      "opens_finalized_asof_audit":closes_total,"opens_finalized_outcome":dict(cats),
      "same_symbol_15min_comparison":{"aligned":len(match_same),"opposite":len(match_opposite),
        "shadow_hold_same_symbol":len(match_hold),"no_explicit_open_or_hold":len(no_proposal),
        "opposite_examples":match_opposite[-15:],"aligned_examples":match_same[-9:]},
      "last_real_opens_pm":[brief_open(x) for x in opens_pm[-15:]]}
report("REAL_PAPER_VS_SHADOW",bots)
reads=[{"at":when(x.get("ts_ms")),"market_read":str((x.get("decision") or {}).get("market_read") or "")[:185]}
       for x in focus_cycles if (x.get("decision") or {}).get("market_read")]
report("SHADOW_MARKET_READS_PM",reads[-12:])
report("AUDIT_LIMITS",{"shadow_hold_is_for_virtual_positions":True,
 "zero_action_for_symbol_does_not_imply_skip":True,
 "shadow_account_differs_from_hawk_and_bull":True,
 "match_window_minutes":15,
 "realized_outcomes_for_closed_paper_trades_only":True,
 "no_counterfactual_profit_proof":True})
print("DEEPSEEK_DAY_READONLY_AUDIT_DONE",flush=True)
