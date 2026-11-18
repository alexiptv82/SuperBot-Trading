"""Replay PAPER verificabile di ingressi (veri dal journal o di controllo) con politiche di uscita e filtri.

Ricerca isolata: mai importata dal runtime, nessun ordine, nessuna rete (le candele si passano dall'esterno).

Regole fisse, senza sguardo al futuro:
* uscite sulle candele da 1 minuto a partire da quella SUCCESSIVA al minuto d'ingresso;
* nella stessa candela lo stop vince sempre (anche sul target e sulla parziale); apertura gia' oltre lo stop = uscita
  all'apertura; slippage avverso ``stop_slippage_bp`` sugli stop; commissioni ``fee_bp`` per lato su ogni esecuzione;
* breakeven, trailing e parziale si ATTIVANO con il massimo/minimo di una candela e valgono dalla candela successiva;
* filtri d'ingresso solo con dati chiusi prima dell'ingresso; protezioni di portafoglio solo con chiusure avvenute
  prima dell'ingresso.
"""
from __future__ import annotations

import heapq
import math
import random
from dataclasses import dataclass, field, replace
from typing import Iterable, Optional, Sequence

MINUTE = 60_000
HOUR = 3_600_000
DAY = 86_400_000


@dataclass(frozen=True)
class Bar:
    t: int            # apertura della candela (ms)
    o: float
    h: float
    l: float
    c: float


@dataclass(frozen=True)
class Entry:
    t: int            # istante della decisione/riempimento (ms)
    symbol: str
    side: int         # +1 LONG, -1 SHORT
    entry: float
    stop: float
    tag: str = ""


@dataclass(frozen=True)
class ExitPolicy:
    name: str = "A_baseline"
    tp_r: Optional[float] = 2.0
    max_hold_h: float = 24.0
    be_trigger_r: Optional[float] = None     # a +X R lo stop va a ingresso + costi (dalla candela dopo)
    trail_trigger_r: Optional[float] = None  # da +X R lo stop segue il massimo favorevole a distanza trail_r
    trail_r: float = 1.0
    partial_r: Optional[float] = None        # chiude partial_frac a +X R (stessa candela, se lo stop non e' toccato)
    partial_frac: float = 0.5


@dataclass(frozen=True)
class EntryFilter:
    min_stop_cost_mult: Optional[float] = None   # stop >= mult x costo andata-ritorno
    min_stop_atr_mult: Optional[float] = None    # stop >= mult x ATR(15m, 14) su barre chiuse
    max_stop_atr_mult: Optional[float] = None


@dataclass(frozen=True)
class PortfolioGuard:
    cooldown_h_after_stop: Optional[float] = None
    max_same_side_open: Optional[int] = None
    hwm_drawdown_halt: Optional[float] = None     # niente nuove aperture sotto HWM x (1 - x)
    daily_loss_halt: Optional[float] = None       # niente nuove aperture se il giorno perde > x dell'equity d'inizio


@dataclass(frozen=True)
class Costs:
    fee_bp: float = 6.0
    entry_slippage_bp: float = 2.0
    stop_slippage_bp: float = 2.0

    @property
    def roundtrip_frac(self) -> float:
        return (2 * self.fee_bp + self.entry_slippage_bp + self.stop_slippage_bp) / 1e4


@dataclass(frozen=True)
class Sizing:
    equity0: float = 2000.0
    max_loss_fraction: float = 0.042857142857142857
    max_position_margin_fraction: float = 0.20
    max_total_margin_fraction: float = 0.55
    leverage: int = 20


@dataclass
class TradeResult:
    entry: Entry
    qty: float
    exit_t: int
    pnl: float
    fees: float
    reason: str
    r_realized: float
    mfe_r: float
    mae_r: float
    margin: float


# ------------------------------------------------------------------------------------------------ singola operazione
def simulate_exit(e: Entry, bars: Sequence[Bar], qty: float, pol: ExitPolicy, costs: Costs) -> TradeResult:
    """Percorre ``bars`` (gia' ordinate) dalla candela successiva al minuto d'ingresso."""
    s = e.side
    fill = e.entry * (1 + s * costs.entry_slippage_bp / 1e4)
    risk = abs(fill - e.stop)
    if risk <= 0 or qty <= 0:
        raise ValueError("invalid_trade")
    stop = e.stop
    target = None if pol.tp_r is None else fill + s * pol.tp_r * risk
    deadline = e.t + pol.max_hold_h * HOUR
    first = e.t // MINUTE * MINUTE + MINUTE
    remaining, pnl, fees = qty, 0.0, qty * fill * costs.fee_bp / 1e4
    best = 0.0      # massimo favorevole in R
    worst = 0.0
    be_armed = trail_armed = partial_done = False
    pending_be = pending_trail = False
    exit_t, reason = None, None

    def close(px: float, part: float):
        nonlocal remaining, pnl, fees
        pnl += s * (px - fill) * part
        fees += part * px * costs.fee_bp / 1e4
        remaining -= part

    for b in bars:
        if b.t < first:
            continue
        # attivazioni decise sulla candela precedente: valgono da questa
        if pending_be and not be_armed:
            be_armed = True
            be_px = fill + s * fill * costs.roundtrip_frac
            stop = max(stop, be_px) if s == 1 else min(stop, be_px)
        if pending_trail:
            trail_armed = True
        if trail_armed:
            trail_px = fill + s * (best - pol.trail_r) * risk
            stop = max(stop, trail_px) if s == 1 else min(stop, trail_px)
        adverse = b.l if s == 1 else b.h
        favorable = b.h if s == 1 else b.l
        hit_stop = (adverse <= stop) if s == 1 else (adverse >= stop)
        if hit_stop:
            gap = (b.o <= stop) if s == 1 else (b.o >= stop)
            px = b.o if gap else stop
            px *= (1 - s * costs.stop_slippage_bp / 1e4)
            worst = min(worst, s * (px - fill) / risk)
            close(px, remaining)
            exit_t = b.t + MINUTE
            reason = "stop" if not (be_armed or trail_armed) else ("trail" if trail_armed else "breakeven")
            break
        worst = min(worst, s * (adverse - fill) / risk)
        best = max(best, s * (favorable - fill) / risk)
        if pol.partial_r is not None and not partial_done and best >= pol.partial_r:
            close(fill + s * pol.partial_r * risk, remaining * pol.partial_frac)
            partial_done = True
        if target is not None and ((favorable >= target) if s == 1 else (favorable <= target)):
            close(target, remaining)
            exit_t, reason = b.t + MINUTE, "take_profit"
            break
        if pol.be_trigger_r is not None and best >= pol.be_trigger_r:
            pending_be = True
        if pol.trail_trigger_r is not None and best >= pol.trail_trigger_r:
            pending_trail = True
        if b.t + MINUTE >= deadline:
            close(b.c, remaining)
            exit_t, reason = b.t + MINUTE, "timeout"
            break
    if exit_t is None:
        raise ValueError("insufficient_bars")
    return TradeResult(e, qty, exit_t, pnl - fees, fees, reason, (pnl - fees) / (risk * qty), best, worst, 0.0)


# ------------------------------------------------------------------------------------------------ filtri d'ingresso
def atr15(bars: Sequence[Bar], t: int, n: int = 14) -> Optional[float]:
    """ATR su candele 15m costruite dai minuti CHIUSI prima di ``t``."""
    end = t // (15 * MINUTE) * (15 * MINUTE)
    start = end - (n + 1) * 15 * MINUTE
    buckets: dict[int, list[Bar]] = {}
    for b in bars:
        if start <= b.t < end:
            buckets.setdefault(b.t // (15 * MINUTE), []).append(b)
    if len(buckets) < n + 1:
        return None
    agg = []
    for k in sorted(buckets):
        bs = buckets[k]
        agg.append((max(x.h for x in bs), min(x.l for x in bs), bs[-1].c))
    trs = [max(h - l, abs(h - pc), abs(l - pc)) for (h, l, _), (_, _, pc) in zip(agg[1:], agg[:-1])]
    return sum(trs[-n:]) / n


def entry_allowed(e: Entry, flt: EntryFilter, costs: Costs, bars: Sequence[Bar]) -> Optional[str]:
    dist = abs(e.entry - e.stop) / e.entry
    if flt.min_stop_cost_mult is not None and dist < flt.min_stop_cost_mult * costs.roundtrip_frac:
        return "stop_inside_costs"
    if flt.min_stop_atr_mult is not None or flt.max_stop_atr_mult is not None:
        a = atr15(bars, e.t)
        if a is None:
            return "atr_unavailable"
        ratio = abs(e.entry - e.stop) / a
        if flt.min_stop_atr_mult is not None and ratio < flt.min_stop_atr_mult:
            return "stop_inside_noise"
        if flt.max_stop_atr_mult is not None and ratio > flt.max_stop_atr_mult:
            return "stop_too_wide_for_volatility"
    return None


# ------------------------------------------------------------------------------------------------ portafoglio
@dataclass(frozen=True)
class Variant:
    name: str
    exit: ExitPolicy = field(default_factory=ExitPolicy)
    filt: EntryFilter = field(default_factory=EntryFilter)
    guard: PortfolioGuard = field(default_factory=PortfolioGuard)


@dataclass
class RunResult:
    variant: str
    trades: list[TradeResult]
    skipped: dict
    equity_curve: list[tuple[int, float]]


def run_portfolio(entries: Iterable[Entry], bars_by_symbol: dict[str, Sequence[Bar]], v: Variant,
                  costs: Costs = Costs(), sizing: Sizing = Sizing()) -> RunResult:
    equity, hwm = sizing.equity0, sizing.equity0
    pending: list = []                       # heap (exit_t, seq, TradeResult)
    open_pos: list[TradeResult] = []
    last_stop: dict[str, int] = {}
    day_start: dict[int, float] = {}
    day_pnl: dict[int, float] = {}
    trades, skipped, curve = [], {}, [(0, equity)]
    seq = 0

    def settle(until: int):
        nonlocal equity, hwm
        while pending and pending[0][0] <= until:
            t, _, tr = heapq.heappop(pending)
            equity += tr.pnl
            hwm = max(hwm, equity)
            d = t // DAY
            day_pnl[d] = day_pnl.get(d, 0.0) + tr.pnl
            if tr.reason == "stop":
                last_stop[tr.entry.symbol] = t
            open_pos.remove(tr)
            curve.append((t, equity))

    def skip(why):
        skipped[why] = skipped.get(why, 0) + 1

    for e in sorted(entries, key=lambda x: x.t):
        settle(e.t)
        bars = bars_by_symbol.get(e.symbol) or []
        d = e.t // DAY
        day_start.setdefault(d, equity)
        if any(p.entry.symbol == e.symbol for p in open_pos):
            skip("symbol_already_open"); continue
        why = entry_allowed(e, v.filt, costs, bars)
        if why:
            skip(why); continue
        g = v.guard
        if g.cooldown_h_after_stop is not None and e.t - last_stop.get(e.symbol, -10**18) < g.cooldown_h_after_stop * HOUR:
            skip("cooldown_after_stop"); continue
        if g.max_same_side_open is not None and sum(p.entry.side == e.side for p in open_pos) >= g.max_same_side_open:
            skip("correlated_cap"); continue
        if g.hwm_drawdown_halt is not None and equity < hwm * (1 - g.hwm_drawdown_halt):
            skip("hwm_drawdown_halt"); continue
        if g.daily_loss_halt is not None and -day_pnl.get(d, 0.0) > g.daily_loss_halt * day_start[d]:
            skip("daily_loss_halt"); continue
        dist = abs(e.entry - e.stop) / e.entry
        qty_risk = equity * sizing.max_loss_fraction / (e.entry * (dist + costs.roundtrip_frac))
        margin_used = sum(p.margin for p in open_pos)
        margin_room = min(equity * sizing.max_position_margin_fraction,
                          equity * sizing.max_total_margin_fraction - margin_used)
        if margin_room <= 0:
            skip("margin_full"); continue
        qty = min(qty_risk, margin_room * sizing.leverage / e.entry)
        if qty * e.entry < 5:
            skip("below_min_notional"); continue
        try:
            tr = simulate_exit(e, bars, qty, v.exit, costs)
        except ValueError:
            skip("insufficient_bars"); continue
        tr.margin = qty * e.entry / sizing.leverage
        open_pos.append(tr)
        heapq.heappush(pending, (tr.exit_t, seq, tr))
        seq += 1
        trades.append(tr)
    settle(10**19)
    return RunResult(v.name, trades, skipped, curve)


# ------------------------------------------------------------------------------------------------ metriche
def metrics(res: RunResult, equity0: float = 2000.0) -> dict:
    tr = res.trades
    pnl = [t.pnl for t in tr]
    wins = [x for x in pnl if x > 0]
    losses = [-x for x in pnl if x <= 0]
    peak, dd, eq = equity0, 0.0, equity0
    for _, e in res.equity_curve:
        eq = e
        peak = max(peak, e)
        dd = max(dd, (peak - e) / peak)
    gave_back = [t for t in tr if t.mfe_r >= 1.0 and t.r_realized <= 0]
    by_reason: dict = {}
    for t in tr:
        by_reason[t.reason] = by_reason.get(t.reason, 0) + 1
    return {
        "variant": res.variant, "trades": len(tr), "skipped": res.skipped,
        "net_pnl": round(sum(pnl), 2), "fees": round(sum(t.fees for t in tr), 2),
        "win_rate": round(len(wins) / len(tr), 3) if tr else None,
        "avg_win": round(sum(wins) / len(wins), 2) if wins else None,
        "avg_loss": round(sum(losses) / len(losses), 2) if losses else None,
        "expectancy": round(sum(pnl) / len(tr), 2) if tr else None,
        "expectancy_r": round(sum(t.r_realized for t in tr) / len(tr), 3) if tr else None,
        "profit_factor": round(sum(wins) / sum(losses), 3) if losses and sum(losses) > 0 else None,
        "max_drawdown_pct": round(dd * 100, 2), "final_equity": round(eq, 2),
        "worst_trade": round(min(pnl), 2) if pnl else None,
        "reached_1r_then_lost": len(gave_back),
        "exit_reasons": by_reason,
    }


def bootstrap_diff(a: Sequence[float], b: Sequence[float], n: int = 2000, seed: int = 7) -> tuple[float, float, float]:
    """IC 90% della differenza delle medie (b - a) su campioni indipendenti, ricampionamento con reinserimento."""
    rng = random.Random(seed)
    diffs = []
    for _ in range(n):
        ma = sum(rng.choice(a) for _ in a) / len(a)
        mb = sum(rng.choice(b) for _ in b) / len(b)
        diffs.append(mb - ma)
    diffs.sort()
    return (sum(b) / len(b) - sum(a) / len(a), diffs[int(0.05 * n)], diffs[int(0.95 * n)])
