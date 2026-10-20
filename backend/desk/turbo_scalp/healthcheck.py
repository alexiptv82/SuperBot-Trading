"""Salute del container Turbo Scalp: sano solo se il ciclo gira E se arrivano dati.

Il controllo dell'osservatore dei bot guarda solo il battito (ts_ms): qui non basta, perche' un ciclo che gira
ma non scarica nessuna candela (rete o API giu') produce un'ombra cieca che sembrerebbe sana. Servono entrambe:
  - battito: status.json aggiornato negli ultimi HEARTBEAT_MS (un ciclo dura 5 minuti: tollera un ciclo lento)
  - dati: last_success_ms (ultimo ciclo con almeno un simbolo scaricato) negli ultimi DATA_MS (3 cicli)
Esce 0 se sano, 1 altrimenti. Legge solo <SIDECAR_OUT>/turbo/status.json, non scrive nulla.
"""
import json
import os
import sys
import time

HEARTBEAT_MS = 7 * 60 * 1000
DATA_MS = 15 * 60 * 1000


def healthy(root, now_ms):
    try:
        with open(os.path.join(root, "turbo", "status.json")) as stream:
            status = json.load(stream)
        if now_ms - int(status["ts_ms"]) > HEARTBEAT_MS:
            return False
        last_ok = status.get("last_success_ms")
        return last_ok is not None and now_ms - int(last_ok) <= DATA_MS
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return False


if __name__ == "__main__":
    sys.exit(0 if healthy(os.environ.get("SIDECAR_OUT", "/out"), int(time.time() * 1000)) else 1)
