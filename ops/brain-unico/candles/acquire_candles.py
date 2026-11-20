"""Acquisizione CIRCOSCRITTA di candele pubbliche Bitget per la validazione degli snapshot e delle etichette.

Produce un archivio attestabile (`ops/brain-unico/training/candle_provenance.py`): file di dati derivati dalle
risposte grezze conservate, `candles_meta.json`, `candle_manifest.json` con SHA-256 di ogni file. Lo SHA-256 del
manifest che lo strumento stampa va registrato dall'OPERATORE come ancora esterna (non dall'agente).

* Fonte: la STESSA funzione del runtime (`backend.v3.lab_tools.fetch_candles.fetch_rows`, endpoint pubblico
  `history-candles`, USDT-FUTURES, nessuna chiave): l'archivio deve contenere le stesse candele che il Brain ha visto.
  Lo strumento verifica che le righe derivate dalle risposte grezze coincidano con quelle del runtime, altrimenti
  si ferma senza scrivere.
* Solo candele CHIUSE: la fine del periodo viene allineata alla griglia e non supera l'istante di acquisizione.
* Nessuna rete senza ``--confirm-network``; ``--plan`` stampa richieste e dimensione stimate senza scaricare nulla.
* Mai sovrascrivere: la destinazione non deve esistere. Nessun accesso a dati privati, nessuna scrittura altrove.
* ``--compare-with ARCHIVIO``: confronta le candele sovrapposte con un archivio precedente (secondo scaricamento di
  controllo) e registra l'esito nel manifest (``cross_check``; resta un'informazione dichiarata).

Uso (solo con autorizzazione del proprietario; vedi docs/v3/BRAIN-UNICO-ACQUISIZIONE-CANDELE-20261120.md):
  python3 ops/brain-unico/candles/acquire_candles.py --start 2026-10-15 --end 2026-12-01 --out DIR --plan
  python3 ops/brain-unico/candles/acquire_candles.py --start ... --end ... --out DIR --confirm-network
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Callable, Optional

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "ops", "brain-unico", "training"))

import candle_provenance as CP  # noqa: E402
from backend.v3.lab_tools.fetch_candles import fetch_rows  # noqa: E402

TIMEFRAMES = {"15m": 900_000, "1h": 3_600_000, "4h": 14_400_000}
SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT")
META = {"exchange": "bitget", "market": "usdt_perp", "price_basis": "last", "source": "public_rest_v2_history_candles"}
WINDOW_BARS = 200
ROW_BYTES, RAW_BYTES = 110, 140          # stime per riga (file di dati, risposta grezza)


def _ms(text: str) -> int:
    return int(datetime.fromisoformat(text).replace(tzinfo=timezone.utc).timestamp() * 1000)


def plan(start_ms: int, end_ms: int, symbols=SYMBOLS, timeframes=TIMEFRAMES) -> dict:
    files, requests, rows = 0, 0, 0
    for step in timeframes.values():
        bars = max(0, (end_ms // step * step - start_ms) // step)
        files += len(symbols)
        rows += bars * len(symbols)
        requests += (-(-bars // WINDOW_BARS) + 1) * len(symbols)       # +1: pagina vuota finale
    return {"files": files, "requests_estimate": requests, "rows_estimate": rows,
            "bytes_estimate": rows * (ROW_BYTES + RAW_BYTES), "network": False}


def acquire(out: str, *, start_ms: int, end_ms: int, get_json: Callable[[str], object], now_ms: int,
            symbols=SYMBOLS, timeframes=TIMEFRAMES, tool: Optional[dict] = None,
            compare_with: Optional[str] = None) -> str:
    """Scarica, verifica la coerenza col runtime, scrive l'archivio. Restituisce lo SHA-256 del manifest."""
    if os.path.exists(out):
        raise ValueError("destination_exists")
    if not (0 < start_ms < end_ms):
        raise ValueError("invalid_period")
    fetched = {}
    for tf, step in timeframes.items():
        end = min(end_ms, now_ms) // step * step                     # solo candele chiuse
        for sym in symbols:
            recorded = []

            def rec(url, _recorded=recorded):
                body = get_json(url)
                _recorded.append((url, body))
                return body

            runtime_rows = fetch_rows(sym, start_ms, end, candle_ms=step, get_json=rec)
            derived = CP.derive_rows(recorded, step, now_ms)
            derived = {t: v for t, v in derived.items() if start_ms <= t < end}
            if derived != runtime_rows:
                raise ValueError(f"derivation_differs_from_runtime:{tf}:{sym}")
            fetched[f"{tf}/{sym}.jsonl"] = {"symbol": sym, "interval_ms": step, "responses": recorded}
    cross = None
    if compare_with:
        cross = {"method": "second_download", "against": os.path.basename(os.path.abspath(compare_with)),
                 "files_compared": 0, "candles_compared": 0, "mismatches": 0, "declared_only": True}
        for rel, f in fetched.items():
            old = CP._read_jsonl(os.path.join(compare_with, rel))
            if old is None:
                continue
            new = CP.derive_rows(f["responses"], f["interval_ms"], now_ms)
            common = set(old) & set(new)
            cross["files_compared"] += 1
            cross["candles_compared"] += len(common)
            cross["mismatches"] += sum(1 for t in common if old[t] != new[t])
    mid = "candles-" + datetime.fromtimestamp(now_ms / 1000, timezone.utc).strftime("%Y%m%dT%H%M%SZ") + \
          "-" + secrets.token_hex(4)
    os.makedirs(out)
    return CP.write_archive(out, manifest_id=mid, acquired_at_ms=now_ms,
                            tool=tool or {"name": "acquire_candles", "version": "1"}, fetched=fetched,
                            meta=META, cross_check=cross)


def _git_commit() -> Optional[str]:
    try:
        return subprocess.run(["git", "-C", ROOT, "rev-parse", "HEAD"], capture_output=True, text=True,
                              timeout=10).stdout.strip() or None
    except Exception:
        return None


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--start", required=True, help="inizio UTC, es. 2026-10-15")
    ap.add_argument("--end", required=True, help="fine UTC (esclusa), es. 2026-12-01")
    ap.add_argument("--out", required=True, help="directory NUOVA di destinazione")
    ap.add_argument("--symbols", default=",".join(SYMBOLS))
    ap.add_argument("--plan", action="store_true", help="solo stima, nessuna rete")
    ap.add_argument("--confirm-network", action="store_true", help="scarica davvero (serve autorizzazione)")
    ap.add_argument("--compare-with", help="archivio precedente per il controllo incrociato")
    a = ap.parse_args(argv)
    start, end = _ms(a.start), _ms(a.end)
    symbols = tuple(s for s in a.symbols.split(",") if s)
    p = plan(start, end, symbols)
    print(json.dumps(p))
    if a.plan or not a.confirm_network:
        print("PLAN ONLY: nessuna richiesta inviata (serve --confirm-network)")
        return 0
    from backend.v3.lab_tools.fetch_candles import http_json
    sha = acquire(a.out, start_ms=start, end_ms=end, get_json=http_json, now_ms=int(time.time() * 1000),
                  symbols=symbols, tool={"name": "acquire_candles", "version": "1", "git_commit": _git_commit()},
                  compare_with=a.compare_with)
    with open(os.path.join(a.out, CP.MANIFEST)) as fh:
        mid = json.load(fh)["manifest_id"]
    print(f"ARCHIVIO: {a.out}\nMANIFEST_ID: {mid}\nMANIFEST_SHA256: {sha}\n"
          "Registrare l'ancora {manifest_id: sha256} in un canale dell'operatore (non a cura dell'agente).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
