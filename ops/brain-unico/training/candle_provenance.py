"""Archivi di candele: INTEGRITA' dei file e PROVENIENZA verificabile, due verdetti distinti (nessuna rete).

`candles_meta.json` DICHIARA scambio, mercato e intervallo: e' una dichiarazione, non una prova. Questo modulo
aggiunge un manifest (`candle_manifest.json`, alla radice dell'archivio) e le RISPOSTE GREZZE della fonte pubblica:

  integrita'     ogni file dell'archivio (dati, meta, risposte grezze) e' elencato nel manifest con il suo SHA-256
                 e coincide; nessun file non elencato.                                  -> "intact" | motivo
  provenienza    integrita' + fonte = endpoint pubblico atteso (lo stesso del runtime, `history-candles` USDT-FUTURES)
                 + ogni file di dati e' RIDERIVATO dalle sue risposte grezze (URL con simbolo, granularita' e finestra
                 coerenti; solo candele chiuse all'istante di acquisizione) e coincide riga per riga
                 + lo SHA-256 del manifest coincide con un'ANCORA ESTERNA registrata dall'operatore
                 (`--candle-anchors`), non dall'agente che costruisce il dataset.    -> "attested" | motivo
  Senza manifest: "declared_only" (solo `candles_meta.json`).

Non equivalenti e separati da: coerenza matematica delle feature (`snapshot_verify`) e attestazione del journal e
delle decisioni (Fase 0, `attestation.py`). Limite dichiarato: la provenienza prova che i file sono cio' che la fonte ha
risposto alle richieste elencate, all'ora dichiarata; non prova che la fonte stessa sia corretta, e l'ancora vale
quanto la sua registrazione. Un secondo scaricamento di controllo e' riportato (`cross_check`) ma resta dichiarato.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from decimal import Decimal, InvalidOperation
from typing import Optional
from urllib.parse import parse_qs, urlsplit

MANIFEST = "candle_manifest.json"
META = "candles_meta.json"
KIND = "candle_manifest_v1"
SOURCE = {"exchange": "bitget", "base_url": "https://api.bitget.com", "path": "/api/v2/mix/market/history-candles",
          "product_type": "USDT-FUTURES"}
GRANULARITY = {60_000: "1m", 900_000: "15m", 3_600_000: "1H", 14_400_000: "4H"}
ID_RE = re.compile(r"candles-[0-9]{8}T[0-9]{6}Z-[A-Za-z0-9]{1,16}")
SHA_RE = re.compile(r"[0-9a-f]{64}")
_NUM = re.compile(r"-?\d+(\.\d+)?([eE][+-]?\d+)?")
_SYMBOL = re.compile(r"[A-Z0-9]{3,30}")
INTACT, ATTESTED, DECLARED = "intact", "attested", "declared_only"


def _sha(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _files(root: str) -> list:
    out = []
    for d, dirs, names in os.walk(root):
        dirs.sort()
        for n in sorted(names):
            p = os.path.join(d, n)
            rel = os.path.relpath(p, root).replace(os.sep, "/")
            if rel != MANIFEST:
                out.append(rel)
    return out


def derive_rows(responses: list, interval_ms: int, acquired_at_ms: int) -> dict:
    """{apertura_ms: (o, h, l, c, v)} come stringhe, dalle risposte grezze. Stesse regole del runtime
    (`fetch_candles._row`): righe non numeriche o incoerenti scartate, mai corrette; in piu' solo righe dentro la
    finestra della PROPRIA richiesta e candele gia' CHIUSE all'istante di acquisizione."""
    rows: dict = {}
    for url, body in responses:
        q = parse_qs(urlsplit(url).query)
        try:
            lo, hi = int(q["startTime"][0]), int(q["endTime"][0])
        except (KeyError, ValueError, IndexError):
            raise ValueError("request_window_missing") from None
        data = body.get("data") if isinstance(body, dict) and body.get("code") == "00000" else None
        for raw in data or ():
            if not isinstance(raw, (list, tuple)) or len(raw) < 6:
                continue
            try:
                ts = int(float(raw[0]))
            except (TypeError, ValueError):
                continue
            vals = tuple(str(x) for x in raw[1:6])
            if not (lo <= ts <= hi) or ts % interval_ms or ts + interval_ms > acquired_at_ms:
                continue
            if not all(_NUM.fullmatch(v) for v in vals):
                continue
            try:
                o, h, l, c, v = (Decimal(x) for x in vals)
            except InvalidOperation:
                continue
            if min(o, h, l, c) <= 0 or v < 0 or not (l <= o <= h and l <= c <= h):
                continue
            rows[ts] = vals
    return rows


def _read_jsonl(path: str) -> Optional[dict]:
    out: dict = {}
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                d = json.loads(line)
                ts = d["t"]
                vals = tuple(d[k] for k in ("o", "h", "l", "c", "v"))
                if type(ts) is not int or any(type(x) is not str for x in vals) or ts in out:
                    return None
                out[ts] = vals
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return out


def write_archive(root: str, *, manifest_id: str, acquired_at_ms: int, tool: dict, fetched: dict,
                  meta: dict, cross_check: Optional[dict] = None) -> str:
    """Scrive un archivio nuovo. ``fetched``: {percorso relativo del file di dati (`15m/BTCUSDT.jsonl` o
    `BTCUSDT.jsonl`): {"symbol", "interval_ms", "responses": [(url, risposta JSON)]}}. Restituisce lo SHA-256 del
    manifest (da registrare come ancora ESTERNA, a cura dell'operatore)."""
    if not ID_RE.fullmatch(manifest_id) or os.path.exists(os.path.join(root, MANIFEST)):
        raise ValueError("archive_exists_or_bad_id")
    entries = []
    for rel, f in sorted(fetched.items()):
        sym, iv = f["symbol"], f["interval_ms"]
        if not _SYMBOL.fullmatch(sym) or iv not in GRANULARITY or os.path.basename(rel) != sym + ".jsonl":
            raise ValueError("bad_file_spec")
        rows = derive_rows(f["responses"], iv, acquired_at_ms)
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path) or root, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            for ts in sorted(rows):
                o, h, l, c, v = rows[ts]
                fh.write(json.dumps({"t": ts, "o": o, "h": h, "l": l, "c": c, "v": v}) + "\n")
        meta_path = os.path.join(os.path.dirname(path), META)
        if not os.path.exists(meta_path):
            with open(meta_path, "w", encoding="utf-8") as fh:
                json.dump({**meta, "interval_ms": iv}, fh, sort_keys=True)
        reqs = []
        for i, (url, body) in enumerate(f["responses"]):
            raw_rel = f"raw/{rel[:-6]}/{i:05d}.json"
            raw_path = os.path.join(root, raw_rel)
            os.makedirs(os.path.dirname(raw_path), exist_ok=True)
            with open(raw_path, "w", encoding="utf-8") as fh:
                json.dump(body, fh, sort_keys=True, separators=(",", ":"))
            reqs.append({"url": url, "raw": raw_rel})
        entry = {"path": rel, "symbol": sym, "interval_ms": iv, "rows": len(rows),
                 "first_open_ms": min(rows) if rows else None, "last_open_ms": max(rows) if rows else None,
                 "requests": reqs}
        if "window" in f:                                       # copertura: cio' che manca resta dichiarato, mai riempito
            lo, hi = f["window"]
            expected = [t for t in range(-(-lo // iv) * iv, hi, iv)]
            missing = [t for t in expected if t not in rows]
            entry.update(requested_window=[lo, hi], expected_rows=len(expected), missing_rows=len(missing),
                         missing_open_ms_sample=missing[:50])
        entries.append(entry)
    hashes = {rel: _sha(os.path.join(root, rel)) for rel in _files(root)}
    manifest = {"kind": KIND, "manifest_id": manifest_id, "source": dict(SOURCE), "tool": dict(tool),
                "acquired_at_ms": acquired_at_ms, "files": entries, "sha256": hashes,
                "cross_check": cross_check}
    raw = json.dumps(manifest, sort_keys=True, indent=1).encode()
    with open(os.path.join(root, MANIFEST), "wb") as fh:
        fh.write(raw)
    return hashlib.sha256(raw).hexdigest()


def load_anchors(path: Optional[str]) -> dict:
    """Ancore esterne {manifest_id: sha256 del manifest}, registrate dall'operatore. Formato rigoroso."""
    if not path:
        return {}
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict) or not all(ID_RE.fullmatch(str(k)) and SHA_RE.fullmatch(str(v))
                                             for k, v in data.items()):
        raise ValueError("candle_anchors_invalid")
    return dict(data)


def _load_manifest(root: str):
    path = os.path.join(root, MANIFEST)
    try:
        if not stat.S_ISREG(os.lstat(path).st_mode):
            return None, None, "manifest_not_regular"
        with open(path, "rb") as fh:
            raw = fh.read()
        m = json.loads(raw.decode("utf-8"))
    except FileNotFoundError:
        return None, None, "manifest_missing"
    except (OSError, ValueError, UnicodeDecodeError):
        return None, None, "manifest_invalid"
    if (not isinstance(m, dict) or m.get("kind") != KIND or not ID_RE.fullmatch(str(m.get("manifest_id")))
            or not isinstance(m.get("files"), list) or not isinstance(m.get("sha256"), dict)
            or type(m.get("acquired_at_ms")) is not int):
        return None, None, "manifest_invalid"
    return m, hashlib.sha256(raw).hexdigest(), None


def check(root: Optional[str], anchors: Optional[dict] = None) -> dict:
    """{"integrity": intact|motivo, "provenance": attested|declared_only|motivo, "manifest_id", "manifest_sha256"}."""
    if not root or not os.path.isdir(root):
        return {"integrity": "archive_missing", "provenance": "archive_missing", "manifest_id": None,
                "manifest_sha256": None}
    m, msha, problem = _load_manifest(root)
    if m is None:
        prov = DECLARED if problem == "manifest_missing" else problem
        return {"integrity": problem, "provenance": prov, "manifest_id": None, "manifest_sha256": None}
    out = {"integrity": INTACT, "provenance": None, "manifest_id": m["manifest_id"], "manifest_sha256": msha}
    present = _files(root)
    listed = m["sha256"]
    if set(present) - set(listed):
        out["integrity"] = "file_unlisted"
    elif set(listed) - set(present):
        out["integrity"] = "file_missing"
    elif any(_sha(os.path.join(root, rel)) != listed[rel] for rel in present):
        out["integrity"] = "file_hash_mismatch"
    if out["integrity"] != INTACT:
        out["provenance"] = "integrity_" + out["integrity"]
        return out
    out["provenance"] = _provenance(root, m, msha, anchors or {})
    return out


def _provenance(root: str, m: dict, msha: str, anchors: dict) -> str:
    if m.get("source") != SOURCE:
        return "source_unexpected"
    acquired = m["acquired_at_ms"]
    data_files = {rel for rel in m["sha256"] if rel.endswith(".jsonl") and not rel.startswith("raw/")}
    entries = {e.get("path"): e for e in m["files"] if isinstance(e, dict)}
    if set(entries) != data_files or not data_files:
        return "files_not_described"
    for rel, e in sorted(entries.items()):
        sym, iv, reqs = e.get("symbol"), e.get("interval_ms"), e.get("requests")
        if (not isinstance(sym, str) or iv not in GRANULARITY or os.path.basename(rel) != f"{sym}.jsonl"
                or not isinstance(reqs, list) or not reqs):
            return "requests_missing"
        try:
            with open(os.path.join(os.path.dirname(os.path.join(root, rel)), META), encoding="utf-8") as fh:
                meta = json.load(fh)
        except (OSError, ValueError):
            return "meta_missing"
        if not isinstance(meta, dict) or meta.get("interval_ms") != iv:
            return "meta_interval_mismatch"
        responses = []
        for r in reqs:
            url, raw_rel = (r.get("url"), r.get("raw")) if isinstance(r, dict) else (None, None)
            if type(url) is not str or type(raw_rel) is not str or raw_rel not in m["sha256"]:
                return "requests_missing"
            parts = urlsplit(url)
            q = parse_qs(parts.query)
            if (f"{parts.scheme}://{parts.netloc}" != SOURCE["base_url"] or parts.path != SOURCE["path"]
                    or q.get("symbol") != [sym] or q.get("productType") != [SOURCE["product_type"]]
                    or q.get("granularity") != [GRANULARITY[iv]]):
                return "request_not_matching_file"
            try:
                with open(os.path.join(root, raw_rel), encoding="utf-8") as fh:
                    responses.append((url, json.load(fh)))
            except (OSError, ValueError):
                return "raw_unreadable"
        try:
            derived = derive_rows(responses, iv, acquired)
        except ValueError:
            return "request_window_missing"
        stored = _read_jsonl(os.path.join(root, rel))
        if stored is None or stored != derived:
            return "file_not_derived_from_source"
    anchor = anchors.get(m["manifest_id"])
    if anchor is None:
        return "manifest_unanchored"
    if anchor != msha:
        return "anchor_mismatch"
    return ATTESTED
