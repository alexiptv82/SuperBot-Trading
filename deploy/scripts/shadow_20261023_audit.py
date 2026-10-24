#!/usr/bin/env python3
"""Read only: 23 Oct 2026 shadow DeepSeek and real PAPER trade audit (UTC)."""
import os,sys,json,time,gzip,datetime as dt,collections
DAY="2026-10-23"; ROOT="/opt/superbot-desk-data"; AI="/opt/superbot-ai-data/ai"
LO=int(dt.datetime(2026,10,23,tzinfo=dt.timezone.utc).timestamp()*1000); HI=LO+86400000
NOW=int(time.time()*1000); H24=NOW-86400000
def load(path,zip=False):
    rows=[];bad=0
    if not os.path.isfile(path): return [],0,False
    try:
        with (gzip.open(path,"rt") if zip else open(path,encoding="utf8")) as f:
            for line in f:
                if not line.strip():continue
                try:
                    x=json.loads(line)
                    if isinstance(x,dict): rows.append(x)
                    else: bad+=1
                except ValueError:bad+=1
    except (OSError,EOFError):bad+=1
    return rows,bad,True
def json_file(path):
    try:
        with open(path) as f:return json.load(f)
    except (OSError,ValueError):return {}
def n(v):
    try:return float(v or 0)
    except (ValueError,TypeError):return 0.
def t(r):
    return int(r.get("ts_ms") or r.get("ts") or r.get("close_ms") or r.get("bar_t") or 0)
def ct(r):
    return int(r.get("close_ms") or r.get("ts") or 0)
def side(r):
    s=r.get("side");return "LONG" if str(s) in ("1","LONG","buy") else "SHORT" if str(s) in ("-1","SHORT","sell") else "?"
def stamp(ms):
    return dt.datetime.fromtimestamp(int(ms)/1000,dt.timezone.utc).strftime("%d/%m %H:%M") if ms else "?"
def period(rows,low,high):
    ops=[r for r in rows if r.get("ev")=="open" and low<=t(r)<high]
    cls=[r for r in rows if r.get("ev")=="close" and low<=ct(r)<high]
    fin=[r for r in cls if not r.get("partial")]
    osl=collections.Counter(side(r) for r in ops); csl=collections.Counter(side(r) for r in fin)
    return {"opens":len(ops),"long_open":osl["LONG"],"short_open":osl["SHORT"],
            "closes_final":len(fin),"partial_close_rows":len(cls)-len(fin),
            "long_closed":csl["LONG"],"short_closed":csl["SHORT"],
            "net_realized_usd":round(sum(n(r.get("net")) for r in cls),4),
            "symbols_open":dict(collections.Counter(r.get("symbol") for r in ops)),
            "symbols_close":dict(collections.Counter(r.get("symbol") for r in fin))}
def out(label,obj):
    print(label,json.dumps(obj,ensure_ascii=False,separators=(",",":")),flush=True)
def main():
    print("READ_ONLY_AUDIT day=2026-10-23 tz=UTC now="+stamp(NOW),flush=True)
    bots={}
    for bot in ("hawk","bull"):
        root=os.path.join(ROOT,bot)
        rows,bad,have=load(root+"/learning_log.jsonl")
        hist,hbad,hhave=load(root+"/trade_history.jsonl")
        state=json_file(root+"/state_v2.json"); hb=json_file(root+"/heartbeat.json")
        p=state.get("main",{}).get("positions",{})
        d=period(rows,LO,HI);rolling=period(rows,H24,NOW+1)
        out("BOT_META_"+bot,{"has_learning":have,"has_history":hhave,"learning_rows":len(rows),"history_rows":len(hist),
                            "bad_learning":bad,"bad_history":hbad,"version":hb.get("version"),"mode":hb.get("exec_mode"),
                            "current_open":len(p),"current_long":sum(side(x)=="LONG" for x in p.values()),
                            "current_short":sum(side(x)=="SHORT" for x in p.values()),
                            "current_symbols":{sym:side(x) for sym,x in p.items()},
                            "history_day_close_rows":sum(LO<=ct(x)<HI for x in hist),
                            "history_day_net":round(sum(n(x.get("net")) for x in hist if LO<=ct(x)<HI),4)})
        out("BOT_DAY_"+bot,d);out("BOT_24H_"+bot,rolling)
        out("BOT_DAY_ACTIONS_"+bot,{"opens":[{"t":stamp(t(r)),"symbol":r.get("symbol"),"side":side(r)} for r in rows if r.get("ev")=="open" and LO<=t(r)<HI],
              "closes":[{"t":stamp(ct(r)),"symbol":r.get("symbol"),"side":side(r),"net":round(n(r.get("net")),3),"partial":bool(r.get("partial"))} for r in rows if r.get("ev")=="close" and LO<=ct(r)<HI]})
        bots[bot]=rows
    status=json_file(AI+"/status.json")
    cycles,bad,has=load(AI+"/cycles-"+DAY+".jsonl")
    prompts,pbad,phas=load(AI+"/prompts-"+DAY+".jsonl.gz",True)
    trades,tbad,thas=load(AI+"/trades-"+DAY+".jsonl")
    out("SHADOW_META",{"current_mode":status.get("mode"),"current_applied":status.get("applied"),
         "has_cycles":has,"cycles_rows":len(cycles),"cycles_bad":bad,
         "has_prompts":phas,"prompts_rows":len(prompts),"prompts_bad":pbad,
         "has_virtual_trades":thas,"virtual_trades":len(trades),"virtual_net":round(sum(n(x.get("net")) for x in trades),3)})
    cycles=[c for c in cycles if LO<=t(c)<HI]
    called=[c for c in cycles if c.get("decision",{}).get("called")]
    responded=[c for c in called if c.get("decision",{}).get("n_items") is not None and not c.get("decision",{}).get("parse_error")]
    out("SHADOW_CYCLES",{"cycles":len(cycles),"calls":len(called),"model_responses":len(responded),
         "skips":dict(collections.Counter(c["decision"]["skip"] for c in cycles if c.get("decision",{}).get("skip"))),
         "errors":dict(collections.Counter(c["decision"]["error"] for c in called if c.get("decision",{}).get("error"))),
         "recorded_choices":sum(int(c.get("decision",{}).get("n_items") or 0) for c in responded)})
    mapped={c.get("bar_t"):c for c in called}
    picks=[]; parsebad=0
    for rec in prompts:
        bar=rec.get("bar_t",0); cyc=mapped.get(bar)
        at=t(cyc) if cyc else bar+900000
        if not LO<=at<HI:continue
        response=str(rec.get("response",""));a=response.find("{");b=response.rfind("}")
        try: doc=json.loads(response[a:b+1])
        except (ValueError,TypeError):parsebad+=1;continue
        if not isinstance(doc,dict) or not isinstance(doc.get("decisions"),list):parsebad+=1;continue
        used=set()
        results=(cyc or {}).get("decision",{}).get("results") or []
        for item in doc["decisions"]:
            if not isinstance(item,dict):continue
            symbol=str(item.get("symbol") or "").upper().replace("USDT","")
            action=str(item.get("action") or "").upper()
            rr={}
            for i,r in enumerate(results):
                if i not in used and r.get("symbol")==symbol and r.get("action")==action:rr=r;used.add(i);break
            picks.append({"ms":at,"t":stamp(at),"sym":symbol,"action":action,
                          "conviction":item.get("conviction"),"accepted":rr.get("accepted"),"reason":rr.get("reason"),
                          "thesis":str(item.get("thesis") or "").replace("\n"," ")[:100]})
    cc=collections.Counter(x["action"] for x in picks)
    accepted=collections.Counter(x["action"] for x in picks if x["accepted"] is True)
    rejected=collections.Counter(x["reason"] for x in picks if x["accepted"] is False)
    out("SHADOW_PICKS_SUMMARY",{"decisions":len(picks),"actions":dict(cc),"accepted":dict(accepted),
        "rejected":dict(rejected),"prompt_parse_errors":parsebad})
    out("SHADOW_PICKS_DETAIL",picks[:130])
    out("SHADOW_MARKET_READS",[{"t":stamp(t(c)),"read":str(c["decision"].get("market_read") or "")[:160]} for c in called if c.get("decision",{}).get("market_read")][-6:])
    for bot,rows in bots.items():
        events=[r for r in rows if r.get("ev") in ("open","close") and LO<=t(r)<HI]
        comp=[]
        for d in picks:
            if d["action"] not in ("OPEN_LONG","OPEN_SHORT","CLOSE","PARTIAL_CLOSE"):continue
            same_symbol=[r for r in events if r.get("symbol")==d["sym"] and abs(t(r)-d["ms"])<=3600000]
            yes=[r for r in same_symbol if
                 (d["action"]=="OPEN_LONG" and r.get("ev")=="open" and side(r)=="LONG") or
                 (d["action"]=="OPEN_SHORT" and r.get("ev")=="open" and side(r)=="SHORT") or
                 (d["action"] in ("CLOSE","PARTIAL_CLOSE") and r.get("ev")=="close")]
            no=[r for r in same_symbol if
                 (d["action"]=="OPEN_LONG" and r.get("ev")=="open" and side(r)=="SHORT") or
                 (d["action"]=="OPEN_SHORT" and r.get("ev")=="open" and side(r)=="LONG")]
            verdict="aligned" if yes else "opposite" if no else "no_same_symbol_action"
            comp.append({"when":d["t"],"sym":d["sym"],"action":d["action"],"result":verdict,"shadow_accepted":d["accepted"]})
        summary=collections.Counter(x["result"] for x in comp)
        out("COMPARISON_"+bot,{"window_minutes":60,"actions_compared":len(comp),
             "aligned":summary["aligned"],"opposite":summary["opposite"],"not_comparable":summary["no_same_symbol_action"],
             "matches":[x for x in comp if x["result"]!="no_same_symbol_action"][:55]})
    print("AUDIT_COMPLETE_2026_10_23",flush=True)
if __name__=="__main__":main()
