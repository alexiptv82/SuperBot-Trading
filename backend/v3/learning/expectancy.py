"""Expectancy per cella con intervalli a blocchi di giorni (F7 P4).

Modulo puro: nessuna I/O, nessuna rete, nessun orologio.
Aritmetica in Decimal. Nessuna soglia nel codice.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Callable, Optional, Sequence

from backend.v3.outcomes import LINK_STATUSES, TradeOutcome

_Q4 = Decimal("0.0001")
_MS_PER_DAY = 86_400_000


def _q4(d: Decimal) -> Decimal:
    return d.quantize(_Q4, rounding=ROUND_HALF_EVEN)


@dataclass(frozen=True)
class CellStats:
    key: tuple
    n: int
    n_days: int
    mean_net_bp: Decimal
    median_net_bp: Decimal
    mean_costs_bp: Decimal
    mean_r: Optional[Decimal]
    win_rate: Decimal
    ci_low: Optional[Decimal]
    ci_high: Optional[Decimal]
    status: str


def default_cell_key(o: TradeOutcome) -> tuple:
    return (o.symbol, o.side, o.decision_regime, o.is_manual)


def _validate(outcomes, min_trades, min_days, confidence, n_boot, seed, key, link_statuses):
    if not all(isinstance(o, TradeOutcome) for o in outcomes):
        raise ValueError("invalid_outcome")
    if type(min_trades) is not int or min_trades < 1:
        raise ValueError("invalid_min_trades")
    if type(min_days) is not int or min_days < 2:
        raise ValueError("invalid_min_days")
    if not isinstance(confidence, Decimal) or not (Decimal("0") < confidence < Decimal("1")):
        raise ValueError("invalid_confidence")
    if type(n_boot) is not int or n_boot < 200:
        raise ValueError("invalid_n_boot")
    if type(seed) is not int:
        raise ValueError("invalid_seed")
    if not callable(key):
        raise ValueError("invalid_key")
    if not isinstance(link_statuses, frozenset) or not link_statuses <= set(LINK_STATUSES):
        raise ValueError("invalid_link_statuses")
    if outcomes:
        try:
            k = key(outcomes[0])
            if not isinstance(k, tuple):
                raise ValueError("invalid_key")
        except ValueError:
            raise
        except Exception:
            raise ValueError("invalid_key")


def _day(ms: int) -> int:
    return ms // _MS_PER_DAY


def cell_stats(
    outcomes: Sequence[TradeOutcome],
    *,
    min_trades: int,
    min_days: int,
    confidence: Decimal,
    n_boot: int,
    seed: int,
    key: Callable[[TradeOutcome], tuple] = default_cell_key,
    link_statuses: frozenset[str] = frozenset({"linked"}),
) -> tuple[CellStats, ...]:
    _validate(outcomes, min_trades, min_days, confidence, n_boot, seed, key, link_statuses)

    filtered = [o for o in outcomes if o.link_status in link_statuses]
    groups: dict[tuple, list[TradeOutcome]] = {}
    for o in filtered:
        k = key(o)
        groups.setdefault(k, []).append(o)

    alpha = Decimal("1") - confidence
    results: list[CellStats] = []

    for k in sorted(groups.keys(), key=lambda x: tuple(str(v) for v in x)):
        trades = groups[k]
        nets = [t.net_bp for t in trades]
        costs = [t.costs_bp for t in trades]
        rs = [t.r_multiple for t in trades if t.r_multiple is not None]
        wins = sum(1 for t in trades if t.is_win)
        n = len(trades)
        days = sorted({_day(t.closed_at_ms) for t in trades})
        n_days = len(days)

        mean_net = _q4(sum(nets) / Decimal(n))
        mean_costs = _q4(sum(costs) / Decimal(n))
        mean_r = _q4(sum(rs) / Decimal(len(rs))) if rs else None
        win_rate = _q4(Decimal(wins) / Decimal(n))

        ordered = sorted(nets)
        if n % 2 == 1:
            median = _q4(ordered[n // 2])
        else:
            median = _q4((ordered[n // 2 - 1] + ordered[n // 2]) / Decimal(2))

        if n < min_trades or n_days < min_days:
            results.append(CellStats(
                key=k, n=n, n_days=n_days,
                mean_net_bp=mean_net, median_net_bp=median,
                mean_costs_bp=mean_costs, mean_r=mean_r, win_rate=win_rate,
                ci_low=None, ci_high=None, status="insufficient",
            ))
            continue

        by_day: dict[int, list[Decimal]] = {}
        for t in trades:
            by_day.setdefault(_day(t.closed_at_ms), []).append(t.net_bp)
        day_keys = sorted(by_day.keys())
        rng = random.Random(f"{seed}|{k!r}")
        boots: list[Decimal] = []
        for _ in range(n_boot):
            chosen = [day_keys[rng.randrange(n_days)] for _ in range(n_days)]
            sample = [bp for d in chosen for bp in by_day[d]]
            boots.append(sum(sample) / Decimal(len(sample)))
        boots.sort()
        lo_idx = int((alpha / 2 * Decimal(n_boot)).to_integral_value(rounding=ROUND_HALF_EVEN))
        hi_idx = int(((Decimal("1") - alpha / 2) * Decimal(n_boot)).to_integral_value(rounding=ROUND_HALF_EVEN)) - 1
        lo_idx = max(0, min(lo_idx, n_boot - 1))
        hi_idx = max(0, min(hi_idx, n_boot - 1))
        ci_low = _q4(boots[lo_idx])
        ci_high = _q4(boots[hi_idx])

        if ci_low > 0:
            status = "positive"
        elif ci_high < 0:
            status = "negative"
        else:
            status = "inconclusive"

        results.append(CellStats(
            key=k, n=n, n_days=n_days,
            mean_net_bp=mean_net, median_net_bp=median,
            mean_costs_bp=mean_costs, mean_r=mean_r, win_rate=win_rate,
            ci_low=ci_low, ci_high=ci_high, status=status,
        ))

    return tuple(results)


def format_cells(cells: Sequence[CellStats]) -> str:
    lines = ["key | n | n_days | mean_net_bp | median | win_rate | status"]
    for c in cells:
        lines.append(
            f"{c.key} | {c.n} | {c.n_days} | {c.mean_net_bp} | {c.median_net_bp} | {c.win_rate} | {c.status}"
        )
    return "\n".join(lines)
