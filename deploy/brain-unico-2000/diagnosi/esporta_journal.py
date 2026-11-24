"""Esportazione in SOLA LETTURA (root) del journal della run attiva del Brain unico, per le simulazioni offline.

Copia il database con l'API di backup di SQLite (aperto in ``mode=ro``) in una cartella temporanea, verifica la
catena di hash sulla copia, scrive UN file JSON (``--out``, permessi 600, proprietario ``--owner``) con: tutti gli
eventi della run (sequenza, id, tipo, istante, fonte, payload; il journal non contiene credenziali), la configurazione
della run, conteggio e testa della catena. Nessuna scrittura nella run, nessun servizio toccato.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--owner", default="")
    a = ap.parse_args(argv)
    run = Path(a.run_dir)
    tmp = Path(tempfile.mkdtemp(prefix="esporta-"))
    try:
        dst = tmp / "j.db"
        src = sqlite3.connect(f"file:{run / 'journal.db'}?mode=ro", uri=True, timeout=10)
        out_db = sqlite3.connect(str(dst))
        with out_db:
            src.backup(out_db)
        src.close()
        out_db.close()
        from backend.v3.events import EventJournal
        count, head = EventJournal(str(dst)).verify_chain()
        db = sqlite3.connect(str(dst))
        rows = db.execute("SELECT seq, event_id, run_id, kind, occurred_at_ms, source, payload_json "
                          "FROM v3_events ORDER BY seq").fetchall()
        db.close()
        cfg = json.loads((run / "runner_config.json").read_text())
        rep = {"run_dir": str(run), "chain": {"count": count, "head": head}, "config": cfg,
               "events": [{"seq": s, "id": i, "run_id": r, "kind": k, "t": t, "source": so, "payload": json.loads(p)}
                          for s, i, r, k, t, so, p in rows]}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    out = Path(a.out)
    out.write_text(json.dumps(rep, default=str))
    out.chmod(0o600)
    if a.owner:
        shutil.chown(out, a.owner, a.owner)
    kinds = {}
    for e in rep["events"]:
        kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
    print(f"ESPORTAZIONE=OK eventi={count} testa={head[:16]}… consulti={kinds.get('ai_consultation', 0)} "
          f"aperture={kinds.get('paper_open', 0)}")
    print(f"ESPORTAZIONE_FILE={out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
