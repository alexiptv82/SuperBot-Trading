"""Preregistered precedence; comparisons use Decimal without display rounding."""
from __future__ import annotations

from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext

_CTX = Context(prec=60, rounding=ROUND_HALF_EVEN)


def classify(*, whole_status, mean_net_bp, ci_low, ci_high, n_folds_with_selection,
             oos_n, oos_mean_net_bp, is_mean_net_bp, inverted_mean_net_bp,
             shift_rank_pct, oos_over_train_min, min_oos_trades,
             min_folds_with_selection, control_percentile_min):
    if type(whole_status) is not str or whole_status not in {'insufficient', 'positive', 'negative', 'inconclusive'}:
        raise ValueError('invalid_status')
    for v in (mean_net_bp, ci_low, ci_high, oos_mean_net_bp, is_mean_net_bp, inverted_mean_net_bp, shift_rank_pct):
        if v is not None and (not isinstance(v, Decimal) or not v.is_finite()):
            raise ValueError('invalid_value')
    for v in (n_folds_with_selection, oos_n, min_oos_trades, min_folds_with_selection):
        if type(v) is not int:
            raise ValueError('invalid_value')
    for v in (oos_over_train_min, control_percentile_min):
        if not isinstance(v, Decimal) or not v.is_finite():
            raise ValueError('invalid_threshold')
    try:
        with localcontext(_CTX):
            if whole_status == 'insufficient' or mean_net_bp is None or ci_low is None or ci_high is None:
                return 'DATI_INSUFFICIENTI', ()
            if ci_high < 0:
                return 'NEGATIVO', ()
            e1 = mean_net_bp > 0 and ci_low > 0
            e2 = (n_folds_with_selection >= min_folds_with_selection and oos_n >= min_oos_trades
                  and oos_mean_net_bp is not None and oos_mean_net_bp > 0
                  and is_mean_net_bp is not None and oos_mean_net_bp >= oos_over_train_min * is_mean_net_bp)
            e3 = inverted_mean_net_bp is not None and inverted_mean_net_bp < mean_net_bp and inverted_mean_net_bp <= 0
            e4 = shift_rank_pct is not None and shift_rank_pct >= control_percentile_min
            failed = tuple(name for name, ok in zip(('E1', 'E2', 'E3', 'E4'), (e1, e2, e3, e4)) if not ok)
            if not failed:
                return 'EVIDENZA_POSITIVA', ()
            if mean_net_bp > 0:
                return 'POSITIVO_INCONCLUDENTE', failed
            return 'NULLO', ()
    except ArithmeticError:
        raise ValueError('numeric_out_of_range') from None
