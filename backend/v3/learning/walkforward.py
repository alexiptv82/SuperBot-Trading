"""Walk-forward validation of expectancy cells (F7, step P6).

Chooses cells on a training window, measures them on the following test
window, and reports the decay. Does not decide anything and does not change
any strategy.

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


def _check_int_day(n, code):
    if type(n) is not int or n % _MS_PER_DAY != 0:
        raise ValueError(code)


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


def _validate_folds(folds):
    if not isinstance(folds, (list, tuple)) or not folds:
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


def walk_forward(outcomes, folds, *, min_trades, min_days, confidence, n_boot, seed,
                 key=default_cell_key, link_statuses=frozenset({"linked"})) -> WalkForwardReport:
    cell_stats(outcomes, min_trades=min_trades, min_days=min_days, confidence=confidence,
               n_boot=n_boot, seed=seed, key=key, link_statuses=link_statuses)
    _validate_folds(folds)
    try:
        with localcontext(_CTX):
            fold_results = []
            all_is = []
            all_oos = []
            all_rest = []
            for fold in folds:
                train = [o for o in outcomes if o.link_status in link_statuses
                         and fold.train_start_ms <= o.closed_at_ms < fold.train_end_ms]
                test = [o for o in outcomes if o.link_status in link_statuses
                        and fold.test_start_ms <= o.closed_at_ms < fold.test_end_ms]
                cs = cell_stats(train, min_trades=min_trades, min_days=min_days, confidence=confidence,
                                n_boot=n_boot, seed=seed, key=key, link_statuses=link_statuses)
                evaluated = [c for c in cs if c.status != "insufficient"]
                selected = [c for c in cs if c.status == "positive"]
                selected_ids = {(c.key, repr(c.key)) for c in selected}
                sel_cells = []
                for c in selected:
                    cell_test = [o for o in test if (key(o), repr(key(o))) == (c.key, repr(c.key))]
                    tn = len(cell_test)
                    tm = _q4(sum(o.net_bp for o in cell_test) / Decimal(tn)) if tn else None
                    sel_cells.append(SelectedCell(c.key, c.n, c.mean_net_bp, c.ci_low, tn, tm))
                sel_test = [o for o in test if (key(o), repr(key(o))) in selected_ids]
                rest_test = [o for o in test if (key(o), repr(key(o))) not in selected_ids]
                sn = len(sel_test)
                sm = _q4(sum(o.net_bp for o in sel_test) / Decimal(sn)) if sn else None
                rn = len(rest_test)
                rm = _q4(sum(o.net_bp for o in rest_test) / Decimal(rn)) if rn else None
                fold_results.append(FoldResult(
                    fold, len(train), len(test), len(evaluated), len(selected),
                    tuple(sel_cells), sn, sm, rn, rm,
                ))
                all_is.extend(o.net_bp for c in selected for o in train if (key(o), repr(key(o))) == (c.key, repr(c.key)))
                all_oos.extend(o.net_bp for o in sel_test)
                all_rest.extend(o.net_bp for o in rest_test)
            is_n = len(all_is)
            is_mean = _q4(sum(all_is) / Decimal(is_n)) if is_n else None
            oos_n = len(all_oos)
            oos_mean = _q4(sum(all_oos) / Decimal(oos_n)) if oos_n else None
            rest_n = len(all_rest)
            rest_mean = _q4(sum(all_rest) / Decimal(rest_n)) if rest_n else None
            decay = _q4(is_mean - oos_mean) if is_mean is not None and oos_mean is not None else None
            return WalkForwardReport(
                tuple(fold_results), sum(fr.n_selected for fr in fold_results),
                sum(1 for fr in fold_results if fr.n_selected > 0),
                is_n, is_mean, oos_n, oos_mean, rest_n, rest_mean, decay,
            )
    except ArithmeticError:
        raise ValueError("invalid_outcome") from None
