"""Training Dataset Builder (offline, solo libreria standard): decisioni storiche -> esempi con feature, esiti ed etichette.

Uso:  python3 builder.py --spec spec.json --out DIR_NUOVA [--candles DIR] [--cost-bp 16]

spec.json: {"inputs": [{"id": "falco_hawk", "source_system": "falco", "kind": "classic", "path": "<COPIA>", "verified": false}, ...]}
`path` e' SEMPRE una copia ferma (Fase 0), mai un file vivo. `verified` = vero solo dopo audit di catena/riconciliazione.

Sicurezza: output in directory NUOVA, fuori da qualunque working tree git, file 0600; nessuna rete; nessuna scrittura sugli
input; nessun testo libero nell'output. Determinismo: stessi input -> stesso `examples.jsonl` (stesso digest).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from collections import Counter
from typing import Any, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import candles as C  # noqa: E402
import features as F  # noqa: E402
import labels as L  # noqa: E402
import readers as R  # noqa: E402
import schema as S  # noqa: E402
import sufficiency as SU  # noqa: E402

COST_BP = 16.0
TARGET_R = 2.0
ATR_K = 1.5
MAX_HOLD_MS = 86_400_000
NEAREST_INPUT_MS = 600_000


# --------------------------------------------------------------------------- utilita'

def sha_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def input_files(inp: dict) -> list:
    p = inp["path"]
    if inp["kind"] == "classic":
        return [f for f in (os.path.join(p, "learning_log.jsonl"), os.path.join(p, "trade_history.jsonl")) if os.path.isfile(f)]
    return [p] if os.path.isfile(p) else []


def inside_repo(path: str) -> bool:
    p = os.path.abspath(path)
    while True:
        if os.path.lexists(os.path.join(p, ".git")):
            return True
        parent = os.path.dirname(p)
        if parent == p:
            return False
        p = parent


def _n(x: Any) -> Optional[float]:
    return R._num(x)


def _round(x: Optional[float], nd: int = 6) -> Optional[float]:
    return None if x is None else round(x, nd)


# --------------------------------------------------------------------------- etichette e feature

def barrier_params(proposal: dict, side: int, feats: Optional[dict]) -> tuple:
    entry, stop, target = _n(proposal.get("entry")), _n(proposal.get("stop")), _n(proposal.get("target"))
    if entry and stop and entry > 0 and abs(entry - stop) > 0 and ((side == 1 and stop < entry) or (side == -1 and stop > entry)):
        sp = abs(entry - stop) / entry
        tp = abs(target - entry) / entry if target and ((side == 1 and target > entry) or (side == -1 and target < entry)) else TARGET_R * sp
        return sp, tp, "proposal"
    atr = (feats or {}).get("atr_pct14")
    if atr:
        return ATR_K * atr, TARGET_R * ATR_K * atr, "atr_default"
    return None, None, "none"


def make_labels(store, symbol: str, ts: int, side: int, proposal: dict, feats: Optional[dict], cost_bp: float) -> tuple:
    if store is None or not store.has(symbol):
        return {"status": "no_candles"}, False
    sides = [side] if side in (1, -1) else [1, -1]
    out, complete = {}, True
    for sd in sides:
        sp, tp, src = barrier_params(proposal if side else {}, sd, feats)
        hz = L.forward_returns(store, symbol, ts, sd, cost_bp)
        bar = (L.barrier(store, symbol, ts, sd, sp, tp, MAX_HOLD_MS, cost_bp) if sp
               else {"first": "incomplete", "complete": False})
        bar["barrier_source"] = src
        out["long" if sd == 1 else "short"] = {"horizons": hz, "barrier": bar}
        complete = complete and all(v["complete"] for v in hz.values()) and bool(bar.get("complete"))
    return {"status": "ok", "cost_bp": cost_bp, "sides": out, "directional": side in (1, -1)}, complete


def get_features(store, symbol: str, ts: int, logged: Optional[dict]) -> tuple:
    if logged:
        return logged, "logged_at_decision"
    if store is not None:
        f = F.compute_features(store, symbol, ts)
        if f:
            return f, "reconstructed_from_candles"
    return None, "none"


# --------------------------------------------------------------------------- riga

class Ctx:
    def __init__(self, inp: dict, store, cost_bp: float):
        self.inp, self.store, self.cost = inp, store, cost_bp
        self.rows: list = []
        self.stats: Counter = Counter()

    def add(self, run: str, kind: str, key: str, ts: int, symbol: str, action: str, proposal: dict, outcome: dict,
            logged_features: Optional[dict], extra_prov: Optional[dict] = None) -> None:
        side = 1 if action == "LONG" else -1 if action == "SHORT" else 0
        feats, fsrc = get_features(self.store, symbol, ts, logged_features)
        lab, complete = make_labels(self.store, symbol, ts, side, proposal, feats, self.cost)
        if outcome["status"] != "not_executed" and outcome.get("mfe_mae_source") == "none" and self.store is not None:
            m = L.mfe_mae_r(self.store, symbol, side, _n(proposal.get("entry")) or 0, _n(proposal.get("stop")) or 0,
                            outcome.get("opened_ms") or ts, outcome.get("closed_ms") or ts)
            if m and outcome["status"] == "closed":
                outcome.update(m)
                outcome["mfe_mae_source"] = "reconstructed_from_candles"
        row = {"schema_version": S.SCHEMA_VERSION, "example_id": S.example_id(self.inp["source_system"], run, kind, key),
               "source_system": self.inp["source_system"], "source_run": run, "source_kind": self.inp["kind"],
               "record_kind": kind, "decision_ts_ms": ts, "decision_day": S.utc_day(ts), "symbol": symbol, "action": action,
               "side": side, "executed": kind == "executed", "features": feats, "feature_source": fsrc,
               "feature_asof_ms": (feats or {}).get("asof_candle_open_ms"), "proposal": proposal, "outcome": outcome,
               "labels": lab, "label_complete": complete, "is_synthetic": False,
               "provenance": {"input_id": self.inp["id"], "builder_version": S.BUILDER_VERSION, "feature_set": F.FEATURE_SET,
                              "inputs_verified": bool(self.inp.get("verified")), **(extra_prov or {})}}
        errs = S.validate_row(row)
        if errs:
            self.stats["invalid_rows_skipped"] += 1
            self.stats["invalid:" + errs[0].split(":")[0]] += 1
            return
        self.rows.append(row)


def not_executed() -> dict:
    return {"status": "not_executed", "net_pnl": None, "closed_ms": None, "mfe_mae_source": "none", "is_manual": False}


# --------------------------------------------------------------------------- classici (Falco / Toro)

def _classic_outcome(open_ev: Optional[dict], recs: Optional[list]) -> dict:
    if not recs:
        return {"status": "open_censored", "net_pnl": None, "closed_ms": None, "mfe_mae_source": "none", "is_manual": False,
                "opened_ms": R._int((open_ev or {}).get("ts"))}
    recs = sorted(recs, key=lambda r: R._int(r.get("close_ms")) or 0)
    last = recs[-1]
    nets = [_n(r.get("net")) for r in recs]
    nr = [_n(r.get("net_r")) for r in recs]
    exit_reason = R.map_exit_reason(last.get("why") or last.get("reason"))
    manual = any(R.map_exit_reason(r.get("why") or r.get("reason")) == "manual" for r in recs)
    opened = R._int(last.get("open_ms")) or R._int((open_ev or {}).get("ts"))
    closed = R._int(last.get("close_ms"))
    mfe = next((_n(r.get("mfe_r")) for r in reversed(recs) if r.get("mfe_r") is not None), None)
    mae = next((_n(r.get("mae_r")) for r in reversed(recs) if r.get("mae_r") is not None), None)
    return {"status": "closed", "net_pnl": _round(sum(x for x in nets if x is not None), 4), "closed_ms": closed,
            "opened_ms": opened, "hold_ms": (closed - opened) if closed and opened else None,
            "net_r": _round(sum(x for x in nr if x is not None), 4) if any(x is not None for x in nr) else None,
            "fees": _round(sum(_n(r.get("fees")) or 0 for r in recs), 4),
            "funding": _round(sum(_n(r.get("funding")) or 0 for r in recs), 4),
            "funding_known": any(r.get("funding") is not None for r in recs),
            "exit_reason": exit_reason, "exit_reason_code": S.short_code(last.get("why") or last.get("reason")),
            "is_manual": manual, "partials": len(recs),
            "mfe_r": mfe, "mae_r": mae, "mfe_mae_source": "logged" if mfe is not None or mae is not None else "none"}


def build_classic(inp: dict, store, cost_bp: float) -> Ctx:
    cx = Ctx(inp, store, cost_bp)
    d = R.read_classic(inp["path"])
    cx.stats.update({"reader:" + k: v for k, v in d["stats"].items()})
    used = set()
    for (run, i), ev in sorted(d["opens"].items(), key=lambda kv: (str(kv[0][0]), kv[0][1])):
        ts, side, sym = R._int(ev.get("ts")), R._side(ev.get("side")), ev.get("symbol")
        if not ts or not side or not sym:
            cx.stats["open_skipped_incomplete"] += 1
            continue
        used.add((run, i))
        proposal = {"entry": _n(ev.get("entry") or ev.get("price")), "stop": _n(ev.get("sl")), "target": _n(ev.get("tp")),
                    "leverage": _n(ev.get("leverage")), "confidence": _n(ev.get("confidence")),
                    "decider": S.short_code(ev.get("source")), "trade_type": S.short_code(ev.get("trade_type"))}
        cx.add(f"run{run}", "executed", i, ts, str(sym), "LONG" if side == 1 else "SHORT", proposal,
               _classic_outcome(ev, d["closes"].get((run, i))), R.sanitize_features(ev.get("features")) or None,
               {"open_logged": True})
    for (run, i), recs in sorted(d["closes"].items(), key=lambda kv: (str(kv[0][0]), kv[0][1])):
        if (run, i) in used:
            continue
        r0 = sorted(recs, key=lambda r: R._int(r.get("close_ms")) or 0)[0]
        ts, side, sym = R._int(r0.get("open_ms")), R._side(r0.get("side")), r0.get("symbol")
        if not ts or not side or not sym:
            cx.stats["close_without_open_skipped"] += 1
            continue
        cx.add(f"run{run}" if run is not None else "run_unknown", "executed", i, ts, str(sym), "LONG" if side == 1 else "SHORT",
               {"entry": _n(r0.get("entry")), "stop": None, "target": None, "leverage": _n(r0.get("leverage")),
                "confidence": _n(r0.get("confidence")), "decider": S.short_code(r0.get("source")), "trade_type": "unknown"},
               _classic_outcome(None, recs), None, {"open_logged": False, "history_only": True})
    for c in sorted(d["candidates"], key=lambda e: (R._int(e.get("ts")) or 0, str(e.get("symbol")))):
        ts, side, sym = R._int(c.get("ts")), R._side(c.get("side")), c.get("symbol")
        if not ts or not side or not sym:
            cx.stats["candidate_skipped_incomplete"] += 1
            continue
        status = str(c.get("status") or "")
        code = S.short_code(status.split(":", 1)[1] if ":" in status else status)
        cx.add(f"run{c.get('run_no', 1)}", "candidate_rejected", f"{ts}:{sym}:{side}", ts, str(sym),
               "LONG" if side == 1 else "SHORT", {"entry": _n(c.get("price")), "stop": None, "target": None, "reject_code": code},
               not_executed(), R.sanitize_features(c.get("features")) or None)
    cx.stats["other_event_kinds"] = len(d["other_events"])
    return cx


# --------------------------------------------------------------------------- journal V3 (Arena, Brain V3)

def build_v3(inp: dict, store, cost_bp: float) -> Ctx:
    cx = Ctx(inp, store, cost_bp)
    d = R.read_v3(inp["path"])
    cx.stats.update({"reader:" + k: v for k, v in d["stats"].items()})
    by_decision: dict = {}
    for pid, o in d["opens"].items():
        by_decision.setdefault(str(o["p"].get("decision_event_id") or ""), []).append(pid)

    def outcome_for(pid: str, o: dict) -> dict:
        c = d["closes"].get(pid)
        if c is None:
            return {"status": "open_censored", "net_pnl": None, "closed_ms": None, "opened_ms": o["ts"],
                    "mfe_mae_source": "none", "is_manual": False}
        p = c["p"]
        fill, stop, qty = _n(o["p"].get("fill_price")), _n(o["p"].get("stop_price")), _n(o["p"].get("quantity"))
        risk = abs(fill - stop) * qty if fill and stop and qty else None
        pnl = _n(p.get("realized_pnl"))
        reason = R.map_exit_reason(p.get("reason"))
        return {"status": "closed", "net_pnl": pnl, "closed_ms": c["ts"], "opened_ms": o["ts"], "hold_ms": R._int(p.get("held_ms")),
                "net_r": _round(pnl / risk, 4) if risk and pnl is not None else None, "fees": _n(p.get("fees")),
                "funding": None, "funding_known": False, "exit_reason": reason, "exit_reason_code": S.short_code(p.get("reason")),
                "is_manual": reason == "manual", "partials": 1, "mfe_r": None, "mae_r": None, "mfe_mae_source": "none",
                "loss_exceeds_margin": bool(p.get("loss_exceeds_margin"))}

    def proposal_for(o: dict, dec: Optional[dict]) -> dict:
        p = o["p"]
        return {"entry": _n(p.get("fill_price")), "stop": _n(p.get("stop_price")), "target": None, "leverage": _n(p.get("leverage")),
                "confidence": None, "decider": S.short_code(p.get("originating_ai")),
                "strategy_id": S.short_code((dec or {}).get("strategy_id")) if (dec or {}).get("strategy_id") else None,
                "regime": S.short_code((dec or {}).get("regime")) if (dec or {}).get("regime") else None}

    linked = set()
    for eid, dec in sorted(d["decisions"].items(), key=lambda kv: (kv[1]["ts"], kv[0])):
        sym = str(dec.get("symbol") or "")
        kind, status = str(dec.get("kind") or ""), str(dec.get("status") or "")
        pids = by_decision.get(eid, [])
        for pid in pids:
            o = d["opens"][pid]
            side = R._side(o["p"].get("side"))
            if side and sym:
                linked.add(pid)
                cx.add(o["run"], "executed", pid, dec["ts"], sym, "LONG" if side == 1 else "SHORT", proposal_for(o, dec),
                       outcome_for(pid, o), None, {"link_status": "linked"})
        if pids:
            continue
        if kind == "NO_TRADE" and sym:
            cx.add(dec["run"], "no_trade", eid, dec["ts"], sym, "NO_TRADE", {"entry": None, "stop": None, "target": None,
                   "regime": S.short_code(dec.get("regime")) if dec.get("regime") else None}, not_executed(), None)
        elif kind == "OPEN" and sym:
            code = "approved_not_executed" if status == "APPROVED" else S.short_code(status)
            cx.add(dec["run"], "candidate_rejected", eid, dec["ts"], sym, "OPEN_REJECTED",
                   {"entry": None, "stop": None, "target": None, "reject_code": code}, not_executed(), None)
        else:
            cx.stats["non_entry_decisions"] += 1
    for pid, o in sorted(d["opens"].items(), key=lambda kv: (kv[1]["ts"], kv[0])):
        if pid in linked:
            continue
        side, sym = R._side(o["p"].get("side")), o["p"].get("symbol")
        if side and sym:
            did = str(o["p"].get("decision_event_id") or "")
            cx.add(o["run"], "executed", pid, o["ts"], str(sym), "LONG" if side == 1 else "SHORT", proposal_for(o, None),
                   outcome_for(pid, o), None, {"link_status": "dangling" if did else "unlinked"})
        else:
            cx.stats["open_skipped_incomplete"] += 1
    return cx


# --------------------------------------------------------------------------- Brain storico (formato tollerante)

def build_brain_free(inp: dict, store, cost_bp: float) -> Ctx:
    cx = Ctx(inp, store, cost_bp)
    d = R.read_brain_free(inp["path"])
    cx.stats.update({"reader:" + k: v for k, v in d["stats"].items()})
    inputs = sorted(d["ai_inputs"], key=lambda x: x["ts"] or 0)

    def nearest_input(ts: int) -> Optional[dict]:
        best = None
        for x in inputs:
            if x["ts"] and x["ts"] <= ts and ts - x["ts"] <= NEAREST_INPUT_MS:
                best = x
        return R.sanitize_features(best["features"]) if best else None

    open_ts: dict = {}
    for key, o in sorted(d["opens"].items(), key=lambda kv: (kv[1]["ts"] or 0, str(kv[0]))):
        ep, sym, pid = key
        if not o["ts"] or not o["side"] or not o["symbol"]:
            cx.stats["open_skipped_incomplete"] += 1
            continue
        open_ts.setdefault(sym, []).append(o["ts"])
        c = d["closed"].get(key)
        if c is None:
            out = {"status": "open_censored", "net_pnl": None, "closed_ms": None, "opened_ms": o["ts"], "mfe_mae_source": "none",
                   "is_manual": False}
        else:
            reason = R.map_exit_reason(c["reason_raw"])
            out = {"status": "closed", "net_pnl": _round(c["net"], 4), "closed_ms": c["ts"], "opened_ms": o["ts"],
                   "hold_ms": (c["ts"] - o["ts"]) if c["ts"] else None, "net_r": None, "fees": c["fees"], "funding": c["funding"],
                   "funding_known": c["funding"] is not None, "exit_reason": reason, "exit_reason_code": S.short_code(c["reason_raw"]),
                   "is_manual": reason == "manual", "partials": 1 + len(d["partials"].get(key, [])),
                   "mfe_r": c["mfe_r"], "mae_r": c["mae_r"],
                   "mfe_mae_source": "logged" if c["mfe_r"] is not None or c["mae_r"] is not None else "none"}
            if out["net_pnl"] is None:
                cx.stats["closed_without_net"] += 1
                continue
        cx.add(f"epoch{ep}", "executed", f"{sym}:{pid}", o["ts"], str(sym), "LONG" if o["side"] == 1 else "SHORT",
               {"entry": o["entry"], "stop": o["stop"], "target": o["target"], "leverage": o["leverage"], "confidence": None,
                "decider": "brain_free"}, out, nearest_input(o["ts"]), {"schema_unverified": True})
    for x in d["ai_decisions"]:
        if x["action"] in ("hold", "no_trade", "none", "wait", "flat", "skip") and x["ts"] and x["symbol"]:
            if any(abs(t - x["ts"]) <= 300_000 for t in open_ts.get(x["symbol"], [])):
                continue                                         # coperta dalla riga eseguita
            cx.add("epoch_any", "no_trade", f"{x['ts']}:{x['symbol']}", x["ts"], str(x["symbol"]), "NO_TRADE",
                   {"entry": None, "stop": None, "target": None}, not_executed(), nearest_input(x["ts"]), {"schema_unverified": True})
    for x in d["rejects"]:
        if x["ts"] and x["symbol"]:
            act = "LONG" if x["side"] == 1 else "SHORT" if x["side"] == -1 else "OPEN_REJECTED"
            cx.add("epoch_any", "candidate_rejected", f"{x['ts']}:{x['symbol']}:{x['side']}", x["ts"], str(x["symbol"]), act,
                   {"entry": None, "stop": None, "target": None, "reject_code": x["reason"]}, not_executed(),
                   nearest_input(x["ts"]), {"schema_unverified": True})
    cx.stats["keys_seen_kinds"] = len(d["keys_seen"])
    cx.keys_seen = d["keys_seen"]
    return cx


BUILDERS = {"classic": build_classic, "v3": build_v3, "brain_free": build_brain_free}


# --------------------------------------------------------------------------- orchestrazione

def dedup_key(r: dict) -> Optional[str]:
    o, p = r["outcome"], r["proposal"]
    if r["record_kind"] != "executed" or not o.get("opened_ms") or not p.get("entry"):
        return None
    return hashlib.sha256(f"{r['symbol']}|{r['side']}|{o['opened_ms'] // 60000}|{round(p['entry'], 4)}".encode()).hexdigest()[:24]


def build(spec: dict, candles_dir: Optional[str] = None, cost_bp: float = COST_BP) -> dict:
    store = C.CandleStore(candles_dir) if candles_dir else None
    rows, per_input, keys_seen = [], {}, {}
    seen_ids: dict = {}
    seen_trades: dict = {}
    dup_ids = dup_trades = 0
    for inp in spec["inputs"]:
        if inp["source_system"] not in S.SOURCES or inp["kind"] not in BUILDERS:
            raise ValueError("bad_input_spec")
        cx = BUILDERS[inp["kind"]](inp, store, cost_bp)
        keep = []
        for r in cx.rows:
            if r["example_id"] in seen_ids:
                dup_ids += 1
                continue
            seen_ids[r["example_id"]] = True
            k = dedup_key(r)
            if k and k in seen_trades:
                r["provenance"]["duplicate_of"] = seen_trades[k]
                dup_trades += 1
            elif k:
                seen_trades[k] = r["example_id"]
            keep.append(r)
        rows += keep
        per_input[inp["id"]] = {"source_system": inp["source_system"], "kind": inp["kind"], "rows": len(keep),
                                "verified": bool(inp.get("verified")), "stats": dict(sorted(cx.stats.items())),
                                "files": {os.path.basename(f): sha_file(f) for f in input_files(inp)}}
        if hasattr(cx, "keys_seen"):
            keys_seen[inp["id"]] = cx.keys_seen
    rows.sort(key=lambda r: (r["decision_ts_ms"], r["example_id"]))
    verified = {i["id"] for i in spec["inputs"] if i.get("verified")}
    return {"rows": rows, "per_input": per_input, "verified": verified, "keys_seen": keys_seen,
            "duplicate_example_ids": dup_ids, "duplicate_trades_flagged": dup_trades,
            "candle_stats": store.stats if store else None}


def summarize(res: dict) -> dict:
    rows = res["rows"]
    c = lambda f: dict(sorted(Counter(f(r) for r in rows).items()))  # noqa: E731
    ex = [r for r in rows if r["executed"]]
    return {"schema_version": S.SCHEMA_VERSION, "builder_version": S.BUILDER_VERSION, "classification": "NUMBERS_ONLY",
            "rows": len(rows), "by_source": c(lambda r: r["source_system"]), "by_record_kind": c(lambda r: r["record_kind"]),
            "by_action": c(lambda r: r["action"]), "by_outcome": c(lambda r: r["outcome"]["status"]),
            "feature_source": c(lambda r: r["feature_source"]), "label_complete": c(lambda r: r["label_complete"]),
            "executed": len(ex), "losses": sum(1 for r in ex if (r["outcome"].get("net_pnl") or 0) < 0),
            "wins": sum(1 for r in ex if (r["outcome"].get("net_pnl") or 0) > 0),
            "manual_closes": sum(1 for r in ex if r["outcome"].get("is_manual")),
            "funding_known": sum(1 for r in ex if r["outcome"].get("funding_known")),
            "mfe_mae_source": c(lambda r: r["outcome"].get("mfe_mae_source", "none")),
            "duplicates_flagged": res["duplicate_trades_flagged"], "duplicate_example_ids": res["duplicate_example_ids"],
            "days": len({r["decision_day"] for r in rows}), "sufficiency": SU.report(rows, res["verified"])}


def _write_new(path: str, data: bytes, mode: int) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)
    os.chmod(path, mode)


def write_outputs(res: dict, out_dir: str) -> dict:
    out = os.path.abspath(out_dir)
    parent = os.path.dirname(out)
    if not os.path.isdir(parent) or os.path.realpath(parent) != parent:
        raise ValueError("out_parent_missing_or_symlink")
    if os.path.lexists(out):
        raise FileExistsError("out_exists")
    if inside_repo(out):
        raise ValueError("out_inside_git_worktree")
    os.mkdir(out, 0o700)
    body = "".join(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n" for r in res["rows"]).encode()
    digest = hashlib.sha256(body).hexdigest()
    _write_new(os.path.join(out, "examples.jsonl"), body, 0o600)
    summary = summarize(res)
    manifest = {"classification": "PRIVATE_DO_NOT_COMMIT", "examples_sha256": digest, "summary": summary,
                "per_input": res["per_input"], "candle_stats": res["candle_stats"], "keys_seen_unverified_schemas": res["keys_seen"]}
    _write_new(os.path.join(out, "manifest.json"), json.dumps(manifest, indent=1, sort_keys=True).encode(), 0o600)
    _write_new(os.path.join(out, "public_summary.json"),
               json.dumps({**summary, "examples_sha256": digest}, indent=1, sort_keys=True).encode(), 0o644)
    return {"examples_sha256": digest, "rows": len(res["rows"])}


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--spec", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--candles")
    ap.add_argument("--cost-bp", type=float, default=COST_BP)
    a = ap.parse_args(argv)
    with open(a.spec, encoding="utf-8") as fh:
        spec = json.load(fh)
    try:
        res = build(spec, a.candles, a.cost_bp)
        info = write_outputs(res, a.out)
    except (ValueError, OSError) as exc:
        print(f"NO-GO: {type(exc).__name__}: {str(exc)[:80]}")
        return 1
    print(f"GO: rows={info['rows']} sha256={info['examples_sha256']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
