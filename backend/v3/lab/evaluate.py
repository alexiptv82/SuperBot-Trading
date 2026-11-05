"""One strategy/asset report. Diagnostics 6/10 intentionally use all complete labels.

WF ratios and E2 use the already-rounded report means, as preregistered.
All outcome statistics exclude openings before the evaluation start.
"""
from __future__ import annotations

from dataclasses import asdict
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext

from backend.v3.learning.opportunity import label_candidates
from backend.v3.learning.expectancy import cell_stats, default_cell_key
from backend.v3.learning.walkforward import make_folds, walk_forward
from backend.v3.lab.adapter import outcomes_from_labels
from backend.v3.lab.controls import invert_candidates
from backend.v3.lab.verdict import classify

_CTX = Context(prec=60, rounding=ROUND_HALF_EVEN)
_MS_PER_DAY = 86_400_000


def _q4(d):
    r = d.quantize(Decimal('0.0001'))
    return abs(r) if r == 0 else r


def _mean(values):
    return _q4(sum(values, Decimal('0')) / len(values)) if values else None


def _json(v):
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, dict):
        return {k: _json(x) for k, x in v.items()}
    if isinstance(v, (tuple, list)):
        return [_json(x) for x in v]
    return v


def evaluation_window(protocol, candles):
    if not candles:
        raise ValueError('invalid_candles')
    first, last = candles[0].open_time_ms, candles[-1].open_time_ms
    start = ((first + _MS_PER_DAY - 1) // _MS_PER_DAY) * _MS_PER_DAY + protocol.evaluation.warmup_days * _MS_PER_DAY
    end = ((last + protocol.candle_ms) // _MS_PER_DAY) * _MS_PER_DAY
    return start, end


def evaluation_folds(protocol, start, end):
    if end <= start:
        return ()
    e = protocol.evaluation
    try:
        return make_folds(start_ms=start, end_ms=end, train_ms=e.train_days * _MS_PER_DAY,
                          test_ms=e.test_days * _MS_PER_DAY, step_ms=e.step_days * _MS_PER_DAY,
                          embargo_ms=e.embargo_days * _MS_PER_DAY, expanding=e.expanding)
    except ValueError as exc:
        if str(exc) not in ('no_folds', 'invalid_window'):
            raise
        return ()


def _cell(cells):
    if not cells:
        return dict(n=0, n_days=0, mean_net_bp=None, mean_r=None, ci_low=None, ci_high=None, status='insufficient')
    c = cells[0]
    return {k: getattr(c, k) for k in ('n', 'n_days', 'mean_net_bp', 'mean_r', 'ci_low', 'ci_high', 'status')}


def _wf(outcomes, folds, spec, key):
    if not folds:
        return dict(status='no_folds', n_folds=0, n_folds_with_selection=0, n_selections=0,
                    is_n=0, is_mean_net_bp=None, oos_n=0, oos_mean_net_bp=None,
                    rest_n=0, rest_mean_net_bp=None, decay_bp=None, oos_over_is=None)
    report = walk_forward(outcomes, folds, **asdict(spec), key=key)
    result = {k: getattr(report, k) for k in ('n_folds_with_selection', 'n_selections', 'is_n', 'is_mean_net_bp',
                                            'oos_n', 'oos_mean_net_bp', 'rest_n', 'rest_mean_net_bp', 'decay_bp')}
    ratio = None
    if report.is_mean_net_bp is not None and report.is_mean_net_bp != 0 and report.oos_mean_net_bp is not None:
        ratio = _q4(report.oos_mean_net_bp / report.is_mean_net_bp)
    return dict(status='ok', n_folds=len(folds), **result, oos_over_is=ratio)


def evaluate_candidates(protocol, strategy_id, symbol, candidates, candles, regimes, null_sets):
    try:
        with localcontext(_CTX):
            return _evaluate(protocol, strategy_id, symbol, candidates, candles, regimes, null_sets)
    except ArithmeticError:
        raise ValueError('numeric_out_of_range') from None


def _evaluate(p, strategy_id, symbol, candidates, candles, regimes, null_sets):
    start, end = evaluation_window(p, candles)  # procedure 1
    l = p.labeling

    def labelled(cs, cost, policy):
        labels = label_candidates(cs, {symbol: candles}, candle_ms=p.candle_ms,
                                  horizons_ms=[l.primary_horizon_ms], cost_bp=cost, ambiguous_policy=policy)
        outcomes, incomplete = outcomes_from_labels(cs, labels, strategy_id=strategy_id, run_id=p.run_id,
                                                    horizon_ms=l.primary_horizon_ms, candle_ms=p.candle_ms,
                                                    cost_bp=cost, unit_notional=p.unit_notional, regimes=regimes)
        return labels, outcomes, incomplete, tuple(o for o in outcomes if o.opened_at_ms >= start)

    def cell(os):
        return _cell(cell_stats(os, key=lambda o: ('ALL',), **asdict(p.evaluation.whole)))

    labels, all_outcomes, incomplete, outcomes = labelled(candidates, l.primary_cost_bp, l.primary_policy)  # procedure 2
    whole = cell(outcomes)  # procedure 3
    by_side = {str(c.key[0]): _cell([c]) for c in cell_stats(outcomes, key=lambda o: (o.side,), **asdict(p.evaluation.whole))}
    peak = Decimal('0')
    total = Decimal('0')
    dd = Decimal('0')
    for o in sorted(outcomes, key=lambda o: (o.closed_at_ms, o.position_id)):
        total += o.r_multiple
        peak = max(peak, total)
        dd = max(dd, peak - total)
    max_dd = _q4(dd) if outcomes else None
    folds = evaluation_folds(p, start, end)  # procedure 4
    wf = _wf(outcomes, folds, p.evaluation.wf, lambda o: (o.symbol, o.side))
    wf_regime = _wf(outcomes, folds, p.evaluation.wf, default_cell_key)
    stress = {str(cost): cell(labelled(candidates, cost, l.primary_policy)[3]) for cost in l.stress_costs_bp}  # procedure 5
    bound = dict(policy=l.bound_policy, cell=cell(labelled(candidates, l.primary_cost_bp, l.bound_policy)[3]))  # procedure 6
    complete_labels = [label.horizons[0] for label in labels if label.horizons[0].status == 'complete']
    n_ambiguous = sum(h.ambiguous for h in complete_labels)
    ambiguous = dict(n=n_ambiguous, share=_q4(Decimal(str(n_ambiguous)) / len(complete_labels)) if complete_labels else None)
    inverted, n_skipped = invert_candidates(candidates)  # procedure 7
    inverse = dict(n_skipped=n_skipped, cell=cell(labelled(inverted, l.primary_cost_bp, l.primary_policy)[3]))
    null_means = []  # procedure 8
    for cs in null_sets:
        os = labelled(cs, l.primary_cost_bp, l.primary_policy)[3]
        mean = _mean([o.net_bp for o in os])
        if mean is not None:
            null_means.append(mean)
    observed = _mean([o.net_bp for o in outcomes])
    below = sum(m < observed for m in null_means) if observed is not None else 0
    rank = Decimal('100') * below / len(null_means) if null_means and observed is not None else None
    shift = dict(n_sets=len(null_sets), n_used=len(null_means), observed_mean_net_bp=observed,
                 n_null_below=below, rank_pct=_q4(rank) if rank is not None else None, null_means=sorted(null_means))
    by_time = {c.open_time_ms: c for c in candles}  # procedure 9
    gaps = [Decimal(str(c.side)) * (by_time[c.signal_time_ms].open - c.entry_price) / c.entry_price * Decimal('10000')
            for c in candidates if c.signal_time_ms >= start and c.signal_time_ms in by_time]
    barriers = {k: sum(h.barrier == k for h in complete_labels) for k in ('target', 'stop', 'timeout')}  # procedure 10
    verdict, failed = classify(whole_status=whole['status'], mean_net_bp=whole['mean_net_bp'], ci_low=whole['ci_low'],
                               ci_high=whole['ci_high'], n_folds_with_selection=wf['n_folds_with_selection'],
                               oos_n=wf['oos_n'], oos_mean_net_bp=wf['oos_mean_net_bp'], is_mean_net_bp=wf['is_mean_net_bp'],
                               inverted_mean_net_bp=inverse['cell']['mean_net_bp'], shift_rank_pct=rank,
                               **asdict(p.verdict))  # procedure 11
    return _json(dict(strategy_id=strategy_id, symbol=symbol, verdict=verdict, failed=failed,
                      counts=dict(candidates=len(candidates), complete=len(all_outcomes), incomplete=incomplete, in_eval=len(outcomes)),
                      whole=whole, by_side=by_side, max_dd_r=max_dd, walk_forward=wf, walk_forward_regime=wf_regime,
                      stress=stress, bound=bound, inverted=inverse, shift_control=shift, ambiguous=ambiguous,
                      entry_gap=dict(n=len(gaps), mean_adverse_gap_bp=_mean(gaps)), barriers=barriers))
