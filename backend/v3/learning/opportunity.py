"""Etichettatura a posteriori delle opportunita' (F7, passo P5: nucleo dell'Opportunity Cost Engine).

Il campione dei soli trade eseguiti e' troppo piccolo per distinguere un edge di
poche decine di bp netti per cella. Questo modulo etichetta anche i *candidati non
eseguiti* (long e short): "se lo avessi preso, cosa sarebbe successo a +15 min,
+1 h, +4 h, e quale livello, stop o obiettivo, sarebbe stato toccato per primo?".
Etichetta soltanto: non decide, non apre, non chiude nulla.

Regole esatte (contratto verificato dai test)
---------------------------------------------
* Modulo puro: nessuna I/O, rete, orologio, casualita'; solo libreria standard;
  niente ``float``. ``Decimal`` in un contesto LOCALE (60 cifre, half-even): il
  risultato non dipende dal contesto globale del chiamante. bp a 4 decimali half-even.
* Nessuna scelta di modello nel codice: ``candle_ms``, ``horizons_ms``, ``cost_bp``
  e ``ambiguous_policy`` sono argomenti obbligatori, senza default.
* Finestra: per un orizzonte ``h``, ``start = ceil(signal_time_ms / candle_ms) *
  candle_ms`` (interi) e la finestra e' formata dalle ``h / candle_ms`` candele con
  ``open_time_ms = start, start + candle_ms, ...``. La candela che CONTIENE il
  segnale (segnale non allineato) e' esclusa: del suo percorso prima del segnale non
  si sa nulla. Se una qualunque candela della finestra manca (buco, serie finita,
  simbolo assente) l'orizzonte e' ``incomplete`` con tutti gli altri campi ``None``.
  Mai interpolare.
* Tocchi, in ordine di candela. Long: ``stop = low <= stop_price``,
  ``target = high >= target_price``; short: ``stop = high >= stop_price``,
  ``target = low <= target_price``. Alla prima candela con un tocco: solo stop ->
  ``stop``; solo obiettivo -> ``target``; ENTRAMBI nella stessa candela ->
  ``ambiguous=True`` e vince ``stop`` con ``stop_first``, ``target`` con
  ``target_first``. Nessun tocco -> ``timeout`` al ``close`` dell'ultima candela.
* ``gross_bp = side * (exit - entry) / entry * 10000``; ``net_bp = gross_bp -
  cost_bp``. Entrambi sono calcolati esatti e poi arrotondati a 4 decimali
  (``net_bp`` NON e' il ``gross_bp`` gia' arrotondato meno il costo). ``cost_bp``
  (costi round-trip in bp del nozionale d'ingresso) e' lo stesso per ogni barriera.
* Coerenza fra orizzonti: se a ``h1`` la barriera e' stop/target, ogni orizzonte
  piu' lungo (completo) ha la stessa barriera, ``touch_time_ms``, ``exit_price`` e
  ``ambiguous``; possono differire solo i ``timeout``.
* L'output segue l'ordine dei candidati in ingresso; gli input non sono modificati.

Validazione (``ValueError`` con il codice come messaggio, prima di qualunque calcolo,
in quest'ordine): ``invalid_candle_ms``, ``invalid_horizons``, ``invalid_cost_bp``,
``invalid_ambiguous_policy``, ``invalid_candidate`` (``candidates`` deve essere una
SEQUENZA, non un generatore ne' un insieme; ogni elemento valido; id unici),
``invalid_candles`` (mapping simbolo -> SEQUENZA di ``Candle`` validi, allineati alla
griglia, strettamente crescenti). Dopo la validazione l'unico errore possibile e'
``numeric_out_of_range`` (prezzi finiti ma a scale tali da non essere rappresentabili).

Limiti noti: non si modellano gap ne' slippage (l'uscita a stop/obiettivo e' esattamente
al livello dichiarato, anche se la candela apre oltre); l'ordine di tocco dentro una
stessa candela e' sconosciuto (da qui ``ambiguous``); i costi non dipendono dalla barriera.
"""
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext
from typing import Optional

_CTX = Context(prec=60, rounding=ROUND_HALF_EVEN)
_Q4 = Decimal("0.0001")
_BP = Decimal(10000)
_ID_RE = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}")      # usata con fullmatch: niente "\n" finale
POLICIES = ("stop_first", "target_first")


def _q4(d: Decimal) -> Decimal:
    """4 decimali half-even; mai uno zero negativo."""
    r = d.quantize(_Q4, rounding=ROUND_HALF_EVEN)
    return abs(r) if r == 0 else r


@dataclass(frozen=True)
class Candle:
    open_time_ms: int       # inizio della candela, UTC ms
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal


@dataclass(frozen=True)
class Candidate:
    candidate_id: str       # [a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}
    symbol: str             # non vuoto
    side: int               # +1 long / -1 short
    signal_time_ms: int     # > 0
    entry_price: Decimal    # > 0
    stop_price: Decimal     # long: < entry ; short: > entry
    target_price: Decimal   # long: > entry ; short: < entry


@dataclass(frozen=True)
class HorizonLabel:
    horizon_ms: int
    status: str                       # "complete" | "incomplete"
    barrier: Optional[str]            # "target" | "stop" | "timeout"; None se incomplete
    ambiguous: bool                   # stop e target nella STESSA candela (risolto dalla policy)
    touch_time_ms: Optional[int]      # open_time_ms della candela del tocco; None se timeout/incomplete
    exit_price: Optional[Decimal]
    gross_bp: Optional[Decimal]
    net_bp: Optional[Decimal]


@dataclass(frozen=True)
class OpportunityLabel:
    candidate_id: str
    symbol: str
    side: int
    horizons: tuple[HorizonLabel, ...]   # nello stesso ordine di horizons_ms


# ---------------------------------------------------------------------------
# validazione
# ---------------------------------------------------------------------------

def _finite_pos(d: object) -> bool:
    return isinstance(d, Decimal) and d.is_finite() and d > 0


def _check_candidate(c: object, seen: set) -> None:
    bad = ValueError("invalid_candidate")
    if not isinstance(c, Candidate):
        raise bad
    if not isinstance(c.candidate_id, str) or not _ID_RE.fullmatch(c.candidate_id):
        raise bad
    if c.candidate_id in seen:
        raise bad
    seen.add(c.candidate_id)
    if not isinstance(c.symbol, str) or not c.symbol:
        raise bad
    if type(c.side) is not int or c.side not in (-1, 1):
        raise bad
    if type(c.signal_time_ms) is not int or c.signal_time_ms <= 0:
        raise bad
    if not (_finite_pos(c.entry_price) and _finite_pos(c.stop_price) and _finite_pos(c.target_price)):
        raise bad
    ok = (c.stop_price < c.entry_price < c.target_price) if c.side == 1 \
        else (c.target_price < c.entry_price < c.stop_price)
    if not ok:
        raise bad


def _check_candle(cn: object, candle_ms: int, prev_t: int) -> None:
    bad = ValueError("invalid_candles")
    if not isinstance(cn, Candle):
        raise bad
    if not all(_finite_pos(p) for p in (cn.open, cn.high, cn.low, cn.close)):
        raise bad
    if cn.low > min(cn.open, cn.close) or cn.high < max(cn.open, cn.close):
        raise bad
    if type(cn.open_time_ms) is not int or cn.open_time_ms < 0 or cn.open_time_ms % candle_ms != 0:
        raise bad
    if cn.open_time_ms <= prev_t:
        raise bad


def _validate(candidates, candles, candle_ms, horizons_ms, cost_bp, ambiguous_policy) -> None:
    if type(candle_ms) is not int or candle_ms < 1:
        raise ValueError("invalid_candle_ms")
    if not isinstance(horizons_ms, (list, tuple)) or not horizons_ms:
        raise ValueError("invalid_horizons")
    prev = 0
    for h in horizons_ms:
        if type(h) is not int or h <= prev or h % candle_ms != 0:
            raise ValueError("invalid_horizons")
        prev = h
    if not isinstance(cost_bp, Decimal) or not cost_bp.is_finite() or cost_bp < 0:
        raise ValueError("invalid_cost_bp")
    if not isinstance(ambiguous_policy, str) or ambiguous_policy not in POLICIES:
        raise ValueError("invalid_ambiguous_policy")
    # Una SEQUENZA, non un iteratore: validare un generatore lo consumerebbe e il
    # calcolo vedrebbe zero candidati (risultato vuoto in silenzio); un insieme non ha ordine.
    if not isinstance(candidates, Sequence):
        raise ValueError("invalid_candidate")
    seen: set = set()
    for c in candidates:
        _check_candidate(c, seen)
    if not isinstance(candles, Mapping):
        raise ValueError("invalid_candles")
    for sym, series in candles.items():
        if not isinstance(sym, str) or not isinstance(series, Sequence):
            raise ValueError("invalid_candles")
        prev_t = -1
        for cn in series:
            _check_candle(cn, candle_ms, prev_t)
            prev_t = cn.open_time_ms


# ---------------------------------------------------------------------------
# etichettatura
# ---------------------------------------------------------------------------

def _label_horizon(c: Candidate, by_time: Mapping[int, Candle], start: int, h: int,
                   candle_ms: int, cost_bp: Decimal, policy: str) -> HorizonLabel:
    window = []
    for i in range(h // candle_ms):
        cn = by_time.get(start + i * candle_ms)
        if cn is None:
            return HorizonLabel(h, "incomplete", None, False, None, None, None, None)
        window.append(cn)

    barrier: Optional[str] = None
    ambiguous = False
    touch_time: Optional[int] = None
    for cn in window:
        if c.side == 1:
            stop_hit, target_hit = cn.low <= c.stop_price, cn.high >= c.target_price
        else:
            stop_hit, target_hit = cn.high >= c.stop_price, cn.low <= c.target_price
        if stop_hit or target_hit:
            ambiguous = stop_hit and target_hit
            if ambiguous:
                barrier = "stop" if policy == "stop_first" else "target"
            else:
                barrier = "stop" if stop_hit else "target"
            touch_time = cn.open_time_ms
            break
    if barrier is None:
        barrier, exit_price = "timeout", window[-1].close
    else:
        exit_price = c.stop_price if barrier == "stop" else c.target_price

    gross = Decimal(c.side) * (exit_price - c.entry_price) / c.entry_price * _BP
    return HorizonLabel(h, "complete", barrier, ambiguous, touch_time, exit_price,
                        _q4(gross), _q4(gross - cost_bp))


def label_candidates(
    candidates: Sequence[Candidate],
    candles: Mapping[str, Sequence[Candle]],
    *,
    candle_ms: int,
    horizons_ms: Sequence[int],
    cost_bp: Decimal,
    ambiguous_policy: str,
) -> tuple[OpportunityLabel, ...]:
    """Etichetta ogni candidato a ogni orizzonte (vedi la docstring del modulo)."""
    _validate(candidates, candles, candle_ms, horizons_ms, cost_bp, ambiguous_policy)

    index: dict[str, dict[int, Candle]] = {}          # per simbolo, costruito una volta sola
    out = []
    try:
        with localcontext(_CTX):
            for c in candidates:
                by_time = index.get(c.symbol)
                if by_time is None:
                    by_time = index[c.symbol] = {cn.open_time_ms: cn for cn in candles.get(c.symbol, ())}
                start = -(-c.signal_time_ms // candle_ms) * candle_ms          # ceil con soli interi
                out.append(OpportunityLabel(
                    c.candidate_id, c.symbol, c.side,
                    tuple(_label_horizon(c, by_time, start, h, candle_ms, cost_bp, ambiguous_policy)
                          for h in horizons_ms)))
    except ArithmeticError:
        # prezzi finiti ma a scale non rappresentabili: non si inventano numeri
        raise ValueError("numeric_out_of_range") from None
    return tuple(out)
