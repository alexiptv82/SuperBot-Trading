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
* LIMITI RIGIDI (autorizzazione del 20/11/2026): al massimo 350 tentativi HTTP complessivi, retry compresi; archivio
  al massimo 100 MB; periodo al massimo 47 giorni, mai date future; solo gli 8 simboli e i 3 timeframe. Superare un
  limite interrompe tutto: l'archivio si costruisce in una directory temporanea e diventa la destinazione SOLO se ogni
  controllo e' superato; altrimenti resta soltanto un rapporto ``<destinazione>.ABORTED.json`` senza dati.
* Se la fonte non restituisce tutto il periodo si conservano solo le candele ricevute: ogni file dichiara nel
  manifest finestra richiesta, righe attese, righe mancanti (mai interpolate).

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
MAX_HTTP_ATTEMPTS = 350
MAX_BYTES = 100 * 1024 * 1024
MAX_DAYS = 47
DAY_MS = 86_400_000
TRIES_PER_URL = 3
USER_AGENT = "superbot-lab/1.0"


class LimitExceeded(RuntimeError):
    pass


def _ms(text: str) -> int:
    return int(datetime.fromisoformat(text).replace(tzinfo=timezone.utc).timestamp() * 1000)


class LimitedHttp:
    """GET pubblico con un BUDGET di tentativi: ogni tentativo (anche un retry) consuma 1; a budget finito solleva
    ``LimitExceeded`` prima di inviare la richiesta. Retry solo per 429/5xx/rete, al massimo ``TRIES_PER_URL`` per URL."""

    def __init__(self, max_attempts: int = MAX_HTTP_ATTEMPTS, opener: Optional[Callable] = None,
                 sleep: Callable[[float], None] = time.sleep, min_gap: float = 0.09):
        self.max_attempts, self.attempts, self.sleep, self.min_gap = max_attempts, 0, sleep, min_gap
        self.outcomes: dict = {}                                      # esito -> numero di tentativi
        self._open = opener or self._urlopen
        self._last = 0.0

    @staticmethod
    def _urlopen(url: str) -> bytes:
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.read()

    def _count(self, key: str) -> None:
        self.outcomes[key] = self.outcomes.get(key, 0) + 1

    def __call__(self, url: str):
        import urllib.error
        wait, last = 1.0, None
        for _ in range(TRIES_PER_URL):
            if self.attempts >= self.max_attempts:
                raise LimitExceeded("http_attempts_exceeded")
            pause = self._last + self.min_gap - time.time()
            if pause > 0:
                self.sleep(pause)
            self._last = time.time()
            self.attempts += 1
            try:
                body = json.loads(self._open(url))
                self._count("ok")
                return body
            except urllib.error.HTTPError as e:
                last = e
                self._count(f"http_{e.code}")
                if e.code not in (429, 500, 502, 503, 504):
                    raise
            except (OSError, ValueError) as e:
                last = e
                self._count(type(e).__name__)
            self.sleep(wait)
            wait *= 2
        raise RuntimeError(f"source_unavailable: {type(last).__name__}")


def check_request(start_ms: int, end_ms: int, now_ms: int, symbols, timeframes) -> None:
    """I vincoli dell'autorizzazione, controllati PRIMA di qualunque rete."""
    if not (0 < start_ms < end_ms):
        raise ValueError("invalid_period")
    if end_ms > now_ms:
        raise ValueError("future_dates_not_allowed")
    if end_ms - start_ms > MAX_DAYS * DAY_MS:
        raise ValueError("period_over_47_days")
    if not set(symbols) <= set(SYMBOLS) or not symbols:
        raise ValueError("symbol_not_authorized")
    if not set(timeframes) <= set(TIMEFRAMES) or not timeframes:
        raise ValueError("timeframe_not_authorized")


def plan(start_ms: int, end_ms: int, symbols=SYMBOLS, timeframes=TIMEFRAMES) -> dict:
    files, requests, rows = 0, 0, 0
    for step in timeframes.values():
        bars = max(0, (end_ms // step * step - start_ms) // step)
        files += len(symbols)
        rows += bars * len(symbols)
        requests += (-(-bars // WINDOW_BARS) + 1) * len(symbols)       # +1: margine per pagina finale
    return {"files": files, "requests_estimate": requests, "rows_estimate": rows,
            "bytes_estimate": rows * (ROW_BYTES + RAW_BYTES), "network": False,
            "limits": {"max_http_attempts": MAX_HTTP_ATTEMPTS, "max_bytes": MAX_BYTES, "max_days": MAX_DAYS}}


def _size(root: str) -> int:
    return sum(os.path.getsize(os.path.join(d, n)) for d, _, names in os.walk(root) for n in names)


def acquire(out: str, *, start_ms: int, end_ms: int, get_json: Callable[[str], object], now_ms: int,
            symbols=SYMBOLS, timeframes=TIMEFRAMES, tool: Optional[dict] = None,
            compare_with: Optional[str] = None, max_bytes: int = MAX_BYTES) -> str:
    """Scarica, verifica, scrive l'archivio in una directory temporanea e la rende definitiva solo se ogni controllo
    e' superato. Restituisce lo SHA-256 del manifest. Su qualunque errore: nessun archivio, solo il rapporto."""
    if os.path.exists(out) or os.path.exists(out + ".ABORTED.json"):
        raise ValueError("destination_exists")
    check_request(start_ms, end_ms, now_ms, symbols, timeframes)
    if plan(start_ms, end_ms, symbols, timeframes)["bytes_estimate"] > max_bytes:
        raise ValueError("archive_over_size_limit")
    staging = out + ".partial-" + secrets.token_hex(4)
    try:
        sha = _acquire_into(staging, start_ms=start_ms, end_ms=end_ms, get_json=get_json, now_ms=now_ms,
                            symbols=symbols, timeframes=timeframes, tool=tool, compare_with=compare_with)
        size = _size(staging)
        if size > max_bytes:
            raise LimitExceeded("archive_over_size_limit")
        os.rename(staging, out)
        return sha
    except BaseException as exc:
        import shutil
        shutil.rmtree(staging, ignore_errors=True)
        with open(out + ".ABORTED.json", "w", encoding="utf-8") as fh:
            json.dump({"aborted": True, "reason": str(exc)[:600], "kind": type(exc).__name__,
                       "http_attempts": getattr(get_json, "attempts", None),
                       "http_outcomes": getattr(get_json, "outcomes", None), "archive_written": False,
                       "at_ms": now_ms}, fh, indent=1)
        raise


def _acquire_into(out, *, start_ms, end_ms, get_json, now_ms, symbols, timeframes, tool, compare_with) -> str:
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
            derived = CP.derive_rows(recorded, step, now_ms, (start_ms, end))
            if derived != runtime_rows:
                only_rt = sorted(set(runtime_rows) - set(derived))
                only_dv = sorted(set(derived) - set(runtime_rows))
                diff = sorted(t for t in set(derived) & set(runtime_rows) if derived[t] != runtime_rows[t])
                raise ValueError(f"derivation_differs_from_runtime:{tf}:{sym}:only_runtime={len(only_rt)}"
                                 f"{only_rt[:3]}:only_derived={len(only_dv)}{only_dv[:3]}:values={len(diff)}{diff[:3]}")
            fetched[f"{tf}/{sym}.jsonl"] = {"symbol": sym, "interval_ms": step, "responses": recorded,
                                            "window": (start_ms, end)}
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
    info = dict(tool or {"name": "acquire_candles", "version": "2"})
    info.update(http_attempts_used=getattr(get_json, "attempts", None),
                limits={"max_http_attempts": getattr(get_json, "max_attempts", None), "max_bytes": MAX_BYTES,
                        "max_days": MAX_DAYS})
    return CP.write_archive(out, manifest_id=mid, acquired_at_ms=now_ms, tool=info, fetched=fetched,
                            meta=META, cross_check=cross)


PROBE_MAX_ATTEMPTS = 3
PROBE_BARS = 400                       # due pagine da 200: il dubbio riguarda il confine fra richieste


def probe(get_json, *, now_ms: int, report_path: str, symbol: str = "BTCUSDT") -> dict:
    """Controllo preliminare su ``symbol`` 15m: le stesse risposte reali, due regole di derivazione a confronto con il
    runtime. Scrive solo un rapporto (istanti e conteggi, nessun archivio). ``ok`` = regola corrente == runtime."""
    if os.path.exists(report_path):
        raise ValueError("report_exists")
    if symbol not in SYMBOLS:
        raise ValueError("symbol_not_authorized")
    step = TIMEFRAMES["15m"]
    end = now_ms // step * step
    start = end - PROBE_BARS * step
    recorded = []

    def rec(url):
        body = get_json(url)
        recorded.append((url, body))
        return body

    result = {"symbol": symbol, "timeframe": "15m", "window": [start, end], "ok": False}
    try:
        runtime = fetch_rows(symbol, start, end, candle_ms=step, get_json=rec)
        current = CP.derive_rows(recorded, step, now_ms, (start, end))
        old = CP.derive_rows(recorded, step, now_ms)
        outside, seen, conflicts = [], {}, []
        for i, (url, body) in enumerate(recorded):
            from urllib.parse import parse_qs, urlsplit
            q = parse_qs(urlsplit(url).query)
            lo, hi = int(q["startTime"][0]), int(q["endTime"][0])
            data = body.get("data") if isinstance(body, dict) and body.get("code") == "00000" else None
            for raw in data or ():
                try:
                    ts = int(float(raw[0]))
                except (TypeError, ValueError, IndexError):
                    continue
                if not lo <= ts <= hi:
                    outside.append({"request": i, "open_ms": ts, "request_start": lo, "request_end": hi,
                                    "side": "before_start" if ts < lo else "after_end"})
                vals = tuple(str(x) for x in raw[1:6])
                if ts in seen and seen[ts] != vals:
                    conflicts.append(ts)
                seen.setdefault(ts, vals)

        def diff(a, b):
            return {"only_runtime": sorted(set(b) - set(a))[:50], "only_derived": sorted(set(a) - set(b))[:50],
                    "different_values": sorted(t for t in set(a) & set(b) if a[t] != b[t])[:50]}
        result.update(ok=current == runtime, pages=len(recorded), runtime_rows=len(runtime),
                      derived_rows=len(current), current_rule_vs_runtime=diff(current, runtime),
                      old_per_request_rule_equal=old == runtime, old_rule_vs_runtime=diff(old, runtime),
                      outside_request_window_count=len(outside), outside_request_window=outside[:50],
                      conflicting_duplicate_opens=sorted(set(conflicts))[:50])
    except BaseException as exc:
        result.update(error=f"{type(exc).__name__}: {str(exc)[:200]}")
        raise
    finally:
        result.update(http_attempts=getattr(get_json, "attempts", None),
                      http_outcomes=getattr(get_json, "outcomes", None), at_ms=now_ms)
        os.makedirs(os.path.dirname(os.path.abspath(report_path)), exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=1)
    return result


def _git_commit() -> Optional[str]:
    try:
        return subprocess.run(["git", "-C", ROOT, "rev-parse", "HEAD"], capture_output=True, text=True,
                              timeout=10).stdout.strip() or None
    except Exception:
        return None


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--probe", action="store_true", help="solo controllo preliminare BTCUSDT 15m (max 3 tentativi)")
    ap.add_argument("--probe-report", help="file NUOVO per il rapporto del controllo preliminare")
    ap.add_argument("--max-attempts", type=int, default=MAX_HTTP_ATTEMPTS,
                    help="budget di tentativi per questa esecuzione (al massimo 350 meno quelli gia' usati)")
    ap.add_argument("--start", help="inizio UTC, es. 2026-10-04")
    ap.add_argument("--end", help="fine UTC (esclusa), mai nel futuro")
    ap.add_argument("--out", help="directory NUOVA di destinazione")
    ap.add_argument("--symbols", default=",".join(SYMBOLS))
    ap.add_argument("--plan", action="store_true", help="solo stima, nessuna rete")
    ap.add_argument("--confirm-network", action="store_true", help="scarica davvero (serve autorizzazione)")
    ap.add_argument("--compare-with", help="archivio precedente per il controllo incrociato")
    a = ap.parse_args(argv)
    if not 1 <= a.max_attempts <= MAX_HTTP_ATTEMPTS:
        print("RIFIUTATO: max-attempts fuori da 1..350")
        return 2
    if a.probe:
        if not a.confirm_network or not a.probe_report:
            print("PLAN ONLY: il controllo preliminare richiede --confirm-network e --probe-report")
            return 0
        http = LimitedHttp(max_attempts=min(PROBE_MAX_ATTEMPTS, a.max_attempts))
        try:
            r = probe(http, now_ms=int(time.time() * 1000), report_path=a.probe_report)
        except BaseException as exc:
            print(f"SONDA INTERROTTA: {type(exc).__name__}: {str(exc)[:160]} (tentativi {http.attempts})")
            return 1
        print(f"SONDA: ok={r['ok']} pagine={r['pages']} righe={r['runtime_rows']} tentativi={http.attempts} "
              f"fuori_finestra={r['outside_request_window_count']} vecchia_regola_uguale={r['old_per_request_rule_equal']}")
        return 0 if r["ok"] else 1
    if not (a.start and a.end and a.out):
        print("RIFIUTATO: servono --start, --end e --out")
        return 2
    start, end = _ms(a.start), _ms(a.end)
    symbols = tuple(s for s in a.symbols.split(",") if s)
    now = int(time.time() * 1000)
    try:
        check_request(start, end, now, symbols, TIMEFRAMES)
    except ValueError as exc:
        print(f"RIFIUTATO: {exc}")
        return 2
    p = plan(start, end, symbols)
    print(json.dumps(p))
    if p["requests_estimate"] > a.max_attempts or p["bytes_estimate"] > MAX_BYTES:
        print("RIFIUTATO: stima oltre i limiti")
        return 2
    if a.plan or not a.confirm_network:
        print("PLAN ONLY: nessuna richiesta inviata (serve --confirm-network)")
        return 0
    http = LimitedHttp(max_attempts=a.max_attempts)
    try:
        sha = acquire(a.out, start_ms=start, end_ms=end, get_json=http, now_ms=now, symbols=symbols,
                      tool={"name": "acquire_candles", "version": "2", "git_commit": _git_commit()},
                      compare_with=a.compare_with)
    except BaseException as exc:
        print(f"INTERROTTO: {type(exc).__name__}: {str(exc)[:160]} (tentativi HTTP: {http.attempts}); "
              f"nessun archivio, rapporto in {a.out}.ABORTED.json")
        return 1
    with open(os.path.join(a.out, CP.MANIFEST)) as fh:
        mid = json.load(fh)["manifest_id"]
    print(f"ARCHIVIO: {a.out}\nMANIFEST_ID: {mid}\nMANIFEST_SHA256: {sha}\nTENTATIVI_HTTP: {http.attempts}\n"
          f"BYTE: {_size(a.out)}\n"
          "L'ancora {manifest_id: sha256} va registrata dal proprietario, non dall'agente.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
