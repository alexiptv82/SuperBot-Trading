"""Bracci controfattuali delle USCITE (laboratorio offline, solo libreria standard, nessuna rete, nessun I/O).

Stesse entrate, stesse candele, stessi costi: cambia SOLO la regola d'uscita. Nulla qui tocca il runtime,
il journal o i parametri: il risultato e' una proposta per il proprietario. Le regole del confronto sono
registrate in anticipo in `preregistration.json` (vedi `PREREG.md`).

Convenzioni comuni a TUTTI i bracci (identiche al runtime `backend/v3/runner/exits.py` dove esiste):
* R = |ingresso - stop iniziale| in prezzo; take-profit = ingresso + side * tp_r * R.
* Candele 1m chiuse, in ordine; la candela in cui la posizione apre a meta' non e' usata.
* Il livello di stop valido per la candela t e' calcolato SOLO con le candele precedenti (nessuno sguardo
  avanti): break-even, trailing e protezione si aggiornano a candela chiusa.
* Stop e take-profit nella stessa candela: vince lo stop. Gap oltre lo stop: uscita all'apertura, la peggiore.
* Uscite a stop (anche spostato): slippage `stop_slippage_bp` sfavorevole. Take-profit: al prezzo esatto.
  Uscite a mercato (durata massima, inversione): slippage `market_slippage_bp` sfavorevole, uguale per tutti.
* Commissioni `fee_bp` per lato sul nozionale; funding a ogni scadenza attraversata (00, 08, 16 UTC), il long
  paga se il tasso e' positivo. Il funding si passa come funzione: tassi attestati oppure ipotesi dichiarata.
* Risultato in R netti: (side * (uscita - ingresso) - commissioni - funding) / R.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional, Sequence

FUNDING_PERIOD_MS = 8 * 3_600_000
HOUR_MS = 3_600_000


@dataclass(frozen=True)
class Bar:
    open_time_ms: int
    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True)
class Position:
    side: int                 # +1 long, -1 short
    fill: float
    stop: float
    opened_at_ms: int


@dataclass(frozen=True)
class Costs:
    fee_bp: float = 6.0                 # per lato, configurazione del runner
    stop_slippage_bp: float = 2.0       # exit_policy.json
    market_slippage_bp: float = 2.0     # slippage_bps del runner, per le uscite a mercato
    funding: Callable[[int], float] = field(default=lambda ts_ms: 0.0)   # tasso per scadenza (frazione)


@dataclass(frozen=True)
class Arm:
    name: str
    family: str                                   # baseline | break_even | trailing | protect | reversal
    tp_r: Optional[float] = 2.0                   # None = nessun take-profit
    max_hold_ms: int = 24 * HOUR_MS
    be_at_r: Optional[float] = None               # break-even: sposta lo stop all'ingresso + costi
    trail_at_r: Optional[float] = None            # trailing: attivazione
    trail_dist_r: Optional[float] = None          # trailing: distanza dal migliore prezzo
    protect_at_r: Optional[float] = None          # protezione: attivazione
    protect_frac: Optional[float] = None          # protezione: quota dell'escursione favorevole bloccata
    reversal_ema: Optional[int] = None            # inversione: EMA sulle chiusure 1h


@dataclass(frozen=True)
class Outcome:
    reason: str               # stop | take_profit | timeout | reversal | open
    exit_price: Optional[float]
    exit_ms: Optional[int]
    net_r: Optional[float]
    mfe_r: float              # massima escursione favorevole (in R) vista prima dell'uscita
    funding_r: float


def _ema_last(values: Sequence[float], n: int) -> Optional[float]:
    if len(values) < n:
        return None
    k = 2.0 / (n + 1)
    e = sum(values[:n]) / n
    for v in values[n:]:
        e = v * k + e * (1 - k)
    return e


def _funding_r(pos: Position, exit_ms: int, r: float, costs: Costs) -> float:
    t = (pos.opened_at_ms // FUNDING_PERIOD_MS + 1) * FUNDING_PERIOD_MS
    total = 0.0
    while t <= exit_ms:
        total += pos.side * costs.funding(t) * pos.fill        # long paga un tasso positivo
        t += FUNDING_PERIOD_MS
    return total / r


def _net_r(pos: Position, exit_price: float, exit_ms: int, r: float, costs: Costs) -> tuple:
    fees = costs.fee_bp / 1e4 * (pos.fill + exit_price)
    fund = _funding_r(pos, exit_ms, r, costs)
    return (pos.side * (exit_price - pos.fill) - fees) / r - fund, fund


def simulate(pos: Position, bars: Sequence[Bar], arm: Arm, costs: Costs, candle_ms: int = 60_000,
             prior_hour_closes: Sequence[float] = ()) -> Outcome:
    """Prima uscita della posizione secondo il braccio, sulle candele chiuse (contigue, in ordine).
    `prior_hour_closes`: chiusure 1h attestate PRECEDENTI all'apertura (note in quel momento), per l'EMA
    del braccio di inversione; senza storia sufficiente l'inversione non scatta (mai inventata)."""
    if pos.side not in (1, -1) or pos.fill <= 0 or pos.stop <= 0 or pos.fill == pos.stop:
        raise ValueError("invalid_position")
    if (pos.side == 1) != (pos.stop < pos.fill):
        raise ValueError("invalid_position")
    s, r = pos.side, abs(pos.fill - pos.stop)
    target = pos.fill + s * arm.tp_r * r if arm.tp_r is not None else None
    stop = pos.stop
    best = pos.fill                      # miglior prezzo favorevole delle candele gia' chiuse
    be_cost = pos.fill * (2 * costs.fee_bp + costs.stop_slippage_bp) / 1e4
    hour_closes: list = list(prior_hour_closes)
    for bar in bars:
        if bar.open_time_ms < pos.opened_at_ms:
            continue
        stop_hit = bar.low <= stop if s == 1 else bar.high >= stop
        target_hit = target is not None and (bar.high >= target if s == 1 else bar.low <= target)
        mfe_r = s * (best - pos.fill) / r
        if stop_hit:
            base = min(stop, bar.open) if s == 1 else max(stop, bar.open)
            px = base - s * base * costs.stop_slippage_bp / 1e4
            net, fund = _net_r(pos, px, bar.open_time_ms, r, costs)
            return Outcome("stop", px, bar.open_time_ms, net, mfe_r, fund)
        if target_hit:
            net, fund = _net_r(pos, target, bar.open_time_ms, r, costs)
            return Outcome("take_profit", target, bar.open_time_ms, net, max(mfe_r, arm.tp_r), fund)
        end_ms = bar.open_time_ms + candle_ms
        # aggiornamenti a candela CHIUSA: valgono dalla candela successiva
        best = max(best, bar.high) if s == 1 else min(best, bar.low)
        mfe = s * (best - pos.fill)
        if arm.be_at_r is not None and mfe >= arm.be_at_r * r:
            lvl = pos.fill + s * be_cost
            stop = max(stop, lvl) if s == 1 else min(stop, lvl)
        if arm.trail_at_r is not None and mfe >= arm.trail_at_r * r:
            lvl = best - s * arm.trail_dist_r * r
            stop = max(stop, lvl) if s == 1 else min(stop, lvl)
        if arm.protect_at_r is not None and mfe >= arm.protect_at_r * r:
            lvl = pos.fill + s * arm.protect_frac * mfe
            stop = max(stop, lvl) if s == 1 else min(stop, lvl)
        mkt = None
        if arm.reversal_ema is not None and end_ms % HOUR_MS == 0:
            hour_closes.append(bar.close)
            e = _ema_last(hour_closes, arm.reversal_ema)
            if e is not None and (bar.close < e if s == 1 else bar.close > e):
                mkt = "reversal"
        if mkt is None and end_ms - pos.opened_at_ms >= arm.max_hold_ms:
            mkt = "timeout"
        if mkt is not None:
            px = bar.close - s * bar.close * costs.market_slippage_bp / 1e4
            net, fund = _net_r(pos, px, bar.open_time_ms, r, costs)
            return Outcome(mkt, px, bar.open_time_ms, net, s * (best - pos.fill) / r, fund)
    return Outcome("open", None, None, None, s * (best - pos.fill) / r, 0.0)


def arms_from_spec(spec: dict) -> list:
    """Bracci dalla preregistrazione (nessun parametro fuori dall'elenco registrato)."""
    out = []
    for a in spec["arms"]:
        kw = {k: v for k, v in a.items() if k not in ("name", "family", "max_hold_hours")}
        out.append(Arm(name=a["name"], family=a["family"], max_hold_ms=int(a.get("max_hold_hours", 24)) * HOUR_MS,
                       **kw))
    if sum(1 for a in out if a.family == "baseline") != 1:
        raise ValueError("exactly_one_baseline")
    return out
