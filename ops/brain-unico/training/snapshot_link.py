"""Collegamento causale fra le decisioni del Brain V3 e i loro snapshot `brain_decision_snapshot_v2` (PR #122).

Uno snapshot e' una DICHIARAZIONE del Brain su cio' che sapeva al momento della decisione. Il journal non impone che sia
stata scritta in quel momento (`occurred_at_ms` lo fornisce chi scrive), quindi un timestamp coerente NON basta: uno
snapshot compilato dopo l'esito e retrodatato sarebbe indistinguibile. Si ammette uno snapshot solo se TUTTE le prove
seguenti, ricavabili dal solo journal copiato, tengono; altrimenti le feature NON entrano nella riga e il motivo e'
registrato (`snapshot_status`). Le righe con feature da snapshot restano comunque NON ammesse al training
(`snapshot_unverified`) finche' la fonte di mercato non e' verificata in modo indipendente.

Prove (ogni fallimento ha un codice breve):
 1. unico snapshot per decisione, stesso run, schema 2                  snapshot_conflict | snapshot_run_mismatch | snapshot_schema
 2. legato alla decisione per id E per hash dell'evento                  snapshot_hash_mismatch
 3. istante, simbolo, azione e stato uguali a quelli della decisione    snapshot_ts_mismatch | snapshot_symbol_mismatch | snapshot_decision_mismatch
 4. feature_asof <= captured <= decision_ts, tutti interi positivi     snapshot_time_order
 5. ORDINE DI SCRITTURA nel journal (numero di sequenza, non l'orologio):
      seq(snapshot) > seq(decisione)                                      snapshot_before_decision
      seq(snapshot) < seq di ogni paper_open collegato alla decisione     snapshot_after_open
      seq(snapshot) < seq del primo evento con istante > decisione+grazia snapshot_written_late
 6. valori finiti, nomi consentiti, nessun testo                          snapshot_features_invalid

Nessun testo libero entra mai nel dataset. Moduli puri: nessuna I/O.
"""
from __future__ import annotations

import bisect
import math
import re
from typing import Any, Optional

KIND = "brain_decision_snapshot_v2"
WRITE_GRACE_MS = 120_000          # un evento piu' recente di cosi' prova che lo snapshot doveva esistere gia'
FEATURE_RE = re.compile(r"[a-z][a-z0-9_]{0,31}")
NUMBER_RE = re.compile(r"-?[0-9]+(\.[0-9]+)?")
HASH_RE = re.compile(r"[0-9a-f]{64}")
RISK_PREFIX = "risk_"
MAX_VALUES = 64


class Timeline:
    """Per run: primo numero di sequenza fra gli eventi (esclusi gli snapshot) con istante > soglia."""

    def __init__(self) -> None:
        self._raw: dict = {}
        self._built: dict = {}

    def add(self, run: str, ts: int, seq: int) -> None:
        self._raw.setdefault(run, []).append((ts, seq))
        self._built.pop(run, None)

    def first_seq_after(self, run: str, threshold_ms: int) -> Optional[int]:
        if run not in self._built:
            pairs = sorted(self._raw.get(run, ()))
            times = [t for t, _ in pairs]
            suffix: list = []
            low = None
            for _, s in reversed(pairs):
                low = s if low is None or s < low else low
                suffix.append(low)
            suffix.reverse()
            self._built[run] = (times, suffix)
        times, suffix = self._built[run]
        i = bisect.bisect_right(times, threshold_ms)
        return suffix[i] if i < len(times) else None


class Admission:
    __slots__ = ("features", "asof_ms", "status", "reason", "flags", "prov")

    def __init__(self, status: str, reason: Optional[str] = None, features: Optional[dict] = None,
                 asof_ms: Optional[int] = None) -> None:
        self.status, self.reason, self.features, self.asof_ms = status, reason, features, asof_ms
        self.flags = ["snapshot_unverified"] if status == "admitted" else (["snapshot_rejected"] if status == "rejected" else [])
        self.prov = {"snapshot_status": status}
        if reason:
            self.prov["snapshot_reject"] = reason


def _is_int(x: Any) -> bool:
    return type(x) is int and x > 0


def _values(raw: Any, prefix: str) -> Optional[dict]:
    if not isinstance(raw, dict) or len(raw) > MAX_VALUES:
        return None
    out: dict = {}
    for k, v in raw.items():
        if type(k) is not str or not FEATURE_RE.fullmatch(k) or type(v) is not str or not NUMBER_RE.fullmatch(v):
            return None
        x = float(v)
        if not math.isfinite(x):
            return None
        out[prefix + k] = x
    return out


def admit(decision_id: str, decision: dict, snapshots: Optional[list], open_seqs: list, timeline: Timeline) -> Admission:
    """`decision`: {ts, run, seq, hash, kind, status, symbol}; `snapshots`: eventi `brain_decision_snapshot_v2` con
    quell'id decisione ({seq, run, p}); `open_seqs`: seq dei paper_open collegati alla decisione."""
    if not snapshots:
        return Admission("none")
    if len(snapshots) != 1:
        return Admission("rejected", "snapshot_conflict")
    s = snapshots[0]
    p = s["p"]
    if s["run"] != decision["run"]:
        return Admission("rejected", "snapshot_run_mismatch")
    if p.get("schema_version") != 2 or type(p.get("schema_version")) is not int:
        return Admission("rejected", "snapshot_schema")
    dh = decision.get("hash")
    if (p.get("decision_event_id") != decision_id or type(dh) is not str or not HASH_RE.fullmatch(dh)
            or p.get("decision_event_hash") != dh):
        return Admission("rejected", "snapshot_hash_mismatch")
    if p.get("decision_ts_ms") != decision["ts"] or type(p.get("decision_ts_ms")) is not int:
        return Admission("rejected", "snapshot_ts_mismatch")
    if not isinstance(decision.get("symbol"), str) or p.get("symbol") != decision["symbol"]:
        return Admission("rejected", "snapshot_symbol_mismatch")
    if p.get("action") != decision.get("kind") or p.get("status") != decision.get("status"):
        return Admission("rejected", "snapshot_decision_mismatch")
    cap, asof = p.get("snapshot_captured_at_ms"), p.get("feature_asof_ms")
    feats_raw = p.get("features")
    if not _is_int(cap) or cap > decision["ts"] or (asof is not None and (not _is_int(asof) or asof > cap)):
        return Admission("rejected", "snapshot_time_order")
    if feats_raw and asof is None:
        return Admission("rejected", "snapshot_time_order")
    seq = s["seq"]
    if seq <= decision["seq"]:
        return Admission("rejected", "snapshot_before_decision")
    if any(seq >= o for o in open_seqs):
        return Admission("rejected", "snapshot_after_open")
    later = timeline.first_seq_after(decision["run"], decision["ts"] + WRITE_GRACE_MS)
    if later is not None and seq >= later:
        return Admission("rejected", "snapshot_written_late")
    feats, risk = _values(feats_raw if feats_raw is not None else {}, ""), _values(p.get("risk") or {}, RISK_PREFIX)
    if feats is None or risk is None or set(feats) & set(risk):
        return Admission("rejected", "snapshot_features_invalid")
    merged = {**feats, **risk}
    if not merged:
        return Admission("none")
    return Admission("admitted", features=merged, asof_ms=asof)
