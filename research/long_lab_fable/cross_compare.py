#!/usr/bin/env python3
"""Confronto OFFLINE Toro (ombra) ↔ Brain: per ogni segnale di Toro, che cosa ha fatto Brain sullo stesso simbolo.

Sola lettura: legge ``osservazioni.jsonl`` di shadow.py, il ``journal.db`` di Brain (SQLite in modalita' ro) e,
se presente, ``proposal_observations.jsonl`` (osservatorio facoltativo delle proposte). Non scrive nulla accanto ai
dati letti, non chiama reti o modelli, non tocca decisioni.

Memoria a tre livelli, tenuti separati nell'uscita:
* ``fatti``: una riga per segnale di Toro con la vista di Brain nella finestra e gli esiti osservati di entrambi;
* ``ipotesi``: per ogni vista di Brain con almeno MIN_N esiti chiusi di Toro, R medio e intervallo al 95%;
* ``regole_validate``: solo le ipotesi confermate su un SECONDO campione successivo (``--validazione-da``), con
  intervallo che esclude lo zero e lo stesso segno nel primo. Nient'altro puo' arrivare a Brain, e solo dopo test
  e autorizzazione.

Uso: python cross_compare.py --toro DIR_OMBRA --journal journal.db --run-id RUN [--proposte FILE]
                             [--validazione-da AAAA-MM-GG] --out risultato.json
"""
from __future__ import annotations

import argparse
import calendar
import json
import math
import sqlite3
import time
from pathlib import Path

DAY = 86_400_000
WINDOW_MS = DAY            # Toro decide alla chiusura giornaliera: si guarda Brain nelle 24 ore successive
MIN_N = 30
VIEWS = ("LONG_aperto", "SHORT_aperto", "LONG_proposto_respinto", "SHORT_proposto_respinto", "NO_TRADE", "non_valutato")


def _day_close_ms(date: str) -> int:
    """Fine della candela giornaliera UTC del giorno di segnale = istante della decisione di Toro."""
    return calendar.timegm(time.strptime(date, "%Y-%m-%d")) * 1000 + DAY


def _brain(journal: Path, run_id: str) -> dict:
    con = sqlite3.connect(Path(journal).resolve().as_uri() + "?mode=ro", uri=True, timeout=3)
    try:
        rows = con.execute("SELECT kind, occurred_at_ms, payload_json FROM v3_events "
                           "WHERE portfolio_id='brain' AND run_id=? ORDER BY seq", (run_id,)).fetchall()
    finally:
        con.close()
    decisions, opens, closes = [], {}, {}
    for kind, ts, raw in rows:
        try:
            p = json.loads(raw)
        except ValueError:
            continue
        if kind == "brain_decision":
            decisions.append((ts, p.get("symbol"), p.get("kind"), p.get("status")))
        elif kind == "paper_open" and isinstance(p.get("position_id"), str):
            opens[p["position_id"]] = (ts, p.get("symbol"), p.get("side"))
        elif kind == "paper_close" and isinstance(p.get("position_id"), str):
            closes[p["position_id"]] = (p.get("realized_pnl"), p.get("reason"))
    return {"decisions": decisions, "opens": opens, "closes": closes}


def _proposals(path: Path | None) -> list:
    if path is None or not Path(path).is_file():
        return []
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if type(r) is dict and type(r.get("ts_ms")) is int and r.get("kind") == "OPEN" and r.get("side") in (-1, 1):
            out.append((r["ts_ms"], r.get("symbol"), r["side"]))
    return out


def brain_view(symbol: str, t0: int, brain: dict, proposals: list) -> dict:
    t1 = t0 + WINDOW_MS
    opened = [(ts, side, pid) for pid, (ts, sym, side) in brain["opens"].items() if sym == symbol and t0 <= ts < t1]
    proposed = [side for ts, sym, side in proposals if sym == symbol and t0 <= ts < t1]
    decided = [d for d in brain["decisions"] if d[1] == symbol and t0 <= d[0] < t1]
    if any(s == 1 for _, s, _ in opened):
        view = "LONG_aperto"
    elif any(s == -1 for _, s, _ in opened):
        view = "SHORT_aperto"
    elif 1 in proposed:
        view = "LONG_proposto_respinto"
    elif -1 in proposed:
        view = "SHORT_proposto_respinto"
    elif decided:
        view = "NO_TRADE"
    else:
        view = "non_valutato"
    pnl = []
    for _, side, pid in opened:
        c = brain["closes"].get(pid)
        if c and c[0] is not None:
            pnl.append({"lato": side, "pnl_usdt": float(c[0]), "uscita": c[1]})
    return {"vista_brain": view, "decisioni_brain": len(decided), "proposte_registrate": len(proposed),
            "esiti_brain": pnl}


def _ci(xs: list) -> dict:
    n = len(xs)
    m = sum(xs) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1)) if n > 1 else 0.0
    half = 1.96 * sd / math.sqrt(n) if n > 1 else float("inf")
    return {"n": n, "R_medio": round(m, 3), "ic95": [round(m - half, 3), round(m + half, 3)]}


def groups(facts: list) -> dict:
    out = {}
    for v in VIEWS:
        xs = [f["toro"]["R"] for f in facts if f["vista_brain"] == v and f["toro"].get("R") is not None]
        if len(xs) >= 2:
            out[v] = _ci(xs)
    return out


def compare(toro_dir: Path, journal: Path, run_id: str, proposals: Path | None = None,
            validation_from: str | None = None) -> dict:
    brain = _brain(journal, run_id)
    props = _proposals(proposals)
    facts = []
    for line in (Path(toro_dir) / "osservazioni.jsonl").read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        t0 = _day_close_ms(r["data_segnale"])
        toro = {k: r.get(k) for k in ("esito", "stato", "netto_pct", "R", "motivo_uscita", "giorni", "massimo_flottante_pct",
                                      "mae_pct", "distanza_stop_pct")}
        facts.append({"data_segnale": r["data_segnale"], "simbolo": r["simbolo"], "toro": toro,
                      **brain_view(r["simbolo"], t0, brain, props)})
    discovery = [f for f in facts if validation_from is None or f["data_segnale"] < validation_from]
    validation = [f for f in facts if validation_from is not None and f["data_segnale"] >= validation_from]
    hyp = {v: g for v, g in groups(discovery).items() if g["n"] >= MIN_N}
    val = groups(validation)
    rules = []
    for v, g in hyp.items():
        w = val.get(v)
        if (w and w["n"] >= MIN_N and (w["ic95"][0] > 0 or w["ic95"][1] < 0)
                and math.copysign(1, w["R_medio"]) == math.copysign(1, g["R_medio"])):
            rules.append({"vista_brain": v, "scoperta": g, "validazione": w,
                          "lettura": ("Toro guadagna quando Brain " if w["R_medio"] > 0 else "Toro perde quando Brain ")
                          + v.replace("_", " ").lower()})
    return {"versione": "cross_compare_v1", "segnali_toro": len(facts),
            "conteggio_viste": {v: sum(f["vista_brain"] == v for f in facts) for v in VIEWS},
            "fatti": facts, "ipotesi": hyp, "ipotesi_sotto_soglia": {v: g for v, g in groups(discovery).items() if g["n"] < MIN_N},
            "regole_validate": rules,
            "avvertenze": ["una regola validata e' un'evidenza statistica, non un ordine per Brain",
                           "senza proposal_observations.jsonl le proposte respinte risultano NO_TRADE"]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--toro", required=True)
    ap.add_argument("--journal", required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--proposte")
    ap.add_argument("--validazione-da")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    res = compare(Path(a.toro), Path(a.journal), a.run_id, Path(a.proposte) if a.proposte else None, a.validazione_da)
    Path(a.out).write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("segnali_toro", "conteggio_viste", "ipotesi", "regole_validate")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
