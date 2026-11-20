"""Validazione INDIPENDENTE delle feature di uno snapshot v2 (`decision_features_v1`), senza rete e senza codice del runtime.

Lo snapshot dichiara: le feature, la finestra esatta delle candele usate per timeframe (`inputs_window`: apertura della
prima candela, numero di candele), lo sha256 di quelle candele (`inputs_digest`) e il taglio dei dati
(`snapshot_captured_at_ms`). Il runtime le ha scaricate dall'exchange al momento della decisione; qui si rifa' tutto
partendo da COPIE ATTESTATE delle candele (una directory per timeframe, ognuna con `candles_meta.json` valido e
intervallo coerente, stesso formato di `candles.py`) e con un'implementazione propria degli indicatori.

Esito `verified` solo se TUTTO coincide:
  1. ogni timeframe della finestra ha un archivio attestato (meta valido)        market_data_unattested
  2. le candele della finestra ci sono tutte, contigue, senza doppioni diversi    candles_missing / candles_conflict
  3. ogni candela e' chiusa entro il taglio dei dati                              window_not_closed
  4. lo sha256 ricalcolato coincide con quello dichiarato                         inputs_mismatch
     (il runtime ha visto dati diversi da quelli del mercato attestato)
  5. ogni feature dichiarata e' ricalcolata e coincide (tolleranza 1e-9)          features_mismatch / unknown_feature
     e nessuna feature calcolabile manca                                          features_incomplete
  6. l'istante dei dati (asof) coincide                                           asof_mismatch
Qualunque altro caso: motivo specifico, e lo snapshot resta `snapshot_unverified` (escluso dal training).

Limite dichiarato: verifica che le feature siano la funzione v1 di candele di mercato attestate, chiuse prima della
decisione. Non dimostra che il MODELLO abbia visto esattamente quelle candele (lo dimostra, per le aperture, il
`context_hash` del laboratorio LLM) ne' che le candele attestate siano vere oltre la loro attestazione.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from decimal import Context, Decimal, InvalidOperation, ROUND_HALF_EVEN, localcontext
from typing import Optional

import candles as C

FEATURE_SET = "decision_features_v1"
TF_MS = {"15m": 900_000, "1h": 3_600_000, "4h": 14_400_000}
PERIOD = 14
TOLERANCE = Decimal("1e-9")
VERIFIED = "verified"
_CTX = Context(prec=60, rounding=ROUND_HALF_EVEN)
_Q = Decimal("1e-10")
_NAME = re.compile(r"^t(15m|1h|4h)_(ret_([0-9]{1,3})|atr14_pct|rsi14)$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_NUMBER = re.compile(r"^-?[0-9]+(\.[0-9]+)?$")


@dataclass(frozen=True)
class Bar:
    t: int
    o: Decimal
    h: Decimal
    l: Decimal
    c: Decimal
    v: Decimal


class DecisionCandles:
    """Una directory con una sottodirectory per timeframe (`15m`, `1h`, `4h`), ognuna un archivio `candles.py`."""

    def __init__(self, root: str):
        self.root = os.path.abspath(root)
        self.meta_ids: dict = {}
        self.problems: dict = {}
        for tf, ms in TF_MS.items():
            sub = os.path.join(self.root, tf)
            if not os.path.isdir(sub) or os.path.islink(sub):
                self.problems[tf] = "archive_missing"
                continue
            store = C.CandleStore(sub, interval_ms=ms)          # solo per il meta: stessa regola del builder
            if store.meta_id is None:
                self.problems[tf] = store.meta_problem or "meta_invalid"
            else:
                self.meta_ids[tf] = store.meta_id
        self._cache: dict = {}

    def bars(self, tf: str, symbol: str) -> Optional[dict]:
        """{open_ms: Bar} con valori decimali ESATTI; None se un open compare due volte con valori diversi."""
        key = (tf, symbol)
        if key in self._cache:
            return self._cache[key]
        out: dict = {}
        conflict = False
        path = os.path.join(self.root, tf, symbol + ".jsonl")
        try:
            if not stat.S_ISREG(os.lstat(path).st_mode):
                raise OSError("not_regular")
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    try:
                        d = json.loads(line, parse_float=Decimal, parse_int=Decimal)
                        b = Bar(int(d["t"]), *(Decimal(str(d[k])) for k in ("o", "h", "l", "c")),
                                Decimal(str(d.get("v", 0))))
                    except (ValueError, KeyError, TypeError, InvalidOperation):
                        continue
                    if not (b.l <= min(b.o, b.c) and b.h >= max(b.o, b.c) and b.l > 0 and b.t % TF_MS[tf] == 0):
                        continue
                    if b.t in out and out[b.t] != b:
                        conflict = True
                    out[b.t] = b
        except OSError:
            out = {}
        self._cache[key] = None if conflict else out
        return self._cache[key]


def _num(d: Decimal) -> str:
    return format(d.normalize(), "f")


def digest(windows: dict) -> str:
    """Formato canonico dichiarato del digest (stesso contratto del runtime, implementato qui a parte)."""
    h = hashlib.sha256()
    for name in sorted(windows):
        h.update(f"tf={name}\n".encode())
        for b in windows[name]:
            h.update(f"{b.t},{_num(b.o)},{_num(b.h)},{_num(b.l)},{_num(b.c)},{_num(b.v)}\n".encode())
    return h.hexdigest()


def _wilder(values: list, n: int) -> Optional[Decimal]:
    """Media di Wilder seminata col primo valore (alpha = 1/n); definita dall'indice n-1."""
    if len(values) < n:
        return None
    acc = values[0]
    for v in values[1:]:
        acc = acc + (v - acc) / n
    return acc


def _atr_pct(bars: list) -> Optional[Decimal]:
    tr = [bars[0].h - bars[0].l]
    for prev, b in zip(bars, bars[1:]):
        tr.append(max(b.h - b.l, abs(b.h - prev.c), abs(b.l - prev.c)))
    a = _wilder(tr, PERIOD)
    return None if a is None else a / bars[-1].c


def _rsi(bars: list) -> Optional[Decimal]:
    if len(bars) <= PERIOD:
        return None
    ups = [max(b.c - a.c, Decimal(0)) for a, b in zip(bars, bars[1:])]
    downs = [max(a.c - b.c, Decimal(0)) for a, b in zip(bars, bars[1:])]
    ag, al = ups[0], downs[0]
    for u, d in zip(ups[1:], downs[1:]):
        ag += (u - ag) / PERIOD
        al += (d - al) / PERIOD
    if ag == 0 and al == 0:
        return Decimal(50)
    if al == 0:
        return Decimal(100)
    return Decimal(100) - Decimal(100) / (1 + ag / al)


def recompute(windows: dict, claimed: dict) -> tuple[dict, set]:
    """(valori ricalcolati per i nomi dichiarati, nomi obbligatori calcolabili)."""
    out: dict = {}
    required: set = set()
    with localcontext(_CTX):
        for tf, bars in windows.items():
            p = "t" + tf
            if len(bars) < 2:
                continue
            required.add(p + "_ret_1")
            out[p + "_ret_1"] = bars[-1].c / bars[-2].c - 1
            a, r = _atr_pct(bars), _rsi(bars)
            if a is not None:
                out[p + "_atr14_pct"] = a
                required.add(p + "_atr14_pct")
            if r is not None:
                out[p + "_rsi14"] = r
                required.add(p + "_rsi14")
        for name in claimed:
            m = _NAME.match(name)
            if m and m.group(3) and m.group(3) != "1":
                n, bars = int(m.group(3)), windows.get(m.group(1), [])
                if len(bars) > n:
                    out[name] = bars[-1].c / bars[-1 - n].c - 1
    return {k: v.quantize(_Q) for k, v in out.items()}, required


def verify(payload: dict, candles: Optional[DecisionCandles]) -> tuple[str, dict]:
    """(esito, provenienza) per il payload di uno snapshot GIA' ammesso dalla regola di collegamento."""
    if candles is None:
        return "no_decision_candles", {}
    if payload.get("feature_set") != FEATURE_SET:
        return "unsupported_feature_set", {}
    window, dig, feats = payload.get("inputs_window"), payload.get("inputs_digest"), payload.get("features")
    cut, symbol = payload.get("snapshot_captured_at_ms"), payload.get("symbol")
    if (not isinstance(window, dict) or not window or type(dig) is not str or not _HEX64.match(dig)
            or not isinstance(feats, dict) or not feats or type(cut) is not int or not isinstance(symbol, str)):
        return "provenance_incomplete", {}
    windows: dict = {}
    for tf, spec in window.items():
        if tf not in TF_MS or not isinstance(spec, list) or len(spec) != 2 or any(type(x) is not int for x in spec):
            return "provenance_incomplete", {}
        if tf not in candles.meta_ids:
            return "market_data_unattested", {}
        first, count = spec
        archive = candles.bars(tf, symbol)
        if archive is None:
            return "candles_conflict", {}
        step = TF_MS[tf]
        bars = [archive.get(first + i * step) for i in range(count)]
        if count <= 0 or any(b is None for b in bars):
            return "candles_missing", {}
        if bars[-1].t + step > cut:
            return "window_not_closed", {}
        windows[tf] = bars
    prov = {"decision_market_dataset_ids": {tf: candles.meta_ids[tf] for tf in sorted(windows)}}
    if digest(windows) != dig:
        return "inputs_mismatch", prov
    if any(type(k) is not str or not _NAME.match(k) for k in feats):
        return "unknown_feature", prov
    if any(type(v) is not str or not _NUMBER.match(v) for v in feats.values()):
        return "features_mismatch", prov
    values, required = recompute(windows, feats)
    if not required <= set(feats):
        return "features_incomplete", prov
    for k, v in feats.items():
        if k not in values or abs(Decimal(v) - values[k]) > TOLERANCE:
            return "features_mismatch", prov
    asof = max((bars[-1].t + TF_MS[tf] for tf, bars in windows.items() if len(bars) >= 2), default=None)
    if payload.get("feature_asof_ms") != asof:
        return "asof_mismatch", prov
    return VERIFIED, prov
