"""P9a contract tests: independent decisions, exact barriers, stubs and mutations."""
from __future__ import annotations

import ast
import copy
import dataclasses
import random
import time
from decimal import Decimal, localcontext
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.v3.detectors import common as C, breakout as B, reversal as R, trend as T
from backend.v3.features import indicators as I
from backend.v3.learning.opportunity import Candidate, Candle, label_candidates

D = Decimal
F = Fraction
MS = 60_000
RISK = C.RiskSpec(2, D('1.5'), D('2.5'), 0)
BP = B.DonchianParams(7, None)
RP = R.BbMacdParams(5, D(3), D('.2'), D('.8'), 3, 8, 4)
TP = T.EmaCrossParams(4, 9, 6, D(25))
CASES = [(B, B.detect_donchian_breakout, BP, 'S07'),
         (R, R.detect_bollinger_macd_reversal, RP, 'S05'),
         (T, T.detect_ema_cross_adx, TP, 'S02')]


def bars(n=12, prices=None, ms=MS):
    prices = [D(100)] * n if prices is None else list(map(D, prices))
    return [I.Bar(i * ms, p, p + 1, p - 1, p, D(1)) for i, p in enumerate(prices)]


def risk(cd=0):
    return dataclasses.replace(RISK, cooldown_bars=cd)


def error(code, fn, *args, **kwargs):
    with pytest.raises(ValueError) as caught:
        fn(*args, **kwargs)
    assert str(caught.value) == code
    assert caught.value.__cause__ is None


def patch_atr(mp, values):
    calls = []
    def stub(bs, n, *, candle_ms):
        calls.append((bs, n, candle_ms))
        return tuple(values[:len(bs)])
    mp.setattr(C, 'atr', stub)
    return calls


def build(bs, sides, rs=RISK):
    return C.build_candidates('BTCUSDT', bs, sides, strategy_id='S07', risk=rs, candle_ms=MS)


def emit_indices(out):
    return [c.signal_time_ms // MS - 1 for c in out]


# Each hand-written expected price is first checked independently as a Fraction.
def vector_expected(sid, side=1):
    entry, distance = F(100), F('1.5') * F(2)
    stop = entry - side * distance
    target = entry + side * F('2.5') * distance
    texts = ('100', '97', '107.5') if side == 1 else ('100', '103', '92.5')
    assert (entry, stop, target) == tuple(map(F, texts))
    time_text = '360000'
    assert int(time_text) == (5 + 1) * MS
    return Candidate(f"{sid}:BTCUSDT:360000:{'L' if side == 1 else 'S'}",
                     'BTCUSDT', side, int(time_text), *map(D, texts))


@pytest.mark.parametrize('side', [1, -1])
def test_build_hand_vector(monkeypatch, side):
    bs = bars()
    calls = patch_atr(monkeypatch, [D(2)] * 12)
    sides = [0] * 12
    sides[5] = side
    before = copy.deepcopy((bs, sides))
    assert build(bs, sides) == (vector_expected('S07', side),)
    assert (bs, sides) == before
    assert calls == [(bs, 2, MS)]


@pytest.mark.parametrize('cd,expected', [(0, [0, 1, 2, 3, 4, 5, 6]),
                                        (1, [0, 2, 4, 6]), (2, [0, 3, 6])])
def test_cooldown_consecutive(monkeypatch, cd, expected):
    patch_atr(monkeypatch, [D(2)] * 7)
    assert emit_indices(build(bars(7), [1, -1, 1, -1, 1, -1, 1], risk(cd))) == expected


@pytest.mark.parametrize('cd,expected', [(0, [0, 2, 3, 5, 8]), (1, [0, 2, 5, 8]), (2, [0, 3, 8])])
def test_cooldown_spaced(monkeypatch, cd, expected):
    patch_atr(monkeypatch, [D(2)] * 9)
    assert emit_indices(build(bars(9), [1, 0, -1, 1, 0, -1, 0, 0, 1], risk(cd))) == expected


def test_build_zero_side(monkeypatch):
    patch_atr(monkeypatch, [D(2)] * 2)
    assert build(bars(2), [0, 0]) == ()


def test_build_warmup(monkeypatch):
    patch_atr(monkeypatch, [None, D(2)])
    assert emit_indices(build(bars(2), [1, -1], risk(10))) == [1]


@pytest.mark.parametrize('side', [1, -1])
def test_build_zero_atr_does_not_cool(monkeypatch, side):
    patch_atr(monkeypatch, [D(0), D(2), D(2)])
    assert emit_indices(build(bars(3), [side, side, -side], risk(1))) == [1]


@pytest.mark.parametrize('side,atr_value', [(1, '100'), (-1, '40'), (1, '66.6666666666666666666666666666666666666666666666666666666667')])
def test_build_nonpositive_barrier_does_not_cool(monkeypatch, side, atr_value):
    patch_atr(monkeypatch, [D(atr_value), D(2)])
    assert emit_indices(build(bars(2), [side, side], risk(10))) == [1]


def test_build_stop_exactly_zero(monkeypatch):
    patch_atr(monkeypatch, [D(100), D(2)])
    rs = C.RiskSpec(1, D(1), D(1), 10)
    assert emit_indices(build(bars(2), [1, 1], rs)) == [1]


def test_build_target_exactly_zero(monkeypatch):
    patch_atr(monkeypatch, [D(100), D(2)])
    rs = C.RiskSpec(1, D(1), D(1), 10)
    assert emit_indices(build(bars(2), [-1, -1], rs)) == [1]


def test_build_time_id_order_and_label_contract(monkeypatch):
    bs = bars(4)
    patch_atr(monkeypatch, [D(2)] * 4)
    out = build(bs, [1, -1, 0, 1])
    assert [c.candidate_id for c in out] == ['S07:BTCUSDT:60000:L', 'S07:BTCUSDT:120000:S', 'S07:BTCUSDT:240000:L']
    assert [c.signal_time_ms for c in out] == [60000, 120000, 240000]
    candles = {'BTCUSDT': [Candle(b.open_time_ms, b.open, b.high, b.low, b.close) for b in bs]}
    labels = label_candidates(out, candles, candle_ms=MS, horizons_ms=[MS], cost_bp=D(0), ambiguous_policy='stop_first')
    assert len(labels) == 3
    assert labels[0].horizons[0].touch_time_ms is None
    assert labels[-1].horizons[0].status == 'incomplete'


@pytest.mark.parametrize('sides', [[], [1], [1, 0, 1]])
def test_build_length(monkeypatch, sides):
    def no_call(*a, **k):
        pytest.fail('ATR called before length check')
    monkeypatch.setattr(C, 'atr', no_call)
    error('invalid_sides', build, bars(2), sides)


@pytest.mark.parametrize('exc', [OverflowError, ZeroDivisionError, ArithmeticError])
def test_build_arithmetic_conversion(monkeypatch, exc):
    def bad(*a, **k):
        raise exc('injected')
    monkeypatch.setattr(C, 'atr', bad)
    error('numeric_out_of_range', build, bars(1), [1])


def test_build_decimal_context_and_no_rounding(monkeypatch):
    bs = bars(2)
    values = [D('1.23456789123456789123456789123456789123456789')] * 2
    patch_atr(monkeypatch, values)
    expected = build(bs, [1, -1])
    with localcontext() as ctx:
        ctx.prec = 5
        assert build(bs, [1, -1]) == expected
    assert F(expected[0].stop_price) == F(100) - F('1.5') * F(values[0])
    assert F(expected[0].target_price) == F(100) + F('2.5') * F('1.5') * F(values[0])


# Stub the entire feature boundary, preserving argument spies and real candidate construction.
def feature_stubs(mp, mod, n, overrides=None):
    data = dict(high=[D(101)] * n, low=[D(99)] * n, te=[D(99)] * n,
                pb=[D('.5')] * n, line=[D(1)] * n, hist=[D(1)] * n,
                ef=[D(100)] * n, es=[D(100)] * n, ax=[D(25)] * n)
    if overrides:
        data.update(overrides)
    calls = []
    def dc(bs, period, *, candle_ms):
        calls.append(('donchian', bs, period, candle_ms))
        return SimpleNamespace(high=data['high'], low=data['low'])
    def ema(values, period):
        calls.append(('ema', values, period))
        key = 'te' if mod is B else ('ef' if period == TP.fast_n else 'es')
        return tuple(data[key])
    def bb(bs, period, k, *, candle_ms):
        calls.append(('bollinger', bs, period, k, candle_ms))
        return SimpleNamespace(percent_b=data['pb'])
    def mc(bs, fast, slow, signal, *, candle_ms):
        calls.append(('macd', bs, fast, slow, signal, candle_ms))
        return SimpleNamespace(line=data['line'], hist=data['hist'])
    def ax(bs, period, *, candle_ms):
        calls.append(('adx', bs, period, candle_ms))
        return SimpleNamespace(adx=data['ax'])
    for name, fn in [('donchian', dc), ('ema', ema), ('bollinger', bb), ('macd', mc), ('adx', ax)]:
        if hasattr(mod, name):
            mp.setattr(mod, name, fn)
    patch_atr(mp, [D(2)] * n)
    return data, calls


@pytest.mark.parametrize('case', CASES, ids=['S07', 'S05', 'S02'])
@pytest.mark.parametrize('side', [1, -1])
def test_detector_hand_vector(monkeypatch, case, side):
    mod, fn, params, sid = case
    data, calls = feature_stubs(monkeypatch, mod, 12)
    if mod is B:
        data['high'][4] = D(99) if side == 1 else D(101)
        data['low'][4] = D(99) if side == 1 else D(101)
    elif mod is R:
        data['pb'][5], data['line'][5], data['hist'][5] = (D('.1'), D(-1), D(1)) if side == 1 else (D('.9'), D(1), D(-1))
    else:
        data['ef'][5] = D(100 + side)
    assert fn('BTCUSDT', bars(), params, RISK, candle_ms=MS) == (vector_expected(sid, side),)
    assert calls


# All three strict S07 edges, both directions, channel index and each None separately.
@pytest.mark.parametrize('side', [1, -1])
@pytest.mark.parametrize('edge', ['signal', 'channel_equal', 'ema_equal', 'ema_wrong', 'ema_none', 'high_none', 'low_none', 'current_channel_only'])
def test_breakout_edges(monkeypatch, side, edge):
    data, _ = feature_stubs(monkeypatch, B, 2)
    data['high'][0], data['low'][0] = (D(99), D(98)) if side == 1 else (D(102), D(101))
    data['te'][1] = D(99 if side == 1 else 101)
    if edge == 'channel_equal':
        data['high' if side == 1 else 'low'][0] = D(100)
    if edge == 'ema_equal':
        data['te'][1] = D(100)
    if edge == 'ema_wrong':
        data['te'][1] = D(101 if side == 1 else 99)
    if edge == 'ema_none':
        data['te'][1] = None
    if edge in ('high_none', 'low_none'):
        data[edge.split('_')[0]][0] = None
    if edge == 'current_channel_only':
        data['high'][1], data['low'][1] = data['high'][0], data['low'][0]
        data['high'][0], data['low'][0] = D(101), D(99)
    out = B.detect_donchian_breakout('BTCUSDT', bars(2), B.DonchianParams(7, 3), RISK, candle_ms=MS)
    assert [c.side for c in out] == ([side] if edge == 'signal' else [])


def test_breakout_filter_off_does_not_call_ema(monkeypatch):
    data, _ = feature_stubs(monkeypatch, B, 2)
    data['high'][0] = D(99)
    def forbidden(*a, **k):
        pytest.fail('EMA used with disabled filter')
    monkeypatch.setattr(B, 'ema', forbidden)
    assert len(B.detect_donchian_breakout('BTCUSDT', bars(2), BP, RISK, candle_ms=MS)) == 1


@pytest.mark.parametrize('side', [1, -1])
@pytest.mark.parametrize('edge', ['signal', 'pb_equal', 'pb_wrong', 'hist_zero', 'hist_wrong', 'line_zero', 'line_wrong', 'pb_none', 'line_none', 'hist_none'])
def test_reversal_edges(monkeypatch, side, edge):
    data, _ = feature_stubs(monkeypatch, R, 1)
    data['pb'][0], data['hist'][0], data['line'][0] = (D('.1'), D(1), D(-1)) if side == 1 else (D('.9'), D(-1), D(1))
    changes = {'pb_equal': ('pb', RP.pb_low if side == 1 else RP.pb_high),
               'pb_wrong': ('pb', D('.5')), 'hist_zero': ('hist', D(0)),
               'hist_wrong': ('hist', D(-side)), 'line_zero': ('line', D(0)),
               'line_wrong': ('line', D(side)), 'pb_none': ('pb', None),
               'line_none': ('line', None), 'hist_none': ('hist', None)}
    if edge in changes:
        key, val = changes[edge]
        data[key][0] = val
    out = R.detect_bollinger_macd_reversal('BTCUSDT', bars(1), RP, RISK, candle_ms=MS)
    assert [c.side for c in out] == ([side] if edge == 'signal' else [])


@pytest.mark.parametrize('side', [1, -1])
@pytest.mark.parametrize('edge', ['equal_before', 'strict_before', 'wrong_before', 'equal_after', 'wrong_after', 'adx_low', 'prev_fast_none', 'prev_slow_none', 'fast_none', 'slow_none', 'adx_none'])
def test_trend_edges(monkeypatch, side, edge):
    data, _ = feature_stubs(monkeypatch, T, 2)
    data['ef'][1] = D(100 + side)
    if edge == 'strict_before':
        data['ef'][0] = D(100 - side)
    if edge == 'wrong_before':
        data['ef'][0] = D(100 + side)
    if edge == 'equal_after':
        data['ef'][1] = D(100)
    if edge == 'wrong_after':
        data['ef'][1] = D(100 - side)
    if edge == 'adx_low':
        data['ax'][1] = D('24.999')
    nones = {'prev_fast_none': ('ef', 0), 'prev_slow_none': ('es', 0),
             'fast_none': ('ef', 1), 'slow_none': ('es', 1), 'adx_none': ('ax', 1)}
    if edge in nones:
        key, i = nones[edge]
        data[key][i] = None
    out = T.detect_ema_cross_adx('BTCUSDT', bars(2), TP, RISK, candle_ms=MS)
    assert [c.side for c in out] == ([side] if edge in ('equal_before', 'strict_before') else [-side] if edge == 'wrong_after' else [])


@pytest.mark.parametrize('case', CASES, ids=['S07', 'S05', 'S02'])
def test_feature_argument_spies(monkeypatch, case):
    mod, fn, params, _ = case
    bs = bars()
    _, calls = feature_stubs(monkeypatch, mod, len(bs))
    if mod is B:
        params = B.DonchianParams(7, 3)
    fn('BTCUSDT', bs, params, RISK, candle_ms=MS)
    closes = [b.close for b in bs]
    expected = [('donchian', bs, 7, MS), ('ema', closes, 3)] if mod is B else (
        [('bollinger', bs, 5, D(3), MS), ('macd', bs, 3, 8, 4, MS)] if mod is R else
        [('ema', closes, 4), ('ema', closes, 9), ('adx', bs, 6, MS)])
    assert calls == expected


@pytest.mark.parametrize('mod,fn,params', [(B, B.detect_donchian_breakout, BP), (T, T.detect_ema_cross_adx, TP)])
def test_zero_index_excluded(monkeypatch, mod, fn, params):
    data, _ = feature_stubs(monkeypatch, mod, 1)
    data['high'][0] = D(99)
    data['ef'][0] = D(101)
    assert fn('BTCUSDT', bars(1), params, RISK, candle_ms=MS) == ()


# Input validation, including numerically valid bool values and exact dataclass types.
BAD_POS_INT = [True, False, 1.0, None, 0, -1, D(1)]
BAD_POS_DEC = [True, 1.0, None, 1, D('NaN'), D('sNaN'), D('Infinity'), D('-Infinity'), D(0), D(-1)]
BAD_FIN_DEC = [True, 1.0, None, 1, D('NaN'), D('sNaN'), D('Infinity'), D('-Infinity')]
BAD_PARAMS = []
for base, fields in [(BP, ['n', 'trend_ema_n']), (RP, ['bb_n', 'macd_fast', 'macd_slow', 'macd_signal']), (TP, ['fast_n', 'slow_n', 'adx_n'])]:
    for field in fields:
        for value in BAD_POS_INT:
            if value is None and field == 'trend_ema_n':
                continue
            BAD_PARAMS.append((type(base), dataclasses.replace(base, **{field: value})))
for field in ['bb_k', 'pb_low', 'pb_high']:
    for value in (BAD_POS_DEC if field == 'bb_k' else BAD_FIN_DEC):
        BAD_PARAMS.append((type(RP), dataclasses.replace(RP, **{field: value})))
for value in BAD_FIN_DEC + [D(-1)]:
    BAD_PARAMS.append((type(TP), dataclasses.replace(TP, adx_min=value)))
BAD_PARAMS += [(type(RP), dataclasses.replace(RP, bb_n=1)),
               (type(RP), dataclasses.replace(RP, pb_low=D('.8'))),
               (type(RP), dataclasses.replace(RP, pb_low=D('.9'))),
               (type(RP), dataclasses.replace(RP, macd_fast=8)),
               (type(RP), dataclasses.replace(RP, macd_fast=9)),
               (type(TP), dataclasses.replace(TP, fast_n=9)),
               (type(TP), dataclasses.replace(TP, fast_n=10))]


@pytest.mark.parametrize('cls,bad', BAD_PARAMS)
def test_each_params_field(cls, bad):
    _, fn, params, _ = next(c for c in CASES if type(c[2]) is cls)
    error('invalid_params', fn, 'BTCUSDT', bars(2), bad, RISK, candle_ms=MS)


BAD_RISK = [None, {}, True]
for field in ['atr_n', 'cooldown_bars']:
    for value in BAD_POS_INT:
        if value == 0 and type(value) is int and field == 'cooldown_bars':
            continue
        BAD_RISK.append(dataclasses.replace(RISK, **{field: value}))
for field in ['stop_atr_mult', 'target_r_mult']:
    for value in BAD_POS_DEC:
        BAD_RISK.append(dataclasses.replace(RISK, **{field: value}))


@pytest.mark.parametrize('bad', BAD_RISK)
def test_each_risk_field(bad):
    error('invalid_risk', C.check_risk, bad)


@pytest.mark.parametrize('bad', [True, False, 1.0, None, 0, -1, D(1)])
def test_candle_ms(bad):
    error('invalid_candle_ms', C.check_candle_ms, bad)


@pytest.mark.parametrize('bad', ['', 'BTC\n', 'x' * 41, 'BTC/USDT', None, True, 1, '.BTC', 'é', 'BTC:USDT'])
def test_symbol(bad):
    error('invalid_symbol', C.check_symbol, bad)


@pytest.mark.parametrize('valid', ['A', 'x' * 40, 'BTC-USDT', 'a.b_c9', '0'])
def test_valid_symbol(valid):
    C.check_symbol(valid)


@pytest.mark.parametrize('case', CASES, ids=['S07', 'S05', 'S02'])
@pytest.mark.parametrize('which', ['params', 'risk'])
def test_dataclass_subclasses(monkeypatch, case, which):
    _, fn, params, _ = case
    base = params if which == 'params' else RISK
    subclass = type('Child', (type(base),), {})
    bad = subclass(**dataclasses.asdict(base))
    error('invalid_' + which, fn, 'BTCUSDT', bars(2), bad if which == 'params' else params,
          bad if which == 'risk' else RISK, candle_ms=MS)


def test_symbol_subclass():
    class Str(str):
        pass
    error('invalid_symbol', C.check_symbol, Str('BTC'))


@pytest.mark.parametrize('case', CASES, ids=['S07', 'S05', 'S02'])
@pytest.mark.parametrize('pair', range(4))
def test_error_order(case, pair):
    _, fn, params, _ = case
    args = dict(symbol='BTCUSDT', bars=bars(2), params=params, risk=RISK, candle_ms=MS)
    fields = ['candle_ms', 'symbol', 'params', 'risk', 'bars']
    codes = ['invalid_candle_ms', 'invalid_symbol', 'invalid_params', 'invalid_risk', 'invalid_bars']
    args[fields[pair]] = True if pair == 0 else None
    args[fields[pair + 1]] = None
    error(codes[pair], fn, **args)


@pytest.mark.parametrize('case', CASES, ids=['S07', 'S05', 'S02'])
@pytest.mark.parametrize('kind', ['generator', 'none', 'second_bad', 'late_nan', 'late_bool_time'])
def test_bad_bars(case, kind):
    _, fn, params, _ = case
    bs = bars(2)
    if kind == 'generator':
        bs = iter(bs)
    elif kind == 'none':
        bs = None
    elif kind == 'second_bad':
        bs[1] = None
    elif kind == 'late_nan':
        bs[1] = dataclasses.replace(bs[1], volume=D('NaN'))
    else:
        bs[1] = dataclasses.replace(bs[1], open_time_ms=True)
    error('invalid_bars', fn, 'BTCUSDT', bs, params, RISK, candle_ms=MS)


@pytest.mark.parametrize('case', CASES, ids=['S07', 'S05', 'S02'])
def test_empty(case):
    _, fn, params, _ = case
    assert fn('BTCUSDT', [], params, RISK, candle_ms=MS) == ()


# Independent oracle uses trusted feature series but no detector helpers for decisions/prices.
def q(value):
    with localcontext(I._CTX):
        return D(value.numerator) / D(value.denominator)


def oracle(sid, bs, params, rs):
    size = len(bs)
    directions = []
    if sid == 'S07':
        dc = I.donchian(bs, params.n, candle_ms=MS)
        te = I.ema([b.close for b in bs], params.trend_ema_n) if params.trend_ema_n is not None else None
    elif sid == 'S05':
        bb = I.bollinger(bs, params.bb_n, params.bb_k, candle_ms=MS)
        mc = I.macd(bs, params.macd_fast, params.macd_slow, params.macd_signal, candle_ms=MS)
    else:
        fast = I.ema([b.close for b in bs], params.fast_n)
        slow = I.ema([b.close for b in bs], params.slow_n)
        ax = I.adx(bs, params.adx_n, candle_ms=MS).adx
    for j in range(size):
        side = 0
        if sid == 'S07' and j:
            h, lo = dc.high[j - 1], dc.low[j - 1]
            if h is not None and lo is not None:
                if bs[j].close > h:
                    side = 1
                if bs[j].close < lo:
                    side = -1
                if te is not None:
                    if te[j] is None:
                        side = 0
                    elif side * (F(bs[j].close) - F(te[j])) <= 0:
                        side = 0
        elif sid == 'S05':
            p, l, h = bb.percent_b[j], mc.line[j], mc.hist[j]
            if p is not None and l is not None and h is not None:
                if all((p < params.pb_low, h > 0, l < 0)):
                    side = 1
                if all((p > params.pb_high, h < 0, l > 0)):
                    side = -1
        elif sid == 'S02' and j:
            vals = (fast[j - 1], slow[j - 1], fast[j], slow[j], ax[j])
            if None not in vals and ax[j] >= params.adx_min:
                before, after = F(fast[j - 1]) - F(slow[j - 1]), F(fast[j]) - F(slow[j])
                if before <= 0 and after > 0:
                    side = 1
                if before >= 0 and after < 0:
                    side = -1
        directions.append(side)
    av = I.atr(bs, rs.atr_n, candle_ms=MS)
    results = []
    emitted = []
    for j, direction in enumerate(directions):
        if direction == 0 or av[j] is None:
            continue
        if emitted and j <= emitted[-1] + rs.cooldown_bars:
            continue
        distance = q(F(rs.stop_atr_mult) * F(av[j]))
        reward = q(F(rs.target_r_mult) * F(distance))
        entry = bs[j].close
        stop = q(F(entry) - direction * F(distance))
        target = q(F(entry) + direction * F(reward))
        if min(stop, target) <= 0:
            continue
        if not (direction * (entry - stop) > 0 and direction * (target - entry) > 0):
            continue
        timestamp = bs[j].open_time_ms + MS
        results.append(Candidate(f"{sid}:BTCUSDT:{timestamp}:{'L' if direction > 0 else 'S'}",
                                 'BTCUSDT', direction, timestamp, entry, stop, target))
        emitted.append(j)
    return tuple(results)


def random_bars(seed, n):
    rng = random.Random(seed)
    price = 10000
    out = []
    for j in range(n):
        opening = price
        price += rng.randint(-40, 40)
        out.append(I.Bar(j * MS, D(opening), D(max(opening, price) + rng.randint(0, 4)),
                         D(min(opening, price) - rng.randint(0, 4)), D(price), D(rng.randint(0, 10))))
    I.check_bars(out, candle_ms=MS)
    return out


REAL_PARAMS = [B.DonchianParams(2, None), R.BbMacdParams(5, D(1), D('.45'), D('.55'), 3, 8, 4),
               T.EmaCrossParams(2, 5, 2, D(0))]
REAL_RISK = C.RiskSpec(2, D(1), D(2), 0)


@pytest.mark.parametrize('index', range(3))
@pytest.mark.parametrize('seed', [17, 123, 20261104])
def test_real_random_oracle(index, seed):
    _, fn, _, sid = CASES[index]
    ps = REAL_PARAMS[index]
    bs = random_bars(seed, 1500)
    before = copy.deepcopy(bs)
    out = fn('BTCUSDT', bs, ps, REAL_RISK, candle_ms=MS)
    assert out == oracle(sid, bs, ps, REAL_RISK)
    assert sum(c.side == 1 for c in out) >= 5
    assert sum(c.side == -1 for c in out) >= 5
    reduced = fn('BTCUSDT', bs, ps, dataclasses.replace(REAL_RISK, cooldown_bars=20), candle_ms=MS)
    assert len(reduced) < len(out)
    if index == 0:
        assert len(fn('BTCUSDT', bs, B.DonchianParams(2, 20), REAL_RISK, candle_ms=MS)) < len(out)
    if index == 2:
        assert len(fn('BTCUSDT', bs, dataclasses.replace(ps, adx_min=D(90)), REAL_RISK, candle_ms=MS)) < len(out)
    assert bs == before


def assert_prefix(fn, bs, ps, rs):
    full = fn('BTCUSDT', bs, ps, rs, candle_ms=MS)
    for m in range(1, len(bs) + 1):
        cutoff = bs[m - 1].open_time_ms + MS
        assert fn('BTCUSDT', bs[:m], ps, rs, candle_ms=MS) == tuple(c for c in full if c.signal_time_ms <= cutoff)


@pytest.mark.parametrize('index', range(3))
def test_no_lookahead(index):
    assert_prefix(CASES[index][1], random_bars(17, 65), REAL_PARAMS[index], REAL_RISK)


def test_prefix_meta_test_detects_future_entry():
    def wrong(symbol, bs, params, rs, *, candle_ms):
        out = B.detect_donchian_breakout(symbol, bs, params, rs, candle_ms=candle_ms)
        return tuple(dataclasses.replace(c, entry_price=bs[c.signal_time_ms // MS].close)
                     if c.signal_time_ms // MS < len(bs) else c for c in out)
    with pytest.raises(AssertionError):
        assert_prefix(wrong, random_bars(17, 65), REAL_PARAMS[0], REAL_RISK)


@pytest.mark.parametrize('index', range(3))
def test_ambient_context(index):
    bs = random_bars(17, 120)
    fn, ps = CASES[index][1], REAL_PARAMS[index]
    expected = fn('BTCUSDT', bs, ps, RISK, candle_ms=MS)
    with localcontext() as ctx:
        ctx.prec = 5
        assert fn('BTCUSDT', bs, ps, RISK, candle_ms=MS) == expected


@pytest.mark.parametrize('index', range(3))
@pytest.mark.parametrize('exponent', [99990, -99990, 999999, -1000100])
def test_extreme_scale(index, exponent):
    fn, ps = CASES[index][1], REAL_PARAMS[index]
    bs = random_bars(17, 80)
    with localcontext(I._CTX):
        try:
            scaled = [dataclasses.replace(b, **{k: getattr(b, k).scaleb(exponent) for k in ('open', 'high', 'low', 'close')}) for b in bs]
        except ArithmeticError:
            # Construct finite inputs outside indicator exponent range without doing arithmetic.
            scaled = [I.Bar(b.open_time_ms, D(f'{b.open}E{exponent}'), D(f'{b.high}E{exponent}'),
                            D(f'{b.low}E{exponent}'), D(f'{b.close}E{exponent}'), b.volume) for b in bs]
    try:
        actual = fn('BTCUSDT', scaled, ps, REAL_RISK, candle_ms=MS)
    except ValueError as exc:
        assert str(exc) == 'numeric_out_of_range'
        assert exc.__cause__ is None
        return
    reference = fn('BTCUSDT', bs, ps, REAL_RISK, candle_ms=MS)
    assert actual and len(actual) == len(reference)
    # Compare in exact rational arithmetic: no ambient exponent or rounding effects.
    factor = F(D(f'1E{exponent}'))
    for got, want in zip(actual, reference):
        assert (got.side, got.signal_time_ms) == (want.side, want.signal_time_ms)
        for field in ('entry_price', 'stop_price', 'target_price'):
            assert F(getattr(got, field)) == F(getattr(want, field)) * factor


@pytest.mark.parametrize('which', ['overflow', 'underflow'])
def test_common_numeric_range(monkeypatch, which):
    av = D('1E+999999') if which == 'overflow' else D('1E-1000100')
    patch_atr(monkeypatch, [av])
    error('numeric_out_of_range', build, bars(1), [1], C.RiskSpec(1, D('9.9'), D(2), 0))


# Purity checks use the actual module location; usable from /tmp as well as repo root.
ALLOWED = {
    '__future__': {'annotations'}, 'collections.abc': {'Sequence'}, 'dataclasses': {'dataclass'},
    'decimal': {'Decimal', 'localcontext'}, 'typing': {'Optional'},
    'backend.v3.detectors.common': {'RiskSpec', 'build_candidates', 'check_candle_ms', 'check_risk', 'check_symbol'},
    'backend.v3.learning.opportunity': {'Candidate'},
}
FEATURE_NAMES = {C: {'Bar', '_CTX', 'atr'}, B: {'Bar', 'check_bars', 'donchian', 'ema'},
                 R: {'Bar', 'bollinger', 'check_bars', 'macd'}, T: {'Bar', 'adx', 'check_bars', 'ema'}}


@pytest.mark.parametrize('mod', [C, B, R, T])
def test_purity(mod):
    tree = ast.parse(Path(mod.__file__).read_text())
    used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
    features = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert mod is C and len(node.names) == 1 and node.names[0].name == 're'
            assert node.names[0].asname is None and 're' in used
        if isinstance(node, ast.ImportFrom):
            permitted = FEATURE_NAMES[mod] if node.module == 'backend.v3.features.indicators' else ALLOWED.get(node.module, set())
            for alias in node.names:
                assert alias.name in permitted and alias.asname is None
                assert alias.name == 'annotations' or alias.name in used
                if node.module == 'backend.v3.features.indicators':
                    features.add(alias.name)
        if isinstance(node, ast.Constant):
            assert not isinstance(node.value, float)
        if isinstance(node, ast.Name):
            assert node.id not in {'float', 'open', 'eval', 'exec', '__import__', 'print'}
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert not node.args.defaults and all(v is None for v in node.args.kw_defaults)
    assert features == FEATURE_NAMES[mod]


def test_init_docstring_only():
    tree = ast.parse(Path(C.__file__).with_name('__init__.py').read_text())
    assert len(tree.body) == 1 and isinstance(tree.body[0], ast.Expr) and isinstance(tree.body[0].value, ast.Constant)
    assert isinstance(tree.body[0].value.value, str)


# Measure detector work with dense feature stubs; rare runs exercise real indicators too.
@pytest.mark.parametrize('index', range(4))
@pytest.mark.parametrize('dense', [False, True])
def test_speed(monkeypatch, index, dense):
    durations = []
    for n in (15000, 60000):
        bs = bars(n)
        sides = [1 if i % 2 else -1 for i in range(n)]
        if index == 3:
            patch_atr(monkeypatch, [D(2)] * n)
            call = lambda: build(bs, sides if dense else [0] * n, REAL_RISK)
        else:
            mod, fn, ps, _ = CASES[index]
            if dense:
                data, _ = feature_stubs(monkeypatch, mod, n)
                if mod is B:
                    data['high'] = [D(99) if i % 2 == 0 else D(102) for i in range(n)]
                    data['low'] = [D(98) if i % 2 == 0 else D(101) for i in range(n)]
                if mod is R:
                    data['pb'] = [D('.1') if i % 2 else D('.9') for i in range(n)]
                    data['hist'] = [D(1) if i % 2 else D(-1) for i in range(n)]
                    data['line'] = [-h for h in data['hist']]
                if mod is T:
                    data['ef'] = [D(99) if i % 2 else D(101) for i in range(n)]
            call = lambda: fn('BTCUSDT', bs, ps, REAL_RISK, candle_ms=MS)
        # Repetition reduces scheduler noise; data preparation is excluded at both sizes.
        timings = []
        for _ in range(2):
            start = time.perf_counter()
            out = call()
            timings.append(time.perf_counter() - start)
        elapsed = min(timings)
        assert len(out) >= n - 1 if dense else len(out) == 0
        assert elapsed < 15
        durations.append(elapsed)
    ratio = durations[1] / durations[0]
    print(f'SPEED index={index} dense={dense} n15000={durations[0]:.6f} n60000={durations[1]:.6f} ratio={ratio:.6f}')
    # Il rapporto fra tempi NON e' asserito (instabile sulle macchine lente, tempi di pochi ms): la linearita'
    # e' provata in modo deterministico da test_work_is_linear_not_quadratic (conteggio delle letture).


class CountList(list):
    """Lista che conta quante volte i suoi elementi vengono letti (indice, fetta, iterazione)."""
    reads = 0

    def __getitem__(self, key):
        CountList.reads += 1
        return list.__getitem__(self, key)

    def __iter__(self):
        for item in list.__iter__(self):
            CountList.reads += 1
            yield item


@pytest.mark.parametrize('index', range(4))
@pytest.mark.parametrize('dense', [False, True])
def test_work_is_linear_not_quadratic(monkeypatch, index, dense):
    # Prova DETERMINISTICA (nessun orologio): letture di barre e lati a n e a 2n. Lineare -> rapporto ~2;
    # una scansione per segnale (quadratica) -> ~4. Soglia 2.5.
    reads = {}
    for n in (2000, 4000):
        bs = CountList(bars(n))
        sides = CountList([1 if i % 2 else -1 for i in range(n)])
        if index == 3:
            patch_atr(monkeypatch, [D(2)] * n)
            call = lambda: build(bs, sides if dense else CountList([0] * n), REAL_RISK)
        else:
            mod, fn, ps, _ = CASES[index]
            if dense:
                data, _ = feature_stubs(monkeypatch, mod, n)
                if mod is B:
                    data['high'] = [D(99) if i % 2 == 0 else D(102) for i in range(n)]
                    data['low'] = [D(98) if i % 2 == 0 else D(101) for i in range(n)]
                if mod is R:
                    data['pb'] = [D('.1') if i % 2 else D('.9') for i in range(n)]
                    data['hist'] = [D(1) if i % 2 else D(-1) for i in range(n)]
                    data['line'] = [-h for h in data['hist']]
                if mod is T:
                    data['ef'] = [D(99) if i % 2 else D(101) for i in range(n)]
            call = lambda: fn('BTCUSDT', bs, ps, REAL_RISK, candle_ms=MS)
        CountList.reads = 0
        out = call()
        reads[n] = CountList.reads
        assert len(out) >= n - 1 if dense else len(out) == 0
        assert reads[n] > 0
    assert reads[4000] / reads[2000] < 2.5, reads


@pytest.mark.parametrize('value', [RISK, BP, RP, TP])
def test_dataclass_frozen_required(value):
    fields = dataclasses.fields(value)
    assert all(f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING for f in fields)
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(value, fields[0].name, 999)


class IntSubclass(int):
    pass


@pytest.mark.parametrize('case', CASES, ids=['S07', 'S05', 'S02'])
def test_int_subclasses_in_params(case):
    _, fn, ps, _ = case
    for field in dataclasses.fields(ps):
        value = getattr(ps, field.name)
        if type(value) is int:
            bad = dataclasses.replace(ps, **{field.name: IntSubclass(value)})
            error('invalid_params', fn, 'BTCUSDT', bars(2), bad, RISK, candle_ms=MS)
    if type(ps) is B.DonchianParams:
        error('invalid_params', fn, 'BTCUSDT', bars(2), B.DonchianParams(7, IntSubclass(1)), RISK, candle_ms=MS)


@pytest.mark.parametrize('field', ['atr_n', 'cooldown_bars'])
def test_int_subclasses_in_risk(field):
    error('invalid_risk', C.check_risk, dataclasses.replace(RISK, **{field: IntSubclass(getattr(RISK, field))}))


def test_int_subclass_candle_ms():
    error('invalid_candle_ms', C.check_candle_ms, IntSubclass(1))
