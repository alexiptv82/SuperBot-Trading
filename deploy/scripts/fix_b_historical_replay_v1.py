#!/usr/bin/env python3
"""Fix B Fase 1: point-in-time historical evidence replay, NO trades/AI/network/writes.
2026-10-10T00:00Z <= final CLOSE < 2026-10-24T00:00Z (14 completed UTC days).
Strictly separates recorded ROI >=20% from a candle-extrema MFE upper bound.
Prudent scenario values are NOT Claude outputs, trade fills, or an alert backtest.
"""
from __future__ import annotations
import collections, datetime as dt, glob, json, math, os

D=dt.timezone.utc
START=int(dt.datetime(2026,10,10,tzinfo=D).timestamp()*1000)
END=int(dt.datetime(2026,10,24,tzinfo=D).timestamp()*1000)
BOTROOT="/opt/superbot-desk-data"
SIDEROOT="/opt/superbot-sidecar-data"
TRESH=20.0
def num(v):
    if isinstance(v,bool):return None
    try:
        x=float(v)
        return x if math.isfinite(x) else None
    except (ValueError,TypeError):return None
def timestamp(v):
    x=num(v)
    return int(x) if x is not None and x>=0 else 0
def date(t):
    return dt.datetime.fromtimestamp(t/1000,tz=D).strftime("%Y-%m-%d %H:%M") if t else "?"
def load_rows(path):
    rows=[];bad=0
    try:
        with open(path,encoding="utf-8") as f:
            for ln in f:
                try:
                    x=json.loads(ln)
                    if isinstance(x,dict):rows.append(x)
                    else:bad+=1
                except ValueError:bad+=1
    except OSError: return None,0
    return rows,bad
def key(row):
    if row.get("run_no") is None or row.get("id") is None:return None
    return (str(row["run_no"]),str(row["id"]))
def trade_history(bot):
    logs,bad=load_rows(f"{BOTROOT}/{bot}/learning_log.jsonl")
    hist,hbad=load_rows(f"{BOTROOT}/{bot}/trade_history.jsonl")
    if logs is None or hist is None or bad or hbad:raise RuntimeError("source_missing_or_corrupt_"+bot)
    opens,closes=collections.defaultdict(list),collections.defaultdict(list)
    for r in logs:
        if r.get("ev")=="open" and key(r):opens[key(r)].append(r)
        if r.get("ev")=="close" and key(r):closes[key(r)].append(r)
    out=[];excluded=collections.Counter()
    for k,cs in closes.items():
        finals=[r for r in cs if not r.get("partial")]
        if not any(START <= timestamp(r.get("close_ms") or r.get("ts")) < END for r in finals):
            continue
        if len(finals)!=1:
            excluded["missing_or_duplicate_final"]+=1;continue
        if len(opens[k])!=1:
            excluded["missing_or_duplicate_open"]+=1;continue
        o=opens[k][0];fin=finals[0]
        if o.get("symbol") != fin.get("symbol") or o.get("side") != fin.get("side"):
            excluded["symbol_or_side_conflict"]+=1;continue
        if timestamp(o.get("ts")) >= timestamp(fin.get("close_ms")):
            excluded["invalid_time"]+=1;continue
        if any((r.get("symbol"),r.get("side"))!=(fin.get("symbol"),fin.get("side")) for r in cs):
            excluded["component_conflict"]+=1;continue
        if any(num(r.get("net")) is None or num(r.get("margin")) is None for r in cs):
            excluded["missing_pnl_or_margin"]+=1;continue
        lifecycle_margin=sum(num(r["margin"]) for r in cs)
        if lifecycle_margin<=0:excluded["invalid_lifecycle_margin"]+=1;continue
        actual=sum(num(r["net"]) for r in cs)
        peak_candidates=[num(r.get("mfe_r")) for r in cs]
        peak_candidates=[v for v in peak_candidates if v is not None and v>=0]
        risk=num(o.get("risk_plan_usd"))
        # Upper bound gross, not proof of an available net exit; never count as true ROI crossing.
        bound=max(peak_candidates)*risk/lifecycle_margin*100 if peak_candidates and risk is not None and risk>0 else None
        is_plain=(len(cs)==1 and not fin.get("partial") and int(num(fin.get("dca_count")) or 0)==0 and int(num(fin.get("legs")) or 0)<=1 and not o.get("split_plan"))
        out.append({"key":k,"open":o,"final":fin,"closes":cs,"close_ms":timestamp(fin.get("close_ms")),
                    "open_ms":timestamp(o.get("ts")),"symbol":o.get("symbol"),
                    "side":o.get("side"),"margin":lifecycle_margin,"actual":actual,
                    "actual_roi_pct":actual/lifecycle_margin*100,"mfe_upper_bound_gross_roi_pct":bound,
                    "plain":is_plain,"has_partials":len(cs)>1,
                    "max_dca":int(num(fin.get("dca_count")) or 0),
                    "final_reason":str(fin.get("why") or "").strip().lower()})
    # Compare realized totals from trade_history within requested window against learning close events.
    a=sum(num(r["net"]) for r in logs if r.get("ev")=="close" and START<=timestamp(r.get("close_ms") or r.get("ts"))<END and num(r.get("net")) is not None)
    b=sum(num(r["net"]) for r in hist if START<=timestamp(r.get("close_ms"))<END and num(r.get("net")) is not None)
    return out,excluded,{"learning_rows":len(logs),"history_rows":len(hist),
                         "sum_learning_net":round(a,4),"sum_history_net":round(b,4),
                         "totals_match_within_one_cent":abs(a-b)<=.01}

def observed_positions(bot,closed):
    by_id={(str(x["key"][0]),str(x["key"][1]),x["symbol"],x["open_ms"]):x for x in closed}
    seen=collections.defaultdict(dict)
    summary=collections.Counter()
    coverage=collections.Counter()
    for path in sorted(glob.glob(f"{SIDEROOT}/{bot}/events-*.jsonl")):
        arr,bad=load_rows(path)
        if arr is None or bad:raise RuntimeError("sidecar_corrupt_"+bot)
        for line in arr:
            b=line.get("body") or {}
            if b.get("ev")!="cycle":continue
            asof=timestamp(b.get("asof_ms"))
            if not START<=asof<END:continue
            coverage[date(asof)[:10]]+=1
            rn=b.get("run_no")
            for rec in b.get("positions",[]):
                snap=rec.get("snapshot") or {}
                k=(str(rn),str(snap.get("id")),str(snap.get("symbol") or ""),timestamp(snap.get("open_ms")))
                # Some snapshots omit symbol in root; fallback to position key and require id/open_ms matching.
                if k not in by_id:
                    x=[a for a in by_id if a[0]==str(rn) and a[1]==str(snap.get("id")) and a[3]==timestamp(snap.get("open_ms"))]
                    if len(x)==1:k=x[0]
                if k not in by_id:summary["sidecar_no_matching_closed_trade"]+=1;continue
                tr=by_id[k]
                if not tr["open_ms"] < asof < tr["close_ms"]:continue
                if snap.get("ambiguous_order") is True or rec.get("frozen"):
                    summary["frozen_or_ambiguous_snapshot"]+=1;continue
                roi=rec.get("liquidable_now") or {}
                pct=num(roi.get("roi_pct"))
                net=num(roi.get("net_usd"))
                prudent=rec.get("prudent_exit") or {}
                conservative=num(prudent.get("net_usd"))
                if pct is None or net is None:
                    summary["missing_contemporaneous_net_roi"]+=1;continue
                if asof not in seen[k]:
                    seen[k][asof]={"at":asof,"roi_pct":pct,"net":net,"prudent":conservative}
    by_trade=collections.defaultdict(list)
    for k,at in seen.items():by_trade[k]=sorted(at.values(),key=lambda v:v["at"])
    return by_trade,summary,dict(sorted(coverage.items()))

def report(bot):
    allclosed,excluded,reconciliation=trade_history(bot)
    snapshots,bad,coverage=observed_positions(bot,allclosed)
    stats=collections.Counter()
    rows=[]
    for tr in allclosed:
        stats["completed_trades"]+=1
        grossbound=tr["mfe_upper_bound_gross_roi_pct"]
        if grossbound is not None:
            stats["mfe_gross_bound_available"]+=1
            if grossbound>=TRESH:stats["potential_20_gross_upper_bound"]+=1
        if tr["actual_roi_pct"]>=TRESH:stats["final_lifecycle_net_at_least_20"]+=1
        if "take profit" in tr["final_reason"]:stats["final_take_profit"]+=1
        k=(str(tr["key"][0]),str(tr["key"][1]),str(tr["symbol"]),tr["open_ms"])
        history=snapshots.get(k,[])
        if history:stats["completed_with_sidecar_observations"]+=1
        else:stats["completed_without_sidecar_observations"]+=1
        if not history:continue
        peak=max(x["roi_pct"] for x in history)
        hits=[s for s in history if s["roi_pct"]>=TRESH]
        if not hits:
            stats["sampled_but_not_at_20"]+=1
            continue
        stats["observed_reached_20"]+=1
        first=hits[0]
        peaknet=max(x["net"] for x in history)
        giveback_vs_peak=peaknet-tr["actual"]
        if giveback_vs_peak>.01:stats["observed_peak_net_given_back_vs_final"]+=1
        if tr["actual_roi_pct"] < 20:stats["final_net_roi_below_20"]+=1
        if "take profit" in tr["final_reason"]:
            stats["tp_reached_after_observed_20"]+=1
        stats["sum_baseline_net_cents"]+=round(tr["actual"]*100)
        stats["sum_signal_prudent_cents"]+=round((first["prudent"] if first["prudent"] is not None else first["net"])*100)
        if tr["plain"] and first["prudent"] is not None:
            stats["plain_with_prudent_signal"]+=1
            delta=first["prudent"]-tr["actual"]
            stats["plain_baseline_cents"]+=round(tr["actual"]*100)
            stats["plain_prudent_signal_cents"]+=round(first["prudent"]*100)
            stats["plain_full_exit_delta_cents"]+=round(delta*100)
            stats["plain_half_no_stop_delta_cents"]+=round(delta*50)
            if delta > .01:stats["plain_full_would_outperform"]+=1
            elif delta < -.01:stats["plain_full_would_underperform"]+=1
            else:stats["plain_close_neutral"]+=1
            if "take profit" in tr["final_reason"] and delta<-.01:
                stats["plain_early_close_false_positive_tp"]+=1
        else:
            stats["observed_threshold_excluded_from_scenario"]+=1
        rows.append({"trade":len(rows)+1,"symbol":tr["symbol"],"direction":"LONG" if tr["side"]==1 else "SHORT",
                     "observed_peak_roi_pct":round(peak,2),
                     "first20_at_utc":date(first["at"]),
                     "net_if_exit_now_prudent_usd":round(first["prudent"],2) if first["prudent"] is not None else None,
                     "baseline_actual_net_usd":round(tr["actual"],2),
                     "baseline_final_roi_pct":round(tr["actual_roi_pct"],2),
                     "last_exit":tr["final_reason"],"plain_no_dca_split_partial":tr["plain"],
                     "tp_reached_after_first20": "take profit" in tr["final_reason"],
                     "gave_back_observed_profit":giveback_vs_peak>.01})
    # Round trip vs signal isn't executable; no stops / next-bar fills / AI model calls reconstructed.
    clean={k:v for k,v in stats.items() if not k.endswith("_cents")}
    for k in sorted(stats):
        if k.endswith("_cents"):clean[k.replace("_cents","_usd")]=round(stats[k]/100,2)
    print("BOT_RESULT",bot,json.dumps({"range_utc":"2026-10-10..2026-10-23",
         "closed_trades":len(allclosed),"exclusions":dict(excluded),"coverage_sidecar_cycles_by_utc_day":coverage,
         "sidecar_reconstruction":dict(bad),"baseline_reconciliation":reconciliation,
         "metrics":clean,"cases_reached20":rows},
         ensure_ascii=False,separators=(",",":"),allow_nan=False))
    return clean

def main():
    x=report("hawk");y=report("bull")
    print("FIX_B_REPLAY_COMPLETE",flush=True)
if __name__=="__main__": main()
