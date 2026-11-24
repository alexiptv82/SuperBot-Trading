"""Brain Live Evolution: comando dell'operatore (SOLO root, dalla VPS). Nessuna scrittura nel journal: le richieste
approvate passano dal runner, che le rivalida e le registra fra un giro e l'altro.

    strategia.py --data-dir RUN --run-id ID --config RUN/runner_config.json stato
    strategia.py ... proponi "Da questo momento esamina i mercati ogni 15 minuti"
    strategia.py ... approva <id> [--motivo "..."]
    strategia.py ... esito

``proponi`` interpreta la richiesta (interprete deterministico del Brain, nessuna AI), la valida e la salva come
proposta; ``approva`` la consegna al runner, che la applica dal giro successivo alle sole nuove aperture.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from backend.v3.events import EventJournal
from backend.v3.strategy_versions import (LABELS, RESULT_FILE, StrategyError, approve, describe, effective, propose,
                                          read_registry, save_proposal, strategy_view)


def _registry(data_dir: Path, run_id: str):
    return read_registry(EventJournal(str(data_dir / "journal.db")), run_id)


def main(argv=None, *, now_fn=lambda: int(time.time() * 1000), out=sys.stdout) -> int:
    ap = argparse.ArgumentParser(description="Strategie versionate del Brain unico (solo PAPER)")
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--config", required=True)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("stato")
    p = sub.add_parser("proponi")
    p.add_argument("testo")
    p = sub.add_parser("approva")
    p.add_argument("id")
    p.add_argument("--motivo", default="")
    sub.add_parser("esito")
    a = ap.parse_args(argv)
    data_dir = Path(a.data_dir)
    if not (data_dir / "journal.db").is_file():
        print("ERRORE: run inesistente", file=out)
        return 2
    base = Path(a.config).read_bytes()
    w = lambda line: print(line, file=out)
    try:
        if a.cmd == "stato":
            v = strategy_view(EventJournal(str(data_dir / "journal.db")), a.run_id)
            reg = _registry(data_dir, a.run_id)
            eff = effective(base, reg)
            w(f"Versione attiva per le nuove aperture: {v['active']}")
            ov = reg.versions[reg.active].overlay
            for k, val in ov.items():
                w(f"  · {LABELS.get(k, k)}: {val}")
            if not ov:
                w("  · configurazione di base della run")
            w(f"  frequenza di analisi: ogni {eff.config.cycle_minutes} minuti")
            w("Versioni: " + ", ".join(f"{x['version']}" + (f" ({x['description']})" if x['description'] else "")
                                       for x in v["versions"]))
            for h in v["history"]:
                w(f"  {time.strftime('%d/%m %H:%M', time.gmtime(h['at_ms'] / 1000))} UTC  {h['from']} → {h['to']}"
                  + (" (rollback)" if h["rollback"] else "") + f"  approvato da {h['approved_by']}")
        elif a.cmd == "proponi":
            prop = propose(a.testo, _registry(data_dir, a.run_id), base, now_fn())
            save_proposal(data_dir, prop)
            for line in describe(prop):
                w(line)
            w(f"Per applicarla: approva {prop.id}")
        elif a.cmd == "approva":
            who = os.environ.get("SUDO_USER") or os.environ.get("USER") or "operatore"
            approve(data_dir, a.id, f"operatore ({who})", a.motivo, now_fn())
            w(f"APPROVATA {a.id}: il runner la registra nel journal entro pochi secondi e vale dal giro successivo.")
            w("Esito: comando 'esito'.")
        elif a.cmd == "esito":
            try:
                w(json.dumps(json.loads((data_dir / RESULT_FILE).read_text()), ensure_ascii=False))
            except (OSError, ValueError):
                w("nessun esito registrato")
    except StrategyError as exc:
        w(f"RIFIUTATA: {exc}")
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
