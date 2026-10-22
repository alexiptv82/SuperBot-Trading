"""
learning_log_manifest.py — manifesto/hash del learning_log (SOLA LETTURA)

Legge /data/{hawk,bull}/learning_log.jsonl, calcola sha256 e statistiche
di integrità. Non stampa MAI righe di testo dei trade nel repo pubblico:
solo conteggi, hash e campi strutturali aggregati.

Uscita macchina (--json) per il workflow; uscita leggibile di default.

Uso:
  python learning_log_manifest.py --data-root /data --bots hawk,bull
  python learning_log_manifest.py --data-root /data --bots hawk,bull --json
"""
import argparse
import hashlib
import json
import os
import sys
from collections import Counter

# Campi obbligatori attesi in ogni record valido
REQUIRED_FIELDS = {"symbol", "side", "entry_ts", "exit_ts", "net", "gross", "fees"}

# Versioni schema ammesse (campo "schema_version" se presente)
KNOWN_VERSIONS = {None, "1", "1.0", "1.1", "2", "2.0"}


def manifest_one(path: str, bot: str) -> dict:
    """Ritorna il manifesto per un singolo file. Nessun dato grezzo in output."""
    if not os.path.exists(path):
        return {
            "bot": bot,
            "path": path,
            "exists": False,
            "sha256": None,
            "size_bytes": 0,
            "lines_total": 0,
            "lines_empty": 0,
            "lines_invalid_json": 0,
            "lines_valid": 0,
            "lines_missing_fields": 0,
            "lines_unknown_version": 0,
            "symbols_seen": 0,
            "sides_seen": [],
            "schema_versions_seen": [],
            "ts_min": None,
            "ts_max": None,
            "error": "file non trovato",
        }

    with open(path, "rb") as f:
        raw = f.read()

    sha256 = hashlib.sha256(raw).hexdigest()
    size_bytes = len(raw)
    text = raw.decode("utf-8", errors="replace")
    lines_raw = text.splitlines()

    lines_total = len(lines_raw)
    lines_empty = 0
    lines_invalid_json = 0
    lines_missing_fields = 0
    lines_unknown_version = 0
    lines_valid = 0

    symbols: set = set()
    sides: Counter = Counter()
    schema_versions: Counter = Counter()
    ts_values: list = []

    for raw_line in lines_raw:
        line = raw_line.strip()
        if not line:
            lines_empty += 1
            continue
        try:
            rec = json.loads(line)
        except (ValueError, TypeError):
            lines_invalid_json += 1
            continue

        # Verifica campi obbligatori
        missing = REQUIRED_FIELDS - set(rec.keys())
        if missing:
            lines_missing_fields += 1
            continue

        # Versione schema
        sv = str(rec.get("schema_version")) if rec.get("schema_version") is not None else None
        schema_versions[sv] += 1
        if sv not in KNOWN_VERSIONS:
            lines_unknown_version += 1

        # Aggregati strutturali (NO valori di trading individuali)
        sym = str(rec.get("symbol", ""))
        if sym:
            symbols.add(sym)
        side = str(rec.get("side", ""))
        if side:
            sides[side] += 1

        # Range temporale (solo indice, non contenuto)
        for ts_key in ("entry_ts", "exit_ts"):
            v = rec.get(ts_key)
            if isinstance(v, (int, float)) and v > 0:
                ts_values.append(v)

        lines_valid += 1

    ts_min = min(ts_values) if ts_values else None
    ts_max = max(ts_values) if ts_values else None

    return {
        "bot": bot,
        "path": path,
        "exists": True,
        "sha256": sha256,
        "size_bytes": size_bytes,
        "lines_total": lines_total,
        "lines_empty": lines_empty,
        "lines_invalid_json": lines_invalid_json,
        "lines_valid": lines_valid,
        "lines_missing_fields": lines_missing_fields,
        "lines_unknown_version": lines_unknown_version,
        "symbols_seen": len(symbols),
        "sides_seen": sorted(sides.keys()),
        "sides_counts": dict(sides),
        "schema_versions_seen": sorted(str(k) for k in schema_versions.keys()),
        "schema_versions_counts": {str(k): v for k, v in schema_versions.items()},
        "ts_min": ts_min,
        "ts_max": ts_max,
        "error": None,
    }


def fmt_ts(ts):
    if ts is None:
        return "n/d"
    import datetime
    return datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def print_human(manifests: list[dict]) -> None:
    print("=" * 60)
    print("MANIFESTO learning_log — SOLA LETTURA, nessun dato grezzo")
    print("=" * 60)
    ok = True
    for m in manifests:
        bot = m["bot"].upper()
        print(f"\n--- {bot} ---")
        if not m["exists"]:
            print(f"  ERRORE: {m['error']}")
            ok = False
            continue
        print(f"  sha256        : {m['sha256']}")
        print(f"  dimensione    : {m['size_bytes']:,} byte")
        print(f"  righe totali  : {m['lines_total']}")
        print(f"  righe vuote   : {m['lines_empty']}")
        print(f"  json invalidi : {m['lines_invalid_json']}")
        print(f"  campi mancanti: {m['lines_missing_fields']}")
        print(f"  versione ignota: {m['lines_unknown_version']}")
        print(f"  VALIDI        : {m['lines_valid']}")
        print(f"  simboli visti : {m['symbols_seen']}")
        print(f"  lati          : {m['sides_counts']}")
        print(f"  versioni schema: {m['schema_versions_counts']}")
        print(f"  ts range      : {fmt_ts(m['ts_min'])} → {fmt_ts(m['ts_max'])}")
        if m["lines_invalid_json"] > 0:
            print(f"  ATTENZIONE: {m['lines_invalid_json']} righe JSON invalide")
        if m["lines_missing_fields"] > 0:
            print(f"  ATTENZIONE: {m['lines_missing_fields']} righe con campi mancanti")
        if m["lines_unknown_version"] > 0:
            print(f"  ATTENZIONE: {m['lines_unknown_version']} righe con versione schema non riconosciuta")
    print("\n" + "=" * 60)
    if ok:
        print("MANIFESTO OK — hash e conteggi sopra, nessun dato grezzo stampato")
    else:
        print("MANIFESTO CON ERRORI — vedi sopra")
    print("=" * 60)
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", default="/data")
    ap.add_argument("--bots", default="hawk,bull")
    ap.add_argument("--json", dest="json_out", action="store_true")
    args = ap.parse_args()

    bots = [b.strip() for b in args.bots.split(",")]
    manifests = []
    for bot in bots:
        path = os.path.join(args.data_root, bot, "learning_log.jsonl")
        manifests.append(manifest_one(path, bot))

    if args.json_out:
        print(json.dumps(manifests, indent=2))
        errors = [m for m in manifests if not m["exists"] or m.get("error")]
        sys.exit(1 if errors else 0)
    else:
        ok = print_human(manifests)
        errors = [m for m in manifests if not m["exists"] or m.get("error")]
        sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
