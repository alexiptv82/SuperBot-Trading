"""Healthcheck del container desk: NON avvia il bot, controlla solo che lo stato sia fresco.

Perche' esiste: il vecchio HEALTHCHECK lanciava `python -m desk.cli health`, ma quel
sottocomando non esiste piu' e cli.py ignora gli argomenti sconosciuti, quindi ogni 5
minuti partiva un SECONDO bot completo dentro il container (cicli di mercato, chiamate
a Claude, messaggi Telegram, scrittura concorrente di state_v2.json).

Qui si legge soltanto l'eta' del file di stato: il bot dorme 15-30 minuti tra i cicli e
salva state_v2.json a ogni ciclo, quindi e' vivo se il file e' stato modificato da meno
di MAX_AGE_S. Se pause.flag esiste il bot e' fermo di proposito e va considerato sano.
"""
import os
import sys
import time
from typing import Optional

MAX_AGE_S = 75 * 60   # 2 cicli da 30 min + margine


def check(data_dir: str, now: Optional[float] = None) -> bool:
    now = time.time() if now is None else now
    if os.path.exists(os.path.join(data_dir, "pause.flag")):
        return True
    try:
        age = now - os.path.getmtime(os.path.join(data_dir, "state_v2.json"))
    except OSError:
        return False
    return age < MAX_AGE_S


if __name__ == "__main__":
    sys.exit(0 if check(os.environ.get("DESK_DATA_DIR", "/app/data/desk")) else 1)
