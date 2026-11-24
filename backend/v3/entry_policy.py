"""Politica d'ingresso e di gestione VERSIONABILE del Brain unico (Brain Live Evolution, 24/11/2026).

Blocco opzionale ``brain_unico.entry_policy`` della configurazione. Ogni campo ha un valore predefinito che riproduce
ESATTAMENTE il comportamento precedente: senza blocco (o con il blocco ai predefiniti) nulla cambia. Le regole sono
deterministiche e verificabili sui dati che il Brain ha gia' al momento della decisione (vista di mercato su candele
chiuse, prezzo, stop proposto); nessuna regola allarga uno stop o aumenta il rischio autorizzato.

* Filtri d'ingresso (prima del consulto, senza spesa AI):
  - ``long_trend_filter``: un LONG solo con trend favorevole su 1h E 4h (prezzo sopra l'EMA lenta e EMA veloce sopra
    la lenta, ``ema_slow_gap_bp > 0`` e ``ema_cross == 1``); dati mancanti = nessun LONG (``trend_unknown``).
  - ``max_cost_fraction_r``: costi di andata e ritorno (commissioni + slittamento, ``estimated_roundtrip_cost_bp``)
    divisi per la distanza dello stop; sopra la soglia nessuna apertura. Non allarga mai lo stop.
* Consulto di Claude sull'ingresso: soglie di confidenza differenziate (BTC, ETH, oro, argento / altri), regime
  EXPANSION come criterio si'/no, comportamento quando Claude non e' consultabile (limite, budget, errore):
  ``veto`` (com'e' oggi) oppure ``half_risk`` (apertura a rischio dimezzato, solo con confidenza sopra soglia).
* Guardia sugli stop spostati dall'AI: distanza minima dal prezzo in multipli dell'ATR 1h; rifiuto degli stop che
  fissano una piccola perdita vicino all'ingresso (zona dei costi): la protezione resta a pareggio, trailing e parziale.
* Secondo ingresso: miglioramento minimo del prezzo e distanza minima dallo stop, in R.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from typing import Mapping, Optional

TIER_A = frozenset({"BTCUSDT", "ETHUSDT", "XAUUSDT", "XAGUSDT"})
FALLBACKS = ("veto", "half_risk")
HALF_RISK = 0.5
# stati di ClaudeView in cui Claude NON ha dato un giudizio (limite per giro, budget, errore, risposta illeggibile)
NOT_CONSULTED = ("skipped_limit", "budget", "timeout_or_error", "unavailable", "invalid")


@dataclass(frozen=True)
class EntryPolicy:
    long_trend_filter: bool = False
    max_cost_fraction_r: Optional[Decimal] = None
    consult_conf_tier_a: Decimal = Decimal("0.65")
    consult_conf_other: Decimal = Decimal("0.65")
    consult_on_expansion: bool = True
    consult_limit_fallback: str = "veto"
    stop_guard_atr_mult: Optional[Decimal] = None
    stop_guard_cost_zone: bool = False
    scale_in_min_gap_r: Decimal = Decimal("0.25")
    scale_in_min_stop_room_r: Decimal = Decimal("0.3")

    def to_json(self) -> dict:
        return {k: (str(v) if isinstance(v, Decimal) else v) for k, v in asdict(self).items()}

    def consult_threshold(self, symbol: str) -> Decimal:
        return self.consult_conf_tier_a if symbol in TIER_A else self.consult_conf_other


DEFAULT = EntryPolicy()
_KEYS = set(DEFAULT.to_json())


def _dec(v, lo: str, hi: str, *, nullable: bool = False) -> Optional[Decimal]:
    if v is None and nullable:
        return None
    if isinstance(v, bool):
        raise ValueError("invalid_entry_policy")
    try:
        d = Decimal(str(v))
    except (InvalidOperation, ValueError):
        raise ValueError("invalid_entry_policy") from None
    if not d.is_finite() or not Decimal(lo) <= d <= Decimal(hi):
        raise ValueError("invalid_entry_policy")
    return d


def policy_from_config(raw) -> EntryPolicy:
    if raw is None:
        return DEFAULT
    if not isinstance(raw, Mapping) or set(raw) != _KEYS:
        raise ValueError("invalid_entry_policy")
    for k in ("long_trend_filter", "consult_on_expansion", "stop_guard_cost_zone"):
        if type(raw[k]) is not bool:
            raise ValueError("invalid_entry_policy")
    if raw["consult_limit_fallback"] not in FALLBACKS:
        raise ValueError("invalid_entry_policy")
    return EntryPolicy(
        long_trend_filter=raw["long_trend_filter"],
        max_cost_fraction_r=_dec(raw["max_cost_fraction_r"], "0.05", "1", nullable=True),
        consult_conf_tier_a=_dec(raw["consult_conf_tier_a"], "0", "1"),
        consult_conf_other=_dec(raw["consult_conf_other"], "0", "1"),
        consult_on_expansion=raw["consult_on_expansion"],
        consult_limit_fallback=raw["consult_limit_fallback"],
        stop_guard_atr_mult=_dec(raw["stop_guard_atr_mult"], "0.1", "5", nullable=True),
        stop_guard_cost_zone=raw["stop_guard_cost_zone"],
        scale_in_min_gap_r=_dec(raw["scale_in_min_gap_r"], "0.1", "2"),
        scale_in_min_stop_room_r=_dec(raw["scale_in_min_stop_room_r"], "0.1", "2"))


def of_open_payload(payload, default: EntryPolicy = DEFAULT) -> EntryPolicy:
    """Politica con cui la posizione e' nata (fotografia ``strategy.entry_policy``); senza: ``default``."""
    snap = payload.get("strategy") if isinstance(payload, Mapping) else None
    raw = snap.get("entry_policy") if isinstance(snap, Mapping) else None
    if raw is None:
        return default
    try:
        return policy_from_config(raw)
    except ValueError:
        return default


# ----------------------------------------------------------------------------- regole
def _tf(market, name: str) -> Optional[Mapping]:
    for e in (market or {}).get("timeframes", ()) if isinstance(market, Mapping) else ():
        if isinstance(e, Mapping) and e.get("tf") == name and e.get("status") == "ok":
            return e
    return None


def trend(market, tf: str) -> Optional[int]:
    """+1 trend su (prezzo sopra EMA lenta, EMA veloce sopra la lenta), -1 giu', 0 misto, None dati mancanti."""
    e = _tf(market, tf)
    if e is None:
        return None
    try:
        gap, cross = Decimal(str(e.get("ema_slow_gap_bp"))), int(e.get("ema_cross"))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if gap > 0 and cross == 1:
        return 1
    if gap < 0 and cross == -1:
        return -1
    return 0


def atr_bp(market, tf: str = "1h") -> Optional[Decimal]:
    e = _tf(market, tf)
    try:
        v = Decimal(str(e.get("atr_bp"))) if e is not None else None
    except (InvalidOperation, TypeError, ValueError):
        return None
    return v if v is not None and v.is_finite() and v > 0 else None


def cost_fraction(entry: Decimal, stop: Decimal, roundtrip_cost_bp: Decimal) -> Optional[Decimal]:
    dist = abs(entry - stop)
    if entry <= 0 or dist <= 0:
        return None
    return (entry * roundtrip_cost_bp / Decimal(10000)) / dist


def entry_block(policy: EntryPolicy, *, side: int, entry: Decimal, stop: Decimal, market,
                roundtrip_cost_bp: Decimal) -> Optional[str]:
    """Codice del filtro che blocca l'apertura, o None. Mai un allargamento dello stop."""
    if policy.long_trend_filter and side == 1:
        t1, t4 = trend(market, "1h"), trend(market, "4h")
        if t1 is None or t4 is None:
            return "long_trend_unknown"
        if not (t1 == 1 and t4 == 1):
            return "long_against_trend"
    if policy.max_cost_fraction_r is not None:
        c = cost_fraction(entry, stop, roundtrip_cost_bp)
        if c is None or c > policy.max_cost_fraction_r:
            return "cost_too_high_for_stop"
    return None


def stop_guard(policy: EntryPolicy, *, side: int, entry: Decimal, initial_stop: Decimal, new_stop: Decimal,
               price: Decimal, atr_1h_bp: Optional[Decimal], roundtrip_cost_bp: Decimal) -> Optional[str]:
    """Codice che rifiuta uno stop spostato dall'AI (gia' piu' stretto del precedente), o None."""
    if policy.stop_guard_atr_mult is not None:
        if atr_1h_bp is None:
            return "stop_volatility_unknown"
        if side * (price - new_stop) < price * policy.stop_guard_atr_mult * atr_1h_bp / Decimal(10000):
            return "stop_too_tight_for_volatility"
    if policy.stop_guard_cost_zone:
        r0 = abs(entry - initial_stop)
        locked = side * (new_stop - entry)                    # > 0: profitto bloccato; < 0: perdita ancora possibile
        costs = entry * roundtrip_cost_bp / Decimal(10000)
        if r0 > 0 and -Decimal("0.5") * r0 < locked < costs:
            return "stop_in_cost_zone"
    return None
