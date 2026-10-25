"""SuperBot read-only diagnostic MCP for Claude chat.

Design goals:
- absolutely no Docker socket, shell, subprocess, network fetch or trading keys;
- no arbitrary path, no raw Docker environment, no state writes;
- only an allowlisted, bind-mounted PAPER dataset available read-only;
- bearer-authenticated Streamable HTTP, accessible only via a separately secured HTTPS tunnel.
Requires the 2.x Python MCP SDK.
"""
from __future__ import annotations

import collections
import datetime as dt
import hmac
import json
import os
from pathlib import Path
from starlette.responses import PlainTextResponse
from mcp.server import MCPServer

TOKEN = os.environ.get("MCP_BEARER_TOKEN", "")
if len(TOKEN) < 48:
    raise RuntimeError("MCP_BEARER_TOKEN must be random, secret, and at least 48 chars")

BASE = Path("/data/desk")
SHADOW = Path("/data/shadow/ai")
BOTS = ("hawk", "bull")
mcp = MCPServer("SuperBot-Singapore-ReadOnly")

def _bot(bot: str) -> str:
    value = str(bot).strip().lower()
    if value not in BOTS:
        raise ValueError("Only hawk or bull supported")
    return value

def _obj(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        return {}
    if path.stat().st_size > 5 * 1024 * 1024:
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}

def _events(path: Path, max_entries: int = 30, max_bytes: int = 6_000_000) -> list[dict]:
    """Bounded backward tail of a JSONL journal; never scans secrets or returns raw records."""
    if path.is_symlink() or not path.is_file():
        return []
    # Read at most the final max_bytes to keep latency and memory bounded.
    with path.open("rb") as f:
        n = f.seek(0, os.SEEK_END)
        f.seek(max(0, n-max_bytes))
        buf = f.read()
    if n > len(buf):
        buf = buf.split(b"\n", 1)[-1]
    result = []
    for raw in reversed(buf.splitlines()):
        if len(result) >= max_entries:
            break
        if len(raw) > 100_000:
            continue
        try:
            x = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            continue
        if isinstance(x, dict):
            result.append(x)
    return result

def _num(n):
    if isinstance(n, bool):
        return None
    try:
        f = float(n)
        return round(f, 5) if abs(f) < 1e10 else None
    except (ValueError, TypeError):
        return None

def _fields(x: dict, names: tuple[str, ...]) -> dict:
    return {name: x.get(name) for name in names if name in x}

@mcp.tool()
def bot_status(bot: str) -> dict:
    """Read the current PAPER bot heartbeat, capital mode and slot count (no actions)."""
    b = _bot(bot)
    path = BASE/b
    hb = _obj(path/"heartbeat.json")
    state = _obj(path/"state_v2.json")
    main = state.get("main") or {}
    positions = main.get("positions") or {}
    return {
        "portfolio": b,
        "heartbeat": _fields(hb, ("version", "mode", "capital_v1", "cycles", "last_ok",
                                  "last_end_ms", "started_ms", "halt", "open_positions")),
        "capital_status_recorded":(state.get("capital") or {}).get("status"),
        "positions_count": len(positions),
        "position_symbols": sorted(positions),
        "cash_usd":_num(main.get("cash")),
        "day_start_equity_usd":_num(main.get("day_start_equity")),
        "prices_updated_ms":state.get("last_prices_ms"),
        "last_ai_call_ms":state.get("last_call_ms"),
        "ai_budget": _fields(state.get("budget") or {},("day","spent","calls")),
        "warning":"PAPER data only. No VPS env/secrets/container shell exposed.",
    }

@mcp.tool()
def bot_positions(bot: str) -> dict:
    """Read open PAPER positions, entry, side, saved price, protective SL/TP and margin."""
    b=_bot(bot)
    st=_obj(BASE/b/"state_v2.json")
    main=st.get("main") or {}
    px=st.get("last_prices") or {}
    out=[]
    for sym,p in sorted((main.get("positions") or {}).items()):
        if not isinstance(p,dict):continue
        out.append({
            "symbol":sym,
            "side":"LONG" if p.get("side")==1 else "SHORT" if p.get("side")==-1 else "UNKNOWN",
            "entry":_num(p.get("entry")),"last_price":_num(px.get(sym)),
            "qty":_num(p.get("qty")),"margin":_num(p.get("total_margin",p.get("margin"))),
            "sl":_num(p.get("sl")),"tp":_num(p.get("tp")),
            "open_ms":p.get("open_ms"),"trade_type":p.get("trade_type")
        })
    return {"portfolio":b,"prices_ms":st.get("last_prices_ms"),"positions":out,
            "note":"Prices are saved bot prices, not live exchange quotes."}

@mcp.tool()
def bot_recent_events(bot: str, count: int = 30) -> dict:
    """Read a bounded sample of recent paper open/close/candidate/AI-call events."""
    b=_bot(bot)
    count=max(1,min(int(count),75))
    data=_events(BASE/b/"learning_log.jsonl",max_entries=1000)
    whitelist=("ev","ts","symbol","side","source","status","action","net","reason",
               "why","confidence","stop_reason","ok","n_decisions","fail_reason",
               "open_ms","close_ms","partial","run_no","trade_type")
    rows=[_fields(x,whitelist) for x in data if x.get("ev") in
         ("open","close","candidate","claude_call")][:count]
    return {"portfolio":b,"newest_first":rows,"count":len(rows),
            "note":"Only selected diagnostic fields returned; full Claude replies deliberately excluded."}

@mcp.tool()
def bot_lessons_check(bot: str) -> dict:
    """Check whether approved patience/empty-slot and 70-80% lessons exist (no raw file dump)."""
    b=_bot(bot)
    path=BASE/b/"lessons.md"
    if path.is_symlink() or not path.is_file():
        return {"portfolio":b,"present":False}
    if path.stat().st_size>2_000_000:
        return {"portfolio":b,"error":"file too large"}
    t=path.read_text("utf-8")
    heads=[x[:140] for x in t.splitlines() if x.startswith("#")][-10:]
    return {"portfolio":b,"present":True,"lesson_marker":"[LESSON-STARTUP-20261024]" in t,
            "empty_slots_valid":"Slot vuoto = scelta valida" in t,
            "kpi_70_80_recorded":"70–80%" in t or "70-80%" in t,
            "last_headings":heads}

@mcp.tool()
def deepseek_shadow_status() -> dict:
    """Read DeepSeek shadow status and spending; never enable applied or read model keys."""
    st=_obj(SHADOW/"status.json")
    return _fields(st,("ts_ms","last_success_ms","algo","mode","applied","symbols_ok",
                      "symbols_total","model","spend","equity","open","closed_total"))

@mcp.tool()
def deepseek_recent_decisions(count: int=50) -> dict:
    """Read recent shadow decisions as sanitized actions + arbiter acceptance; no prompts/API keys."""
    count=max(1,min(int(count),80))
    now=dt.datetime.now(dt.timezone.utc)
    events=[]
    for day in [now,now-dt.timedelta(days=1)]:
        p=SHADOW/("cycles-"+day.strftime("%Y-%m-%d")+".jsonl")
        events.extend(_events(p,max_entries=120))
    events.sort(key=lambda x:x.get("ts_ms") or 0,reverse=True)
    rows=[]
    for row in events:
        dec=row.get("decision") or {}
        for x in dec.get("results") or []:
            if not isinstance(x,dict):continue
            rows.append({
                "ts_ms":row.get("ts_ms"),"symbol":x.get("symbol"),
                "action":x.get("action"),"accepted":x.get("accepted"),
                "reason":str(x.get("reason") or "")[:130],
            })
            if len(rows)>=count:break
        if len(rows)>=count:break
    return {"mode":"ombra","count":len(rows),"newest_first":rows,
            "warning":"HOLD is position-specific. Shadow results are not real Hawk/Bull instructions."}

# Enforce bearer token before any HTTP request reaches the MCP implementation.
# Do not log supplied token, headers or request bodies.
inner = mcp.streamable_http_app(stateless_http=True, json_response=True)
async def app(scope, receive, send):
    if scope["type"]=="http":
        headers=dict(scope.get("headers") or ())
        bearer=headers.get(b"authorization",b"").decode("utf-8","ignore")
        if not hmac.compare_digest(bearer, "Bearer "+TOKEN):
            await PlainTextResponse("Unauthorized",status_code=401)(scope,receive,send)
            return
    await inner(scope,receive,send)
