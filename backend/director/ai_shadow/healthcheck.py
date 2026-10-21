"""Salute del container AI in ombra: sano solo se il ciclo gira E arrivano candele (un'ombra cieca non e' sana).
Un modello che sbaglia (chiave, saldo) NON rende il container "non sano": si vede in status.json e nel report.
Esce 0 se sano, 1 altrimenti. Legge solo <AI_OUT>/ai/status.json."""
import json
import os
import sys
import time

HEARTBEAT_MS = 25 * 60 * 1000      # un ciclo dura 15 minuti
DATA_MS = 45 * 60 * 1000


def healthy(root: str, now_ms: int) -> bool:
    try:
        with open(os.path.join(root, "ai", "status.json")) as f:
            s = json.load(f)
        if now_ms - int(s["ts_ms"]) > HEARTBEAT_MS:
            return False
        last_ok = s.get("last_success_ms")
        return last_ok is not None and now_ms - int(last_ok) <= DATA_MS
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return False


if __name__ == "__main__":
    sys.exit(0 if healthy(os.environ.get("AI_OUT", "/out"), int(time.time() * 1000)) else 1)
