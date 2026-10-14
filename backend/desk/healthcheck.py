"""Healthcheck del container desk: NON avvia il bot, controlla solo che sia vivo.

Perche' esiste: il vecchio HEALTHCHECK lanciava `python -m desk.cli health`, ma quel
sottocomando non esiste piu' e cli.py ignora gli argomenti sconosciuti, quindi ogni 5
minuti partiva un SECONDO bot completo dentro il container (cicli di mercato, chiamate
a Claude, messaggi Telegram, scrittura concorrente di state_v2.json).

Il bot scrive heartbeat.json ogni pochi secondi (anche in pausa e anche durante un ciclo
lungo): se il battito e' recente il processo e' vivo. Se il file non esiste o non e'
leggibile (bot di una versione precedente) si ricade sulla vecchia regola: stato salvato
da poco, oppure pause.flag presente.
"""
import json
import os
import sys
import time
from typing import Optional

HEARTBEAT_MAX_AGE_S = 15 * 60   # un ciclo lento (API lente) non deve far dichiarare morto il bot
MAX_AGE_S = 75 * 60             # regola di ripiego: 2 cicli da 30 min + margine


def check(data_dir: str, now: Optional[float] = None) -> bool:
    now = time.time() if now is None else now
    try:
        with open(os.path.join(data_dir, "heartbeat.json")) as f:
            ts = float(json.load(f)["ts"])
        return now - ts < HEARTBEAT_MAX_AGE_S
    except (OSError, ValueError, KeyError, TypeError):
        pass
    if os.path.exists(os.path.join(data_dir, "pause.flag")):
        return True
    try:
        age = now - os.path.getmtime(os.path.join(data_dir, "state_v2.json"))
    except OSError:
        return False
    return age < MAX_AGE_S


if __name__ == "__main__":
    sys.exit(0 if check(os.environ.get("DESK_DATA_DIR", "/app/data/desk")) else 1)
