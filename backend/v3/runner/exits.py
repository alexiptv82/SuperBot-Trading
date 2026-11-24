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

Protezione dei profitti (solo con politica schema 2; lo schema 1 di oggi e' invariato)
-----------------------------------------------------------------------------------
Break-even (stop all'ingresso + commissioni di andata e ritorno + slippage dello stop), trailing a distanza in R
dal miglior prezzo, protezione di una quota dell'escursione favorevole: stesse regole dei bracci pre-registrati del
laboratorio ``ops/brain-unico/exits/arms.py`` (un test le confronta). Lo stop valido per una candela dipende solo
dalle candele gia' CHIUSE e si muove solo verso il profitto. L'uscita resta ``stop``; ``ExitSignal.stop_kind`` dice
se lo stop era quello iniziale o uno spostato. Nessuna chiusura legata all'ora del giorno.

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
STOP_INITIAL, STOP_BREAK_EVEN, STOP_TRAILING, STOP_PROTECT = "initial", "break_even", "trailing", "protect"
STOP_BRAIN = "brain"          # Brain unico: stop stretto dalla revisione AI (solo verso il profitto)

_CTX = Context(prec=60, rounding=ROUND_HALF_EVEN)
_Q8 = Decimal("0.00000001")
_BP = Decimal(10000)
_HOUR_MS = 3_600_000


@dataclass(frozen=True)
class ExitPolicy:
    take_profit_r: Decimal      # multiplo della distanza dallo stop; > 0, al massimo 20
    max_hold_ms: Optional[int]  # durata massima della posizione; > 0. None (solo schema 2, Brain unico 24/11) = NESSUNA
                                # chiusura per solo tempo: decidono stop, take-profit, protezione e revisione AI
    stop_slippage_bp: Decimal   # slippage sfavorevole sull'uscita a stop; da 0 a 100
    # Protezione dei profitti (schema 2, SPENTA se None). Stesse regole e stessi nomi dei bracci del laboratorio
    # pre-registrato ``ops/brain-unico/exits/arms.py``: lo stop valido per una candela dipende SOLO dal miglior
    # prezzo delle candele gia' chiuse; si muove solo verso il profitto, mai indietro.
    be_at_r: Optional[Decimal] = None        # break-even: a +be_at_r R lo stop va all'ingresso + costi
    trail_at_r: Optional[Decimal] = None     # trailing: attivazione a +trail_at_r R ...
    trail_dist_r: Optional[Decimal] = None   # ... a trail_dist_r R dal miglior prezzo
    protect_at_r: Optional[Decimal] = None   # protezione: a +protect_at_r R blocca ...
    protect_frac: Optional[Decimal] = None   # ... questa quota dell'escursione favorevole (0-1)

    @property
    def protects(self) -> bool:
        return any(v is not None for v in (self.be_at_r, self.trail_at_r, self.protect_at_r))


@dataclass(frozen=True)
class ExitSignal:
    reason: str                 # stop | take_profit | timeout
    price: Decimal              # prezzo di uscita, 8 decimali
    bar_open_time_ms: int       # candela che ha causato l'uscita
    stop_kind: str = STOP_INITIAL   # solo per reason=stop: initial | break_even | trailing | protect


def _r_value(v, *, upper=Decimal(20), frac=False) -> bool:
    if type(v) is not Decimal or not v.is_finite():
        return False
    return 0 < v < 1 if frac else 0 < v <= upper


def _check_policy(policy: object) -> None:
    if (type(policy) is not ExitPolicy
            or type(policy.take_profit_r) is not Decimal or not policy.take_profit_r.is_finite()
            or not 0 < policy.take_profit_r <= 20
            or (policy.max_hold_ms is not None and (type(policy.max_hold_ms) is not int or policy.max_hold_ms <= 0))
            or type(policy.stop_slippage_bp) is not Decimal
            or not policy.stop_slippage_bp.is_finite() or not 0 <= policy.stop_slippage_bp <= 100):
        raise ValueError("invalid_policy") from None
    if ((policy.be_at_r is not None and not _r_value(policy.be_at_r))
            or (policy.trail_at_r is None) != (policy.trail_dist_r is None)
            or (policy.trail_at_r is not None
                and not (_r_value(policy.trail_at_r) and _r_value(policy.trail_dist_r)))
            or (policy.protect_at_r is None) != (policy.protect_frac is None)
            or (policy.protect_at_r is not None
                and not (_r_value(policy.protect_at_r) and _r_value(policy.protect_frac, frac=True)))):
        raise ValueError("invalid_policy") from None


def protected_stop(side: int, fill_price: Decimal, stop_price: Decimal, best: Decimal,
                   policy: ExitPolicy, fee_bps: Optional[Decimal]) -> tuple[Decimal, str]:
    """Stop valido dopo che il miglior prezzo favorevole (candele CHIUSE) e' ``best``, e chi lo determina.

    Funzione del solo ``best`` (monotono): per questo il monitor puo' riprendere il calcolo dopo un buco del feed
    passando il miglior prezzo dei tratti precedenti, con lo stesso risultato di un'unica serie di candele."""
    stop, kind = stop_price, STOP_INITIAL
    if not policy.protects:
        return stop, kind
    with localcontext(_CTX):
        risk = abs(fill_price - stop_price)
        mfe = side * (best - fill_price)
        levels = []
        if policy.be_at_r is not None and mfe >= policy.be_at_r * risk:
            if type(fee_bps) is not Decimal or not fee_bps.is_finite() or not 0 <= fee_bps <= 100:
                raise ValueError("invalid_fee") from None
            # ingresso + commissioni di andata e ritorno + slippage dello stop: l'uscita al break-even non perde
            levels.append((fill_price + side * fill_price * (2 * fee_bps + policy.stop_slippage_bp) / _BP,
                           STOP_BREAK_EVEN))
        if policy.trail_at_r is not None and mfe >= policy.trail_at_r * risk:
            levels.append((best - side * policy.trail_dist_r * risk, STOP_TRAILING))
        if policy.protect_at_r is not None and mfe >= policy.protect_at_r * risk:
            levels.append((fill_price + side * policy.protect_frac * mfe, STOP_PROTECT))
        for level, why in levels:
            if side * (level - stop) > 0:
                stop, kind = level, why
        return stop.quantize(_Q8, rounding=ROUND_HALF_EVEN), kind


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


def favorable_extreme(side: int, best: Optional[Decimal], bars, opened_at_ms: int) -> Optional[Decimal]:
    """Miglior prezzo favorevole (massimo per il long, minimo per lo short) fra ``best`` e le candele dall'apertura."""
    for bar in bars:
        if bar.open_time_ms < opened_at_ms:
            continue
        px = bar.high if side == 1 else bar.low
        if best is None or side * (px - best) > 0:
            best = px
    return best


def evaluate_exit(*, side: int, fill_price: Decimal, stop_price: Decimal, opened_at_ms: int,
                  bars, candle_ms: int, policy: ExitPolicy, fee_bps: Optional[Decimal] = None,
                  best_before: Optional[Decimal] = None, stop_moves: tuple = ()) -> Optional[ExitSignal]:
    """Prima uscita della posizione sulle candele chiuse ``bars`` (contigue, in ordine), o ``None``.

    Con protezione attiva (``policy.protects``): ``fee_bps`` = commissioni per lato (servono al break-even) e
    ``best_before`` = miglior prezzo favorevole delle candele chiuse PRIMA di ``bars`` (tratti precedenti a un
    buco del feed). Senza protezione i due argomenti non contano e il risultato e' quello di sempre."""
    _check_policy(policy)
    _check_position(side, fill_price, stop_price)
    if best_before is not None and (type(best_before) is not Decimal or not best_before.is_finite()
                                    or best_before <= 0):
        raise ValueError("invalid_position") from None
    if best_before is None or side * (best_before - fill_price) < 0:
        best_before = fill_price
    best = best_before
    stop_price_now, kind = protected_stop(side, fill_price, stop_price, best, policy, fee_bps)
    if type(opened_at_ms) is not int or opened_at_ms <= 0:
        raise ValueError("invalid_opened_at") from None
    try:
        check_bars(bars, candle_ms=candle_ms)
    except ValueError as exc:
        raise ValueError("invalid_candle_ms" if str(exc) == "invalid_candle_ms"
                         else "invalid_bars") from None
    target = take_profit_price(side, fill_price, stop_price, policy)
    # Brain unico: stop stretti dall'AI ``(valido_dalla_candela_ms, prezzo)``; valgono solo se piu' favorevoli dello
    # stop del momento (mai un allargamento). Nessuno spostamento = comportamento di sempre.
    for move in stop_moves:
        if (type(move) is not tuple or len(move) != 2 or type(move[0]) is not int or type(move[1]) is not Decimal
                or not move[1].is_finite() or move[1] <= 0):
            raise ValueError("invalid_position") from None
    with localcontext(_CTX):
        for bar in bars:
            if bar.open_time_ms < opened_at_ms:
                continue
            stop_now, kind_now = stop_price_now, kind
            for at_ms, level in stop_moves:
                if at_ms <= bar.open_time_ms and side * (level - stop_now) > 0:
                    stop_now, kind_now = level, STOP_BRAIN
            if side == 1:
                stop_hit, target_hit = bar.low <= stop_now, bar.high >= target
            else:
                stop_hit, target_hit = bar.high >= stop_now, bar.low <= target
            if stop_hit:
                base = min(stop_now, bar.open) if side == 1 else max(stop_now, bar.open)
                price = base - side * base * policy.stop_slippage_bp / _BP
                return ExitSignal(EXIT_STOP, price.quantize(_Q8, rounding=ROUND_HALF_EVEN),
                                  bar.open_time_ms, kind_now)
            if target_hit:
                return ExitSignal(EXIT_TAKE_PROFIT, target, bar.open_time_ms)
            if policy.max_hold_ms is not None and bar.open_time_ms + candle_ms - opened_at_ms >= policy.max_hold_ms:
                return ExitSignal(EXIT_TIMEOUT, bar.close, bar.open_time_ms)
            if policy.protects:          # aggiornamento a candela CHIUSA: vale dalla candela successiva
                px = bar.high if side == 1 else bar.low
                if side * (px - best) > 0:
                    best = px
                    stop_price_now, kind = protected_stop(side, fill_price, stop_price, best, policy, fee_bps)
    return None


# ----------------------------------------------------------------------------- politica da file
_POLICY_KEYS = {"schema_version", "take_profit_r", "max_hold_hours", "stop_slippage_bp"}
_PROTECT_KEYS = {"be_at_r", "trail_at_r", "trail_dist_r", "protect_at_r", "protect_frac"}   # schema 2


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
        version = data.get("schema_version") if type(data) is dict else None
        if type(version) is not int or version not in (1, 2):
            raise ValueError("invalid_policy")
        if set(data) != (_POLICY_KEYS if version == 1 else _POLICY_KEYS | _PROTECT_KEYS):
            raise ValueError("invalid_policy")
        hours = data["max_hold_hours"]
        if not ((type(hours) is int and 1 <= hours <= 720) or (hours is None and version == 2)):
            raise ValueError("invalid_policy")          # null (solo schema 2) = nessun limite di tempo
        extra = {k: (None if data[k] is None else _number(data[k])) for k in _PROTECT_KEYS} if version == 2 else {}
        policy = ExitPolicy(_number(data["take_profit_r"]), None if hours is None else hours * _HOUR_MS,
                            _number(data["stop_slippage_bp"]), **extra)
        _check_policy(policy)
        return policy
    except Exception:
        raise ValueError("invalid_policy") from None


def default_policy_path() -> Path:
    return Path(__file__).with_name("exit_policy.json")


def load_default_policy() -> ExitPolicy:
    """Unico punto che legge il file: da chiamare in configurazione."""
    return load_exit_policy(default_policy_path().read_bytes())


def gross_r_for_net_target(stop_fraction: Decimal, roundtrip_cost_fraction: Decimal, net_r: Decimal) -> Decimal:
    """PROPOSTA, non applicata: multiplo LORDO della distanza dallo stop che serve per un obiettivo NETTO.

    Il RiskManager misura il rischio a stop COSTI INCLUSI: 1R netto = (d + c) del prezzo (d = distanza dallo stop,
    c = costi di andata e ritorno). Al take-profit lordo k*d il risultato netto e' (k*d - c), quindi
    netto in R = (k*d - c) / (d + c)  ->  k = (net_r * (d + c) + c) / d.
    Esempio: d = 0,5 %, c = 0,16 %: il TP lordo 3R vale circa 2,03R netti; per 3R netti serve circa 4,28R lordi."""
    for v in (stop_fraction, roundtrip_cost_fraction, net_r):
        if type(v) is not Decimal or not v.is_finite() or v < 0:
            raise ValueError("invalid_input") from None
    if stop_fraction <= 0 or net_r <= 0:
        raise ValueError("invalid_input") from None
    with localcontext(_CTX):
        return (net_r * (stop_fraction + roundtrip_cost_fraction) + roundtrip_cost_fraction) / stop_fraction
