
# ---------------------------------------------------------------------------------------------------------------
# Parte eseguita sul server, in coda al codice di backend/desk/analyst.py (i due file si concatenano e si passano a
# `python3 -I -`). Argomenti: hawk=CARTELLA bull=CARTELLA. SOLA LETTURA: legge learning_log.jsonl e le candele pubbliche.
import os
import sys
import time

_dirs = dict(a.split("=", 1) for a in sys.argv[1:] if "=" in a)
_events = {bot: read_jsonl(os.path.join(d, "learning_log.jsonl")) for bot, d in _dirs.items()}
_span = {}
for _bot, _evs in _events.items():
    for _e in _evs:
        if _e.get("ev") == "candidate" and _e.get("symbol") and _e.get("ts"):
            _lo, _hi = _span.get(_e["symbol"], (_e["ts"], _e["ts"]))
            _span[_e["symbol"]] = (min(_lo, _e["ts"]), max(_hi, _e["ts"]))
_now = int(time.time() * 1000)
_candles = {}
for _sym, (_lo, _hi) in sorted(_span.items()):
    _candles[_sym] = fetch_range(_sym, _lo, min(_now, _hi + 25 * 3_600_000))
print(examine(_events, _candles, _now))
print("candele scaricate: " + ", ".join(f"{s}={len(c)}" for s, c in sorted(_candles.items())))
