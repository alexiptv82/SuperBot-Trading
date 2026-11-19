"""Lettori delle sorgenti storiche, SOLO su COPIE ferme (mai sui file vivi) e in sola lettura.

Ogni lettore restituisce record normalizzati + `stats` (righe lette, non valide, chiavi non riconosciute): niente viene
scartato in silenzio. Nessuna rete, nessuna scrittura, nessun symlink seguito.
Famiglie: classic (Falco/Toro: learning_log.jsonl + trade_history.jsonl), v3 (journal `v3_events`: Arena e Brain V3),
brain_free (Brain storico: SQLite con `events(seq, kind, ts, body)` -- formato TOLLERANTE, da verificare su una copia reale).
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import stat
from collections import Counter, defaultdict
from typing import Any, Optional
from urllib.parse import quote

from schema import short_code
import snapshot_link as SL

_SAFE_STR = re.compile(r"[A-Za-z0-9_.:/+-]{1,24}")
_DROP_KEYS = frozenset({"reason", "why", "seasonal", "rationale", "note", "text", "pattern"})


def sanitize_features(d: Any) -> dict:
    """Solo numeri, bool e codici brevi: nessun testo libero (modelli/utente) nel dataset."""
    out: dict = {}
    if not isinstance(d, dict):
        return out
    for k, v in d.items():
        if k in _DROP_KEYS or not isinstance(k, str) or len(k) > 40:
            continue
        if isinstance(v, bool) or v is None:
            out[k] = v
        elif isinstance(v, (int, float)):
            if v == v and abs(v) != float("inf"):
                out[k] = v
        elif isinstance(v, str) and _SAFE_STR.fullmatch(v):
            out[k] = v
    return out


def _lines(path: str, stats: Counter):
    try:
        st = os.lstat(path)
        if not stat.S_ISREG(st.st_mode):
            stats["not_regular_file"] += 1
            return
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                stats["rows"] += 1
                try:
                    d = json.loads(line)
                except ValueError:
                    stats["bad_rows"] += 1
                    continue
                if not isinstance(d, dict):
                    stats["non_dict_rows"] += 1       # righe vecchie (liste) di reset passati
                    continue
                yield d
    except FileNotFoundError:
        stats["file_missing"] += 1


def _num(x: Any) -> Optional[float]:
    try:
        v = float(x)
        return v if v == v and abs(v) != float("inf") else None
    except (TypeError, ValueError):
        return None


def _int(x: Any) -> Optional[int]:
    v = _num(x)
    return int(v) if v is not None else None


def _side(v: Any) -> int:
    if isinstance(v, str):
        v = v.lower()
        return 1 if v in ("long", "buy", "1", "+1") else -1 if v in ("short", "sell", "-1") else 0
    n = _int(v)
    return n if n in (-1, 1) else 0


def map_exit_reason(raw: Any) -> str:
    s = str(raw or "").lower()
    if "manual" in s:
        return "manual"
    if s.startswith(("sl", "stop")) or "stop" in s:
        return "stop"
    if s.startswith(("tp", "take")) or "target" in s:
        return "take_profit"
    if "liq" in s:
        return "liquidation"
    if "time" in s or "scad" in s or "max_hold" in s:
        return "timeout"
    if "brain" in s or "ai" == s or "claude" in s:
        return "brain_close"
    return "unknown"


# --------------------------------------------------------------------------- classic (Falco / Toro)

def read_classic(path: str) -> dict:
    st = Counter()
    opens: dict = {}
    closes: dict = defaultdict(list)
    candidates: list = []
    other: Counter = Counter()
    ll_close_keys: dict = {}
    for ev in _lines(os.path.join(path, "learning_log.jsonl"), st):
        k, run = ev.get("ev"), ev.get("run_no", 1)
        if k == "open" and ev.get("id") is not None:
            opens[(run, str(ev["id"]))] = ev
        elif k == "close" and ev.get("id") is not None:
            closes[(run, str(ev["id"]))].append(ev)
            ll_close_keys[(str(ev["id"]), _int(ev.get("close_ms")))] = run
        elif k == "candidate":
            candidates.append(ev)
        else:
            other[str(k)] += 1
    hist_only = hist_dup = 0
    ids_to_run = defaultdict(set)
    for (run, i) in list(opens) + list(closes):
        ids_to_run[i].add(run)
    for rec in _lines(os.path.join(path, "trade_history.jsonl"), st):
        if rec.get("id") is None:
            st["history_without_id"] += 1
            continue
        i, cms = str(rec["id"]), _int(rec.get("close_ms"))
        if (i, cms) in ll_close_keys:
            hist_dup += 1                                           # stessa chiusura gia' nel learning_log: non si somma due volte
            continue
        runs = ids_to_run.get(i, set())
        run = next(iter(runs)) if len(runs) == 1 else None
        closes[(run, i)].append({**rec, "_from_history_only": True})
        hist_only += 1
    st["history_duplicates_skipped"] += hist_dup
    st["history_only_closes"] += hist_only
    return {"kind": "classic", "opens": opens, "closes": dict(closes), "candidates": candidates,
            "other_events": dict(other), "stats": dict(st)}


# --------------------------------------------------------------------------- journal V3 (Arena, Brain V3)

def open_frozen(path: str) -> sqlite3.Connection:
    """Copia ferma e standalone: nessun sidecar, apertura immutable (non crea file)."""
    for suf in ("-wal", "-shm", "-journal"):
        if os.path.lexists(path + suf):
            raise ValueError("sqlite_sidecar_present:" + suf)
    st = os.lstat(path)
    if not stat.S_ISREG(st.st_mode):
        raise ValueError("not_regular_file")
    return sqlite3.connect("file:" + quote(os.path.realpath(path), safe="/") + "?mode=ro&immutable=1", uri=True)


def read_v3(path: str) -> dict:
    st = Counter()
    decisions: dict = {}
    opens: dict = {}
    closes: dict = {}
    runs: set = set()
    snapshots: dict = {}
    timeline = SL.Timeline()
    con = open_frozen(path)
    try:
        if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='v3_events'").fetchone():
            return {"kind": "v3", "decisions": {}, "opens": {}, "closes": {}, "runs": [], "stats": {"no_v3_table": 1},
                    "snapshots": {}, "timeline": timeline}
        cols = {r[1] for r in con.execute("PRAGMA table_info(v3_events)")}
        hash_col = "event_hash" if "event_hash" in cols else "NULL"
        for seq, eid, run, kind, ts, payload, ehash in con.execute(
                f"SELECT seq,event_id,run_id,kind,occurred_at_ms,payload_json,{hash_col} FROM v3_events ORDER BY seq"):
            st["rows"] += 1
            runs.add(run)
            if kind != SL.KIND and type(ts) is int:
                timeline.add(run, ts, seq)
            try:
                p = json.loads(payload)
            except ValueError:
                st["bad_rows"] += 1
                continue
            if not isinstance(p, dict):
                st["non_dict_rows"] += 1
                continue
            if kind == "brain_decision":
                decisions[eid] = {"ts": ts, "run": run, "seq": seq, "hash": ehash, "kind": p.get("kind"), "status": p.get("status"),
                                  "symbol": p.get("symbol"), "regime": p.get("regime"),
                                  "strategy_id": p.get("strategy_id"), "strategy_origin": p.get("strategy_origin")}
            elif kind == SL.KIND:
                snapshots.setdefault(str(p.get("decision_event_id")), []).append({"seq": seq, "run": run, "ts": ts, "p": p})
                st["snapshots"] += 1
            elif kind == "paper_open":
                opens[str(p.get("position_id"))] = {"ts": ts, "run": run, "seq": seq, "p": p}
            elif kind == "paper_close":
                pid = str(p.get("position_id"))
                if pid in closes:
                    st["duplicate_closes_skipped"] += 1
                else:
                    closes[pid] = {"ts": ts, "run": run, "seq": seq, "p": p}
            else:
                st["other_kinds"] += 1
    finally:
        con.close()
    return {"kind": "v3", "decisions": decisions, "opens": opens, "closes": closes, "runs": sorted(runs), "stats": dict(st),
            "snapshots": snapshots, "timeline": timeline}


# --------------------------------------------------------------------------- Brain storico (SQLite legacy, formato tollerante)

def _first(d: dict, *names: str) -> Any:
    for n in names:
        if n in d and d[n] is not None:
            return d[n]
    return None


def _flat_numeric(body: dict, limit: int = 60) -> dict:
    out = {}
    for k, v in body.items():
        if isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and abs(v) != float("inf"):
            out[str(k)[:40]] = v
        if len(out) >= limit:
            break
    return out


def read_brain_free(path: str) -> dict:
    st = Counter()
    keys: dict = defaultdict(Counter)
    epoch = 0
    opens: dict = {}
    partials: dict = defaultdict(list)
    closed: dict = {}
    inputs: list = []
    decisions: list = []
    rejects: list = []
    con = open_frozen(path)
    try:
        for kind, ts, body in con.execute("SELECT kind,ts,body FROM events ORDER BY seq"):
            st["rows"] += 1
            try:
                b = json.loads(body)
            except (ValueError, TypeError):
                st["bad_rows"] += 1
                continue
            if not isinstance(b, dict):
                st["non_dict_rows"] += 1
                continue
            for k in b:
                keys[kind][k] += 1
            ts = _int(ts) or _int(b.get("ts"))
            if kind == "experiment_reframed":
                epoch += 1
            elif kind == "open":
                key = (epoch, str(b.get("symbol")), str(_first(b, "position_id", "id")))
                opens[key] = {"ts": ts, "side": _side(_first(b, "side", "direction")), "symbol": b.get("symbol"),
                              "entry": _num(_first(b, "entry", "fill_price", "price")),
                              "stop": _num(_first(b, "stop", "stop_loss", "sl", "stop_price")),
                              "target": _num(_first(b, "target", "take_profit", "tp")),
                              "leverage": _num(b.get("leverage")), "margin": _num(_first(b, "margin", "margin_used")),
                              "cycle": _first(b, "cycle_id", "decision_id", "input_id")}
            elif kind == "partial_trade":
                partials[(epoch, str(b.get("symbol")), str(_first(b, "position_id", "id")))].append(
                    {"ts": ts, "net": _num(_first(b, "net", "pnl"))})
            elif kind == "trade_closed":
                closed[(epoch, str(b.get("symbol")), str(_first(b, "position_id", "id")))] = {
                    "ts": ts, "net": _num(_first(b, "net", "pnl")), "fees": _num(b.get("fees")),
                    "funding": _num(b.get("funding")), "reason_raw": _first(b, "reason", "exit_reason", "why"),
                    "mfe_r": _num(b.get("mfe_r")), "mae_r": _num(b.get("mae_r"))}
            elif kind == "ai_input":
                # epoca, simbolo e ciclo servono a un legame CAUSALE con la decisione: senza, nessuna feature.
                inputs.append({"ts": ts, "epoch": epoch, "symbol": b.get("symbol"),
                               "cycle": _first(b, "cycle_id", "decision_id", "input_id"), "features": _flat_numeric(b)})
            elif kind == "ai_decision":
                decisions.append({"ts": ts, "epoch": epoch, "symbol": b.get("symbol"),
                                  "cycle": _first(b, "cycle_id", "decision_id", "input_id"),
                                  "action": str(_first(b, "action", "decision", "kind") or "").lower(),
                                  "side": _side(_first(b, "side", "direction"))})
            elif kind == "execution_rejected":
                rejects.append({"ts": ts, "epoch": epoch, "symbol": b.get("symbol"), "side": _side(_first(b, "side", "direction")),
                                "cycle": _first(b, "cycle_id", "decision_id", "input_id"),
                                "reason": short_code(_first(b, "reason", "code", "error"))})
            else:
                st["other_kinds"] += 1
    finally:
        con.close()
    return {"kind": "brain_free", "opens": opens, "partials": dict(partials), "closed": closed, "ai_inputs": inputs,
            "ai_decisions": decisions, "rejects": rejects, "epochs": epoch + 1, "stats": dict(st),
            "keys_seen": {k: sorted(v) for k, v in keys.items()}}


# --------------------------------------------------------------------------- annotazioni manuali dell'Arena

ARENA_REASONS = ("profit_protection", "loss_reduction", "trend_change", "other", "unspecified")


def read_annotations(path: str) -> dict:
    """`human_close_annotations.jsonl` (COPIA): position_id -> codice del motivo. Il testo libero (`note`) NON viene letto
    nel dataset. Un motivo fuori dalla lista chiusa diventa `invalid`; piu' annotazioni per la stessa posizione: vale l'ultima."""
    st: Counter = Counter()
    out: dict = {}
    for rec in _lines(path, st):
        pid = rec.get("position_id")
        if pid is None:
            st["without_position_id"] += 1
            continue
        reason = rec.get("reason")
        out[str(pid)] = reason if reason in ARENA_REASONS else "invalid"
    return {"by_position": out, "stats": dict(st)}
