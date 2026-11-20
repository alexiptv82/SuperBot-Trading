"""Traccia causale di ogni decisione del Brain: snapshot v2 scritto DOPO la decisione e PRIMA di un'apertura.

Per ogni simbolo deciso nel giro, ``record_decision_trace``:
  1. trova la ``brain_decision`` scritta da QUESTO passo del motore (seq > ``after_seq``, stesso simbolo e istante):
     anche le NO_TRADE, che il motore scrive senza restituire l'id. Se manca, lo dice (``decision_not_journaled``):
     il motore inghiotte i propri errori di scrittura e qui diventano visibili;
  2. calcola feature deterministiche SOLO da candele chiuse entro ``now_ms`` (nessuna informazione futura) e i
     numeri di rischio del portafoglio usati dal motore per la stessa decisione;
  3. scrive lo snapshot con l'adattatore ``decision_snapshot_v2`` (idempotente, legato a id+hash della decisione,
     controllo dell'ordine di scrittura). Lo snapshot resta ``inputs_verified=False`` e
     ``eligible_for_training=False``: escluso dal training fino a una validazione indipendente.

Non solleva mai: restituisce un ``Trace`` con ``ok`` e un codice. Il ciclo decide che cosa fare di un fallimento
(nessuna apertura senza traccia, errore esplicito nel rapporto). Niente rete, niente orologio, nessuna dipendenza
da RiskManager o ExitService: le uscite non passano di qui.

``trace_coverage`` misura dal SOLO journal le decisioni e le aperture prive di snapshot: un buco resta
rilevabile anche dopo, senza fidarsi del rapporto del giro.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re
from typing import Mapping, Optional, Sequence

from backend.v3.decision_snapshot_v2 import SNAPSHOT_KIND, DecisionSnapshotV2, append_snapshot
from backend.v3.events import EventJournal
from backend.v3.features.indicators import atr, rsi

FEATURE_SET_VERSION = 1
PERIOD = 14
_Q = Decimal("1e-10")
_CODE = re.compile(r"[a-z][a-z0-9_]{0,47}")


@dataclass(frozen=True)
class Trace:
    ok: bool
    code: str                                   # "recorded" | "already_recorded" | codice di errore
    decision_event_id: Optional[str] = None
    snapshot_event_id: Optional[str] = None


def _q(value: Decimal) -> Decimal:
    return value.quantize(_Q)


def decision_features(bars_by_tf: Mapping[str, Sequence], timeframes, *, now_ms: int) -> tuple[dict, Optional[int]]:
    """Feature v1 per timeframe ``t<nome>_*``: ret_1, ret_n (finestra del timeframe), atr14_pct, rsi14.

    Si usano solo barre chiuse entro ``now_ms`` (open + durata <= now). Una feature non calcolabile (storia corta,
    barre non contigue) viene omessa, mai inventata. Restituisce (feature, asof) con asof = chiusura dell'ultima
    barra usata; (``{}``, None) se nessuna barra e' utilizzabile.
    """
    feats: dict[str, Decimal] = {}
    asof: Optional[int] = None
    for spec in timeframes:
        step = spec.candle_ms
        bars = [b for b in (bars_by_tf.get(spec.name) or ()) if b.open_time_ms + step <= now_ms]
        if len(bars) < 2:
            continue
        prefix = "t" + spec.name.lower()
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
    if feats:
        feats["fset_version"] = Decimal(FEATURE_SET_VERSION)
    return feats, asof


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
    rows = journal.list_run("brain", run_id)
    return rows[-1].seq if rows else 0


def record_decision_trace(*, journal: EventJournal, run_id: str, symbol: str, now_ms: int, after_seq: int,
                          expected_event_id: Optional[str], bars_by_tf: Mapping[str, Sequence], timeframes,
                          portfolio) -> Trace:
    try:
        rows = journal.list_run("brain", run_id)
        mine = [r for r in rows if r.seq > after_seq and r.event.kind == "brain_decision"
                and r.event.occurred_at_ms == now_ms and isinstance(r.event.payload, Mapping)
                and r.event.payload.get("symbol") == symbol]
        if expected_event_id is not None:
            mine = [r for r in mine if r.event.event_id == expected_event_id]
        if not mine:
            return Trace(False, "decision_not_journaled")
        if len(mine) != 1:
            return Trace(False, "decision_ambiguous")
        decision_id = mine[0].event.event_id
        feats, asof = decision_features(bars_by_tf, timeframes, now_ms=now_ms)
        snapshot = DecisionSnapshotV2(decision_event_id=decision_id, decision_ts_ms=now_ms, captured_at_ms=now_ms,
                                      feature_asof_ms=asof, features=feats, risk=_risk_numbers(portfolio))
        existed = {r.event.event_id for r in rows if r.event.kind == SNAPSHOT_KIND}
        stored = append_snapshot(journal=journal, run_id=run_id, snapshot=snapshot)
        sid = stored.event.event_id
        return Trace(True, "already_recorded" if sid in existed else "recorded", decision_id, sid)
    except ValueError as exc:                     # adattatore: codici espliciti (ordine, futuro, legame); conflitto
        return Trace(False, "snapshot_" + _safe(str(exc), "rejected"))
    except Exception:
        return Trace(False, "snapshot_write_failed")


@dataclass(frozen=True)
class Coverage:
    decisions: int
    traced: int
    untraced_decisions: tuple[str, ...]
    untraced_opens: tuple[str, ...]          # position_id di aperture la cui decisione non ha snapshot


def trace_coverage(journal: EventJournal, run_id: str, *, since_ms: int = 0) -> Coverage:
    """Dal solo journal: quante decisioni (da ``since_ms``) hanno uno snapshot v2 e quali aperture ne sono prive."""
    rows = journal.list_run("brain", run_id)
    linked = {r.event.payload.get("decision_event_id") for r in rows
              if r.event.kind == SNAPSHOT_KIND and isinstance(r.event.payload, Mapping)}
    decisions = [r.event.event_id for r in rows
                 if r.event.kind == "brain_decision" and r.event.occurred_at_ms >= since_ms]
    untraced = tuple(d for d in decisions if d not in linked)
    opens = tuple(str(r.event.payload.get("position_id")) for r in rows
                  if r.event.kind == "paper_open" and r.event.occurred_at_ms >= since_ms
                  and isinstance(r.event.payload, Mapping)
                  and r.event.payload.get("decision_event_id") not in linked)
    return Coverage(len(decisions), len(decisions) - len(untraced), untraced, opens)
