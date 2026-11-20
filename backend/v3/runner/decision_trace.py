"""Traccia causale di ogni decisione del Brain: input catturati PRIMA del modello, snapshot v2 scritto DOPO la
decisione e PRIMA di un'apertura.

Sequenza nel ciclo, per simbolo:
  1. ``capture_inputs`` (prima della chiamata al modello): feature deterministiche dalle STESSE candele che il modello
     ricevera', solo candele chiuse entro l'istante del giro; finestra esatta e sha256 delle candele usate (cosi' un
     validatore indipendente puo' ricalcolarle da copie attestate); ora di parete della cattura (dichiarata);
  2. il motore decide e scrive la ``brain_decision`` (anche NO_TRADE);
  3. ``record_decision_trace`` trova QUELLA decisione (seq > ``after_seq``, stesso simbolo e istante; letture
     indicizzate, mai l'intera run), scrive lo snapshot e lo giudica subito con la regola canonica
     ``assess_link`` (la stessa del Dataset Builder).

I quattro istanti restano distinti (vedi ``DecisionSnapshotV2``): riferimento della decisione, riferimento dei dati
(``feature_asof_ms``), cattura (``capture_wall_ms``, dichiarata) e scrittura (ordine nel journal; ``write_wall_ms``
dichiarata). L'unica prova verificabile del tempo e' l'ordine di scrittura.

Esiti: ``recorded`` (collegamento valido), ``recorded_decision_written_late`` / ``recorded_snapshot_written_late``
(scritto, ma l'ordine non dimostra la tempestivita': inammissibile per il training), ``already_recorded``, oppure un
errore (``ok=False``). Non solleva mai. Gli snapshot restano ``inputs_verified=False`` e
``eligible_for_training=False`` finche' una validazione indipendente non li verifica.

``trace_coverage`` giudica OGNI collegamento dal solo journal (catena di hash, hash della decisione, ordine,
coerenza causale): la copertura conta solo i collegamenti validi, mai le semplici associazioni per id.
Niente rete; nessuna dipendenza da RiskManager o ExitService.
"""
from __future__ import annotations

import bisect
from dataclasses import dataclass, field, replace
from decimal import Decimal, InvalidOperation
import hashlib
import re
from typing import Callable, Mapping, Optional, Sequence

from backend.v3.decision_snapshot_v2 import (
    SNAPSHOT_KIND, DecisionSnapshotV2, append_snapshot, assess_link,
)
from backend.v3.events import EventJournal
from backend.v3.features.indicators import atr, rsi

FEATURE_SET = "decision_features_v1"
PERIOD = 14
_Q = Decimal("1e-10")
_CODE = re.compile(r"[a-z][a-z0-9_]{0,47}")
LATE = ("decision_written_late", "snapshot_written_late")


@dataclass(frozen=True)
class Capture:
    features: dict
    asof_ms: Optional[int]
    inputs_digest: Optional[str]
    inputs_window: dict = field(default_factory=dict)
    capture_wall_ms: Optional[int] = None


@dataclass(frozen=True)
class Trace:
    ok: bool
    code: str
    decision_event_id: Optional[str] = None
    snapshot_event_id: Optional[str] = None


def _q(value: Decimal) -> Decimal:
    return value.quantize(_Q)


def _num(d: Decimal) -> str:
    return format(d.normalize(), "f")


def closed_windows(bars_by_tf: Mapping[str, Sequence], timeframes, *, now_ms: int) -> dict:
    """Per timeframe le sole candele chiuse entro ``now_ms`` (apertura + durata <= now)."""
    out = {}
    for spec in timeframes:
        bars = [b for b in (bars_by_tf.get(spec.name) or ()) if b.open_time_ms + spec.candle_ms <= now_ms]
        if bars:
            out[spec.name] = bars
    return out


def inputs_digest(windows: Mapping[str, Sequence]) -> Optional[str]:
    """sha256 canonico delle candele usate (timeframe ordinati; numeri normalizzati: "100.20" == "100.2")."""
    if not windows:
        return None
    h = hashlib.sha256()
    for name in sorted(windows):
        h.update(f"tf={name}\n".encode())
        for b in windows[name]:
            h.update(f"{b.open_time_ms},{_num(b.open)},{_num(b.high)},{_num(b.low)},{_num(b.close)},"
                     f"{_num(b.volume)}\n".encode())
    return h.hexdigest()


def features_from_windows(windows: Mapping[str, Sequence], timeframes) -> tuple[dict, Optional[int]]:
    """Feature v1 per timeframe ``t<nome>_*``: ret_1, ret_<finestra>, atr14_pct, rsi14. Una feature non calcolabile
    viene omessa, mai inventata. asof = chiusura dell'ultima candela usata."""
    feats: dict[str, Decimal] = {}
    asof: Optional[int] = None
    for spec in timeframes:
        bars = windows.get(spec.name) or []
        if len(bars) < 2:
            continue
        step, prefix = spec.candle_ms, "t" + spec.name.lower()
        close = [b.close for b in bars]
        used = False
        try:
            feats[prefix + "_ret_1"] = _q(close[-1] / close[-2] - 1)
            used = True
            n = spec.pct_window
            if len(close) > n:
                feats[prefix + f"_ret_{n}"] = _q(close[-1] / close[-1 - n] - 1)
        except (InvalidOperation, ZeroDivisionError, ArithmeticError):
            pass
        for name, fn in (("atr14_pct", atr), ("rsi14", rsi)):
            try:
                value = fn(bars, PERIOD, candle_ms=step)[-1]
            except (ValueError, ArithmeticError):
                continue
            if value is None:
                continue
            feats[f"{prefix}_{name}"] = _q(value / close[-1] if name == "atr14_pct" else value)
            used = True
        if used:
            last = bars[-1].open_time_ms + step
            asof = last if asof is None else max(asof, last)
    return feats, asof


def decision_features(bars_by_tf, timeframes, *, now_ms: int) -> tuple[dict, Optional[int]]:
    return features_from_windows(closed_windows(bars_by_tf, timeframes, now_ms=now_ms), timeframes)


def capture_inputs(bars_by_tf, timeframes, *, now_ms: int,
                   wall_ms: Optional[Callable[[], int]] = None) -> Capture:
    """Da chiamare PRIMA del modello, sulle stesse candele che il modello ricevera'."""
    windows = closed_windows(bars_by_tf, timeframes, now_ms=now_ms)
    feats, asof = features_from_windows(windows, timeframes)
    return Capture(feats, asof, inputs_digest(windows),
                   {k: (v[0].open_time_ms, len(v)) for k, v in windows.items()}, _wall(wall_ms))


def _wall(wall_ms) -> Optional[int]:
    if wall_ms is None:
        return None
    try:
        value = wall_ms()
    except Exception:
        return None
    return value if type(value) is int and value > 0 else None


def _risk_numbers(portfolio) -> dict:
    out = {}
    for key, attr in (("equity_usd", "equity"), ("margin_in_use_usd", "margin_used"),
                      ("open_risk_usd", "existing_open_risk"), ("available_margin_usd", "available_cash")):
        value = getattr(portfolio, attr, None)
        if type(value) is Decimal and value.is_finite() and value >= 0:
            out[key] = _q(value)
    return out


def _safe(code: object, default: str) -> str:
    return code if type(code) is str and _CODE.fullmatch(code) else default


def journal_tip(journal: EventJournal, run_id: str) -> int:
    return journal.last_seq("brain", run_id)


def record_decision_trace(*, journal: EventJournal, run_id: str, symbol: str, now_ms: int, after_seq: int,
                          expected_event_id: Optional[str], capture: Optional[Capture], portfolio,
                          wall_ms: Optional[Callable[[], int]] = None) -> Trace:
    try:
        mine = [r for r in journal.list_run_after("brain", run_id, after_seq)
                if r.event.kind == "brain_decision" and r.event.occurred_at_ms == now_ms
                and isinstance(r.event.payload, Mapping) and r.event.payload.get("symbol") == symbol]
        if expected_event_id is not None:
            mine = [r for r in mine if r.event.event_id == expected_event_id]
        if not mine:
            return Trace(False, "decision_not_journaled")
        if len(mine) != 1:
            return Trace(False, "decision_ambiguous")
        decision = mine[0]
        if type(capture) is not Capture:
            return Trace(False, "capture_missing", decision.event.event_id)
        snapshot = DecisionSnapshotV2(
            decision_event_id=decision.event.event_id, decision_ts_ms=now_ms, captured_at_ms=now_ms,
            feature_asof_ms=capture.asof_ms, features=capture.features, risk=_risk_numbers(portfolio),
            inputs_digest=capture.inputs_digest, capture_phase="pre_model", capture_wall_ms=capture.capture_wall_ms,
            write_wall_ms=_wall(wall_ms) if capture.capture_wall_ms is not None else None,
            feature_set=FEATURE_SET if capture.features else None, inputs_window=capture.inputs_window)
        if (snapshot.write_wall_ms is not None and capture.capture_wall_ms is not None
                and snapshot.write_wall_ms < capture.capture_wall_ms):
            snapshot = replace(snapshot, write_wall_ms=None)        # orologio tornato indietro: nessuna dichiarazione
        before = journal.last_seq("brain", run_id)
        stored = append_snapshot(journal=journal, run_id=run_id, snapshot=snapshot)
        sid = stored.event.event_id
        verdict = assess_link(decision, [stored], [], lambda t: journal.first_seq_stamped_after(
            "brain", run_id, t, SNAPSHOT_KIND))
        if verdict == "valid":
            code = "recorded" if stored.seq > before else "already_recorded"
        elif verdict in LATE:
            code = "recorded_" + verdict
        else:
            return Trace(False, "snapshot_" + _safe(verdict, "invalid"), decision.event.event_id, sid)
        return Trace(True, code, decision.event.event_id, sid)
    except ValueError as exc:                     # adattatore: codici espliciti (futuro, legame, apertura); conflitto
        return Trace(False, "snapshot_" + _safe(str(exc), "rejected"))
    except Exception:
        return Trace(False, "snapshot_write_failed")


# ------------------------------------------------------------------------------------------------ copertura (audit)

class _Stamps:
    """Primo seq di un evento non-snapshot con istante > soglia (come ``Timeline`` del Dataset Builder)."""

    def __init__(self, rows):
        pairs = sorted((r.event.occurred_at_ms, r.seq) for r in rows if r.event.kind != SNAPSHOT_KIND)
        self.times = [t for t, _ in pairs]
        suffix, low = [], None
        for _, s in reversed(pairs):
            low = s if low is None or s < low else low
            suffix.append(low)
        self.suffix = suffix[::-1]

    def __call__(self, threshold_ms: int) -> Optional[int]:
        i = bisect.bisect_right(self.times, threshold_ms)
        return self.suffix[i] if i < len(self.times) else None


@dataclass(frozen=True)
class Coverage:
    decisions: int
    valid: int                                  # collegamenti validi secondo la regola canonica
    chain_ok: Optional[bool]                    # None = catena non verificata
    verdicts: Mapping[str, int]                 # esito -> numero di decisioni
    missing: tuple[str, ...]                    # decisioni senza snapshot
    invalid: tuple[tuple[str, str], ...]        # (decisione, motivo) per i collegamenti presenti ma non validi
    untraced_opens: tuple[str, ...]             # aperture la cui decisione non ha un collegamento VALIDO

    @property
    def ratio(self) -> Decimal:
        return Decimal(self.valid) / Decimal(self.decisions) if self.decisions else Decimal(0)


def trace_coverage(journal: EventJournal, run_id: str, *, since_ms: int = 0, verify_chain: bool = True) -> Coverage:
    """Audit dal solo journal. Con ``verify_chain`` (predefinito) la catena di hash viene verificata: se e' rotta
    nessun collegamento e' affidabile e ``valid`` vale 0."""
    chain_ok: Optional[bool] = None
    if verify_chain:
        try:
            journal.verify_chain()
            chain_ok = True
        except Exception:
            chain_ok = False
    rows = journal.list_run("brain", run_id)
    stamps = _Stamps(rows)
    snaps: dict = {}
    opens: dict = {}
    for r in rows:
        p = r.event.payload if isinstance(r.event.payload, Mapping) else {}
        if r.event.kind == SNAPSHOT_KIND:
            snaps.setdefault(p.get("decision_event_id"), []).append(r)
        elif r.event.kind == "paper_open":
            opens.setdefault(p.get("decision_event_id"), []).append(r)
    verdicts: dict[str, int] = {}
    missing, invalid, valid_ids = [], [], set()
    decisions = [r for r in rows if r.event.kind == "brain_decision" and r.event.occurred_at_ms >= since_ms]
    for d in decisions:
        v = assess_link(d, snaps.get(d.event.event_id, []), [o.seq for o in opens.get(d.event.event_id, [])], stamps)
        if chain_ok is False and v == "valid":
            v = "chain_broken"
        verdicts[v] = verdicts.get(v, 0) + 1
        if v == "valid":
            valid_ids.add(d.event.event_id)
        elif v == "missing":
            missing.append(d.event.event_id)
        else:
            invalid.append((d.event.event_id, v))
    untraced = tuple(str(o.event.payload.get("position_id")) for did, lst in opens.items() for o in lst
                     if o.event.occurred_at_ms >= since_ms and did not in valid_ids)
    return Coverage(len(decisions), len(valid_ids), chain_ok, dict(sorted(verdicts.items())), tuple(missing),
                    tuple(invalid), untraced)
