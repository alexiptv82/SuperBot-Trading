"""Diagnosi PAPER in SOLA LETTURA (root), 24/11/2026. Un solo rapporto JSON leggibile dall'agente (``--out``).

Nessuna scrittura in run, servizi, journal o memorie: i database SQLite si aprono in ``mode=ro`` (il journal attivo
si verifica su una copia temporanea), i JSONL si leggono e basta. I valori con nomi da segreto (key, token, secret,
password, auth, chat) sono mascherati; i file ``.env`` e l'ambiente dei container non si leggono mai.

0. Pausa: ``pause.flag``, battito, ultima apertura rispetto alla pausa, posizioni aperte con stop, catena del journal
   (conteggio e testa, per confronti successivi), esiti chiusi in memoria.
A. Trade SHORT BTC: cronologia completa delle quote (aperture, revisioni, consulti, stop, riduzioni, chiusure con
   motivo/prezzo/lordo/commissioni/netto), eventi della run intorno alle chiusure, esiti dei canali di chiusura,
   candele Bitget 1m e riesecuzione del monitor col codice installato, registri dei servizi.
B. Tutte le run V3 trovate sotto /opt (attiva, archiviate, copie, Arena): trade DISTINTI (quote e riduzioni
   aggregate per decisione), win rate, profit factor, netto, commissioni, drawdown, durata, LONG/SHORT, leva, margine,
   distanza dello stop; decisioni per tipo/esito/motivo, rifiuti di rischio, consulti, revisioni, Guardian; ritmo.
C. Brain libero (``brain.sqlite3`` ovunque sotto /opt, deduplicati): per epoca (experiment_started/reframed) trade
   aperti/chiusi (le parziali sono gia' dentro ``trade_closed``: mai sommate due volte), stesse statistiche;
   decisioni AI, rifiuti di esecuzione, configurazione dell'esperimento, costanti del codice.
D. Falco/Toro classici e Brain pilota (``/opt/superbot-desk-data``, ``/opt/superbot-brain-adaptive*``): trade da
   ``trade_history.jsonl`` (parziali aggregate per id), statistiche per mese e per run, eventi di apprendimento;
   configurazioni JSON e costanti del codice dei container (mai il loro ambiente).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path

OPT = Path("/opt")
RUNS = OPT / "superbot-v3-paper-runs"
DESK = OPT / "superbot-desk-data"
SCALP = "brain-v3-brain-scalp-p1"
MIN = 60_000
SECRET = re.compile(r"(key|token|secret|passw|auth|cookie|chat_?id|bearer|credential|private)", re.I)
SKIP_DIRS = {".venv", "venv", "site-packages", "node_modules", "__pycache__", ".git", "proc", "sys", "containerd",
             "docker", "lost+found", "snap"}


# ----------------------------------------------------------------------------- utilita'
def iso(ms) -> str | None:
    try:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(int(ms) / 1000))
    except (TypeError, ValueError, OverflowError):
        return None


def D(x) -> Decimal | None:
    if x is None or isinstance(x, bool):
        return None
    try:
        v = Decimal(str(x))
        return v if v.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


def redact(o, depth=0):
    if depth > 8:
        return "..."
    if isinstance(o, dict):
        return {k: ("***" if SECRET.search(str(k)) else redact(v, depth + 1)) for k, v in o.items()}
    if isinstance(o, list):
        return [redact(v, depth + 1) for v in o[:60]]
    if isinstance(o, str) and len(o) > 400:
        return o[:400] + "..."
    return o


def short(o, n=1500) -> str:
    s = json.dumps(redact(o), default=str, ensure_ascii=False)
    return s if len(s) <= n else s[:n] + "..."


def ro_connect(db: Path) -> sqlite3.Connection:
    try:
        c = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=10)
        c.execute("SELECT 1 FROM sqlite_master LIMIT 1").fetchall()
        return c
    except sqlite3.Error:
        return sqlite3.connect(f"file:{db}?mode=ro&immutable=1", uri=True, timeout=10)


def walk(root: Path, names: set[str], max_depth=7):
    root = Path(root)
    if not root.is_dir():
        return
    base = len(root.parts)
    for d, dirs, files in os.walk(root, followlinks=False):
        p = Path(d)
        dirs[:] = [] if len(p.parts) - base >= max_depth else [x for x in dirs if x not in SKIP_DIRS]
        for f in files:
            if f in names and not (p / f).is_symlink():
                yield p / f


def num_stats(vals):
    v = sorted(float(x) for x in vals if x is not None)
    if not v:
        return None
    return {"n": len(v), "min": round(v[0], 4), "median": round(v[len(v) // 2], 4), "mean": round(sum(v) / len(v), 4),
            "max": round(v[-1], 4)}


def trade_stats(trades: list[dict], initial=None) -> dict:
    """trade: open_ms, close_ms, side(+1/-1), net, gross, fees, lev, margin, symbol, reasons, stop_bp, closed."""
    closed = [t for t in trades if t.get("closed") and t.get("net") is not None]
    nets = [t["net"] for t in closed]
    gp = sum((n for n in nets if n > 0), Decimal(0))
    gl = -sum((n for n in nets if n < 0), Decimal(0))
    eq = D(initial) or Decimal(0)
    peak, mdd, mdd_frac = eq, Decimal(0), Decimal(0)
    for t in sorted(closed, key=lambda t: t.get("close_ms") or 0):
        eq += t["net"]
        peak = max(peak, eq)
        if peak - eq > mdd:
            mdd = peak - eq
            mdd_frac = (mdd / peak) if peak > 0 else Decimal(0)
    ts = [t["open_ms"] for t in trades if t.get("open_ms")] + [t["close_ms"] for t in closed if t.get("close_ms")]
    span_d = (max(ts) - min(ts)) / 86_400_000 if len(ts) > 1 else None

    def hold(pred):
        return num_stats([(t["close_ms"] - t["open_ms"]) / 60_000 for t in closed
                          if t.get("close_ms") and t.get("open_ms") and pred(t)])
    nwin, nloss = sum(n > 0 for n in nets), sum(n < 0 for n in nets)
    return {
        "opened": len(trades), "closed": len(closed), "still_open": len(trades) - len(closed),
        "first": iso(min(ts)) if ts else None, "last": iso(max(ts)) if ts else None,
        "span_days": round(span_d, 2) if span_d else None,
        "opens_per_day": round(len(trades) / span_d, 2) if span_d else None,
        "wins": nwin, "losses": nloss, "win_rate": round(nwin / len(nets), 4) if nets else None,
        "profit_factor": round(float(gp / gl), 3) if gl else None,
        "net": str(sum(nets, Decimal(0))), "gross_profit": str(gp), "gross_loss": str(gl),
        "gross": str(sum((t.get("gross") or Decimal(0) for t in closed), Decimal(0))),
        "fees": str(sum((t.get("fees") or Decimal(0) for t in closed), Decimal(0))),
        "avg_win": str(gp / nwin) if nwin else None, "avg_loss": str(gl / nloss) if nloss else None,
        "max_drawdown_usd": str(mdd), "max_drawdown_frac": round(float(mdd_frac), 4),
        "hold_min_all": hold(lambda t: True), "hold_min_win": hold(lambda t: t["net"] > 0),
        "hold_min_loss": hold(lambda t: t["net"] < 0),
        "sides": Counter({1: "LONG", -1: "SHORT"}.get(t.get("side"), str(t.get("side"))) for t in trades),
        "net_by_side": {s: str(sum((t["net"] for t in closed if t.get("side") == v), Decimal(0)))
                        for s, v in (("LONG", 1), ("SHORT", -1))},
        "leverage": num_stats([t.get("lev") for t in trades]),
        "margin": num_stats([t.get("margin") for t in trades]),
        "stop_bp": num_stats([t.get("stop_bp") for t in trades]),
        "close_reasons": Counter(r for t in closed for r in (t.get("reasons") or ["?"])).most_common(15),
        "symbols": Counter(t.get("symbol") for t in trades).most_common(30),
        "by_symbol_net": sorted(((s, str(sum((t["net"] for t in closed if t.get("symbol") == s), Decimal(0))))
                                 for s in {t.get("symbol") for t in closed}), key=lambda x: Decimal(x[1]))[:40],
    }


def side_of(x) -> int | None:
    if x in (1, -1):
        return x
    s = str(x).lower()
    if s in ("1", "long", "buy", "open_long"):
        return 1
    if s in ("-1", "short", "sell", "open_short"):
        return -1
    return None


# ----------------------------------------------------------------------------- V3
def v3_rows(db: Path) -> list[dict]:
    c = ro_connect(db)
    try:
        rows = c.execute("SELECT seq, event_id, run_id, kind, occurred_at_ms, source, payload_json, event_hash "
                         "FROM v3_events ORDER BY seq").fetchall()
    finally:
        c.close()
    return [{"seq": s, "id": i, "run": r, "kind": k, "t": t, "src": so, "p": json.loads(pj), "h": h}
            for s, i, r, k, t, so, pj, h in rows]


def v3_trades(ev: list[dict]) -> list[dict]:
    pos_group, groups = {}, {}
    for e in ev:
        p = e["p"]
        if e["kind"] == "paper_open":
            g = p.get("decision_event_id") or p.get("position_id")
            pos_group[p.get("position_id")] = g
            t = groups.setdefault(g, {"open_ms": e["t"], "side": side_of(p.get("side")), "symbol": p.get("symbol"),
                                      "lev": D(p.get("leverage")), "margin": Decimal(0), "net": Decimal(0),
                                      "gross": Decimal(0), "fees": Decimal(0), "reasons": [], "pids": set(),
                                      "closed_pids": set(), "legs": 0})
            t["pids"].add(p.get("position_id"))
            t["legs"] += 1
            t["margin"] += D(p.get("margin_used")) or Decimal(0)
            f, s = D(p.get("fill_price")), D(p.get("stop_price"))
            if f and s:
                t["stop_bp"] = abs(f - s) / f * 10000
        elif e["kind"] == "paper_add":
            t = groups.get(pos_group.get(p.get("position_id")))
            if t:
                t["margin"] += D(p.get("margin_used")) or D(p.get("margin")) or Decimal(0)
                t["adds"] = t.get("adds", 0) + 1
        elif e["kind"] in ("paper_close", "paper_reduce"):
            t = groups.get(pos_group.get(p.get("position_id")))
            if not t:
                continue
            t["net"] += D(p.get("realized_pnl")) or Decimal(0)
            t["gross"] += D(p.get("gross_pnl")) or Decimal(0)
            t["fees"] += D(p.get("fees")) or Decimal(0)
            t["reasons"].append(f"{e['kind'][6:]}:{p.get('reason')}:{p.get('stop_kind') or ''}")
            t["close_ms"] = e["t"]
            if e["kind"] == "paper_close":
                t["closed_pids"].add(p.get("position_id"))
    out = []
    for t in groups.values():
        t["closed"] = bool(t["pids"]) and t["pids"] <= t["closed_pids"]
        t["margin"] = float(t["margin"])
        t["lev"] = float(t["lev"]) if t["lev"] is not None else None
        t["stop_bp"] = float(t["stop_bp"]) if t.get("stop_bp") is not None else None
        t.pop("pids")
        t.pop("closed_pids")
        out.append(t)
    return out


FIELDS = ("kind", "status", "rationale", "risk_reason", "code", "reason", "verdict", "proposed", "executed", "source",
          "state", "strategy_id", "regime", "action", "decision", "outcome", "result", "stop_kind")


def kind_profile(ev: list[dict]) -> dict:
    out, by = {}, defaultdict(list)
    for e in ev:
        by[e["kind"]].append(e)
    for k, rows in by.items():
        prof = {"n": len(rows), "keys": Counter(x for r in rows for x in r["p"]).most_common(30)}
        for f in FIELDS:
            c = Counter(str(r["p"].get(f))[:80] for r in rows if f in r["p"])
            if c:
                prof[f] = c.most_common(25)
        trig = Counter(t for r in rows for t in (r["p"].get("triggers") or []) if isinstance(t, str))
        if trig:
            prof["triggers"] = trig.most_common(20)
        conf = []
        for r in rows:
            for holder in (r["p"], r["p"].get("proposal"), r["p"].get("deepseek"), r["p"].get("claude")):
                if isinstance(holder, dict) and D(holder.get("confidence")) is not None:
                    conf.append(D(holder.get("confidence")))
        if conf:
            prof["confidence"] = num_stats(conf)
        prof["sample"] = [short(r["p"], 900) for r in rows[:2]]
        out[k] = prof
    return out


def v3_run(db: Path, ev: list[dict]) -> dict:
    cfg = None
    f = db.parent / "runner_config.json"
    if f.is_file():
        try:
            cfg = json.loads(f.read_text())
        except ValueError:
            cfg = "illeggibile"
    initial = cfg.get("initial_equity") if isinstance(cfg, dict) else None
    dec = [e for e in ev if e["kind"] == "brain_decision"]
    span = (ev[-1]["t"] - ev[0]["t"]) / 86_400_000 if len(ev) > 1 else None
    rhythm = None
    if dec and span:
        slots = {e["t"] // (5 * MIN) for e in dec}
        rhythm = {"decisions_per_day": round(len(dec) / span, 1),
                  "open_decisions_per_day": round(sum(e["p"].get("kind") == "OPEN" for e in dec) / span, 2),
                  "cycles": len(slots), "cycles_per_day": round(len(slots) / span, 1)}
    return {"path": str(db.parent), "run_id": ev[0]["run"] if ev else None, "events": len(ev),
            "first": iso(ev[0]["t"]) if ev else None, "last": iso(ev[-1]["t"]) if ev else None,
            "head": ev[-1]["h"] if ev else None, "config": redact(cfg) if isinstance(cfg, dict) else cfg,
            "trades": trade_stats(v3_trades(ev), initial), "rhythm": rhythm, "kinds": kind_profile(ev)}


def journal_copy(db: Path) -> tuple[Path, Path]:
    tmp = Path(tempfile.mkdtemp(prefix="diag-j-"))
    dst = tmp / "j.db"
    src = ro_connect(db)
    o = sqlite3.connect(str(dst))
    with o:
        src.backup(o)
    src.close()
    o.close()
    return tmp, dst


# ----------------------------------------------------------------------------- 0. pausa
def pause_section(cur: Path, ev: list[dict], stage: Path) -> dict:
    flag = cur / "pause.flag"
    out = {"pause_flag": flag.exists(), "pause_since": iso(flag.stat().st_mtime * 1000) if flag.exists() else None}
    try:
        out["heartbeat"] = json.loads((cur / "heartbeat.json").read_text())
    except (OSError, ValueError):
        out["heartbeat"] = None
    opens = [e for e in ev if e["kind"] in ("paper_open", "paper_add")]
    out["last_open"] = iso(opens[-1]["t"]) if opens else None
    if flag.exists():
        since = int(flag.stat().st_mtime * 1000)
        out["opens_after_pause"] = sum(1 for e in opens if e["t"] >= since)
        out["kinds_after_pause"] = Counter(e["kind"] for e in ev if e["t"] >= since).most_common()
    run_id = ev[0]["run"] if ev else None
    sys.path.insert(0, str(stage))
    tmp, dst = journal_copy(cur / "journal.db")
    try:
        from backend.v3.dashboard import build_summary
        from backend.v3.events import EventJournal
        j = EventJournal(str(dst))
        count, head = j.verify_chain()
        out["journal_chain"] = {"ok": True, "count": count, "head": head}
        s = build_summary(j, "brain", run_id)
        out["open_positions"] = [{"position_id": p.position_id, "symbol": p.symbol, "side": p.side,
                                  "stop": str(getattr(p, "stop_price", None)), "leg": getattr(p, "leg", None)}
                                 for p in s.open_positions]
        out["summary"] = {"realized_pnl": str(s.realized_pnl), "closed": len(getattr(s, "closed_positions", ()) or ())}
        try:
            from backend.v3.outcomes import extract_outcomes
            out["memory_outcomes"] = len(extract_outcomes(j, "brain", run_id).outcomes)
        except Exception as exc:                              # noqa: BLE001
            out["memory_outcomes"] = type(exc).__name__
    except Exception as exc:                                  # noqa: BLE001
        out["journal_chain"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:200]}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return out


# ----------------------------------------------------------------------------- A. BTC
def btc_section(cur: Path, ev: list[dict], stage: Path, offline: bool) -> dict:
    pids = {e["p"].get("position_id") for e in ev if e["kind"] == "paper_open" and e["p"].get("symbol") == "BTCUSDT"}
    groups = {e["p"].get("decision_event_id") for e in ev if e["p"].get("position_id") in pids} - {None}
    keep = [e for e in ev if e["p"].get("position_id") in pids or e["p"].get("group") in groups or e["id"] in groups
            or e["p"].get("decision_event_id") in groups
            or (e["p"].get("symbol") == "BTCUSDT" and e["kind"] != "brain_decision")]
    kept = {e["seq"] for e in keep}
    closes = [e for e in keep if e["kind"] in ("paper_close", "paper_reduce")]
    tot = {f: str(sum((D(c["p"].get(f)) or Decimal(0) for c in closes), Decimal(0)))
           for f in ("gross_pnl", "fees", "realized_pnl")}
    around = []
    if closes:
        lo, hi = min(c["t"] for c in closes) - 15 * MIN, max(c["t"] for c in closes) + 3 * MIN
        around = [{"seq": e["seq"], "time": iso(e["t"]), "kind": e["kind"], "source": e["src"],
                   "payload": short(e["p"], 700)} for e in ev if lo <= e["t"] <= hi and e["seq"] not in kept]
    out = {"position_ids": sorted(x for x in pids if x),
           "events": [{"seq": e["seq"], "time": iso(e["t"]), "t": e["t"], "kind": e["kind"], "source": e["src"],
                       "payload": redact(e["p"])} for e in keep],
           "closes": [{"position_id": c["p"].get("position_id"), "kind": c["kind"], "reason": c["p"].get("reason"),
                       "stop_kind": c["p"].get("stop_kind"), "closed_by": c["p"].get("closed_by"),
                       "time": iso(c["t"]), "source": c["src"], "exit_price": c["p"].get("exit_price"),
                       "gross": c["p"].get("gross_pnl"), "fees": c["p"].get("fees"), "net": c["p"].get("realized_pnl")}
                      for c in closes],
           "totals": tot, "other_events_around_closes": around[:200]}
    for f in ("close_result.json", "brain_close_result.json", "heartbeat.json"):
        try:
            out[f] = redact(json.loads((cur / f).read_text()))
        except (OSError, ValueError):
            out[f] = None
    opens = [e for e in keep if e["kind"] == "paper_open"]
    if opens and not offline:
        start = min(e["t"] for e in opens) // MIN * MIN
        end = (max(c["t"] for c in closes) if closes else int(time.time() * 1000)) // MIN * MIN + 5 * MIN
        out["candles_1m"] = bitget_minutes("BTCUSDT", start, end)
    if opens:
        try:
            out["monitor_replay"] = replay(stage, cur, keep, out.get("candles_1m") or [])
        except Exception as exc:                              # noqa: BLE001
            out["monitor_replay"] = {"error": f"{type(exc).__name__}: {exc}"[:300]}
    return out


def bitget_minutes(symbol: str, start: int, end: int) -> list[list]:
    import urllib.request
    out, cur = [], start
    while cur < end:
        stop = min(end, cur + 200 * MIN)
        url = (f"https://api.bitget.com/api/v2/mix/market/history-candles?symbol={symbol}&productType=USDT-FUTURES"
               f"&granularity=1m&startTime={cur}&endTime={stop}&limit=200")
        try:
            with urllib.request.urlopen(url, timeout=20) as r:
                data = json.loads(r.read().decode()).get("data") or []
        except Exception:                                     # noqa: BLE001
            data = []
        out += [row[:5] for row in data]
        cur = stop
        time.sleep(0.3)
    return sorted({int(r[0]): r for r in out}.values(), key=lambda r: int(r[0]))


def replay(stage: Path, run_dir: Path, keep: list[dict], candles: list[list]) -> list[dict]:
    """Il monitor installato rigiocato su ogni quota (stop spostati inclusi): uscita attesa e miglior prezzo visto."""
    sys.path.insert(0, str(stage))
    from dataclasses import replace as dc_replace
    from backend.v3.features.indicators import Bar
    from backend.v3.runner.config import load_runner_config
    from backend.v3.runner.exits import evaluate_exit
    cfg = load_runner_config((run_dir / "runner_config.json").read_bytes())
    pol = cfg.exit_policy
    bars = [Bar(int(c[0]), Decimal(c[1]), Decimal(c[2]), Decimal(c[3]), Decimal(c[4]), Decimal(0)) for c in candles]
    moves = defaultdict(list)
    for e in keep:
        if e["kind"] == "stop_move" and D(e["p"].get("stop_price")):
            moves[e["p"].get("position_id")].append(((e["t"] // MIN + 1) * MIN, D(e["p"]["stop_price"])))
    out = []
    for e in keep:
        if e["kind"] != "paper_open":
            continue
        p = e["p"]
        pp = pol if p.get("take_profit_r") is None else dc_replace(pol, take_profit_r=Decimal(str(p["take_profit_r"])))
        mine = [b for b in bars if b.open_time_ms >= e["t"]]
        side = int(p["side"])
        best = (max if side == 1 else min)((b.high if side == 1 else b.low for b in mine), default=None)
        fill, stop = Decimal(str(p["fill_price"])), Decimal(str(p["stop_price"]))
        r_unit = abs(fill - stop)
        row = {"position_id": p.get("position_id"), "leg": p.get("leg"), "fill": str(fill), "stop": str(stop),
               "quantity": p.get("quantity"), "take_profit_r": str(pp.take_profit_r),
               "best_price_seen": None if best is None else str(best),
               "best_r": None if best is None or not r_unit else str(round((best - fill) * side / r_unit, 3)),
               "stop_moves": [(iso(x), str(y)) for x, y in moves.get(p.get("position_id"), [])]}
        if mine:
            try:
                sig = evaluate_exit(side=side, fill_price=fill, stop_price=stop, opened_at_ms=e["t"], bars=mine,
                                    candle_ms=MIN, policy=pp, fee_bps=cfg.fee_bps,
                                    stop_moves=tuple(moves.get(p.get("position_id"), ())))
                row["monitor_exit"] = None if sig is None else {
                    "reason": getattr(sig, "reason", None), "price": str(getattr(sig, "price", None)),
                    "bar": iso(getattr(sig, "bar_open_time_ms", None)), "stop_kind": getattr(sig, "stop_kind", None)}
            except Exception as exc:                          # noqa: BLE001
                row["monitor_exit"] = {"error": f"{type(exc).__name__}: {exc}"[:200]}
        out.append(row)
    return out


# ----------------------------------------------------------------------------- C. Brain libero
def brain_free(db: Path) -> dict:
    c = ro_connect(db)
    try:
        cnt, maxseq, maxts = c.execute("SELECT count(*), max(seq), max(ts) FROM events").fetchone()
        kinds = c.execute("SELECT kind, count(*) FROM events GROUP BY kind ORDER BY 2 DESC").fetchall()
        opens, partials, closes, cur, ep_info, rej = {}, defaultdict(list), {}, 0, [], Counter()
        for seq, kind, ts, body in c.execute(
                "SELECT seq, kind, ts, body FROM events WHERE kind IN ('open','dca','partial_trade','trade_closed',"
                "'experiment_started','experiment_reframed','execution_rejected') ORDER BY seq"):
            try:
                e = json.loads(body)
            except ValueError:
                continue
            if kind in ("experiment_started", "experiment_reframed"):
                cur += kind == "experiment_reframed"
                ep_info.append({"epoch": cur, "kind": kind, "time": iso(ts), "body": short(e, 4000)})
                continue
            if kind == "execution_rejected":
                rej[str(e.get("reason") or e.get("code") or e.get("error"))[:80]] += 1
                continue
            key = (cur, e.get("symbol"), e.get("position_id"))
            if kind == "open":
                opens[key] = (ts, e)
            elif kind == "dca":
                opens.setdefault(key, (ts, e))
            elif kind == "partial_trade":
                partials[key].append(e)
            elif kind == "trade_closed":
                closes[key] = (ts, e)
        ai_keys, acts, conf, dec_rows = Counter(), Counter(), [], []
        for (body,) in c.execute("SELECT body FROM events WHERE kind='ai_decision'"):
            try:
                e = json.loads(body)
            except ValueError:
                continue
            ai_keys.update(list(e))
            d = e.get("decision") if isinstance(e.get("decision"), dict) else e
            acts[str(d.get("action") or d.get("kind") or d.get("decision"))[:40]] += 1
            if D(d.get("confidence")) is not None:
                conf.append(D(d.get("confidence")))
            if len(dec_rows) < 3:
                dec_rows.append(short(e, 1500))
        state = None
        try:
            state = json.loads(c.execute("SELECT body FROM state WHERE id=1").fetchone()[0])
        except Exception:                                     # noqa: BLE001
            pass
        samples = {}
        for k in ("open", "partial_trade", "trade_closed", "execution_rejected", "daily_report", "move_stop"):
            r = c.execute("SELECT body FROM events WHERE kind=? ORDER BY seq LIMIT 1", (k,)).fetchone()
            if r:
                samples[k] = short(json.loads(r[0]), 1500)
    finally:
        c.close()
    by_epoch = defaultdict(list)
    for key, (ts, o) in opens.items():
        t = {"open_ms": ts, "symbol": key[1], "side": side_of(o.get("side")),
             "lev": float(D(o.get("leverage")) or 0) or None,
             "margin": float(D(o.get("margin_added")) or D(o.get("margin")) or 0) or None, "closed": key in closes}
        f, s = D(o.get("entry") or o.get("price")), D(o.get("stop") or o.get("sl"))
        if f and s:
            t["stop_bp"] = float(abs(f - s) / f * 10000)
        if key in closes:
            cts, ce = closes[key]
            segs = [x.get("segment") or {} for x in partials.get(key, [])] + [ce.get("segment") or {}]
            t.update(close_ms=cts, net=D(ce.get("net")) or Decimal(0),
                     gross=sum((D(sg.get("gross")) or Decimal(0) for sg in segs), Decimal(0)),
                     fees=sum(((D(sg.get("fees")) or Decimal(0)) + (D(sg.get("funding")) or Decimal(0))
                               for sg in segs), Decimal(0)),
                     reasons=[str(ce.get("reason") or ce.get("exit_reason"))[:40]],
                     partials=len(partials.get(key, [])))
        by_epoch[key[0]].append(t)
    return {"path": str(db), "events": cnt, "max_seq": maxseq, "last": iso(maxts), "kinds": kinds,
            "experiments": ep_info, "execution_rejected": rej.most_common(25),
            "ai_decisions": {"keys": ai_keys.most_common(30), "actions": acts.most_common(15),
                             "confidence": num_stats(conf), "samples": dec_rows},
            "state": short(state, 5000), "samples": samples,
            "trades_all": trade_stats([t for v in by_epoch.values() for t in v], 2000),
            "trades_by_epoch": {str(k): trade_stats(v, 2000) for k, v in sorted(by_epoch.items())}}


# ----------------------------------------------------------------------------- D. desk classici
def jsonl(p: Path) -> list[dict]:
    rows = []
    try:
        with open(p, errors="ignore") as f:
            for line in f:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if isinstance(r, dict):
                    rows.append(r)
    except OSError:
        pass
    return rows


def classic_trades(rows: list[dict]) -> list[dict]:
    """Righe chiuse di trade_history (anche parziali): un trade = stesso id/simbolo/apertura."""
    g = {}
    for r in rows:
        key = (r.get("id"), r.get("symbol"), r.get("open_ms"))
        t = g.setdefault(key, {"open_ms": r.get("open_ms"), "symbol": r.get("symbol"), "side": side_of(r.get("side")),
                               "lev": float(D(r.get("leverage")) or 0) or None, "margin": Decimal(0),
                               "net": Decimal(0), "fees": Decimal(0), "reasons": [], "closed": False, "parts": 0,
                               "run": r.get("run")})
        t["net"] += D(r.get("net")) or Decimal(0)
        t["fees"] += (D(r.get("fees")) or Decimal(0)) + (D(r.get("funding")) or Decimal(0))
        t["margin"] += D(r.get("margin")) or Decimal(0)
        t["parts"] += 1
        t["close_ms"] = max(t.get("close_ms") or 0, r.get("close_ms") or 0) or None
        t["reasons"].append(str(r.get("reason"))[:40])
        if not r.get("partial"):
            t["closed"] = True
        e, s = D(r.get("entry")), D(r.get("sl") or r.get("stop"))
        if e and s:
            t["stop_bp"] = float(abs(e - s) / e * 10000)
    for t in g.values():
        t["gross"] = t["net"] + t["fees"]
        t["margin"] = float(t["margin"]) / max(t["parts"], 1)
    return list(g.values())


def desk_section(folder: Path) -> dict:
    out = {"folder": str(folder), "files": {}}
    for f in sorted(folder.rglob("*")):
        if not f.is_file() or f.is_symlink() or ".env" in f.name or SECRET.search(f.name):
            continue
        info = {"bytes": f.stat().st_size, "mtime": iso(f.stat().st_mtime * 1000)}
        if f.suffix == ".jsonl" and f.stat().st_size < 400_000_000:
            rows = jsonl(f)
            info["rows"] = len(rows)
            info["keys"] = Counter(k for r in rows for k in r).most_common(40)
            for k in ("ev", "event", "kind", "action", "reason", "run", "outcome", "side"):
                c = Counter(str(r.get(k))[:40] for r in rows if k in r)
                if c:
                    info.setdefault("categories", {})[k] = c.most_common(20)
            info["sample"] = [short(r, 800) for r in rows[:2]]
            if f.name == "trade_history.jsonl":
                tr = classic_trades(rows)
                info["trades"] = trade_stats(tr, None)
                runs, months = defaultdict(list), defaultdict(list)
                for t in tr:
                    runs[str(t.get("run"))].append(t)
                    months[(iso(t.get("open_ms")) or "?")[:7]].append(t)
                if len(runs) > 1:
                    info["trades_by_run"] = {k: trade_stats(v, None) for k, v in runs.items()}
                info["trades_by_month"] = {k: trade_stats(v, None) for k, v in sorted(months.items())}
        elif f.suffix == ".json" and f.stat().st_size < 2_000_000:
            try:
                info["content"] = short(json.loads(f.read_text()), 6000)
            except ValueError:
                info["content"] = "illeggibile"
        out["files"][str(f.relative_to(folder))] = info
    return out


CONST = re.compile(r"^\s*([A-Z][A-Z0-9_]{2,})\s*[:=][^=].{0,160}$")
THRESH = re.compile(r"(score|confid|threshold|soglia|min_|max_|leverage|leva|margin|stop|take_profit|tp_|sl_|cycle"
                    r"|interval|minutes|cooldown)", re.I)


def code_constants(root: Path, limit=600) -> list[str]:
    out = []
    for f in sorted(root.rglob("*.py")):
        if any(x in SKIP_DIRS or x == "tests" for x in f.parts) or f.stat().st_size > 800_000:
            continue
        try:
            lines = f.read_text(errors="ignore").splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines, 1):
            if len(out) >= limit:
                return out
            if (CONST.match(line) or (THRESH.search(line) and re.search(r"(>=|<=|>|<)\s*\d", line))) \
                    and not SECRET.search(line):
                out.append(f"{f.relative_to(root)}:{i}: {line.strip()[:200]}")
    return out


def containers() -> list[dict]:
    """Solo nome, immagine, stato e comando dei container (MAI l'ambiente)."""
    p = subprocess.run(["docker", "ps", "-a", "--format", "{{json .}}"], capture_output=True, text=True, timeout=30)
    rows = [json.loads(x) for x in p.stdout.splitlines() if x.strip()]
    return [{k: r.get(k) for k in ("Names", "Image", "Status", "CreatedAt", "Command")} for r in rows]


def classic_code(names: tuple[str, ...]) -> dict:
    """Costanti del codice in esecuzione nei container classici (file system del container, mai l'ambiente)."""
    out = {}
    for n in names:
        p = subprocess.run(["docker", "inspect", "--format", "{{json .GraphDriver.Data.MergedDir}}", n],
                           capture_output=True, text=True, timeout=20)
        try:
            d = json.loads(p.stdout) if p.returncode == 0 else None
        except ValueError:
            d = None
        if not d:
            continue
        for sub in ("app/backend", "app", "backend", "srv"):
            if (Path(d) / sub).is_dir():
                out[n] = code_constants(Path(d) / sub, 900)
                break
    return out


# ----------------------------------------------------------------------------- main
def main(argv=None) -> int:
    global OPT, RUNS, DESK
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--owner", default="")
    ap.add_argument("--opt", default=str(OPT))                # solo per le prove locali
    ap.add_argument("--stage", default="")
    ap.add_argument("--offline", action="store_true")
    a = ap.parse_args(argv)
    OPT = Path(a.opt)
    RUNS, DESK = OPT / "superbot-v3-paper-runs", OPT / "superbot-desk-data"
    rep: dict = {"generated": iso(time.time() * 1000), "errors": []}
    stage = Path(a.stage or subprocess.run(["systemctl", "show", "-p", "WorkingDirectory", "--value",
                                            "superbot-brain-scalp-p1-exit.service"],
                                           capture_output=True, text=True).stdout.strip())
    rep["stage"] = str(stage)
    cur = RUNS / SCALP

    def step(name, fn):
        try:
            rep[name] = fn()
        except Exception as exc:                              # noqa: BLE001
            rep["errors"].append(f"{name}: {type(exc).__name__}: {exc}"[:300])

    ev = v3_rows(cur / "journal.db") if (cur / "journal.db").is_file() else []
    step("P0_pause", lambda: pause_section(cur, ev, stage))
    step("A_btc", lambda: btc_section(cur, ev, stage, a.offline))
    if not a.offline:
        logs = {}
        for unit in ("superbot-brain-scalp-p1-exit.service", "superbot-brain-scalp-p1-runner.service"):
            logs[unit] = subprocess.run(["journalctl", "-u", unit, "--since", "2026-11-24 14:00", "--no-pager",
                                         "-o", "short-iso"], capture_output=True, text=True).stdout.splitlines()[-150:]
        rep["A_service_log"] = logs

    seen, v3 = set(), []
    for db in walk(OPT, {"journal.db"}):
        try:
            rows = v3_rows(db)
        except Exception as exc:                              # noqa: BLE001
            rep["errors"].append(f"v3 {db}: {type(exc).__name__}")
            continue
        sig = (rows[0]["run"], len(rows), rows[-1]["h"]) if rows else (str(db), 0, "")
        if sig in seen:
            v3.append({"path": str(db.parent), "duplicate_of": list(sig)})
            continue
        seen.add(sig)
        try:
            v3.append(v3_run(db, rows))
        except Exception as exc:                              # noqa: BLE001
            rep["errors"].append(f"v3run {db}: {type(exc).__name__}: {exc}"[:200])
    rep["B_v3_runs"] = v3

    seen, bf = set(), []
    for db in walk(OPT, {"brain.sqlite3"}):
        try:
            c = ro_connect(db)
            sig = tuple(c.execute("SELECT count(*), max(seq), max(ts) FROM events").fetchone())
            c.close()
        except Exception as exc:                              # noqa: BLE001
            rep["errors"].append(f"bf {db}: {type(exc).__name__}")
            continue
        if sig in seen:
            bf.append({"path": str(db), "duplicate_signature": list(sig)})
            continue
        seen.add(sig)
        try:
            bf.append(brain_free(db))
        except Exception as exc:                              # noqa: BLE001
            rep["errors"].append(f"bfrun {db}: {type(exc).__name__}: {exc}"[:200])
    rep["C_brain_free"] = bf
    step("C_brain_free_code", lambda: {d.name: code_constants(d) for d in OPT.glob("superbot-brain-free*")
                                       if d.is_dir()})

    rep["D_desk"] = []
    for d in ([DESK] if DESK.is_dir() else []) + sorted(p for p in OPT.glob("superbot-brain-adaptive*") if p.is_dir()):
        for sub in sorted(x for x in d.iterdir() if x.is_dir()):
            try:
                rep["D_desk"].append(desk_section(sub))
            except Exception as exc:                          # noqa: BLE001
                rep["errors"].append(f"desk {sub}: {type(exc).__name__}: {exc}"[:200])
    if not a.offline:
        step("D_containers", containers)
        step("D_classic_code_constants", lambda: classic_code(("superbot-desk-hawk", "superbot-desk-bull", "superbot")))

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, indent=1, default=str))
    out.chmod(0o644)
    if a.owner:
        shutil.chown(out, a.owner, a.owner)
    p0 = rep.get("P0_pause") or {}
    print("DIAGNOSI_PAUSA=" + json.dumps({k: p0.get(k) for k in ("pause_flag", "opens_after_pause", "last_open")}))
    print("DIAGNOSI_APERTE=" + str(len(p0.get("open_positions") or [])) + " JOURNAL=" + json.dumps(p0.get("journal_chain")))
    a_ = rep.get("A_btc") or {}
    print("DIAGNOSI_BTC_CHIUSURE=" + json.dumps([(c["reason"], c["stop_kind"], c["time"], c["exit_price"], c["net"])
                                                  for c in a_.get("closes") or []]))
    print("DIAGNOSI_BTC_TOTALI=" + json.dumps(a_.get("totals")))
    print(f"DIAGNOSI_STORICO=V3:{len(v3)} BRAIN_LIBERO:{len(bf)} DESK:{len(rep['D_desk'])} ERRORI:{len(rep['errors'])}")
    print("DIAGNOSI_RAPPORTO=" + str(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
