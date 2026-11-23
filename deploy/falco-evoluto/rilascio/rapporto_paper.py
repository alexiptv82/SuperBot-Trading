"""Rapporto operativo PAPER (SOLA LETTURA) di Falco Evoluto, Brain Scalp e Brain RC1.

Copia journal.db e budget.db con sqlite in modalita' ro in una cartella temporanea e lavora SOLO sulle copie:
nessuna scrittura nelle run, nessun servizio toccato, nessuna rete. Stampa codici e importi PAPER, mai segreti,
mai il nome di chi ha approvato il mandato.
Uso (root): PYTHONPATH=<codice installato> <venv>/python3 -I rapporto_paper.py
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time
from collections import Counter
from decimal import Decimal as D
from pathlib import Path

DEFAULT_PARENT = "/opt/superbot-v3-paper-runs"
PARENT = Path(os.environ.get("RAPPORTO_PARENT", DEFAULT_PARENT))  # override solo per i test
RUNS = [("falco", "brain-v3-falco-evoluto-p1", "falco-evoluto-paper-p1"),
        ("scalp", "brain-v3-brain-scalp-p1", "brain-scalp-paper-p1"),
        ("rc1", "brain-v3-unico-paper-rc1", None)]
UTC = "%Y-%m-%d %H:%M:%S"


def ts(ms):
    return "-" if not ms else time.strftime(UTC, time.gmtime(ms / 1000)) + "Z"


def copy_db(src: Path, dst: Path) -> bool:
    if not src.is_file():
        return False
    s = sqlite3.connect(f"file:{src}?mode=ro", uri=True, timeout=10)
    d = sqlite3.connect(str(dst))
    with d:
        s.backup(d)
    s.close()
    d.close()
    return True


def snapshot(name: str, src: Path, tmp: Path) -> Path:
    dst = tmp / name
    dst.mkdir()
    for f in ("journal.db", "budget.db"):
        copy_db(src / f, dst / f)
    for f in ("runner_config.json", "heartbeat.json", "exit_heartbeat.json", "daily_loss.json"):
        if (src / f).is_file():
            shutil.copy(src / f, dst / f)
    return dst


def report(key: str, dirname: str, run_id, tmp: Path, now_ms: int) -> None:
    from backend.v3.compare_view import RunRef, read_run
    from backend.v3.events import EventJournal
    src = PARENT / dirname
    print(f"\n===== {key} ({dirname})")
    if not src.is_dir():
        print("RUN ASSENTE")
        return
    pause = src / "pause.flag"
    print("pausa:", "ATTIVA dal " + ts(int(pause.stat().st_mtime * 1000)) if pause.exists() else "no")
    try:
        m = json.loads((src / "mandate.json").read_text())
        print("mandato approved:", m.get("approved"), "| approvato alle:", m.get("approved_at") or m.get("approved_at_ms") or "-")
    except (OSError, ValueError):
        print("mandato: illeggibile")
    snap = snapshot(key, src, tmp)
    j = EventJournal(str(snap / "journal.db"))
    count, head = j.verify_chain()
    print(f"journal: catena VERIFICATA, {count} eventi, testa {str(head)[:16]}")
    con = sqlite3.connect(str(snap / "journal.db"))
    ids = [r[0] for r in con.execute("SELECT DISTINCT run_id FROM v3_events")]
    con.close()
    run_id = run_id or (ids[0] if len(ids) == 1 else None)
    print("run_id nel journal:", ids)
    if run_id and run_id not in ids:
        print("ATTENZIONE: RUN_ID ATTESO ASSENTE NEL JOURNAL:", run_id)
    if not run_id:
        return
    rows = j.list_run("brain", run_id)
    kinds = Counter(r.event.kind for r in rows)
    print("eventi per tipo:", dict(sorted(kinds.items())))
    for f in ("heartbeat.json", "exit_heartbeat.json", "daily_loss.json"):
        try:
            h = json.loads((snap / f).read_text())
            keep = {k: h.get(k) for k in ("state", "last_error", "ts_ms", "health", "halt_latched", "warn") if k in h}
            print(f"{f}:", keep)
        except (OSError, ValueError):
            print(f"{f}: assente")

    pause_ms = int(pause.stat().st_mtime * 1000) if pause.exists() else None
    cfg = json.loads((snap / "runner_config.json").read_text())
    rp = cfg.get("risk_policy", {})
    eq0 = D(cfg.get("initial_equity", "0"))

    print("-- decisioni (ora UTC | simbolo | tipo | stato | motivo | rischio | fonti)")
    dec = [r for r in rows if r.event.kind == "brain_decision"]
    for r in dec[-60:]:
        p = r.event.payload
        print(" ", ts(r.event.occurred_at_ms), p.get("symbol"), p.get("kind"), p.get("status"),
              str(p.get("rationale", ""))[:60], p.get("risk_reason") or "-", ",".join(p.get("sources") or []) or "-")
    per_sym = Counter((r.event.payload.get("symbol"), r.event.payload.get("kind")) for r in dec)
    print("decisioni per simbolo/tipo:", {f"{s}:{k}": n for (s, k), n in sorted(per_sym.items(), key=str)})
    nmr = sum("no_market_rules" in json.dumps(r.event.payload) for r in rows)
    print("eventi con no_market_rules:", nmr)

    print("-- aperture (ora | simbolo | lato | leva | margine | nozionale | perdita allo stop | % equity | origine)")
    opens = [r for r in rows if r.event.kind == "paper_open"]
    for r in opens:
        p = r.event.payload
        fill, stop, qty = D(p["fill_price"]), D(p["stop_price"]), D(p["quantity"])
        loss = abs(fill - stop) * qty
        lev, mar = int(p.get("leverage", 0)), D(p["margin_used"])
        flags = []
        if key != "rc1":
            if not int(rp.get("min_leverage", 0)) <= lev <= int(rp.get("max_leverage", 999)):
                flags.append("LEVA_FUORI_LIMITE")
            if rp.get("min_margin_usd") and not D(rp["min_margin_usd"]) <= mar <= D(rp["max_margin_usd"]):
                flags.append("MARGINE_FUORI_LIMITE")
            if loss > eq0 * D(rp.get("max_loss_fraction", "1")) * D("1.01"):
                flags.append("RISCHIO_OLTRE_4%")
        if pause_ms and r.event.occurred_at_ms > pause_ms:
            flags.append("APERTA_DOPO_LA_PAUSA")
        print(" ", ts(r.event.occurred_at_ms), p.get("symbol"), "LONG" if p.get("side") == 1 else "SHORT", f"{lev}x",
              mar, p.get("notional"), loss.quantize(D("0.01")), (loss / eq0 * 100).quantize(D("0.01")) if eq0 else "-",
              p.get("originating_ai"), " ".join(flags) or "OK")
    closes = [r for r in rows if r.event.kind == "paper_close"]
    for r in closes:
        p = r.event.payload
        print("  chiusura", ts(r.event.occurred_at_ms), p.get("symbol"), p.get("reason"), p.get("stop_kind") or "-",
              "pnl", p.get("realized_pnl"))

    if key == "rc1":
        after = [r for r in rows if pause_ms and r.event.occurred_at_ms > pause_ms and r.event.kind in
                 ("paper_open", "brain_decision")]
        print("RC1 eventi decisione/apertura dopo la pausa:", len(after))
        return

    g = [r for r in rows if r.event.kind == "guardian_state"]
    print(f"-- Guardian: {len(g)} stati registrati, sequenza:",
          [r.event.payload.get("state") for r in g][-12:])
    if g:
        p = g[-1].event.payload
        print("   ultimo:", ts(g[-1].event.occurred_at_ms), {k: p.get(k) for k in (
            "state", "reasons", "armed", "session_start_equity", "equity", "peak_equity", "floor", "budget",
            "r_unit", "risk_cap", "open_risk", "giveback", "global_drawdown", "ai_cost_session")})
    snaps = kinds.get("brain_decision_snapshot_v2", 0)
    print(f"-- memoria: snapshot v2 = {snaps} per {len(dec)} decisioni")

    v = read_run(RunRef(name=key, label=key, run_id=run_id, dir=snap), now_ms)
    print("-- vista del confronto (stessa funzione della dashboard):")
    for k in ("available", "state", "settled_equity", "net_pnl", "ai_cost_total", "net_after_ai", "mtm_samples",
              "mtm_incomplete", "mtm_drawdown", "closed", "wins", "losses", "fees"):
        print(f"   {k}: {v.get(k)}")
    op = v.get("open_positions") or []
    tm = sum(D(o["margin"]) for o in op)
    print(f"   posizioni aperte: {len(op)} | margine totale {tm} = "
          f"{(tm / eq0 * 100).quantize(D('0.1')) if eq0 else '-'}% (limite 50%)")
    for o in op:
        print("   ", o["symbol"], "LONG" if o["side"] == 1 else "SHORT", f"{o['leverage']}x", "margine", o["margin"],
              "entrata", o["entry"], "stop", o["stop"], "dal", ts(o["opened_at_ms"]))
    print("   spesa AI:", v.get("ai_spend"))


def main() -> None:
    if str(PARENT) == DEFAULT_PARENT and os.geteuid() != 0:
        sys.exit("serve root (le run sono 0700)")
    now_ms = int(time.time() * 1000)
    print("RAPPORTO PAPER (sola lettura) generato", ts(now_ms))
    tmp = Path(tempfile.mkdtemp(prefix="rapporto-paper-"))
    try:
        for key, d, rid in RUNS:
            try:
                report(key, d, rid, tmp, now_ms)
            except Exception as exc:  # noqa: BLE001
                print(f"ERRORE nel rapporto di {key}: {type(exc).__name__}: {str(exc)[:160]}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("\nFINE RAPPORTO")


if __name__ == "__main__":
    main()
