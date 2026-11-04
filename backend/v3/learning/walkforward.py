"""Walk-forward validation of expectancy cells (F7, step P6).

Chooses cells on a training window, measures them on the following test
window, and reports the decay. Does not decide anything and does not change
any strategy.

Exact rules the tests pin down: windows are half-open (a trade closed exactly at train_end is not in
train); the selection uses train trades only; every mean is a per-trade mean of exact values rounded once
(4 decimals, half-even, never "-0.0000"); decay_bp = is - oos is computed from the exact sums, not from the
already rounded means; key() is evaluated once per admitted trade; cost is O(N log N + sum of window sizes).

Known limits: selection is still on many cells (multiple comparisons); the
decay measures the effect, it does not remove it; sliding folds are not
independent when train_ms > step_ms; a test trade in a selected cell may have
opened during train (not leakage: its close is after train_end, but embargo
exists precisely to cover long trades); cells never seen in train fall into
rest; no real data was used.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext
from typing import Optional

from backend.v3.learning.expectancy import CellStats, cell_stats, default_cell_key
from backend.v3.outcomes import TradeOutcome

_CTX = Context(prec=60, rounding=ROUND_HALF_EVEN)
_Q4 = Decimal("0.0001")
_MS_PER_DAY = 86_400_000


def _q4(d: Decimal) -> Decimal:
    r = d.quantize(_Q4, rounding=ROUND_HALF_EVEN)
    return abs(r) if r == 0 else r


@dataclass(frozen=True)
class Fold:
    index: int
    train_start_ms: int
    train_end_ms: int
    test_start_ms: int
    test_end_ms: int


@dataclass(frozen=True)
class SelectedCell:
    key: tuple
    train_n: int
    train_mean_net_bp: Decimal
    train_ci_low: Decimal
    test_n: int
    test_mean_net_bp: Optional[Decimal]


@dataclass(frozen=True)
class FoldResult:
    fold: Fold
    n_train_outcomes: int
    n_test_outcomes: int
    n_cells_evaluated: int
    n_selected: int
    selected: tuple[SelectedCell, ...]
    selected_test_n: int
    selected_test_mean_net_bp: Optional[Decimal]
    rest_test_n: int
    rest_test_mean_net_bp: Optional[Decimal]


@dataclass(frozen=True)
class WalkForwardReport:
    folds: tuple[FoldResult, ...]
    n_selections: int
    n_folds_with_selection: int
    is_n: int
    is_mean_net_bp: Optional[Decimal]
    oos_n: int
    oos_mean_net_bp: Optional[Decimal]
    rest_n: int
    rest_mean_net_bp: Optional[Decimal]
    decay_bp: Optional[Decimal]


def make_folds(*, start_ms, end_ms, train_ms, test_ms, step_ms, embargo_ms, expanding) -> tuple[Fold, ...]:
    if type(start_ms) is not int or type(end_ms) is not int or start_ms < 0 or start_ms % _MS_PER_DAY != 0 or end_ms <= start_ms:
        raise ValueError("invalid_window")
    if type(train_ms) is not int or type(test_ms) is not int or type(step_ms) is not int:
        raise ValueError("invalid_lengths")
    if train_ms <= 0 or test_ms <= 0 or step_ms <= 0:
        raise ValueError("invalid_lengths")
    if train_ms % _MS_PER_DAY != 0 or test_ms % _MS_PER_DAY != 0 or step_ms % _MS_PER_DAY != 0:
        raise ValueError("invalid_lengths")
    if step_ms < test_ms:
        raise ValueError("invalid_lengths")
    if type(embargo_ms) is not int or embargo_ms < 0 or embargo_ms % _MS_PER_DAY != 0:
        raise ValueError("invalid_embargo")
    if type(expanding) is not bool:
        raise ValueError("invalid_expanding")
    folds = []
    k = 0
    while True:
        train_end = start_ms + k * step_ms + train_ms
        train_start = start_ms if expanding else start_ms + k * step_ms
        test_start = train_end + embargo_ms
        test_end = test_start + test_ms
        if test_end > end_ms:
            break
        folds.append(Fold(k, train_start, train_end, test_start, test_end))
        k += 1
    if not folds:
        raise ValueError("no_folds")
    return tuple(folds)


def _validate_folds(folds: Sequence[Fold]) -> None:
    if not isinstance(folds, Sequence) or len(folds) == 0:
        raise ValueError("invalid_folds")
    prev_test_end = None
    for i, f in enumerate(folds):
        if type(f) is not Fold:
            raise ValueError("invalid_folds")
        for v in (f.index, f.train_start_ms, f.train_end_ms, f.test_start_ms, f.test_end_ms):
            if type(v) is not int:
                raise ValueError("invalid_folds")
        if not (0 <= f.train_start_ms < f.train_end_ms <= f.test_start_ms < f.test_end_ms):
            raise ValueError("invalid_folds")
        if f.index != i:
            raise ValueError("invalid_folds")
        if prev_test_end is not None and f.test_start_ms < prev_test_end:
            raise ValueError("invalid_folds")
        prev_test_end = f.test_end_ms


def _lower_bound(a: Sequence[int], x: int) -> int:
    """Primo indice con a[i] >= x in una lista ordinata (ricerca binaria)."""
    lo, hi = 0, len(a)
    while lo < hi:
        mid = (lo + hi) // 2
        if a[mid] < x:
            lo = mid + 1
        else:
            hi = mid
    return lo


def _ident(key: Callable[[TradeOutcome], tuple], o: TradeOutcome) -> tuple[tuple, str]:
    k = key(o)
    return (k, repr(k))


def _mean4(values: Sequence[Decimal]) -> Optional[Decimal]:
    """Media per trade dei valori esatti, arrotondata UNA volta (4 decimali, half-even)."""
    return _q4(sum(values) / Decimal(len(values))) if values else None


def _same_key_ids(cs: Sequence[CellStats]) -> list[tuple[tuple, str]]:
    return [(c.key, repr(c.key)) for c in cs]


def walk_forward(outcomes: Sequence[TradeOutcome], folds: Sequence[Fold], *,
                 min_trades: int, min_days: int, confidence: Decimal, n_boot: int, seed: int,
                 key: Callable[[TradeOutcome], tuple] = default_cell_key,
                 link_statuses: frozenset[str] = frozenset({"linked"})) -> WalkForwardReport:
    # Validazione: tutti i codici di cell_stats (anche `key` provata su ogni trade ammesso), poi i fold.
    cell_stats(outcomes, min_trades=min_trades, min_days=min_days, confidence=confidence,
               n_boot=n_boot, seed=seed, key=key, link_statuses=link_statuses)
    _validate_folds(folds)
    try:
        with localcontext(_CTX):
            # Trade ammessi per posizione di arrivo, ordinati per chiusura UNA volta: ogni finestra e' poi
            # un intervallo trovato con ricerca binaria (O(N log N + somma delle finestre), non O(N * fold)).
            admitted = [i for i, o in enumerate(outcomes) if o.link_status in link_statuses]
            by_time = sorted((outcomes[i].closed_at_ms, i) for i in admitted)
            times = [t for t, _ in by_time]
            ident = {i: _ident(key, outcomes[i]) for i in admitted}      # key() una sola volta per trade

            def window(lo: int, hi: int) -> list[int]:
                """Posizioni dei trade con lo <= closed_at_ms < hi, nell'ordine in cui sono arrivati."""
                return sorted(i for _, i in by_time[_lower_bound(times, lo):_lower_bound(times, hi)])

            fold_results = []
            all_is: list[Decimal] = []
            all_oos: list[Decimal] = []
            all_rest: list[Decimal] = []
            for fold in folds:
                train_pos = window(fold.train_start_ms, fold.train_end_ms)
                test_pos = window(fold.test_start_ms, fold.test_end_ms)
                train = [outcomes[i] for i in train_pos]
                cs = cell_stats(train, min_trades=min_trades, min_days=min_days, confidence=confidence,
                                n_boot=n_boot, seed=seed, key=key, link_statuses=link_statuses)
                evaluated = [c for c in cs if c.status != "insufficient"]
                selected = [c for c in cs if c.status == "positive"]
                sel_ids = _same_key_ids(selected)
                sel_set = set(sel_ids)

                train_by_cell: dict[tuple[tuple, str], list[Decimal]] = {}
                for i in train_pos:
                    train_by_cell.setdefault(ident[i], []).append(outcomes[i].net_bp)
                test_by_cell: dict[tuple[tuple, str], list[Decimal]] = {}
                sel_test: list[Decimal] = []
                rest_test: list[Decimal] = []
                for i in test_pos:
                    net = outcomes[i].net_bp
                    test_by_cell.setdefault(ident[i], []).append(net)
                    (sel_test if ident[i] in sel_set else rest_test).append(net)

                sel_cells = []
                for c, cid in zip(selected, sel_ids):
                    cell_test = test_by_cell.get(cid, [])
                    sel_cells.append(SelectedCell(c.key, c.n, c.mean_net_bp, c.ci_low,
                                                  len(cell_test), _mean4(cell_test)))
                    all_is.extend(train_by_cell.get(cid, []))
                fold_results.append(FoldResult(
                    fold, len(train), len(test_pos), len(evaluated), len(selected),
                    tuple(sel_cells), len(sel_test), _mean4(sel_test), len(rest_test), _mean4(rest_test),
                ))
                all_oos.extend(sel_test)
                all_rest.extend(rest_test)

            is_n, oos_n, rest_n = len(all_is), len(all_oos), len(all_rest)
            if is_n and oos_n:
                # decadimento dai valori ESATTI (non dalle medie gia' arrotondate), arrotondato una volta:
                # is - oos = (S_is * n_oos - S_oos * n_is) / (n_is * n_oos)
                decay = _q4((sum(all_is) * Decimal(oos_n) - sum(all_oos) * Decimal(is_n))
                            / (Decimal(is_n) * Decimal(oos_n)))
            else:
                decay = None
            return WalkForwardReport(
                tuple(fold_results), sum(fr.n_selected for fr in fold_results),
                sum(1 for fr in fold_results if fr.n_selected > 0),
                is_n, _mean4(all_is), oos_n, _mean4(all_oos), rest_n, _mean4(all_rest), decay,
            )
    except ArithmeticError:
        raise ValueError("invalid_outcome") from None
