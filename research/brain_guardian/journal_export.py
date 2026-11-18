"""Esportazione in SOLA LETTURA del journal PAPER del Brain storico, a livello di singola operazione.

Solo libreria standard (gira con /usr/bin/python3 -I sulla VPS). Non scrive dati nella cartella della run (l'unico
file toccato e' l'indice ``*-shm`` dei database in WAL, che qualunque lettore SQLite aggiorna, e un ``*-wal`` vuoto
se mancava):
1. copia coerente del journal con l'API di backup SQLite (sorgente aperta ``mode=ro``) in una cartella temporanea;
2. lettura della copia; nessun testo libero del modello esportato (solo codici ``[a-z0-9_:.-]``);
3. JSON unico: aperture, chiusure, decisioni aggregate per ora, heartbeat, spesa AI per giorno.

Uso: python3 -I journal_export.py --run-dir /opt/superbot-v3-paper-runs/<run> --run-id <run> --out /root/x.json
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import re
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

SCHEMA = "brain_journal_export_v1"
CODE = re.compile(r"^[A-Za-z0-9_:.\-]{1,64}$")
SYMBOL = re.compile(r"^[A-Z0-9]{2,20}USDT$")


def _code(v):
    return v if isinstance(v, str) and CODE.fullmatch(v) else None


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def consistent_copy(src: Path, dst: Path) -> None:
    source = sqlite3.connect(src.as_uri() + "?mode=ro", uri=True, timeout=30)
    target = sqlite3.connect(dst)
    try:
        source.backup(target)
        target.execute("PRAGMA journal_mode=DELETE")
        if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("integrity_check_failed")
    finally:
        target.close()
        source.close()


def export(run_dir: Path, run_id: str, now_ms: int) -> dict:
    with tempfile.TemporaryDirectory(prefix="brain-export-") as tmp:
        copy = Path(tmp) / "journal.db"
        consistent_copy(run_dir / "journal.db", copy)
        con = sqlite3.connect(copy.as_uri() + "?mode=ro", uri=True)
        try:
            rows = con.execute("SELECT seq, event_id, kind, occurred_at_ms, payload_json FROM v3_events "
                               "WHERE portfolio_id='brain' AND run_id=? ORDER BY seq", (run_id,)).fetchall()
            total = con.execute("SELECT COUNT(*) FROM v3_events").fetchone()[0]
        finally:
            con.close()
        copy_sha = _sha(copy)
    events = [(s, i, k, t, json.loads(p)) for s, i, k, t, p in rows]
    decisions = {i: (t, p) for s, i, k, t, p in events if k == "brain_decision"}
    opens, closes = {}, {}
    for s, i, k, t, p in events:
        if k == "paper_open" and isinstance(p.get("position_id"), str):
            opens[p["position_id"]] = (i, t, p)
        elif k == "paper_close" and isinstance(p.get("position_id"), str):
            closes[p["position_id"]] = (i, t, p)
    trades = []
    for pid, (eid, t, p) in opens.items():
        d = decisions.get(p.get("decision_event_id"))
        dp = d[1] if d else {}
        row = {
            "position_id": pid, "open_event_id": eid, "opened_ms": t,
            "symbol": p.get("symbol") if SYMBOL.fullmatch(str(p.get("symbol"))) else None,
            "side": p.get("side"), "fill_price": p.get("fill_price"), "stop_price": p.get("stop_price"),
            "quantity": p.get("quantity"), "notional": p.get("notional"), "margin_used": p.get("margin_used"),
            "leverage": p.get("leverage"), "slippage_bps": p.get("slippage_bps"),
            "originating_ai": _code(p.get("originating_ai")),
            "decision": None if not d else {
                "decided_ms": d[0], "kind": _code(dp.get("kind")), "status": _code(dp.get("status")),
                "rationale": _code(dp.get("rationale")), "regime": _code(dp.get("regime")),
                "strategy_id": _code(dp.get("strategy_id")), "strategy_origin": _code(dp.get("strategy_origin")),
                "sources": [x for x in (dp.get("sources") or []) if _code(x)][:20],
                "confidence_journaled": "confidence" in dp},
            "close": None,
        }
        c = closes.get(pid)
        if c:
            cp = c[2]
            row["close"] = {"close_event_id": c[0], "closed_ms": c[1], "exit_price": cp.get("exit_price"),
                            "reason": _code(cp.get("reason")), "gross_pnl": cp.get("gross_pnl"),
                            "fees": cp.get("fees"), "realized_pnl": cp.get("realized_pnl"),
                            "fee_bps": cp.get("fee_bps"), "held_ms": cp.get("held_ms"),
                            "notional_exit": cp.get("notional_exit"),
                            "loss_exceeds_margin": cp.get("loss_exceeds_margin")}
        trades.append(row)
    trades.sort(key=lambda r: r["opened_ms"])
    by_hour = collections.Counter()
    for t, p in decisions.values():
        hour = time.strftime("%Y-%m-%dT%H", time.gmtime(t / 1000))
        by_hour[(hour, _code(p.get("kind")), _code(p.get("status")), _code(p.get("rationale")), _code(p.get("regime")))] += 1
    out = {
        "schema": SCHEMA, "generated_at_ms": now_ms, "run_id": run_id,
        "journal_copy_sha256": copy_sha, "events_for_run": len(events), "events_total_in_db": total,
        "first_event_ms": events[0][3] if events else None, "last_event_ms": events[-1][3] if events else None,
        "event_kinds": dict(collections.Counter(k for _, _, k, _, _ in events)),
        "orphan_closes": sorted(set(closes) - set(opens)),
        "trades": trades,
        "decisions_by_hour": [{"hour": h, "kind": k, "status": s, "rationale": r, "regime": g, "n": n}
                              for (h, k, s, r, g), n in sorted(by_hour.items(), key=lambda x: tuple(map(str, x[0])))],
        "heartbeats": {}, "ai_spend_by_day": None,
    }
    for name in ("heartbeat.json", "exit_heartbeat.json"):
        try:
            h = json.loads((run_dir / name).read_text(encoding="utf-8"))
            out["heartbeats"][name] = {k: h.get(k) for k in ("state", "ts_ms", "last_error", "last_cycle",
                                                            "daily_loss_level", "daily_loss_pct", "last_monitor_ms")
                                       if not isinstance(h.get(k), (dict, list))}
        except (OSError, ValueError):
            out["heartbeats"][name] = None
    try:
        b = sqlite3.connect((run_dir / "budget.db").as_uri() + "?mode=ro", uri=True, timeout=5)
        try:
            out["ai_spend_by_day"] = {d: {"calls": n, "usd": round(u / 1e6, 4)} for d, n, u in b.execute(
                "SELECT substr(occurred_at,1,10), COUNT(*), SUM(units) FROM spend_events GROUP BY 1 ORDER BY 1")}
        finally:
            b.close()
    except sqlite3.Error:
        pass
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    out = Path(a.out)
    if out.exists():
        print("BRAIN_EXPORT REFUSED=output_exists")
        return 2
    data = export(Path(a.run_dir), a.run_id, int(time.time() * 1000))
    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, sort_keys=True)
    closed = [t for t in data["trades"] if t["close"]]
    print(f"BRAIN_EXPORT ok trades={len(data['trades'])} closed={len(closed)} open={len(data['trades']) - len(closed)} "
          f"events={data['events_for_run']} sha256={_sha(out)} file={out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
