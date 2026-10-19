"""Read-only entry diagnostics; emit only allowlisted aggregate data."""
import collections
import datetime
import json
import math
from pathlib import Path
import re
import subprocess
import time


def read_json(path):
    try:
        with path.open() as stream:
            return json.load(stream)
    except Exception:
        return {}


def count_events(path, start, end):
    events, candidates, sources, calls, confidence = [collections.Counter() for _ in range(5)]
    bad = 0
    allowed = {"conf_bassa", "conf_bassa_macro", "macro_blocco", "rr_basso", "cooldown"}
    if not path.exists():
        return {"missing": True}
    with path.open() as stream:
        for line in stream:
            try:
                row = json.loads(line)
                ts = row.get("ts", row.get("open_ms", row.get("logged_ms", 0)))
                if not isinstance(ts, (int,float)) or not start <= ts < end:
                    continue
                ev = row.get("ev")
                if ev not in {"open", "close", "candidate", "claude_call", "split_fill", "split_cancel"}:
                    continue
                events[ev] += 1
                source = row.get("source") if row.get("source") in ("claude", "rules") else "unknown"
                if ev in ("open", "candidate"):
                    sources[ev+":"+source] += 1
                if ev == "candidate":
                    status = row.get("status", "")
                    label = status if status in allowed else "account_rejected" if status.startswith("rifiutata:") else "other"
                    candidates[label] += 1
                    conf = (row.get("features") or {}).get("conf")
                    if isinstance(conf,(int,float)) and math.isfinite(conf):
                        confidence[str(int(conf)//10*10)+"s:"+source] += 1
                if ev == "claude_call":
                    calls["parsed_ok" if row.get("ok") is True else "failed_or_unparsed"] += 1
                    if row.get("stop_reason") in ("max_tokens", "end_turn", "stop_sequence"):
                        calls[row["stop_reason"]] += 1
                    n = row.get("n_decisions")
                    if isinstance(n,int): calls["decisions_total"] += n
            except Exception:
                bad += 1
    return dict(events=dict(events),candidates=dict(candidates),sources=dict(sources),claude_calls=dict(calls),confidence_buckets=dict(confidence),bad_rows=bad)


def main():
    now = int(time.time()*1000)
    print(json.dumps({"checked_at_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"read_only":True}))
    for bot in ("hawk","bull"):
        root=Path('/opt/superbot-desk-data')/bot
        state=read_json(root/'state_v2.json'); hb=read_json(root/'heartbeat.json')
        account=state.get('main') or {}; budget=state.get('budget') or {}
        run_start=state.get('run_started_ms',now)
        limits=account.get('limits') or {}; positions=account.get('positions') or {}
        prices=state.get('last_prices') or {}
        equity=account.get('cash',0)+sum(p.get('total_margin',0)+p.get('side',0)*(prices.get(s,p.get('entry',0))-p.get('entry',0))*p.get('qty',0) for s,p in positions.items())
        cap=hb.get('daily_cap_usd',.7)
        spent=budget.get('spent',0) if budget.get('day')==time.strftime('%Y-%m-%d',time.gmtime(now/1000)) else 0
        report=dict(bot=bot,run_no=state.get('run_no'),cycle=hb.get('cycles'),last_end_ms=hb.get('last_end_ms'),heartbeat_age_seconds=round(now/1000-hb.get('ts',0)),paper=hb.get('exec_mode')=='paper',paused=hb.get('pause_requested'),trading_enabled=hb.get('trading_enabled'),open_positions=len(positions),current_run_closed=len(account.get('closed') or []),prices_available=len(prices),
                    halt_capital=equity<=limits.get('kill_equity',0),halt_daily=equity<=account.get('day_start_equity',0)*(1-limits.get('daily_stop',0)),
                    ai_budget_calls=budget.get('calls'),ai_budget_remaining_approx=round(cap-spent,4),ai_reserve_available=(cap-spent)>=.04,last_ai_call_ms=state.get('last_call_ms'),
                    macro_enforced=(hb.get('macro') or {}).get('enforce'),macro_blackout=(hb.get('macro') or {}).get('blackout'),hours_blocked=(hb.get('hours') or {}).get('blocked'),claude_schedule_allowed=(hb.get('claude_schedule') or {}).get('allowed'))
        report['since_run_start']=count_events(root/'learning_log.jsonl',run_start,now+1)
        report['daily_utc']={}
        for day in range(13,20):
            dt=datetime.datetime(2026,10,day,tzinfo=datetime.timezone.utc)
            start=int(dt.timestamp()*1000)
            report['daily_utc'][dt.strftime('%Y-%m-%d')]=count_events(root/'learning_log.jsonl',start,min(start+86400000,now+1))
        since=datetime.datetime.fromtimestamp(run_start/1000,datetime.timezone.utc).isoformat()
        proc=subprocess.run(['docker','logs','--since',since,'superbot-desk-'+bot],capture_output=True,text=True,timeout=30)
        log=proc.stdout+proc.stderr
        tags=collections.Counter(re.findall(r'^\[([A-Za-z0-9_: ]+)\]',log,re.M))
        allowed_tags={'CONF_LOW','RR_LOW','COOLDOWN','HALT','FINESTRA','Claude','OPEN','CLOSE','SKIP','WARN','ORARI','PAUSA','MACRO_BLOCCO','MACRO_OSSERVATO','SLEEP','DESK V2'}
        report['log_tags_since_run']={k:v for k,v in tags.items() if k in allowed_tags}
        report['confidence_rejections']=[dict(confidence=int(a),threshold=int(b),count=n) for (a,b),n in collections.Counter(re.findall(r'conf=(\d+) < soglia=(\d+)',log)).most_common(12)]
        report['latest_market_coverage']=re.findall(r'\[DESK V2\] (?:candles ok|readings validi): \d+/\d+ simboli',log)[-4:]
        print(json.dumps(report,sort_keys=True))


if __name__=='__main__': main()
