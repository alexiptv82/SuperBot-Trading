"""Riepilogo del registro Turbo Scalp (sola lettura): python -m desk.turbo_scalp.report <cartella turbo>.
Deduplica gli eventi per id; nessun dato privato (solo risultati ipotetici)."""
import glob
import json
import os
import sys

from .strategy import summarize


def read_exits(folder):
    seen, exits, signals = set(), [], 0
    for path in sorted(glob.glob(os.path.join(folder, "events-*.jsonl"))):
        with open(path) as f:
            for raw in f:
                try:
                    line = json.loads(raw)
                except ValueError:
                    continue            # riga troncata da un arresto: si ignora
                for e in line.get("events", []):
                    if e.get("id") in seen:
                        continue
                    seen.add(e.get("id"))
                    if e.get("ev") == "exit":
                        exits.append(e)
                    elif e.get("ev") == "signal":
                        signals += 1
    return exits, signals


def main(argv=None):
    folder = (argv or sys.argv[1:] or ["/out/turbo"])[0]
    exits, signals = read_exits(folder)
    out = summarize(exits)
    out["signals"] = signals
    out["by_symbol"] = {}
    for e in exits:
        s = out["by_symbol"].setdefault(e["symbol"], {"trades": 0, "net_usd": 0.0})
        s["trades"] += 1
        s["net_usd"] = round(s["net_usd"] + e["net_usd"], 2)
    print(json.dumps(out, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
