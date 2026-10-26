"""15m paper loop, reusing AI shadow market/client/budget and desk paper engine.

SQLite commits account + events atomically; append-only JSONL exports are replayed
idempotently after crashes. Never imports live connectors or touches other bots.
"""
from __future__ import annotations
import argparse
import copy
from dataclasses import replace
import fcntl
import json
import os
from pathlib import Path
import sqlite3
import time

from director.ai_shadow import deepseek, journal
from director.ai_shadow.budget import Budget
from director.ai_shadow.config import Config
from director.ai_shadow.market import BarCache
from . import VERSION, prompt_builder, learning
from .portfolio import Portfolio, number
from .context import ContextCollector

BAR = 900000
MANAGEMENT = {"close","save_profit","partial_close","move_stop","hold"}
ACTIONS = MANAGEMENT | {"open_long","open_short","average","pause","resume"}


def config():
    return replace(Config(), name="brain-paper", bars_4h=240,bars_1d=120,
                   max_tokens=4000,daily_stop=.20,prompt_version=VERSION+"-upgrades-v1")


def validate_thesis(d):
    for key in ("bull_scenario","bear_scenario","verdict"):
        if not isinstance(d.get(key),str) or not d[key].strip():
            raise ValueError("missing_"+key)
        d[key]=d[key].strip()[:600]
    inv=d.get("invalidation")
    if not isinstance(inv,dict) or not isinstance(inv.get("description"),str) or not inv["description"].strip():
        raise ValueError("invalid_invalidation_description")
    if inv.get("timeframe") not in prompt_builder.TF_MS or inv.get("condition") not in ("close_below","close_above"):
        raise ValueError("invalid_invalidation_condition")
    if isinstance(inv.get("level"),bool) or not isinstance(inv.get("level"),(int,float)):
        raise ValueError("invalidation_level_must_be_json_number")
    d["invalidation"]={"description":inv["description"].strip()[:600],"timeframe":inv["timeframe"],
                       "condition":inv["condition"],"level":number(inv.get("level"),1e-12,1e15)}


def parse_response(text, universe, summaries, key=""):
    text = text.replace(key,"[redacted]") if key else text
    raw=json.loads(text,parse_constant=lambda value: (_ for _ in ()).throw(ValueError("nonfinite_json")))
    if not isinstance(raw,dict) or not isinstance(raw.get("decisions"),list) or len(raw["decisions"])>30:
        raise ValueError("invalid_response")
    view=raw.get("market_view")
    if not isinstance(view,str) or not view.strip():
        raise ValueError("missing_market_view")
    number(raw.get("next_check_minutes",15),15,15)
    out=[]; errors=[]; seen=set()
    for item in raw["decisions"]:
        try:
            if not isinstance(item,dict): raise ValueError("invalid_item")
            d=dict(item); action=d.get("action")
            if action not in ACTIONS: raise ValueError("unknown_action")
            if not isinstance(d.get("reason"),str) or not d["reason"].strip(): raise ValueError("missing_reason")
            d["reason"]=d["reason"][:600]
            if action in ("pause","resume"):
                identity="control"
                if action=="pause":
                    d["pause_minutes"]=number(d.get("pause_minutes"),15,120)
                    if not isinstance(d.get("reentry_condition"),str) or not d["reentry_condition"].strip():
                        raise ValueError("missing_reentry_condition")
                    d["reentry_condition"]=d["reentry_condition"][:300]
            else:
                sym=d.get("symbol","").upper()
                sym=sym[:-4] if sym.endswith("USDT") else sym
                if sym not in universe: raise ValueError("unknown_symbol")
                d["symbol"]=sym; identity=sym
                if action.startswith("open_") or action=="average":
                    if sym not in summaries or "BTC" not in summaries: raise ValueError("missing_macro")
                    d["size_pct"]=number(d.get("size_pct"),.01,1)
                    d["conviction"]=number(d.get("conviction"),60,100)
                    validate_thesis(d)
                    atr=number(summaries[sym].get("atr14_1h"),1e-12,1e15)
                    d["_atr_1h"]=atr
                    if action=="average": d["support_level"]=number(d.get("support_level"),1e-12,1e15)
                    else:
                        requested=number(d.get("sl_pct"),1e-7,.08)
                        stop=max(requested,.8*atr/summaries[sym]["price"])
                        if stop>.08:raise ValueError("atr_stop_out_of_bounds")
                        target=number(d.get("tp_pct"),.0001,.5)
                        if target/stop<1.5: raise ValueError("rr_below_1_5")
                        side=1 if action=="open_long" else -1
                        px=summaries[sym]["price"]
                        d.update(sl=px*(1-side*stop),tp=px*(1+side*target),
                                 _requested_sl=px*(1-side*requested),_atr_adjusted=stop>requested)
                if action=="move_stop": d["new_stop"]=number(d.get("new_stop"),1e-12,1e15)
                if action=="partial_close" and "close_fraction" in d:
                    number(d["close_fraction"],.5,.5)
            if identity in seen: raise ValueError("duplicate_symbol_or_control")
            seen.add(identity); out.append(d)
        except (ValueError,TypeError,KeyError,AttributeError):
            errors.append({"kind":"rejected_decision","index":len(out)+len(errors)})
    return view[:1500],out,errors


class Store:
    def __init__(self, root, learning_enabled=True):
        self.learning_enabled = learning_enabled
        self.root=Path(root).resolve()
        # Explicit own directory; never permit known sibling bot directories.
        if self.root.name in {"hawk","bull","ai","superbot-ai-data"} or any(p in {"hawk","bull"} for p in self.root.parts):
            raise ValueError("foreign_data_directory")
        self.root.mkdir(parents=True,exist_ok=True)
        self.lock=open(self.root/"writer.lock","a")
        try: fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except Exception:
            if hasattr(self,"db"):
                self.db.close()
            self.lock.close(); raise
        try:
            self.db=sqlite3.connect(self.root/"brain.sqlite3")
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.execute("PRAGMA synchronous=FULL")
            self.db.execute("CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY CHECK(id=1), body TEXT NOT NULL)")
            self.db.execute("CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY, kind TEXT NOT NULL, body TEXT NOT NULL)")
            self.db.commit()
            # Existing JSONL without authoritative database state must not reset capital.
            if self.load() is None and any((self.root/f).exists() and (self.root/f).stat().st_size for f in ("journal.jsonl","trade_history.jsonl","state.json")):
                raise ValueError("existing_data_requires_explicit_migration")
        except Exception:
            self.lock.close(); raise

    def load(self):
        row=self.db.execute("SELECT body FROM state WHERE id=1").fetchone()
        return json.loads(row[0]) if row else None

    def commit(self,state,events):
        with self.db:
            for kind,row in events:
                self.db.execute("INSERT INTO events(kind,body) VALUES (?,?)",(kind,json.dumps(row,allow_nan=False)))
            if self.learning_enabled:
                try:
                    before = state.get("learning", {}).get("cursor", 0)
                    memory = learning.advance(self.db, state.get("learning"))
                    state["learning"] = memory
                    state["learning_status"] = "ok"
                    if memory["cursor"] != before:
                        audit = {"kind": "learning_update", "cursor": memory["cursor"],
                                 "completed_total": memory["completed_total"], "invalid": memory["invalid"],
                                 "caught_up": memory["caught_up"], "version": learning.VERSION}
                        self.db.execute("INSERT INTO events(kind,body) VALUES ('learning',?)", (json.dumps(audit),))
                except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
                    state["learning_status"] = "unavailable"
            self.db.execute("INSERT OR REPLACE INTO state VALUES (1,?)",(json.dumps(state,allow_nan=False),))
        self.export()

    def export(self):
        for kind, filename in (("journal", "journal.jsonl"), ("trade", "trade_history.jsonl")):
            self.export_kind(kind, filename)
        # Learning audit is authoritative in SQLite. A damaged optional JSONL
        # projection must not stop protective trading or rewrite that file.
        self.learning_export_error = False
        try:
            self.export_kind("learning", "brain_learning.jsonl")
        except (OSError, ValueError, TypeError, KeyError):
            self.learning_export_error = True

    def export_kind(self, kind, filename):
        path=self.root/filename; seen=set()
        if path.exists():
            with path.open("rb") as f:
                for line in f:
                    if not line.endswith(b"\n"):
                        raise ValueError("torn_export_requires_recovery")
                    row=json.loads(line); seen.add(row["brain_event_id"])
        for seq,body in self.db.execute("SELECT seq,body FROM events WHERE kind=? ORDER BY seq",(kind,)):
            ident="brain-"+str(seq)
            if ident not in seen:
                journal.append_jsonl(str(path),dict(json.loads(body),brain_event_id=ident))

    def close(self):
        self.db.close(); self.lock.close()


class Pilot:
    def __init__(self,root,api_key,cache,model_call=deepseek.call,cfg=None,context=None):
        if os.getenv("DESK_MODE","paper")!="paper": raise ValueError("paper_required")
        self.cfg=cfg or config(); self.key=api_key; self.cache=cache; self.call=model_call
        self.context=context
        self.learning_enabled = os.getenv("BRAIN_LEARNING_ENABLED", "1") == "1"
        self.store=Store(root, learning_enabled=self.learning_enabled)
        try:
            self.store.export()
            self.state=self.store.load() or {"version":VERSION,"account":Portfolio().to_dict(),
                "last_bar":None,"last_attempt":None,"pending":[],"recent":[],"pause_until":0,
                "pause_start":0,"pause_epoch":-1,"epoch":0,"pause_reason":"","reentry_condition":""}
            if self.state["version"]!=VERSION: raise ValueError("unsupported_state_version")
            self.portfolio=Portfolio(self.state["account"])
            # Retain protective pending exits, reject legacy exposure that lacks
            # the new thesis/ATR contract. No historical trade is rewritten.
            pending=[];rejected=0
            for order in self.state["pending"]:
                try:
                    if order["action"] not in MANAGEMENT:
                        validate_thesis(order);number(order.get("_atr_1h"),1e-12,1e15)
                    pending.append(order)
                except (ValueError,TypeError,KeyError):rejected+=1
            self.state["pending"]=pending
            self.migration_rejected=rejected
            self.budget=Budget(str(self.store.root/"spend.jsonl"),self.cfg.daily_cap_usd,self.cfg.monthly_cap_usd)
            if self.budget.bad_lines: raise ValueError("corrupt_budget_ledger")
        except Exception:
            self.store.close(); raise

    def close(self): self.store.close()

    def remember_position(self, position):
        ctx = position.features.get("learning_context")
        if ctx:
            key = learning.position_key({"account": "brain-paper", "id": position.id,
                                        "symbol": position.symbol, "side": position.side, "open_ms": position.open_ms})
            self.state.setdefault("learning_open_contexts", {})[key] = ctx

    def memory_view(self, summaries, now_ms):
        if not self.learning_enabled:
            return {"version": learning.VERSION, "status": "disabled", "lessons": [], "cases": []}
        if self.state.get("learning_status") != "ok":
            return {"version": learning.VERSION, "status": "unavailable", "lessons": [], "cases": []}
        try:
            return learning.build_view(self.state.get("learning", learning.empty()), summaries, now_ms)
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
            return {"version": learning.VERSION, "status": "unavailable", "lessons": [], "cases": []}

    def checkpoint(self,events):
        a=self.portfolio.account; all_events=[]
        events=list(events)
        if self.migration_rejected:
            events.append({"kind":"legacy_pending_exposure_rejected","count":self.migration_rejected})
            self.migration_rejected=0
        daily=self.portfolio.daily
        if daily.get("stopped") and not daily.get("stop_logged"):
            events.append({"kind":"daily_stop","reason":"daily_equity_drawdown_20pct",
                           "utc_day":daily["day"],"resume":"next_UTC_day","management_active":True})
            daily["stop_logged"]=True
        for position in a.positions.values():
            self.remember_position(position)
        contexts = self.state.setdefault("learning_open_contexts", {})
        for row in a.closed:
            key = learning.position_key(row)
            enriched = dict(row,run_no=1,start_equity=1000)
            if key in contexts:
                enriched["learning_context"] = contexts[key]
            all_events.append(("trade",enriched))
            if not row.get("partial", False):
                contexts.pop(key, None)
            self.state["recent"].append({k:row.get(k) for k in ("symbol","side","net","why","close_ms")})
            if row["net"]<0: self.state["epoch"]+=1
        a.closed=[]
        self.state["recent"]=self.state["recent"][-10:]
        self.state["account"]=self.portfolio.to_dict()
        self.store.commit(self.state,all_events+[("journal",dict(e,mode="paper",applied=False)) for e in events])

    def control(self,d,now_ms):
        st=self.state
        if d["action"]=="resume":
            st["pause_until"]=0; st["pause_reason"]=d["reason"]
        else:
            if st["pause_epoch"]!=st["epoch"]:
                st["pause_start"]=now_ms; st["pause_epoch"]=st["epoch"]
            end=min(now_ms+int(d["pause_minutes"]*60000),st["pause_start"]+7200000)
            if end<=now_ms: raise ValueError("pause_episode_exhausted")
            st.update(pause_until=end,pause_reason=d["reason"],reentry_condition=d["reentry_condition"])

    def run_once(self,now_ms):
        st=self.state; bar_t=(now_ms-self.cfg.delay_ms)//BAR*BAR-BAR; cutoff=bar_t+BAR
        # No duplicate model call and no duplicate bars after restart.
        data=self.cache.refresh(now_ms,bar_t)
        summaries={}; bars={}; errors=[]
        for sym in self.cfg.symbols:
            frames=data.get(sym,{})
            try: bars[sym]=prompt_builder.closed_bars(frames.get("15m",[]),"15m",cutoff)
            except (ValueError,TypeError,IndexError): continue
            try: summaries[sym]=prompt_builder.summarize(sym,frames,cutoff)
            except (ValueError,TypeError,IndexError): pass
        last=st["last_bar"] if st["last_bar"] is not None else bar_t-BAR
        times=sorted({int(b[0]) for rows in bars.values() for b in rows if last<int(b[0])<=bar_t})
        # Mark equity for risk sizing at each historical OPEN, never at future closes.
        prior=dict(st.get("last_prices",{}))
        prior.update({sym:float(rows[rows[:,0]<=last][-1,4]) for sym,rows in bars.items() if len(rows[rows[:,0]<=last])})
        events=[]
        for t in times:
            current={s:next((b for b in rows if int(b[0])==t),None) for s,rows in bars.items()}
            opens={s:float(b[1]) for s,b in current.items() if b is not None}
            prices={**prior,**opens}
            if all(s in opens for s in self.portfolio.account.positions):
                self.portfolio.roll_day(t,prices)
            due=[o for o in st["pending"] if o["execute_t"]==t]
            st["pending"]=[o for o in st["pending"] if o["execute_t"]>t]
            for order in sorted(due,key=lambda o:0 if o["action"] in MANAGEMENT else 1):
                sym=order["symbol"]
                try:
                    if sym not in opens: raise ValueError("missing_execution_bar")
                    if order["action"] not in MANAGEMENT:
                        validate_thesis(order)
                        if self.portfolio.halted(prices,t):raise ValueError("daily_or_risk_halt")
                        if t<st["pause_until"]: raise ValueError("paused")
                        if (self.store.root/"pause.flag").exists(): raise ValueError("operator_pause")
                        if "BTC" not in opens: raise ValueError("missing_btc_at_execution")
                        if any(s not in opens for s in self.portfolio.account.positions): raise ValueError("missing_position_prices")
                        macro={tf:[b for b in data["BTC"][tf] if b[0]+ms<=t] for tf,ms in prompt_builder.TF_MS.items()}
                        prompt_builder.summarize("BTC",macro,t)
                    # Averaging macro is rechecked using ONLY bars closed at execution.
                    ctx=order.get("context",{})
                    if order["action"] not in MANAGEMENT:
                        historical={tf:[b for b in data[sym][tf] if b[0]+ms<=t] for tf,ms in prompt_builder.TF_MS.items()}
                        ctx=prompt_builder.summarize(sym,historical,t)
                        order["_atr_1h"]=ctx["atr14_1h"]
                    if sym in self.portfolio.account.positions:
                        self.remember_position(self.portfolio.account.positions[sym])
                    result=self.portfolio.apply(order,opens[sym],t,prices,ctx)
                    if result["kind"] == "open":
                        self.remember_position(self.portfolio.account.positions[sym])
                    events.append(dict(result,ts_ms=t))
                    if result["kind"]=="open": st["epoch"]+=1
                except (ValueError,TypeError,KeyError):
                    events.append({"kind":"execution_rejected","symbol":sym,"action":order["action"],"ts_ms":t})
            for sym,b in current.items():
                if b is not None:
                    self.portfolio.account.on_bar(sym,t,*map(float,b[1:5]),BAR)
                    prior[sym]=float(b[4])
            st["last_bar"]=t
            if all(s in current and current[s] is not None for s in self.portfolio.account.positions):
                self.portfolio.roll_day(t+BAR-1,prior)
        # Expire absent target bars; never execute a stale order at a later price.
        expired=[o for o in st["pending"] if o["execute_t"]<=bar_t]
        st["pending"]=[o for o in st["pending"] if o["execute_t"]>bar_t]
        events += [{"kind":"order_expired","symbol":o["symbol"],"ts_ms":now_ms} for o in expired]
        prices=dict(st.get("last_prices",{}))
        prices.update({sym:float(rows[-1,4]) for sym,rows in bars.items()})
        st["last_prices"]=prices
        if all(s in bars for s in self.portfolio.account.positions):
            self.portfolio.roll_day(cutoff-1,prices)
        self.checkpoint(events)
        snapshot=self.portfolio.snapshot(prices,cutoff)
        can_expose=("BTC" in summaries and all(s in summaries for s in self.portfolio.account.positions))
        result={"kind":"cycle","ts_ms":now_ms,"bar_t":bar_t,"called":False,"symbols":len(summaries)}
        if st["last_attempt"]==bar_t:
            result["skip"]="already_attempted"
        elif not self.key or not can_expose or len(summaries)<self.cfg.min_symbols_ok:
            result["skip"]="missing_key_or_macro_data"
        elif (self.store.root/"pause.flag").exists(): result["skip"]="operator_pause"
        else:
            context={"availability":"non disponibile"}
            if self.context is not None:
                try:
                    context=self.context.collect(list(summaries),now_ms,st.setdefault("market_context",{}))
                except Exception:
                    pass  # optional sources never block protective decisions
            memory = self.memory_view(summaries, cutoff)
            references = [lesson["id"] for lesson in memory["lessons"]]
            result["learning"] = {"status": memory["status"], "lesson_ids": references,
                                  "context_digest": learning.digest(memory),
                                  "audit_projection": "unavailable" if self.store.learning_export_error else "ok"}
            user=prompt_builder.build_user(cutoff,summaries,snapshot,st["recent"],
                {"until_ms":st["pause_until"],"reason":st["pause_reason"],"reentry_condition":st["reentry_condition"]},context,memory)
            ok,why,worst=self.budget.check(self.cfg.model,now_ms,len(prompt_builder.SYSTEM)+len(user),self.cfg.max_tokens)
            if not ok: result["skip"]="budget_cap"
            else:
                # Persist attempt BEFORE charging/calling. After a crash this bar is not retried.
                st["last_attempt"]=bar_t; self.checkpoint([{"kind":"model_attempt","bar_t":bar_t,"ts_ms":now_ms,"learning":result["learning"],"episodic_memory":memory}])
                # Reserve worst-case spend before network, even on failure. No undercount on crash.
                self.budget.record(self.cfg.model,now_ms,0,0,0,False,"worst_case_reservation",est_cost=worst)
                result["called"]=True
                try:
                    res=self.call(self.cfg,self.key,prompt_builder.SYSTEM,user)
                    view,orders,rejects=parse_response(res["content"],set(self.cfg.symbols),summaries,self.key)
                    result.update(market_view=view,rejected=len(rejects),usage=res.get("usage",{}))
                    # Controls apply before scheduling exposure; management still allowed in pause.
                    for d in orders:
                        if d["action"] in ("pause","resume"):
                            try:self.control(d,cutoff)
                            except ValueError:result["pause_rejected"]=True
                    opened=0
                    for d in orders:
                        if d["action"] in ("pause","resume","hold"):continue
                        exposure=d["action"].startswith("open_") or d["action"]=="average"
                        if exposure and (cutoff<st["pause_until"] or not can_expose or snapshot["halted"]):continue
                        if d["action"].startswith("open_"):
                            if opened>=3:continue
                            opened+=1
                        # Private provenance always comes from code, never provider JSON.
                        d.pop("_learning_model", None)
                        d.pop("_learning_refs", None)
                        if self.learning_enabled:
                            d["_learning_model"] = self.cfg.model
                            d["_learning_refs"] = references
                        d.update(execute_t=bar_t+BAR,context=summaries.get(d["symbol"],{}))
                        st["pending"].append(d)
                    result["pending"]=len(st["pending"])
                except (deepseek.ModelError,ValueError,KeyError,TypeError):
                    result["error"]="model_or_response_failed"  # never persist provider text/key
        self.checkpoint([result])
        journal.atomic_json(str(self.store.root/"status.json"),
            {"ts_ms":now_ms,"mode":"paper","applied":False,"version":VERSION,
             "equity":snapshot["equity"],"open":len(snapshot["positions"]),"last_cycle":result})
        return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--out",default="/out")
    parser.add_argument("--healthcheck",action="store_true");args=parser.parse_args()
    if args.healthcheck:
        status=journal.read_json(str(Path(args.out)/"status.json")) or {}
        if status.get("mode")!="paper" or time.time()*1000-status.get("ts_ms",0)>2700000:raise SystemExit(1)
        return
    cfg=config();pilot=Pilot(args.out,os.getenv("DEEPSEEK_API_KEY",""),BarCache(cfg),cfg=cfg,context=ContextCollector())
    try:
        while True:
            now=int(time.time()*1000);pilot.run_once(now)
            next_ms=(now//BAR+1)*BAR+cfg.delay_ms
            time.sleep(max(1,(next_ms-int(time.time()*1000))/1000))
    finally:pilot.close()


if __name__=="__main__":main()
