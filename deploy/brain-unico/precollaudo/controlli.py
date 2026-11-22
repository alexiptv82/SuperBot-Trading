"""Controlli in SOLA LETTURA del pre-collaudo Brain Unico. Uso: python controlli.py <cartella run> <run_id> [tutti|uscite]

Il battito del runner riporta un solo motivo di fermo, con priorita' al mandato: la salute del servizio delle uscite
si legge QUI direttamente (exit_service_healthy), separata dal motivo del runner. Uscita 0 = tutti PASS."""
import json
import sqlite3
import sys
import time
from pathlib import Path

from backend.v3.events import EventJournal
from backend.v3.runner.exit_service import exit_service_healthy


def main(argv):
    run, run_id, mode = Path(argv[1]), argv[2], (argv[3] if len(argv) > 3 else "tutti")
    now = int(time.time() * 1000)
    exit_ok = exit_service_healthy(data_dir=run, run_id=run_id, now_ms=now) is True
    print("USCITE: %s" % ("SANE" if exit_ok else "NON SANE"))
    if mode == "uscite":
        return 0 if exit_ok else 1
    def read_json(name):
        try:
            v = json.loads((run / name).read_text())
            return v if isinstance(v, dict) else {}
        except (OSError, ValueError):
            return {}                                      # file assente o illeggibile: i controlli danno FAIL
    beat, mandate = read_json("heartbeat.json"), read_json("mandate.json")
    err = str(beat.get("last_error") or "")
    try:
        con = sqlite3.connect("file:%s?mode=ro" % (run / "budget.db"), uri=True)
        spend = con.execute("select count(*) from spend_events").fetchone()[0]
        con.close()
    except sqlite3.Error:
        spend = -1
    try:
        opens = sum(1 for e in EventJournal(str(run / "journal.db")).list_run("brain", run_id)
                    if e.event.kind == "paper_open")
    except Exception:
        opens = -1
    checks = {
        "mandato approved:false": mandate.get("approved") is False,
        "runner fermo (halted)": beat.get("state") == "halted",
        "motivo del runner = mandato": any(c in err for c in ("no_mandate", "mandate_not_approved", "mandate_mismatch")),
        "nessuna spesa AI": spend == 0,
        "nessuna apertura": opens == 0,
        "battito del runner recente (< 2 min)": type(beat.get("ts_ms")) is int and now - beat["ts_ms"] < 120_000,
        "uscite sane (controllo diretto, separato dal motivo del runner)": exit_ok,
    }
    for k, v in checks.items():
        print("%s  %s" % ("PASS" if v else "FAIL", k))
    print("motivo registrato dal runner: %s" % (err[:120] or "-"))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
