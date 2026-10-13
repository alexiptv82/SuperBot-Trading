"""Converte il calendario scritto in ORA SVIZZERA (deploy/claude-schedule.json) nei file per i bot (orari UTC).

Uso: python3 deploy/make_claude_schedule.py <calendario.json> <cartella_uscita>
Scrive <cartella_uscita>/hawk.json e bull.json e stampa il riepilogo. Esce con errore se qualcosa non torna:
in quel caso nessun file viene scritto sul server."""
import importlib.util
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
TZ = ZoneInfo("Europe/Zurich")
GIORNI = ["lun", "mar", "mer", "gio", "ven", "sab", "dom"]
MESI = ["gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic"]
PER_FINESTRA_USD = 0.70   # tetto di spesa di una finestra, per bot (DESK_DAILY_CAP_USD)


def load_schedule_module():
    spec = importlib.util.spec_from_file_location("sched", os.path.join(HERE, "..", "backend", "desk", "schedule.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def local(day: str, hhmm: str) -> datetime:
    naive = datetime.strptime(f"{day} {hhmm}", "%Y-%m-%d %H:%M")
    a, b = naive.replace(tzinfo=TZ, fold=0), naive.replace(tzinfo=TZ, fold=1)
    if a.utcoffset() != b.utcoffset():
        raise ValueError(f"{day} {hhmm} cade nel cambio d'ora (ambiguo o inesistente): scegli un altro orario")
    if a.astimezone(timezone.utc).astimezone(TZ).replace(tzinfo=None) != naive:
        raise ValueError(f"{day} {hhmm} non esiste (cambio d'ora): scegli un altro orario")
    return a


def convert(rows, where):
    out = []
    for i, r in enumerate(rows, 1):
        try:
            s = local(r["giorno"], r["dalle"])
            e = local(r["giorno"], r["alle"])
            if e <= s:
                e = local((datetime.strptime(r["giorno"], "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d"), r["alle"])
        except (KeyError, ValueError, TypeError) as ex:
            raise SystemExit(f"ERRORE {where}, finestra {i}: {ex}")
        label = (f"{GIORNI[s.weekday()]} {s.day} {MESI[s.month - 1]} {s.strftime('%H:%M')}-{e.strftime('%H:%M')}"
                 f"{'' if e.date() == s.date() else ' (+1g)'} ora svizzera")
        out.append({"start": s.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "end": e.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "label": label})
    return out


def main(src: str, outdir: str) -> None:
    S = load_schedule_module()
    cfg = json.load(open(src, encoding="utf-8"))
    base = cfg.get("windows")
    if not isinstance(base, list):
        raise SystemExit("ERRORE: manca l'elenco 'windows'")
    os.makedirs(outdir, exist_ok=True)
    now = time.time() * 1000
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for bot in ("hawk", "bull"):
        rows = cfg.get(f"windows_{bot}", base)
        wins = convert(rows, bot)
        parsed, err = S.parse_windows({"windows": wins})
        if err:
            raise SystemExit(f"ERRORE {bot}: {err}")
        with open(os.path.join(outdir, f"{bot}.json"), "w", encoding="utf-8") as f:
            json.dump({"version": 1, "generato": stamp, "origine": "deploy/claude-schedule.json (ora svizzera)",
                       "windows": wins}, f, ensure_ascii=False, indent=1)
        future = [w for w in parsed if w["end_ms"] > now]
        print(f"{bot.upper()}: {len(parsed)} finestre, {len(future)} non ancora finite, spesa massima "
              f"{len(future) * PER_FINESTRA_USD:.2f}$")
        for w, p in zip(wins, parsed):
            stato = "finita" if p["end_ms"] <= now else ("IN CORSO" if p["start_ms"] <= now else "futura")
            print(f"  {w['label']:<42} = {w['start']} -> {w['end']}  [{stato}]")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2])
