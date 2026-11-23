"""Audit del freno di perdita giornaliera di una run PAPER (sola lettura; root perche' le run sono 0700).

Uso: PYTHONPATH=<codice installato> <python della stage> audit_freno.py [--bot scalp|falco] [--giorno AAAA-MM-GG]

Non scrive nulla nella run: journal e budget sono copiati con ``sqlite3 mode=ro`` in una cartella temporanea (catena di
hash verificata sulla copia), i file JSON sono solo letti. Unica rete: le candele 1m pubbliche di Bitget, con la stessa
funzione del runner (``fetch_closed_bars``). Ricostruisce minuto per minuto la perdita di oggi con la formula del runner
(``daily_loss.py``: realizzato del giorno UTC + non realizzato delle posizioni aperte, chiusura del minuto contro il
prezzo d'ingresso, sul capitale d'inizio giornata) e la confronta con ``max_daily_loss_between`` del codice in uso.
Stampa: aperture e chiusure del giorno, minuto in cui la perdita ha toccato avviso e stop, contributo di ogni posizione
e distanza dallo stop in quel minuto, stato del freno su disco, Guardian del giorno, aperture o decisioni dopo il blocco.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time
from decimal import Decimal as D
from pathlib import Path

RUNS = {"scalp": ("brain-v3-brain-scalp-p1", "brain-scalp-paper-p1"),
        "falco": ("brain-v3-falco-evoluto-p1", "falco-evoluto-paper-p1")}
PARENT = Path(os.environ.get("AUDIT_PARENT", "/opt/superbot-v3-paper-runs"))
MIN = 60_000


def _pc(x) -> str:
    return f"{(x * 100).normalize():f}"


DAY = 86_400_000


def ts(ms: int) -> str:
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).strftime("%H:%M:%S")


def copy_db(src: Path, dst: Path) -> None:
    s = sqlite3.connect(f"file:{src}?mode=ro", uri=True, timeout=10)
    d = sqlite3.connect(str(dst))
    with d:
        s.backup(d)
    s.close()
    d.close()


def series(opens: dict, closes: dict, start_eq: D, day: int, first: int, last: int, prices: dict):
    """[(minuto E, perdita, frazione, {pid: (non realizzato, prezzo)})] con la formula del runner."""
    out = []
    for e in range(first, last + 1, MIN):
        realized = sum((pnl for t, pnl in closes.values() if day <= t <= e), D(0))
        parts, unreal = {}, D(0)
        for pid, (sym, side, fill, qty, t_open, stop) in opens.items():
            c = closes.get(pid)
            if t_open <= e and (c is None or c[0] > e):
                px = prices.get(sym, {}).get(e - MIN)
                if px is None:
                    parts[pid] = (None, None)
                    unreal = None
                    break
                u = (px - fill) * qty * side
                parts[pid] = (u, px)
                unreal += u
        if unreal is None:
            out.append((e, None, None, parts))
            continue
        loss = max(-(realized + unreal), D(0))
        out.append((e, loss, loss / start_eq, parts))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bot", default="scalp", choices=sorted(RUNS))
    ap.add_argument("--giorno", help="giorno UTC AAAA-MM-GG (predefinito: oggi)")
    a = ap.parse_args(argv)
    if str(PARENT) == "/opt/superbot-v3-paper-runs" and os.geteuid() != 0:
        sys.exit("serve root (le run sono 0700)")
    from backend.v3.dashboard import build_summary
    from backend.v3.events import EventJournal
    from backend.v3.runner.config import load_runner_config
    from backend.v3.runner.daily_loss import max_daily_loss_between
    from backend.v3.runner.feed import fetch_closed_bars
    from backend.v3.lab_tools.fetch_candles import http_json

    dirname, run_id = RUNS[a.bot]
    src = PARENT / dirname
    now = int(time.time() * 1000)
    day = (int(dt.datetime.strptime(a.giorno, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc).timestamp() * 1000)
           if a.giorno else now // DAY * DAY)
    end = min(now, day + DAY)
    print(f"AUDIT FRENO GIORNALIERO (sola lettura) {a.bot} giorno UTC {dt.datetime.fromtimestamp(day / 1000, dt.timezone.utc):%Y-%m-%d}")
    cfg = load_runner_config((src / "runner_config.json").read_bytes())
    print(f"configurazione in uso: avviso {_pc(cfg.daily_loss_warn)} %, stop {_pc(cfg.daily_loss_halt)} %, "
          f"capitale {cfg.initial_equity}, floor {cfg.risk_policy.minimum_equity}")
    for f in ("daily_loss.json", "heartbeat.json"):
        try:
            print(f"{f}:", json.loads((src / f).read_text()))
        except (OSError, ValueError):
            print(f"{f}: assente o illeggibile")
    tmp = Path(tempfile.mkdtemp(prefix="audit-freno-"))
    try:
        copy_db(src / "journal.db", tmp / "journal.db")
        j = EventJournal(str(tmp / "journal.db"))
        count, head = j.verify_chain()
        print(f"journal (copia ro): catena VERIFICATA, {count} eventi, testa {str(head)[:16]}")
        rows = j.list_run("brain", run_id)
        opens, closes = {}, {}
        print("-- aperture e chiusure (ora UTC | simbolo | lato | ingresso | stop | qta | perdita stimata allo stop)")
        for se in rows:
            ev, p = se.event, se.event.payload if isinstance(se.event.payload, dict) else {}
            if ev.kind == "paper_open":
                fill, qty, stop = D(str(p["fill_price"])), D(str(p["quantity"])), D(str(p["stop_price"]))
                opens[p["position_id"]] = (p["symbol"], int(p["side"]), fill, qty, ev.occurred_at_ms, stop)
                if ev.occurred_at_ms >= day - 2 * DAY:
                    print(f"  APRE   {ts(ev.occurred_at_ms)} {p['symbol']} {'LONG' if p['side'] == 1 else 'SHORT'} "
                          f"{fill} stop {stop} qta {qty} leva {p.get('leverage')} margine {p.get('margin_used')} "
                          f"perdita allo stop {(abs(fill - stop) * qty).quantize(D('0.01'))}")
            elif ev.kind == "paper_close":
                closes[p["position_id"]] = (ev.occurred_at_ms, D(str(p.get("realized_pnl"))))
                if ev.occurred_at_ms >= day - 2 * DAY:
                    print(f"  CHIUDE {ts(ev.occurred_at_ms)} {p.get('symbol')} motivo {p.get('reason')} "
                          f"{p.get('stop_kind') or '-'} pnl {p.get('realized_pnl')} prezzo {p.get('exit_price')}")
        before = sum((pnl for t, pnl in closes.values() if t < day), D(0))
        start_eq = cfg.initial_equity + before
        print(f"capitale d'inizio giornata (iniziale + realizzato prima di mezzanotte UTC): {start_eq}")
        first, last = day + MIN, end // MIN * MIN
        need = {}
        for pid, (sym, side, fill, qty, t_open, stop) in opens.items():
            c = closes.get(pid)
            lo = max(first, t_open // MIN * MIN)
            hi = last if c is None else min(last, c[0] // MIN * MIN)
            if lo <= hi:
                span = need.setdefault(sym, [lo, hi])
                span[0], span[1] = min(span[0], lo), max(span[1], hi)
        prices = {}
        for sym, (lo, hi) in need.items():
            prices[sym] = {b.open_time_ms: b.close for b in fetch_closed_bars(sym, lo - MIN, hi, candle_ms=MIN,
                                                                             get_json=http_json)}
        s = series(opens, closes, start_eq, day, first, last, prices)
        missing = [e for e, loss, _, _ in s if loss is None]
        if missing:
            print(f"ATTENZIONE: prezzi mancanti in {len(missing)} minuti (primo {ts(missing[0])}): ricostruzione parziale")
        valid = [x for x in s if x[1] is not None]
        peak = max(valid, key=lambda x: x[2]) if valid else None
        for label, frac in (("avviso", cfg.daily_loss_warn), ("stop", cfg.daily_loss_halt)):
            hit = next((x for x in valid if x[2] >= frac), None)
            if hit is None:
                print(f"{label} ({_pc(frac)} %): mai raggiunto nella ricostruzione")
                continue
            e, loss, fr, parts = hit
            print(f"{label} ({_pc(frac)} %): raggiunto al minuto che termina alle {ts(e)} con perdita "
                  f"{loss.quantize(D('0.01'))} ({fr * 100:.2f} %)")
            for pid, (u, px) in parts.items():
                sym, side, fill, qty, _, stop = opens[pid]
                at_stop = (abs(fill - stop) * qty)
                beyond = (side == 1 and px <= stop) or (side == -1 and px >= stop)
                print(f"    {sym} {'LONG' if side == 1 else 'SHORT'} prezzo {px} non realizzato "
                      f"{u.quantize(D('0.01'))} (perdita allo stop {at_stop.quantize(D('0.01'))}; "
                      f"{'OLTRE LO STOP' if beyond else 'entro lo stop'})")
            real = sum((pnl for t, pnl in closes.values() if day <= t <= e), D(0))
            print(f"    realizzato del giorno fino a quel minuto: {real}")
        if peak:
            print(f"picco ricostruito: {peak[2] * 100:.2f} % alle {ts(peak[0])}; ultimo minuto {ts(valid[-1][0])}: "
                  f"{valid[-1][2] * 100:.2f} %")
        try:
            ref = max_daily_loss_between(journal=j, portfolio_id="brain", run_id=run_id,
                                         initial_equity=cfg.initial_equity, from_ms=day, now_ms=end,
                                         closes_of=lambda sym, lo, hi: {
                                             b.open_time_ms: b.close for b in fetch_closed_bars(
                                                 sym, lo, hi, candle_ms=MIN, get_json=http_json)})
            print(f"controllo con max_daily_loss_between (codice in uso): picco {ref * 100:.2f} % "
                  f"({'COERENTE' if peak and abs(ref - peak[2]) < D('0.0001') else 'DIVERSO: da esaminare'})")
        except Exception as exc:                                   # noqa: BLE001
            print(f"max_daily_loss_between non disponibile: {type(exc).__name__}: {str(exc)[:120]}")
        stop_hit = next((x for x in valid if x[2] >= cfg.daily_loss_halt), None)
        if stop_hit:
            after_open = [se for se in rows if se.event.kind == "paper_open" and se.event.occurred_at_ms > stop_hit[0]]
            after_dec = [se for se in rows if se.event.kind == "brain_decision" and se.event.occurred_at_ms > stop_hit[0]]
            print(f"dopo lo stop delle {ts(stop_hit[0])}: aperture {len(after_open)}, decisioni del modello {len(after_dec)}")
        print("-- Guardian del giorno (ora | stato | motivi | equity | inizio sessione)")
        for se in rows:
            if se.event.kind == "guardian_state" and se.event.occurred_at_ms >= day:
                p = se.event.payload
                print(f"  {ts(se.event.occurred_at_ms)} {p.get('state')} {','.join(p.get('reasons') or []) or '-'} "
                      f"{p.get('equity')} {p.get('session_start_equity')}")
        summ = build_summary(j, "brain", run_id)
        print(f"posizioni aperte ora: {len(summ.open_positions)}; chiusure totali: {len(summ.closed_trades)}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
