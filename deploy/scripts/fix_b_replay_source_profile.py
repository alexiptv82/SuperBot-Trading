#!/usr/bin/env python3
"""Fix B source completeness profile. VPS read-only, do not print private rows."""
import collections,datetime as dt,glob,json,os
ROOT="/opt/superbot-desk-data"; SIDE="/opt/superbot-sidecar-data"
START=int(dt.datetime(2026,10,10,tzinfo=dt.timezone.utc).timestamp()*1000)
END=int(dt.datetime(2026,10,24,tzinfo=dt.timezone.utc).timestamp()*1000)
def records(p):
    rows=[];bad=0
    if not os.path.isfile(p):return rows,0
    with open(p,encoding="utf8") as f:
        for line in f:
            try:
                x=json.loads(line)
                if isinstance(x,dict):rows.append(x)
            except ValueError:bad+=1
    return rows,bad
def stamp(ms):
    try:return dt.datetime.fromtimestamp(float(ms)/1000,dt.timezone.utc).strftime("%Y-%m-%d")
    except (TypeError,ValueError,OverflowError):return "?"
def ts(r):
    return r.get("ts") or r.get("close_ms") or r.get("open_ms") or 0
def info(bot):
    base=os.path.join(ROOT,bot)
    logs,bad=records(base+"/learning_log.jsonl")
    history,hbad=records(base+"/trade_history.jsonl")
    inrange=[r for r in logs if START<=ts(r)<END]
    op=[r for r in inrange if r.get("ev")=="open"]
    close=[r for r in inrange if r.get("ev")=="close"]
    def field_summary(arr):return dict(collections.Counter(k for row in arr for k in row).most_common(80))
    def date_group(arr):return dict(sorted(collections.Counter(stamp(ts(r)) for r in arr).items()))
    def sample_meta(arr):
        if not arr:return {}
        row=arr[0]
        return {k:type(v).__name__ for k,v in row.items()}
    print("BOT",bot,"ROWS",len(logs),"INVALID",bad,"HISTORY",len(history),"HIST_INVALID",hbad)
    print("BOT",bot,"DAYS_OPEN",json.dumps(date_group(op),sort_keys=True))
    print("BOT",bot,"DAYS_CLOSE",json.dumps(date_group(close),sort_keys=True))
    print("BOT",bot,"OPEN_KEYS",json.dumps(field_summary(op),sort_keys=True))
    print("BOT",bot,"CLOSE_KEYS",json.dumps(field_summary(close),sort_keys=True))
    print("BOT",bot,"HIST_KEYS",json.dumps(field_summary(history),sort_keys=True))
    print("BOT",bot,"OPEN_TYPE",json.dumps(sample_meta(op),sort_keys=True))
    print("BOT",bot,"CLOSE_TYPE",json.dumps(sample_meta(close),sort_keys=True))
    print("BOT",bot,"HIST_TYPE",json.dumps(sample_meta(history),sort_keys=True))
    print("BOT",bot,"EVENTS",json.dumps(dict(collections.Counter(r.get("ev") for r in inrange)),sort_keys=True))
    for k in ("mfe_r","roi_net_pct","mfe_roi_pct","peak_roi_net_pct","margin","risk_plan_usd","entry","qty","leverage","total_margin","fee_open"):
        a=[r.get(k) for r in close if r.get(k) is not None]
        numeric=[float(x) for x in a if isinstance(x,(int,float))]
        print("BOT",bot,"FIELD",k,"count",len(a),"numeric",len(numeric),"over20",sum(v>=20 for v in numeric))
    paths=[os.path.basename(x) for x in glob.glob(base+"/*") if os.path.isfile(x)]
    print("BOT",bot,"FILES",json.dumps(sorted(paths)[:75]))
for bot in ("hawk","bull"):info(bot)
for bot in ("hawk","bull"):
    p=os.path.join(SIDE,bot)
    print("SIDECAR",bot,"FILES",json.dumps(sorted(os.path.basename(x) for x in glob.glob(p+"/*"))[:45]))
print("SOURCE_PROFILE_COMPLETE")
