"""Strict protocol loader. Nested JSON groups are frozen specs, never mutable maps.

Protocol keeps root names, with regime/labeling/evaluation/controls/verdict as
frozen records whose fields retain their JSON names. No experimental defaults.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from backend.v3.detectors.common import RiskSpec, check_risk, check_symbol
from backend.v3.detectors.breakout import DonchianParams, detect_donchian_breakout
from backend.v3.detectors.reversal import BbMacdParams, detect_bollinger_macd_reversal
from backend.v3.detectors.trend import EmaCrossParams, detect_ema_cross_adx
from backend.v3.features.regime import RegimeParams, regime_labels
from backend.v3.learning.opportunity import POLICIES


@dataclass(frozen=True)
class StrategySpec:
    id: str
    kind: str
    params: DonchianParams | BbMacdParams | EmaCrossParams


@dataclass(frozen=True)
class WfSpec:
    min_trades: int
    min_days: int
    confidence: Decimal
    n_boot: int
    seed: int


@dataclass(frozen=True)
class RegimeSpec:
    atr_n: int
    pct_window: int
    adx_n: int
    params: RegimeParams


@dataclass(frozen=True)
class LabelSpec:
    primary_horizon_ms: int
    primary_cost_bp: Decimal
    stress_costs_bp: tuple[Decimal, ...]
    primary_policy: str
    bound_policy: str


@dataclass(frozen=True)
class EvaluationSpec:
    warmup_days: int
    train_days: int
    test_days: int
    step_days: int
    embargo_days: int
    expanding: bool
    wf: WfSpec
    whole: WfSpec


@dataclass(frozen=True)
class ControlSpec:
    n_shifts: int
    min_shift_days: int
    seed: int


@dataclass(frozen=True)
class VerdictSpec:
    oos_over_train_min: Decimal
    min_oos_trades: int
    min_folds_with_selection: int
    control_percentile_min: Decimal


@dataclass(frozen=True)
class Protocol:
    protocol_version: int
    run_id: str
    candle_ms: int
    symbols: tuple[str, ...]
    min_segment_bars: int
    unit_notional: Decimal
    risk: RiskSpec
    strategies: tuple[StrategySpec, ...]
    regime: RegimeSpec
    labeling: LabelSpec
    evaluation: EvaluationSpec
    controls: ControlSpec
    verdict: VerdictSpec


def _keys(raw, keys):
    if type(raw) is not dict or set(raw) != set(keys.split()):
        raise ValueError("invalid_protocol")
    return raw


def _integer(v, minimum):
    if type(v) is not int or (minimum is not None and v < minimum):
        raise ValueError("invalid_protocol")
    return v


def _decimal(v):
    if type(v) is not str or re.fullmatch(r"-?\d+(\.\d+)?", v) is None:
        raise ValueError("invalid_protocol")
    d = Decimal(v)
    if not d.is_finite():
        raise ValueError("invalid_protocol")
    return d


def _wf(raw):
    _keys(raw, "min_trades min_days confidence n_boot seed")
    out = WfSpec(_integer(raw['min_trades'], 1), _integer(raw['min_days'], 2),
                 _decimal(raw['confidence']), _integer(raw['n_boot'], 200),
                 _integer(raw['seed'], None))
    if not Decimal('0') < out.confidence < Decimal('1'):
        raise ValueError("invalid_protocol")
    return out


def load_protocol(raw) -> Protocol:
    """Exact keys at every level; delegates detector/regime coherence to owners."""
    try:
        return _load(raw)
    except (ValueError, TypeError, ArithmeticError):
        raise ValueError("invalid_protocol") from None


def _load(raw):
    _keys(raw, 'protocol_version run_id candle_ms symbols min_segment_bars unit_notional risk strategies regime labeling evaluation controls verdict')
    if _integer(raw['protocol_version'], 1) != 1:
        raise ValueError('invalid_protocol')
    run_id = raw['run_id']
    if type(run_id) is not str or re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}', run_id) is None:
        raise ValueError('invalid_protocol')
    ms = _integer(raw['candle_ms'], 1)
    symbols = raw['symbols']
    if type(symbols) is not list or not symbols:
        raise ValueError('invalid_protocol')
    for symbol in symbols:
        check_symbol(symbol)
    if len(set(symbols)) != len(symbols):
        raise ValueError('invalid_protocol')
    segment = _integer(raw['min_segment_bars'], 1)
    unit = _decimal(raw['unit_notional'])
    if unit <= 0:
        raise ValueError('invalid_protocol')
    r = _keys(raw['risk'], 'atr_n stop_atr_mult target_r_mult cooldown_bars')
    risk = RiskSpec(_integer(r['atr_n'], 1), _decimal(r['stop_atr_mult']),
                    _decimal(r['target_r_mult']), _integer(r['cooldown_bars'], 0))
    check_risk(risk)
    specs = raw['strategies']
    if type(specs) is not list or not specs:
        raise ValueError('invalid_protocol')
    strategies = []
    seen = set()
    for s in specs:
        _keys(s, 'id kind params')
        sid, kind = s['id'], s['kind']
        if type(sid) is not str or re.fullmatch(r'S\d{2}', sid) is None or sid in seen:
            raise ValueError('invalid_protocol')
        seen.add(sid)
        if sid == 'S07' and kind == 'donchian':
            p = _keys(s['params'], 'n trend_ema_n')
            params = DonchianParams(_integer(p['n'], 1), None if p['trend_ema_n'] is None else _integer(p['trend_ema_n'], 1))
            detect_donchian_breakout(symbols[0], [], params, risk, candle_ms=ms)
        elif sid == 'S05' and kind == 'bb_macd':
            p = _keys(s['params'], 'bb_n bb_k pb_low pb_high macd_fast macd_slow macd_signal')
            params = BbMacdParams(_integer(p['bb_n'], 2), _decimal(p['bb_k']), _decimal(p['pb_low']), _decimal(p['pb_high']),
                                  _integer(p['macd_fast'], 1), _integer(p['macd_slow'], 1), _integer(p['macd_signal'], 1))
            detect_bollinger_macd_reversal(symbols[0], [], params, risk, candle_ms=ms)
        elif sid == 'S02' and kind == 'ema_cross_adx':
            p = _keys(s['params'], 'fast_n slow_n adx_n adx_min')
            params = EmaCrossParams(_integer(p['fast_n'], 1), _integer(p['slow_n'], 1), _integer(p['adx_n'], 1), _decimal(p['adx_min']))
            detect_ema_cross_adx(symbols[0], [], params, risk, candle_ms=ms)
        else:
            raise ValueError('invalid_protocol')
        strategies.append(StrategySpec(sid, kind, params))
    r = _keys(raw['regime'], 'atr_n pct_window adx_n params')
    p = _keys(r['params'], 'shock_tr_mult expansion_pct_min adx_trend_min adx_range_max')
    regime = RegimeSpec(_integer(r['atr_n'], 1), _integer(r['pct_window'], 1), _integer(r['adx_n'], 1),
                        RegimeParams(**{k: _decimal(v) for k, v in p.items()}))
    regime_labels([], regime.atr_n, regime.pct_window, regime.adx_n, regime.params, candle_ms=ms)
    l = _keys(raw['labeling'], 'primary_horizon_ms primary_cost_bp stress_costs_bp primary_policy bound_policy')
    horizon = _integer(l['primary_horizon_ms'], 1)
    primary = _decimal(l['primary_cost_bp'])
    stress = l['stress_costs_bp']
    if type(stress) is not list or not stress:
        raise ValueError('invalid_protocol')
    costs = tuple(_decimal(v) for v in stress)
    if horizon % ms or primary < 0 or any(v < 0 for v in costs) or len(set(costs)) != len(costs) or primary in costs:
        raise ValueError('invalid_protocol')
    if l['primary_policy'] not in POLICIES or l['bound_policy'] not in POLICIES or l['primary_policy'] == l['bound_policy']:
        raise ValueError('invalid_protocol')
    labeling = LabelSpec(horizon, primary, costs, l['primary_policy'], l['bound_policy'])
    e = _keys(raw['evaluation'], 'warmup_days train_days test_days step_days embargo_days expanding wf whole')
    evaluation = EvaluationSpec(_integer(e['warmup_days'], 0), _integer(e['train_days'], 1),
                                _integer(e['test_days'], 1), _integer(e['step_days'], 1),
                                _integer(e['embargo_days'], 0), e['expanding'], _wf(e['wf']), _wf(e['whole']))
    if type(evaluation.expanding) is not bool or evaluation.step_days < evaluation.test_days:
        raise ValueError('invalid_protocol')
    c = _keys(raw['controls'], 'n_shifts min_shift_days seed')
    controls = ControlSpec(_integer(c['n_shifts'], 1), _integer(c['min_shift_days'], 1), _integer(c['seed'], None))
    v = _keys(raw['verdict'], 'oos_over_train_min min_oos_trades min_folds_with_selection control_percentile_min')
    verdict = VerdictSpec(_decimal(v['oos_over_train_min']), _integer(v['min_oos_trades'], 1),
                          _integer(v['min_folds_with_selection'], 1), _decimal(v['control_percentile_min']))
    if not Decimal('0') < verdict.oos_over_train_min <= Decimal('1') or not Decimal('0') < verdict.control_percentile_min <= Decimal('100'):
        raise ValueError('invalid_protocol')
    return Protocol(1, run_id, ms, tuple(symbols), segment, unit, risk, tuple(strategies), regime, labeling, evaluation, controls, verdict)
