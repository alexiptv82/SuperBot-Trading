#!/usr/bin/env python3
"""Confronta operazione per operazione due replay di replay_classics_twin_real.py e riassume i risultati.
Escluso solo l'orario di sistema della scrittura (logged_ms e simili). Uso: python ... DIR_DEI_REPLAY"""
import json
import sys

import numpy as np

TW = sys.argv[1]
PAIRS = [("f3_hawk_short_rules", "p5_hawk_short_rules"), ("f3_hawk_short_claude", "p5_hawk_short_claude"),
         ("f3_hawk_both_rules", "p5_hawk_both_rules"), ("f3_hawk_both_claude", "p5_hawk_both_claude"),
         ("f3_hawk_short_claude", "p5_hawk_short_claude_toroenv"),
         ("f3_bull_claude", "p5_bull_off_claude"), ("f3_bull_claude", "p5_bull_unset_claude")]
VOL = {"wall_ms", "ts_wall", "pid", "logged_ms"}


def load(n):
    return json.load(open(f"{TW}/{n}/result.json"))


def norm(x):
    if isinstance(x, dict):
        return {k: norm(v) for k, v in x.items() if k not in VOL}
    if isinstance(x, list):
        return [norm(v) for v in x]
    return x


def summary(r):
    full = [c for c in r["closed"] if not c.get("partial")]
    nets = [c["net"] for c in r["closed"]]
    sides = {s: sum(1 for c in full if c["side"] == s) for s in (1, -1)}
    wins, loss = sum(n for n in nets if n > 0), -sum(n for n in nets if n < 0)
    return {"chiusure": len(r["closed"]), "posizioni_chiuse": len(full), "lati": sides,
            "aperture": len(r["opens"]), "pnl": round(sum(nets), 2), "cassa_finale": round(r["cash"], 2),
            "pf": round(wins / loss, 3) if loss else None,
            "win": round(float(np.mean([n > 0 for n in nets])), 3) if nets else None,
            "uscite": {w: sum(1 for c in full if c["why"] == w) for w in sorted({c["why"] for c in full})},
            "aperte_a_fine": len(r["positions"])}


out = {"confronti": {}, "riepiloghi": {}}
for a, b in PAIRS:
    try:
        ra, rb = norm(load(a)), norm(load(b))
    except FileNotFoundError:
        continue
    same = {k: ra[k] == rb[k] for k in ("closed", "opens", "positions", "cash")}
    # candidates: Toro twin adds statuses only in bull; for hawk they must be identical
    same["candidates"] = ra["candidates"] == rb["candidates"]
    first = None
    if not same["closed"]:
        for i, (x, y) in enumerate(zip(ra["closed"], rb["closed"])):
            if x != y:
                first = {"indice": i, "a": x, "b": y}
                break
    out["confronti"][f"{a} vs {b}"] = {"identico": same, "n": (len(ra["closed"]), len(rb["closed"])),
                                        "prima_differenza": first}
import os  # noqa: E402
for n in sorted(os.listdir(TW)):
    if os.path.exists(f"{TW}/{n}/result.json") and n != "t1":
        out["riepiloghi"][n] = summary(load(n))
print(json.dumps(out, indent=1, default=str))
