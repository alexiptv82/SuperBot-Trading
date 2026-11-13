#!/usr/bin/env python3
"""Research-only Toro last Supertrend 15m/1h, fixed/preregistered study.

No secrets, trading APIs, journals, bot services or runtime changes.
Fetches public Bitget 15m candles via pinned RC84 helper and replays closed bars.
Historical output is ELIMINATION only; prior data already observed elsewhere.
"""
from __future__ import annotations

import argparse
import bisect
import csv
import hashlib
import json
import math
import os
import random
import statistics
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

M15 = 900_000
H1 = 3_600_000
H8 = 28_800_000
D1 = 86_400_000
START = 1_763_049_600_000  # 2025-11-13 16:00:00 UTC
END = 1_794_585_600_000    # 2026-11-13 16:00:00 UTC
# A typo in fixed times MUST be caught; never silently move the window.
CUTOFF_UTC = "2026-11-13T16:00:00+00:00"
SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
PREREG = "0c8471a8d189e09fbd7d3f39825a997f2c1cff65"
OUT = Path("/opt/superbot-toro-research/supertrend-last-20261113")
LIMIT_BARS = 48
RISK_PER_TRADE = 12.0
MAX_RISK_OPEN = 24.0
MARGIN_PER_TRADE = 200.0
RT_BP = 16.0
STRESS_BP = 30.0
FUND_BP_PER_8H = 1.0
RAND_SEEDS = 1000

@dataclass(frozen=True)
class Bar:
    t: int
    o: float
    h: float
    l: float
    c: float
    v: float

def say(**parts):
    print("TORO_ST_FINAL " + " ".join(f"{k}={v}" for k,v in parts.items()), flush=True)

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def utc(ms):
    return datetime.fromtimestamp(ms/1000, timezone.utc).isoformat()

def checks():
    fixed = int(datetime.fromisoformat(CUTOFF_UTC).timestamp()*1000)
    assert END == fixed, ("bad cutoff", END, fixed)
    assert END - START == 365*D1, ("bad history size", END-START)
    assert START%M15==END%M15==0

def bars_from_csv(path):
    bars=[]
    with path.open("r",newline="",encoding="utf-8") as f:
        reader=csv.DictReader(f)
        if reader.fieldnames != ["open_time_ms", "open", "high", "low", "close", "volume"]:
            raise ValueError("bad_CSV_header")
        previous = START-M15
        for row in reader:
            b=Bar(int(row["open_time_ms"]),*[float(row[k]) for k in ("open","high","low","close","volume")])
            if b.t != previous+M15:
                raise ValueError(f"gap_or_unsorted:{b.t}:{previous}")
            if not all(math.isfinite(v) for v in (b.o,b.h,b.l,b.c,b.v)):
                raise ValueError("invalid_nonfinite_OHLCV")
            if min(b.o,b.h,b.l,b.c)<=0 or b.v<0 or not (b.l<=min(b.o,b.c)<=max(b.o,b.c)<=b.h):
                raise ValueError("invalid_OHLCV")
            bars.append(b); previous=b.t
    if len(bars) != (END-START)//M15 or bars[0].t!=START or bars[-1].t != END-M15:
        raise ValueError(f"wrong_full_365d_coverage:{len(bars)}")
    return bars

def get_bars(symbol):
    path=OUT/(symbol+"_15m.csv")
    if not path.exists():
        from backend.v3.lab_tools.fetch_candles import fetch_rows, write_csv
        say(event="FETCH_PUBLIC_BEGIN",symbol=symbol,expected=(END-START)//M15)
        rows=fetch_rows(symbol,START,END,candle_ms=M15,window_bars=200,max_requests=1200)
        if len(rows)!=(END-START)//M15:
            raise ValueError(f"public_data_incomplete:{symbol}:{len(rows)}")
        temp=path.with_suffix(".csv.partial")
        write_csv(temp,rows)
        os.replace(temp,path)
        say(event="FETCH_PUBLIC_SAVED",symbol=symbol,sha256=sha(path))
    if path.is_symlink() or not path.is_file():
        raise ValueError("invalid_file")
    result=bars_from_csv(path)
    say(event="DATA_GATE_PASS",symbol=symbol,bars=len(result),sha256=sha(path))
    return result,sha(path)

def calc_atr(bars,period):
    out=[float("nan")]*len(bars)
    if len(bars)<=period:
        return out
    true=[float("nan")]
    for i in range(1,len(bars)):
        a,b=bars[i],bars[i-1]
        true.append(max(a.h-a.l,abs(a.h-b.c),abs(a.l-b.c)))
    val=sum(true[1:period+1])/period
    out[period]=val
    for i in range(period+1,len(bars)):
        val=((period-1)*val+true[i])/period
        out[i]=val
    return out

def supertrend(bars,period=10,mult=3.0):
    a=calc_atr(bars,period)
    up=[float("nan")]*len(bars)
    low=[float("nan")]*len(bars)
    line=[float("nan")]*len(bars)
    direction=[0]*len(bars)
    for i in range(period,len(bars)):
        bb=(bars[i].h+bars[i].l)*0.5
        basic_u=bb+mult*a[i]
        basic_l=bb-mult*a[i]
        if i==period:
            up[i],low[i]=basic_u,basic_l
            direction[i]=1 if bars[i].c>=bb else -1
        else:
            up[i]=basic_u if basic_u<up[i-1] or bars[i-1].c>up[i-1] else up[i-1]
            low[i]=basic_l if basic_l>low[i-1] or bars[i-1].c<low[i-1] else low[i-1]
            if direction[i-1]==1:
                direction[i]=-1 if bars[i].c<low[i-1] else 1
            else:
                direction[i]=1 if bars[i].c>up[i-1] else -1
        line[i]=low[i] if direction[i]==1 else up[i]
    return direction,line

def rsi_wilder(bars,period=14):
    result=[float("nan")]*len(bars)
    if len(bars)<=period:
        return result
    gains=[max(0,bars[i].c-bars[i-1].c) for i in range(1,len(bars))]
    losses=[max(0,bars[i-1].c-bars[i].c) for i in range(1,len(bars))]
    avgg=sum(gains[:period])/period
    avgl=sum(losses[:period])/period
    for i in range(period,len(bars)):
        if i>period:
            avgg=(avgg*(period-1)+gains[i-1])/period
            avgl=(avgl*(period-1)+losses[i-1])/period
        result[i]=50.0 if avgg==0 and avgl==0 else (100.0 if avgl==0 else 100-100/(1+avgg/avgl))
    return result

def ema200(bars):
    out=[]
    val=None
    alpha=2/201
    for b in bars:
        val=b.c if val is None else alpha*b.c+(1-alpha)*val
        out.append(val)
    return out

def make_hourly(bars):
    groups=defaultdict(list)
    for b in bars:
        groups[(b.t//H1)*H1].append(b)
    hourly=[]
    for ts in sorted(groups):
        group=groups[ts]
        if len(group)!=4 or [b.t for b in group]!=[ts,ts+M15,ts+2*M15,ts+3*M15]:
            raise ValueError("missing_or_incomplete_hour")
        hourly.append(Bar(ts,group[0].o,max(b.h for b in group),
                          min(b.l for b in group),group[-1].c,sum(b.v for b in group)))
    return hourly

def signal_candidates(symbol,bars):
    hourly=make_hourly(bars)
    st15,stline=supertrend(bars)
    st1,_=supertrend(hourly)
    atr14=calc_atr(bars,14)
    ema=ema200(bars)
    rsi=rsi_wilder(bars)
    h_ends=[b.t+H1 for b in hourly]
    volsum=[0.0]
    for b in bars:
        volsum.append(volsum[-1]+b.v)
    long_candidates=[]
    counts=Counter()
    regime_eligible=[]
    for i in range(250,len(bars)-1):
        moment=bars[i].t+M15
        h=bisect.bisect_right(h_ends,moment)-1
        if h<50 or st1[h]!=1 or st15[i]==0 or not math.isfinite(atr14[i]):
            continue
        regime_eligible.append(i)
        counts["eligible_1h_up"]+=1
        if not (st15[i-1]==-1 and st15[i]==1):
            continue
        counts["st_flip"]+=1
        if not (bars[i].c>ema[i] and 45<=rsi[i]<=75):
            continue
        counts["ema_rsi"]+=1
        last20=(volsum[i]-volsum[i-20])/20
        if last20<=0 or bars[i].v < 1.2*last20:
            continue
        counts["volume_confirmed"]+=1
        enter=bars[i+1].o
        stop=stline[i]-.25*atr14[i]
        if not (0<stop<enter):
            counts["invalid_stop"]+=1
            continue
        r=(enter-stop)/enter
        if not math.isfinite(r) or r<=0:
            counts["invalid_stop"]+=1
            continue
        meta={"symbol":symbol,"signal_ts":bars[i].t+M15,
              "signal_index":i,"entry_ts":bars[i+1].t,"entry_index":i+1,
              "entry":enter,"stop":stop,"R_price":enter-stop,
              "risk_fraction":r,"st15":stline[i],
              "st1h_end_ts":h_ends[h],"rsi":rsi[i],"ema200":ema[i],
              "vol_ratio":bars[i].v/last20,"atr14":atr14[i]}
        if meta["st1h_end_ts"]>meta["signal_ts"]:
            raise AssertionError("LOOKAHEAD_1H")
        long_candidates.append(meta)
    return long_candidates,counts,regime_eligible

def funding_events(start,end):
    return end//H8-start//H8

def exit_sim(bars,e,entry,stop):
    target=entry+2*(entry-stop)
    if not (stop<entry<target):
        raise ValueError("invalid_entry_stop_target")
    best=-float("inf");worst=float("inf")
    last=min(e+LIMIT_BARS-1,len(bars)-1)
    for j in range(e,last+1):
        b=bars[j]
        best=max(best,b.h)
        worst=min(worst,b.l)
        if b.o<=stop:
            price=b.o;reason="stop_gap"
        elif b.l<=stop:
            price=stop;reason="stop"
        elif b.h>target*(1+0.0001):
            price=target;reason="target_2R"
        else:
            continue
        return j,price,reason,(best-entry)/entry,(worst-entry)/entry
    return last,bars[last].c,"time_12h" if last==e+LIMIT_BARS-1 else "end_of_data",(best-entry)/entry,(worst-entry)/entry

def realized_trade(candidate,bars):
    e=candidate["entry_index"]
    entry=candidate["entry"]
    stop=candidate["stop"]
    end_index,price,reason,mfe,mae=exit_sim(bars,e,entry,stop)
    end_ms=bars[end_index].t+M15
    gross_bp=10000*(price/entry-1)
    fee_funding_bp=funding_events(candidate["entry_ts"],end_ms)*FUND_BP_PER_8H
    riskfrac=candidate["risk_fraction"]
    # Cost-aware notional so worst-case planned stop+round trip costs <=12 USDT.
    notional=min(MARGIN_PER_TRADE*45,RISK_PER_TRADE/(riskfrac+RT_BP/10000+0.0003))
    margin=min(MARGIN_PER_TRADE,notional)
    leverage=notional/margin
    result=dict(candidate)
    result.update({"exit_ts":end_ms,"exit_price":price,"exit_reason":reason,
                   "MFE_fraction":mfe,"MAE_fraction":mae,"gross_bp":gross_bp,
                   "funding_bp":fee_funding_bp,"fee_slippage_bp":RT_BP,
                   "net_bp":gross_bp-RT_BP-fee_funding_bp,
                   "stress_net_bp":gross_bp-STRESS_BP-fee_funding_bp,
                   "notional_usdt":notional,"margin_usdt":margin,
                   "leverage":leverage,"profit_usdt":notional*(gross_bp-RT_BP-fee_funding_bp)/10000})
    return result

def random_matched(trades,assets,eligible,seed_count=1000):
    # Same symbol/month and 1H UP, same trade stop distance, 2R target and costs.
    indices={}
    for sym in SYMBOLS:
        d=defaultdict(list)
        bars=assets[sym]
        for i in eligible[sym]:
            key=datetime.fromtimestamp(bars[i+1].t/1000,timezone.utc).strftime("%Y-%m")
            d[key].append(i)
        indices[sym]=d
    pool=[]
    for t in trades:
        month=datetime.fromtimestamp(t["entry_ts"]/1000,timezone.utc).strftime("%Y-%m")
        candidates=indices[t["symbol"]].get(month,[])
        if not candidates:
            raise RuntimeError("no_matched_random_hour")
        pool.append((t,candidates))
    rand=random.Random(971113)
    distribution=[]
    for _ in range(seed_count):
        total=0.0
        for original,options in pool:
            bars=assets[original["symbol"]]
            i=options[rand.randrange(len(options))]
            e=i+1
            entry=bars[e].o
            stop=entry*(1-original["risk_fraction"])
            end,price,why,mfe,mae=exit_sim(bars,e,entry,stop)
            gross=10000*(price/entry-1)
            cost=funding_events(bars[e].t,bars[end].t+M15)*FUND_BP_PER_8H
            total+=gross-RT_BP-cost
        distribution.append(total/len(pool) if pool else float("nan"))
    distribution.sort()
    return {"draws":len(distribution),
            "random_seed":971113,
            "distribution_bp":distribution,
            "median_bp":distribution[len(distribution)//2] if distribution else None,
            "p95_bp":distribution[int((len(distribution)-1)*0.95)] if distribution else None}

def stats(trades,costkey="net_bp"):
    if not trades:
        return {"n":0,"avg_bp":None,"profit_factor":None,"total_usdt":0}
    vals=[t[costkey] for t in trades]
    pos=sum(x for x in vals if x>0)
    loss=-sum(x for x in vals if x<0)
    return {"n":len(trades),"avg_bp":statistics.mean(vals),
            "profit_factor":(pos/loss if loss>0 else None),
            "total_usdt":sum(t["profit_usdt"] for t in trades),
            "win_pct":100*sum(x>0 for x in vals)/len(vals)}

def save_atomic(path,obj):
    raw=(json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+"\n").encode()
    temp=path.with_name(path.name+f".{os.getpid()}.tmp")
    with temp.open("xb") as f:
        f.write(raw);f.flush();os.fsync(f.fileno())
    os.replace(temp,path)

def do_replay():
    checks()
    if not OUT.is_dir():OUT.mkdir(parents=True)
    if (OUT/"report.json").exists():
        say(result="BLOCK",reason="prior_final_report_exists");return 2
    assets={};hashes={};candidates=[];eligible={};signals={}
    for sym in SYMBOLS:
        bars,digest=get_bars(sym)
        assets[sym]=bars;hashes[sym]=digest
        raw,counts,regime=signal_candidates(sym,bars)
        candidates.extend(raw);eligible[sym]=regime
        signals[sym]=dict(counts)
        say(event="SIGNAL_SCAN",symbol=sym,raw=len(raw),denied=dict(counts))
    # Global portfolio: overlapping positions count toward aggregate risk.
    active=[];last_by_symbol={};trades=[];rejections=Counter()
    for row in sorted(candidates,key=lambda x:(x["entry_ts"],x["symbol"])):
        now=row["entry_ts"]
        active=[a for a in active if a["exit_ts"]>now]
        if any(a["symbol"]==row["symbol"] for a in active):
            rejections["same_asset_open"]+=1;continue
        if (len(active)>=5 or len(active)*RISK_PER_TRADE+RISK_PER_TRADE>MAX_RISK_OPEN+1e-9):
            rejections["aggregate_risk"]+=1;continue
        trade=realized_trade(row,assets[row["symbol"]])
        trades.append(trade);active.append(trade)
    mean_total=stats(trades)
    # The historical replay uses close-only drawdown; not a certified mark-to-market.
    # In particular this estimate may UNDERSTATE worst intrabar loss and is NOT a GO.
    equity=1000;peak=equity;maxdd=0.0
    for t in sorted(trades,key=lambda x:x["exit_ts"]):
        equity+=t["profit_usdt"];peak=max(peak,equity)
        maxdd=max(maxdd,(peak-equity)/peak if peak>0 else 1.0)
    total_stress=statistics.mean(t["stress_net_bp"] for t in trades) if trades else None
    split=START+(END-START)*2//3
    first=stats([t for t in trades if t["signal_ts"]<split])
    final=stats([t for t in trades if t["signal_ts"]>=split])
    by_sym={s:stats([t for t in trades if t["symbol"]==s]) for s in SYMBOLS}
    rand=random_matched(trades,assets,eligible,RAND_SEEDS) if trades else None
    frequency=Counter(datetime.fromtimestamp(t["entry_ts"]/1000,timezone.utc).strftime("%Y-%m") for t in trades)
    signal_frequency=Counter(datetime.fromtimestamp(t["signal_ts"]/1000,timezone.utc).strftime("%Y-%m") for t in candidates)
    # Explicitly include every month even when no setup occurs.
    allmonths=[]
    year,month=2025,11
    while (year,month)<=(2026,11):
        allmonths.append(f"{year:04d}-{month:02d}")
        month+=1
        if month>12:
            year+=1;month=1
    overall_profit=sum(t["profit_usdt"] for t in trades)
    positive_symbols=sum(v["n"]>0 and v["avg_bp"]>0 for v in by_sym.values())
    contrib={s:max(0,v["total_usdt"]) for s,v in by_sym.items()}
    total_contrib=sum(contrib.values())
    max_contrib=max(contrib.values())/total_contrib if total_contrib>0 else 1.0
    checks_dict={
        "min150_and_last50":len(trades)>=150 and final["n"]>=50,
        "expectancy_all_periods_positive":all(isinstance(v["avg_bp"],(int,float)) and v["avg_bp"]>0 for v in (mean_total,first,final)),
        "profit_factor_over115":mean_total["profit_factor"] is not None and mean_total["profit_factor"]>1.15,
        # NO claim a full-pair MTM DD: fail closed until separately validated.
        "mark_to_market_dd_under15_verified":False,
        "positive_3of5_and_not_concentrated":positive_symbols>=3 and max_contrib<=0.50,
        "above_random_p95":bool(rand and mean_total["avg_bp"]>rand["p95_bp"]),
        "stress_cost30bp_positive":total_stress is not None and total_stress>0,
        # testing only routine, independent verifier required before GO
        "independent_incremental_lookahead_test":False,
    }
    report={"classification":"HISTORICAL_ELIMINATION_ONLY_NOT_TRUE_OOS",
            "prereg_commit":PREREG,"time_start":utc(START),"time_end_excl":utc(END),
            "data_sha256":hashes,
            "params":{"st_atr":10,"st_multiplier":3,"rsi":14,"ema":200,
                      "volume_prev":20,"volume_ratio":1.2,"max_hold_bars":48,
                      "stop_atr_buffer":0.25,"takeprofit_R":2.0,
                      "cost_rt_bp":RT_BP,"funding_per_8h":FUND_BP_PER_8H,
                      "stress_cost_rt_bp":STRESS_BP,"random_draws":RAND_SEEDS},
            "raw_signals":signals,"rejections":dict(rejections),
            "summary":mean_total,"first_2_3":first,"last_1_3":final,
            "by_symbol":by_sym,"closed_equity_drawdown":maxdd,
            "closed_equity_drawdown_not_MTM":True,
            "random_matched":rand,"stress_avg_bp":total_stress,
            "monthly_trades":{month:frequency[month] for month in allmonths},
            "monthly_raw_signals":{month:signal_frequency[month] for month in allmonths},
            "all_accepted_trades":trades,"pass_checks":checks_dict,
            "historical_go":False,
            "next":"A PASS is impossible without independently audited mark-to-market DD, "
                   "incremental asof tests, fill model and 30d forward shadow."}
    save_atomic(OUT/"report.json",report)
    say(event="REPLAY_COMPLETE",trades=len(trades),
        avg_net_bp=round(mean_total["avg_bp"],4) if mean_total["n"] else "NA",
        profit_factor=round(mean_total["profit_factor"],4) if mean_total["profit_factor"] is not None else "NA",
        drawdown_close_only=round(maxdd,4),random_p95_bp=round(rand["p95_bp"],4) if rand else "NA",
        stress30_avg_bp=round(total_stress,4) if total_stress is not None else "NA")
    say(result="NO_AUTOMATIC_GO",critical_checks_met=sum(bool(x) for x in checks_dict.values()),
        critical_checks=len(checks_dict),report=OUT/"report.json",paper_orders=0,no_bot_changes=1)
    return 0

def self_test():
    checks()
    ts=START
    vals=[100+i*0.04+0.5*math.sin(i/9.0) for i in range(800)]
    a=[Bar(ts+i*M15,v,v+0.3,v-0.3,v,1000+i%7) for i,v in enumerate(vals)]
    b15,l15=supertrend(a)
    b_part,l_part=supertrend(a[:610])
    assert b15[:610]==b_part
    assert all((math.isnan(x) and math.isnan(y)) or x==y for x,y in zip(l15[:610],l_part))
    hour=make_hourly(a)
    assert len(hour)==200
    assert hour[0].t==START and hour[-1].t+H1==START+len(a)*M15
    # STOP beats TP even if both cross in one candle.
    entry=100;stop=99
    bars=[Bar(ts,entry,105,98,103,1000)]
    j,p,why,mfe,mae=exit_sim(bars,0,entry,stop)
    assert why=="stop" and p==99
    bars=[Bar(ts,98,105,97,103,1000)]
    j,p,why,mfe,mae=exit_sim(bars,0,entry,stop)
    assert why=="stop_gap" and p==98
    assert funding_events(ts,ts+8*H1)==1
    assert rsi_wilder(a)[25]>0
    assert len(signal_candidates("BTCUSDT",a)[1])>=0
    say(synthetic_tests="PASS",no_network=1)
    return 0

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--self-test",action="store_true")
    args=p.parse_args()
    sys.exit(self_test() if args.self_test else do_replay())
