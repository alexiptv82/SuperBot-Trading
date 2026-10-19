#!/usr/bin/env python3
"""Sentinella del backup esterno cifrato: decide se serve un AVVISO, leggendo lo stato scritto sul server
da external_backup.py (/opt/superbot-extbackup/status.json). Gira FUORI dal server (su GitHub), una volta
al giorno dopo il backup notturno: cosi' si accorge anche di un server spento o di un timer che non parte.

Uso:  extbackup_watch.py --status <file con il contenuto di status.json> [--max-age-h 36]
      (file vuoto o assente = server non raggiungibile o stato mancante)
Esce con 0 se va tutto bene (stampa "OK ..."), con 2 se serve un avviso (stampa il testo dell'avviso).

Casi di avviso (decisione dell'utente e consiglio di ChatGPT, 19/10):
  - l'ultimo tentativo e' FALLITO (primo fallimento: avvisa subito, e ogni giorno finche' dura);
  - l'ultimo backup riuscito e' piu' vecchio di --max-age-h ore (timer fermo, server spento, ...);
  - stato illeggibile o server non raggiungibile.
Non stampa mai segreti: lo stato contiene solo nomi di archivi, impronte e orari.
"""
import argparse
import json
import sys
from datetime import datetime, timezone


def parse_ts(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def assess(text, now, max_age_h=36.0):
    """(serve_avviso, messaggio)."""
    if not text or not text.strip():
        return True, ("non riesco a leggere lo stato del backup esterno: server non raggiungibile "
                      "oppure backup mai eseguito")
    try:
        st = json.loads(text)
        if not isinstance(st, dict):
            raise ValueError("non e' un oggetto")
    except ValueError:
        return True, "lo stato del backup esterno e' illeggibile (file rovinato)"
    err = st.get("ultimo_errore")
    ok_ts = st.get("ultimo_successo")
    age_h = None
    if ok_ts:
        try:
            age_h = (now - parse_ts(ok_ts)).total_seconds() / 3600.0
        except ValueError:
            return True, "la data dell'ultimo backup esterno riuscito e' illeggibile"
    if err:
        last = ("ultimo backup riuscito: %s (%.0f ore fa)" % (ok_ts, age_h)) if age_h is not None else \
            "nessun backup riuscito finora"
        return True, "l'ultimo backup esterno e' FALLITO: %s. %s" % (str(err).splitlines()[0][:200], last)
    if age_h is None:
        return True, "non risulta nessun backup esterno riuscito"
    if age_h > max_age_h:
        return True, ("nessun backup esterno riuscito da %.0f ore (ultimo: %s). Il timer sul server potrebbe "
                      "essere fermo o il server spento" % (age_h, ok_ts))
    return False, "OK ultimo backup esterno riuscito %s (%.1f ore fa): %s" % (ok_ts, age_h, st.get("archivio"))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--status", required=True)
    ap.add_argument("--max-age-h", type=float, default=36.0)
    ap.add_argument("--now", default="", help="solo per le prove: AAAA-MM-GGTHH:MM:SSZ")
    a = ap.parse_args(argv)
    try:
        with open(a.status) as f:
            text = f.read()
    except OSError:
        text = ""
    now = parse_ts(a.now) if a.now else datetime.now(timezone.utc)
    alert, msg = assess(text, now, a.max_age_h)
    print(msg)
    return 2 if alert else 0


if __name__ == "__main__":
    sys.exit(main())
