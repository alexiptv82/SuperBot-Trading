#!/usr/bin/env python3
"""Read-only independent VPS health and capital readiness audit, no orders or mutation."""
import datetime as dt
import json
import os
import subprocess
import time
from pathlib import Path

NOW=int(time.time()*1000)
def docker(*args):
    x=subprocess.run(["docker",*args],capture_output=True,text=True,timeout=12)
    if x.returncode:raise RuntimeError("docker_read_failed:"+args[0])
    return x.stdout
def item(path):
    with open(path,encoding="utf8") as f:return json.load(f)
def relevant_errors(name):
    # Do not print raw bot logs, which can contain private context.
    raw=docker("logs","--since=20m","--tail=150",name)
    patterns=("Traceback","CapitalInvariantError","ROLLOVER_PENDING","RECONCILIATION_REQUIRED",
              "[CAPITAL]","[WARN]","[ERROR]","Exception","Ciclo","[SLEEP]")
    matches=[line for line in raw.splitlines() if any(p in line for p in patterns)]
    return {"count":len(matches),"categories":{p:sum(p in line for line in matches)
            for p in patterns if any(p in line for line in matches)}}
for bot in ("hawk","bull"):
    cname="superbot-desk-"+bot
    info=json.loads(docker("inspect",cname))[0]
    env=dict(t.split("=",1) for t in info["Config"]["Env"] if "=" in t)
    state=info["State"]
    hb=item("/opt/superbot-desk-data/"+bot+"/heartbeat.json")
    disk=item("/opt/superbot-desk-data/"+bot+"/state_v2.json")
    c=disk.get("capital")
    capital=c if isinstance(c,dict) else {}
    # Pure read: count journal opens/closes after last restart.
    starts=int(hb.get("started_ms") or 0)
    event_counts={"opens_since_restart":0,"closes_since_restart":0,"opens_last_30_min":0,"closes_last_30_min":0,"last_open_ms":None}
    journal=Path("/opt/superbot-desk-data/"+bot+"/learning_log.jsonl")
    if journal.is_file():
        with journal.open("r",encoding="utf-8") as stream:
            for raw in stream:
                try: ev=json.loads(raw)
                except (ValueError,TypeError):continue
                if not isinstance(ev,dict) or ev.get("ev") not in ("open","close"):continue
                ts=int(ev.get("ts") or ev.get("close_ms") or 0)
                if ev["ev"]=="open" and ts>=starts:
                    event_counts["opens_since_restart"]+=1
                    event_counts["last_open_ms"]=ts
                if ev["ev"]=="close" and ts>=starts:
                    event_counts["closes_since_restart"]+=1
                if ev["ev"]=="open" and NOW-30*60*1000<=ts<=NOW:
                    event_counts["opens_last_30_min"]+=1
                if ev["ev"]=="close" and NOW-30*60*1000<=ts<=NOW:
                    event_counts["closes_last_30_min"]+=1
    day=capital.get("day") or {}
    vault=capital.get("vault") or {}
    valuation=capital.get("valuation") or {}
    print("CAPITAL_READONLY_BOT",json.dumps({
      "bot":bot,"docker_status":state.get("Status"),"docker_running":state.get("Running"),
      "docker_health":(state.get("Health") or {}).get("Status"),
      "docker_started_at_utc":state.get("StartedAt"),"env_paper":env.get("DESK_MODE")=="paper",
      "env_capital_paper":env.get("DESK_CAPITAL_V1")=="paper","code_version":hb.get("version"),
      "heartbeat_started_ms":hb.get("started_ms"),"heartbeat_age_s":int((NOW-int(hb.get("ts",0) or 0))/1000),
      "heartbeat_capital_v1":hb.get("capital_v1"),"heartbeat_cycles":hb.get("cycles"),
       "trade_events":event_counts,
      "last_ok":hb.get("last_ok"),"last_error":str(hb.get("last_error") or "")[:160],
      "last_start_ms":hb.get("last_start_ms"),"last_end_ms":hb.get("last_end_ms"),
      "capital_status":capital.get("status"),"capital_schema_version":capital.get("schema_version"),
      "capital_day":day.get("utc_day"),"day_budget":day.get("day_budget"),
      "stop_latched":day.get("stop_latched"),"vault_balance":vault.get("balance"),
      "valuation_fresh":valuation.get("fresh"),"valuation_ms":valuation.get("valuation_ms"),
      "open_positions":len((disk.get("main") or {}).get("positions") or {}),
      "capital_journal_exists":Path("/opt/superbot-desk-data/"+bot+"/capital-v1-journal.jsonl").is_file(),
      "log_anomalies":relevant_errors(cname),
    },ensure_ascii=False,separators=(",",":")),flush=True)
print("CAPITAL_READONLY_COMPLETE")
