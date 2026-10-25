#!/usr/bin/env python3
"""Bull ONLY: read Singapore PAPER state, lessons, last 30m logs and historical journals.
No edits, no trading calls, no bots stopped; never dump Docker env wholesale.
"""
import collections
import datetime as dt
import json
import math
import os
from pathlib import Path
import re
import subprocess
import time

now_ms=int(time.time()*1000)
window_ms=now_ms-30*60*1000
longer_ms=now_ms-120*60*1000
root=Path("/opt/superbot-desk-data/bull")
def read(path):
    with open(path,encoding="utf-8") as f:return f.read()
def obj(path):
    return json.loads(read(path))
def u(ms):
    try: 
        t=float(ms)
        if not math.isfinite(t) or t<=0:return None
        return dt.datetime.fromtimestamp(t/1000,dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (TypeError,ValueError,OverflowError,OSError):return None
def num(v):
    try:
        n=float(v)
        return n if math.isfinite(n) else None
    except (ValueError,TypeError):return None
def docker(*args):
    x=subprocess.run(["docker",*args],text=True,capture_output=True,timeout=22)
    if x.returncode:raise RuntimeError("docker "+args[0]+" failed")
    return x.stdout+x.stderr if args[0]=="logs" else x.stdout
def events(path):
    with open(path,encoding="utf-8") as f:
        for line in f:
            try:e=json.loads(line)
            except (ValueError,TypeError):continue
            if isinstance(e,dict):yield e
def evt_ms(v):
    kind=v.get("ev")
    if kind=="close":return num(v.get("close_ms") or v.get("ts"))
    if kind=="open":return num(v.get("ts") or v.get("open_ms"))
    return num(v.get("ts") or v.get("logged_ms"))
def record(label,payload):
    print(label,json.dumps(payload,ensure_ascii=False,separators=(",",":"),default=str),flush=True)

info=json.loads(docker("inspect","superbot-desk-bull"))[0]
env=dict(x.split("=",1) for x in info["Config"]["Env"] if "=" in x)
hb=obj(root/"heartbeat.json")
state=obj(root/"state_v2.json")
acc=state.get("main") or {}
positions=acc.get("positions") or {}
limits=acc.get("limits") or {}
prices=state.get("last_prices") or {}
price_age_s=(now_ms-(num(state.get("last_prices_ms")) or 0))/1000
value=sum((num(p.get("side")) or 0)*(num(prices.get(sym,p.get("entry"))) - num(p.get("entry")))*(num(p.get("qty")) or 0) for sym,p in positions.items() if num(prices.get(sym,p.get("entry"))) is not None and num(p.get("entry")) is not None)
equity=(num(acc.get("cash")) or 0)+sum((num(p.get("total_margin") or p.get("margin")) or 0) for p in positions.values())+value
start_equity=num(acc.get("day_start_equity"))
current_daily_stop=0.10 # pinned runtime 297b126 config, not stale disk limits.
halt=None
if equity<=450:halt="kill_equity"
elif start_equity is not None and equity<=start_equity*(1-current_daily_stop):halt="legacy_daily_stop_10pct"
cap=state.get("capital") or {}
budget=state.get("budget") or {}
status=info.get("State") or {}
record("BULL_RUNTIME",{
 "utc_checked":u(now_ms),"docker_status":status.get("Status"),
 "docker_health":(status.get("Health") or {}).get("Status"),"docker_started_utc":status.get("StartedAt"),
 "mode_env":env.get("DESK_MODE"),"capital_env":env.get("DESK_CAPITAL_V1"),
 "any_cooldown_env_keys":[k for k in env if k.startswith("DESK_") and ("COOLDOWN" in k or "STARTUP" in k)],
 "heartbeat_version":hb.get("version"),"heartbeat_capital_v1":hb.get("capital_v1"),
 "heartbeat_last_ok":hb.get("last_ok"),"heartbeat_last_error":str(hb.get("last_error") or "")[:160],
 "heartbeat_last_cycle_utc":u(hb.get("last_end_ms")),"heartbeat_cycles":hb.get("cycles"),
 "heartbeat_pause_requested":hb.get("pause_requested"),"heartbeat_trading_enabled":hb.get("trading_enabled"),
 "heartbeat_hours":{k:v for k,v in (hb.get("hours") or {}).items() if k in ("active","enabled","within_hours","blocked","reason","mode","now","current")},
 "pause_flag_exists":(root/"pause.flag").exists(),
 "code_max_open":6,"position_count":len(positions),"symbols":sorted(positions.keys()),
 "cash_usd":round(num(acc.get("cash")) or 0,2),
 "margin_committed_usd":round(sum((num(p.get("total_margin") or p.get("margin")) or 0) for p in positions.values()),2),
 "equity_usd_at_last_marks":round(equity,2),"day_start_equity_usd":start_equity,
 "legacy_daily_stop_pct":10,"effective_legacy_halt_estimate":halt,
 "price_age_s":round(price_age_s,1),"price_fresh_20m":0<=price_age_s<=1200,
 "capital_state_field":cap.get("status"),"capital_v1_effective":env.get("DESK_CAPITAL_V1")=="paper" and hb.get("capital_v1") is True,
 "ai_budget_spent_usd":budget.get("spent"),"ai_budget_day":budget.get("day"),
 "last_claude_call_utc":u(state.get("last_call_ms")),
 "macro_enforce_flag":(root/"macro_enforce.flag").exists(),
 "startup_cooldown_runtime_field":hb.get("startup_cooldown"),
})
lessons=read(root/"lessons.md")
marker="[LESSON-STARTUP-20261024]"
# Read-only brief proof: last diary headings and final note, but not unfiltered
# raw lessons which could contain externally supplied text.
lines=[s.strip() for s in lessons.splitlines() if s.strip()]
record("BULL_LESSONS",{
 "length_chars":len(lessons),
 "marker_present":marker in lessons,
 "marker_count":lessons.count(marker),
 "slot_empty_phrase_present":"Slot vuoto = scelta valida" in lessons,
 "target_70_80_present":("70–80%" in lessons or "70-80%" in lessons),
 "kpi_70_present":bool(re.search(r"(≥\s*70|70\s*[–-]\s*80)",lessons)),
 "lesson_in_actual_prompt_last1500":marker in lessons[-1500:],
 "slot_phrase_in_actual_prompt_last1500":"Slot vuoto = scelta valida" in lessons[-1500:],
 "target_in_actual_prompt_last1500":("70–80%" in lessons[-1500:] or "70-80%" in lessons[-1500:]),
 "last_headings":[v[:160] for v in lines if v.startswith("#")][-6:],
 "last_note_lines":[v[:170] for v in lines[-5:]],
})
# Only read the most recent 30 minutes; log scan returns allowlisted
# category labels/counts, not raw bot messages, secrets or model reasoning.
logtext=docker("logs","--since=30m","--timestamps","superbot-desk-bull")
logs=logtext.splitlines()
patterns={
 "cycle_candles":r"\[DESK V2\] candles ok",
 "claude_decisions":r"\[Claude\]\s+\d+ decisioni",
 "claude_window_blocked":r"\[FINESTRA\]",
 "rules_fallback":r"fuori dal calendario",
 "no_trade":r"\bno[_ -]?trade\b",
 "skip":r"\[SKIP\b|(?<!\w)skip(?!\w)",
 "score_low":r"\[CONF_LOW\]|score below threshold|conf_bassa",
 "rr_low":r"\[RR_LOW\]",
 "cooldown":r"\[COOLDOWN\]|cooldown",
 "capital_v1":r"capital_v1",
 "rollover":r"ROLLOVER|rollover",
 "halt":r"\[HALT\]|stop giornaliero raggiunto|capitale sotto la soglia minima",
 "macro_block":r"\[MACRO_BLOCCO\]",
 "macro_observe":r"\[MACRO_OSSERVATO\]",
 "pause":r"\[PAUSA\]",
 "hours_block":r"\[ORARI\]|fuori dagli orari",
 "warn":r"\[WARN\]",
 "error":r"\[ERROR\]|ERROR|Traceback|Exception|Fatal|critical",
 "open":r"\[OPEN\]|\[APER",
 "sleep":r"\[SLEEP\]",
}
counts={k:sum(bool(re.search(p,l,re.I)) for l in logs) for k,p in patterns.items()}
labels=[]
for line in logs:
    # Only recognized category prefix, never print unfiltered raw logs
    cats=[k for k,p in patterns.items() if re.search(p,line,re.I)]
    if any(k in cats for k in ("error","warn","halt","cooldown","score_low","skip","rr_low","macro_block","pause","hours_block")):
        labels.append({"time_utc":line[:30],"categories":cats})
record("BULL_LOGS",{
 "window_start_utc":u(window_ms),"window_end_utc":u(now_ms),
 "total_lines":len(logs),"categories":counts,"last_flagged_events":labels[-25:],
})
journal=list(events(root/"learning_log.jsonl"))
last_open=None
last_claude=None
recent_counts=collections.Counter()
recent_source=collections.Counter()
recent_status=collections.Counter()
last120_status=collections.Counter()
recent_cycle_ids=set()
recent_ev_samples=[]
for ev in journal:
    when=evt_ms(ev)
    if when is None:continue
    typ=ev.get("ev")
    if typ=="open" and (last_open is None or when>last_open[0]):
        last_open=(when,ev.get("symbol"),ev.get("source"))
    if typ=="claude_call" and (last_claude is None or when>last_claude[0]):
        last_claude=(when,bool(ev.get("ok")),ev.get("n_decisions"),ev.get("fail_reason"))
    if when>=longer_ms and typ=="candidate":last120_status[str(ev.get("status"))]+=1
    if when < window_ms or when>now_ms:continue
    if typ in ("open","candidate","claude_call","close"):recent_counts[typ]+=1
    if typ in ("open","candidate"):
        recent_source[str(ev.get("source") or "unknown")]+=1
    if typ=="candidate":
        recent_status[str(ev.get("status"))]+=1
        recent_ev_samples.append({"time_utc":u(when),"symbol":ev.get("symbol"),
                                   "status":str(ev.get("status"))[:90],
                                   "decision_source":ev.get("source")})
record("BULL_LEARNING",{
 "last_open_anytime":{"time_utc":u(last_open[0]),"symbol":last_open[1],"source":last_open[2]} if last_open else None,
 "last_claude_call":{"time_utc":u(last_claude[0]),"parsed_ok":last_claude[1],
                     "n_decisions":last_claude[2],"fail_reason":last_claude[3]} if last_claude else None,
 "last30min_event_counts":dict(recent_counts),
 "last30min_open_attempt_source_counts":dict(recent_source),
 "last30min_rejected_candidate_reasons":dict(recent_status),
 "last120min_rejected_candidate_reasons":dict(last120_status),
 "last30min_rejected_candidate_samples":recent_ev_samples[-18:],
 "explicit_no_trade_skip_decisions_logged":False,
 "count_interpretation":"candidate covers attempted entries that failed gates; Claude explicit skip/hold and rules without a candidate are NOT logged per opportunity",
})
th=list(events(root/"trade_history.jsonl"))
th5=th[-5:]
res=[]
for e in th5:
    res.append({
      "symbol":e.get("symbol"),
      "open_utc":u(e.get("open_ms")),
      "close_utc":u(e.get("close_ms")),
      "net_usd":round(num(e.get("net")) or 0,2) if e.get("net") is not None else None,
      "why":str(e.get("why") or e.get("reason") or "")[:100],
      "partial":e.get("partial") is True,
      "keys_no_open_reason":any(k in e for k in ("candidate","no_trade","skip","skip_reason"))
    })
record("BULL_TRADE_HISTORY",{
 "total_rows":len(th),"last5":res,"last5_contains_nonopen_reasons":any(x["keys_no_open_reason"] for x in res),
 "clarification":"trade_history is executed trade/close history, not a no-open decision journal",
})
print("BULL_READ_ONLY_DIAGNOSTIC_COMPLETE")
