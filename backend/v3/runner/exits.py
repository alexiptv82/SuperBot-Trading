"""Uscite meccaniche delle posizioni PAPER del Brain: stop, take-profit, durata massima.

Perche' esiste
--------------
Il motore del Brain apre soltanto (``close_modify_not_executable_r1``): senza uscite non esiste
un esito da cui imparare. Questo modulo decide SE e A QUALE PREZZO una posizione aperta esce, dato
l'elenco delle candele chiuse successive all'apertura. Chiude poi chi lo chiama, con
``executor.paper_close.close_paper`` (motivi ``stop``, ``take_profit``, ``timeout``).

Pura: nessun I/O, nessun orologio, nessuna rete. Il Brain non sceglie il take-profit: lo ricava la
politica da stop e prezzo di ingresso (``take_profit_r`` volte la distanza dallo stop). I valori
della politica sono una PROPOSTA di Claude, modificabile dall'utente solo in ``exit_policy.json``.

Regole (candele in ordine, solo quelle che APRONO a o dopo l'istante di apertura)
-------------------------------------------------------------------------------
* Stop colpito se il minimo (long) / massimo (short) lo raggiunge o lo supera. Prezzo di uscita: lo
  stop, o l'apertura della candela se ha saltato lo stop (gap), il peggiore dei due; poi si
  aggiunge la slippage ``stop_slippage_bp`` sfavorevole.
* Take-profit colpito se massimo (long) / minimo (short) lo raggiunge. Prezzo di uscita: il
  take-profit stesso (mai migliore: scelta prudente).
* Stop e take-profit nella stessa candela: vince lo stop (non si sa quale e' venuto prima).
* Durata massima: se la candela si chiude e dall'apertura sono passati almeno ``max_hold_ms``,
  uscita alla chiusura di quella candela (motivo ``timeout``), dopo i controlli di stop e target.
* La candela in cui la posizione e' stata aperta a meta' non e' usata (non si sa che prezzi
  precedessero l'apertura): lo stop e' controllato dalla candela successiva.
* Nessuna uscita: ``None``.

Codici ``ValueError`` (messaggio = codice): ``invalid_policy``, ``invalid_side``,
``invalid_position``, ``invalid_opened_at``, ``invalid_bars``, ``invalid_candle_ms``.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
from pathlib import Path
from typing import Optional

from backend.v3.features.indicators import Bar, check_bars

EXIT_STOP = "stop"
EXIT_TAKE_PROFIT = "take_profit"
EXIT_TIMEOUT = "timeout"

_CTX = Context(prec=60, rounding=ROUND_HALF_EVEN)
_Q8 = Decimal("0.00000001")
_BP = Decimal(10000)
_HOUR_MS = 3_600_000


@dataclass(frozen=True)
class ExitPolicy:
    take_profit_r: Decimal      # multiplo della distanza dallo stop; > 0, al massimo 20
    max_hold_ms: int            # durata massima della posizione; > 0
    stop_slippage_bp: Decimal   # slippage sfavorevole sull'uscita a stop; da 0 a 100


@dataclass(frozen=True)
class ExitSignal:
    reason: str                 # stop | take_profit | timeout
    price: Decimal              # prezzo di uscita, 8 decimali
    bar_open_time_ms: int       # candela che ha causato l'uscita


def _check_policy(policy: object) -> None:
    if (type(policy) is not ExitPolicy
            or type(policy.take_profit_r) is not Decimal or not policy.take_profit_r.is_finite()
            or not 0 < policy.take_profit_r <= 20
            or type(policy.max_hold_ms) is not int or policy.max_hold_ms <= 0
            or type(policy.stop_slippage_bp) is not Decimal
            or not policy.stop_slippage_bp.is_finite() or not 0 <= policy.stop_slippage_bp <= 100):
        raise ValueError("invalid_policy") from None


def take_profit_price(side: int, fill_price: Decimal, stop_price: Decimal,
                      policy: ExitPolicy) -> Decimal:
    """Prezzo del take-profit: ingresso piu' ``take_profit_r`` volte la distanza dallo stop."""
    _check_policy(policy)
    _check_position(side, fill_price, stop_price)
    with localcontext(_CTX):
        risk = abs(fill_price - stop_price)
        return (fill_price + side * policy.take_profit_r * risk).quantize(_Q8, rounding=ROUND_HALF_EVEN)


def _check_position(side: object, fill: object, stop: object) -> None:
    if type(side) is not int or side not in (-1, 1):
        raise ValueError("invalid_side") from None
    for p in (fill, stop):
        if type(p) is not Decimal or not p.is_finite() or p <= 0:
            raise ValueError("invalid_position") from None
    if (side == 1 and not stop < fill) or (side == -1 and not stop > fill):
        raise ValueError("invalid_position") from None        # lo stop deve stare dal lato della perdita


def evaluate_exit(*, side: int, fill_price: Decimal, stop_price: Decimal, opened_at_ms: int,
                  bars, candle_ms: int, policy: ExitPolicy) -> Optional[ExitSignal]:
    """Prima uscita della posizione sulle candele chiuse ``bars`` (contigue, in ordine), o ``None``."""
    _check_policy(policy)
    _check_position(side, fill_price, stop_price)
    if type(opened_at_ms) is not int or opened_at_ms <= 0:
        raise ValueError("invalid_opened_at") from None
    try:
        check_bars(bars, candle_ms=candle_ms)
    except ValueError as exc:
        raise ValueError("invalid_candle_ms" if str(exc) == "invalid_candle_ms"
                         else "invalid_bars") from None
    target = take_profit_price(side, fill_price, stop_price, policy)
    with localcontext(_CTX):
        for bar in bars:
            if bar.open_time_ms < opened_at_ms:
                continue
            if side == 1:
                stop_hit, target_hit = bar.low <= stop_price, bar.high >= target
            else:
                stop_hit, target_hit = bar.high >= stop_price, bar.low <= target
            if stop_hit:
                base = min(stop_price, bar.open) if side == 1 else max(stop_price, bar.open)
                price = base - side * base * policy.stop_slippage_bp / _BP
                return ExitSignal(EXIT_STOP, price.quantize(_Q8, rounding=ROUND_HALF_EVEN),
                                  bar.open_time_ms)
            if target_hit:
                return ExitSignal(EXIT_TAKE_PROFIT, target, bar.open_time_ms)
            if bar.open_time_ms + candle_ms - opened_at_ms >= policy.max_hold_ms:
                return ExitSignal(EXIT_TIMEOUT, bar.close, bar.open_time_ms)
    return None


# ----------------------------------------------------------------------------- politica da file
_POLICY_KEYS = {"schema_version", "take_profit_r", "max_hold_hours", "stop_slippage_bp"}


def _pairs(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise ValueError("invalid_policy") from None
        out[k] = v
    return out


def _reject_constant(_c):
    raise ValueError("invalid_policy") from None


def _number(value: object) -> Decimal:
    """Stringa decimale semplice (0-3 cifre intere, fino a 4 decimali), come nei parametri L5."""
    if type(value) is not str:
        raise ValueError("invalid_policy") from None
    bits = value.split(".")
    if (len(bits) > 2 or not 1 <= len(bits[0]) <= 3 or not bits[0].isascii() or not bits[0].isdigit()
            or (len(bits) == 2 and (not 1 <= len(bits[1]) <= 4 or not bits[1].isascii()
                                    or not bits[1].isdigit()))):
        raise ValueError("invalid_policy") from None
    return Decimal(value)


def load_exit_policy(raw: bytes) -> ExitPolicy:
    """Legge soltanto byte esatti: niente chiavi doppie, costanti, tipi o intervalli sbagliati."""
    if type(raw) is not bytes:
        raise ValueError("invalid_policy") from None
    try:
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_reject_constant)
        if type(data) is not dict or set(data) != _POLICY_KEYS:
            raise ValueError("invalid_policy")
        version, hours = data["schema_version"], data["max_hold_hours"]
        if type(version) is not int or version != 1 or type(hours) is not int or not 1 <= hours <= 720:
            raise ValueError("invalid_policy")
        policy = ExitPolicy(_number(data["take_profit_r"]), hours * _HOUR_MS,
                            _number(data["stop_slippage_bp"]))
        _check_policy(policy)
        return policy
    except Exception:
        raise ValueError("invalid_policy") from None


def default_policy_path() -> Path:
    return Path(__file__).with_name("exit_policy.json")


def load_default_policy() -> ExitPolicy:
    """Unico punto che legge il file: da chiamare in configurazione."""
    return load_exit_policy(default_policy_path().read_bytes())
