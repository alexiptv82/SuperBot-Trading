"""P10 contract tests: independent Fraction oracles, planted effects, no live data.

Synthetic seed fixed BEFORE experiments: 20261104. Fair random-walk fixture:
independent +/-0.1 price steps, prices > 900, one-bar gross absolute return
< 1.12 bp, so a 12 bp cost dominates. At 2400 trades even the conservative
independent-step SE bound 1.12/sqrt(2400) < 0.023 bp is far below the cost.
No synthetic result is a market claim.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import itertools
import json
import random
import time
from dataclasses import asdict, replace
from decimal import Decimal, localcontext
from fractions import Fraction
from pathlib import Path

import pytest

from backend.v3.lab import adapter, controls, evaluate, protocol, run, verdict
from backend.v3.detectors.common import RiskSpec, build_candidates
from backend.v3.features.indicators import Bar
from backend.v3.learning.opportunity import Candidate, Candle, HorizonLabel, OpportunityLabel, label_candidates
from backend.v3.learning.expectancy import cell_stats
from backend.v3.learning.walkforward import make_folds, walk_forward
from backend.v3.outcomes import TradeOutcome

D = Decimal
MS = 900000
DAY = 86400000
ROOT = Path(protocol.__file__).resolve().parents[3]
JSON = Path(protocol.__file__).with_name('preregistration.json')
SHA = '7e561c2131d33a4214ba973da2163e53a232fe2e6ea115b95443c109d9ab550e'


def raw():
    return json.loads(JSON.read_text())


def small():
    r = raw()
    r['evaluation']['warmup_days'] = 0
    for k in ('wf', 'whole'):
        r['evaluation'][k]['n_boot'] = 200
    r['controls']['n_shifts'] = 2
    return protocol.load_protocol(r)


def q(f, places=4):
    """Fraction arithmetic first, Decimal conversion only for final rounding."""
    f = Fraction(f)
    with localcontext() as ctx:
        ctx.prec = 100
        out = (D(f.numerator) / D(f.denominator)).quantize(D('1').scaleb(-places))
        return abs(out) if not out else out


def test_protocol_all_values_and_hash():
    assert hashlib.sha256(JSON.read_bytes()).hexdigest() == SHA
    p = protocol.load_protocol(raw())
    assert (p.protocol_version, p.run_id, p.candle_ms, p.symbols, p.min_segment_bars, p.unit_notional) == (1, 'lab-p10-2026-11', 900000, ('BTCUSDT', 'ETHUSDT'), 400, D('1000'))
    assert asdict(p.risk) == dict(atr_n=14, stop_atr_mult=D('1.5'), target_r_mult=D('2'), cooldown_bars=3)
    assert [(s.id, s.kind, asdict(s.params)) for s in p.strategies] == [
        ('S07', 'donchian', dict(n=20, trend_ema_n=50)),
        ('S05', 'bb_macd', dict(bb_n=20, bb_k=D('2'), pb_low=D('0.2'), pb_high=D('0.8'), macd_fast=12, macd_slow=26, macd_signal=9)),
        ('S02', 'ema_cross_adx', dict(fast_n=9, slow_n=21, adx_n=14, adx_min=D('25')))]
    assert asdict(p.regime) == dict(atr_n=14, pct_window=2880, adx_n=14, params=dict(shock_tr_mult=D('3'), expansion_pct_min=D('80'), adx_trend_min=D('25'), adx_range_max=D('20')))
    assert asdict(p.labeling) == dict(primary_horizon_ms=14400000, primary_cost_bp=D('12'), stress_costs_bp=(D('0'), D('20')), primary_policy='stop_first', bound_policy='target_first')
    assert asdict(p.evaluation) == dict(warmup_days=30, train_days=120, test_days=30, step_days=30, embargo_days=1, expanding=False,
                                       wf=dict(min_trades=30, min_days=10, confidence=D('0.9'), n_boot=2000, seed=20261104),
                                       whole=dict(min_trades=30, min_days=10, confidence=D('0.99'), n_boot=5000, seed=20261104))
    assert asdict(p.controls) == dict(n_shifts=40, min_shift_days=30, seed=20261104)
    assert asdict(p.verdict) == dict(oos_over_train_min=D('0.5'), min_oos_trades=100, min_folds_with_selection=3, control_percentile_min=D('95'))


def leaves(obj, path=()):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from leaves(v, path + (k,))
    elif isinstance(obj, list):
        for k, v in enumerate(obj):
            yield from leaves(v, path + (k,))
    else:
        yield path, obj


def at(obj, path):
    for k in path:
        obj = obj[k]
    return obj


INT_PATHS = [p for p, v in leaves(raw()) if type(v) is int]
DEC_PATHS = [p for p, v in leaves(raw()) if isinstance(v, str) and v.replace('.', '').isdigit()]
DICT_PATHS = [(), ('risk',), ('regime',), ('regime', 'params'), ('labeling',), ('evaluation',), ('evaluation', 'wf'), ('evaluation', 'whole'), ('controls',), ('verdict',)] + [('strategies', i) for i in range(3)] + [('strategies', i, 'params') for i in range(3)]


@pytest.mark.parametrize('path', INT_PATHS)
@pytest.mark.parametrize('bad', [True, 1.0, None, '1'])
def test_protocol_each_integer_type(path, bad):
    r = raw()
    at(r, path[:-1])[path[-1]] = bad
    if path == ('strategies', 0, 'params', 'trend_ema_n') and bad is None:
        assert protocol.load_protocol(r).strategies[0].params.trend_ema_n is None
        return
    with pytest.raises(ValueError, match='^invalid_protocol$'):
        protocol.load_protocol(r)


@pytest.mark.parametrize('path', DEC_PATHS)
@pytest.mark.parametrize('bad', ['NaN', 'Infinity', '1e2', ' 1', 1.0, True, None])
def test_protocol_each_decimal_type(path, bad):
    r = raw()
    at(r, path[:-1])[path[-1]] = bad
    with pytest.raises(ValueError, match='^invalid_protocol$'):
        protocol.load_protocol(r)


@pytest.mark.parametrize('path', DICT_PATHS)
@pytest.mark.parametrize('mode', ['missing', 'extra'])
def test_protocol_exact_keys(path, mode):
    r = raw()
    node = at(r, path)
    if mode == 'missing':
        node.pop(next(iter(node)))
    else:
        node['extra'] = 1
    with pytest.raises(ValueError, match='^invalid_protocol$'):
        protocol.load_protocol(r)


BAD_VALUES = [
    (('protocol_version',), 2), (('candle_ms',), 0), (('run_id',), ''), (('run_id',), 'a\n'), (('run_id',), 'a'*129),
    (('symbols',), []), (('symbols',), ['BTCUSDT', 'BTCUSDT']), (('symbols',), ['BTCUSDT', '!']),
    (('min_segment_bars',), 0), (('unit_notional',), '0'), (('risk', 'atr_n'), 0), (('risk', 'stop_atr_mult'), '0'),
    (('risk', 'target_r_mult'), '0'), (('risk', 'cooldown_bars'), -1), (('strategies',), []),
    (('strategies', 0, 'id'), 'S05'), (('strategies', 1, 'kind'), 'donchian'), (('strategies', 2, 'kind'), 'bb_macd'),
    (('strategies', 0, 'params', 'n'), 0), (('strategies', 0, 'params', 'trend_ema_n'), 0),
    (('strategies', 1, 'params', 'bb_n'), 1), (('strategies', 1, 'params', 'bb_k'), '0'),
    (('strategies', 1, 'params', 'pb_low'), '0.8'), (('strategies', 1, 'params', 'macd_fast'), 26),
    (('strategies', 2, 'params', 'fast_n'), 21), (('strategies', 2, 'params', 'adx_min'), '-1'),
    (('regime', 'atr_n'), 0), (('regime', 'pct_window'), 0), (('regime', 'adx_n'), 0),
    (('regime', 'params', 'shock_tr_mult'), '0'), (('regime', 'params', 'expansion_pct_min'), '101'),
    (('regime', 'params', 'adx_range_max'), '25'), (('labeling', 'primary_horizon_ms'), 1),
    (('labeling', 'primary_cost_bp'), '-1'), (('labeling', 'stress_costs_bp'), []),
    (('labeling', 'stress_costs_bp'), ['0','0']), (('labeling', 'stress_costs_bp'), ['0','12']), (('labeling', 'stress_costs_bp'), ['-1']),
    (('labeling', 'primary_policy'), 'none'), (('labeling', 'bound_policy'), 'stop_first'),
    (('evaluation', 'warmup_days'), -1), (('evaluation', 'train_days'), 0), (('evaluation', 'test_days'), 0),
    (('evaluation', 'step_days'), 29), (('evaluation', 'embargo_days'), -1), (('evaluation', 'expanding'), 1),
    (('evaluation', 'wf', 'min_trades'), 0), (('evaluation', 'wf', 'min_days'), 1), (('evaluation', 'wf', 'confidence'), '0'),
    (('evaluation', 'whole', 'confidence'), '1'), (('evaluation', 'wf', 'n_boot'), 199),
    (('controls', 'n_shifts'), 0), (('controls', 'min_shift_days'), 0),
    (('verdict', 'oos_over_train_min'), '0'), (('verdict', 'oos_over_train_min'), '1.01'),
    (('verdict', 'min_oos_trades'), 0), (('verdict', 'min_folds_with_selection'), 0),
    (('verdict', 'control_percentile_min'), '0'), (('verdict', 'control_percentile_min'), '100.01')]


@pytest.mark.parametrize('path,value', BAD_VALUES)
def test_protocol_boundaries(path, value):
    r = raw()
    at(r, path[:-1])[path[-1]] = value
    with pytest.raises(ValueError, match='^invalid_protocol$'):
        protocol.load_protocol(r)


def test_protocol_valid_boundaries():
    r = raw()
    r['strategies'][0]['params']['trend_ema_n'] = None
    r['verdict'].update(oos_over_train_min='1', control_percentile_min='100', min_oos_trades=1, min_folds_with_selection=1)
    r['evaluation'].update(warmup_days=0, embargo_days=0)
    r['risk']['cooldown_bars'] = 0
    assert protocol.load_protocol(r).strategies[0].params.trend_ema_n is None


def candidate(side=1, signal=MS, entry='100', distance='1', target_distance='2', cid='x'):
    e, d, t = D(entry), D(distance), D(target_distance)
    return Candidate(cid, 'BTCUSDT', side, signal, e, e-side*d, e+side*t)


def adapt(cs, labels, **kw):
    args = dict(strategy_id='S07', run_id='test', horizon_ms=MS, candle_ms=MS, cost_bp=D('12'),
                unit_notional=D('1000'), regimes={c.signal_time_ms-MS: 'RANGE' for c in cs})
    args.update(kw)
    return adapter.outcomes_from_labels(cs, labels, **args)


def lab(c, barrier='target', ambiguous=False, gross='200', net='188', exit_price='102', touch=MS):
    return OpportunityLabel(c.candidate_id, c.symbol, c.side,
                            (HorizonLabel(MS, 'complete', barrier, ambiguous, touch, D(exit_price), D(gross), D(net)),))


@pytest.mark.parametrize('side', [-1,1])
@pytest.mark.parametrize('barrier', ['target','stop','timeout'])
@pytest.mark.parametrize('unit', ['1000','777.7777'])
@pytest.mark.parametrize('signal', [MS, MS+1])
def test_adapter_every_field_fraction(side, barrier, unit, signal):
    c = candidate(side, signal=signal, entry='103', distance='0.1234567', target_distance='0.2469134')
    start = ((signal+MS-1)//MS)*MS
    ex = c.target_price if barrier == 'target' else c.stop_price if barrier == 'stop' else D('103.01')
    g = Fraction(side) * (Fraction(ex)-Fraction(c.entry_price))/Fraction(c.entry_price)*10000
    gb, nb = q(g), q(g-12)
    h = lab(c, barrier, gross=str(gb), net=str(nb), exit_price=str(ex), touch=start if barrier != 'timeout' else None)
    out = adapt([c], [h], unit_notional=D(unit))[0][0]
    close = start+MS
    dist = abs(Fraction(c.entry_price)-Fraction(c.stop_price))/Fraction(c.entry_price)*10000
    gross = q(Fraction(unit)*Fraction(gb)/10000,8)
    fee = q(Fraction(unit)*12/10000,8)
    expected = dict(schema_version=1, position_id='x', portfolio_id='lab', run_id='test', symbol='BTCUSDT', side=side,
                    originating_ai='S07', leverage=1, opened_at_ms=signal, closed_at_ms=close, hold_ms=close-signal,
                    entry_price=c.entry_price, exit_price=ex, quantity=q(Fraction(unit)/103,8), notional_entry=D(unit),
                    margin_used=D(unit), gross_pnl=gross, fees=fee, realized_pnl=gross-fee, gross_bp=gb, costs_bp=D('12'),
                    net_bp=nb, stop_distance_bp=q(dist), r_multiple=q(Fraction(nb)/dist),
                    exit_reason='stop' if barrier=='stop' else 'brain_close', loss_exceeds_margin=False,
                    decision_event_id='x', link_status='linked', decision_regime='RANGE')
    assert asdict(out) == expected


def test_adapter_quantized_components_not_net():
    c = candidate()
    h = lab(c, gross='0.0001', net='0', exit_price='100')
    o = adapt([c],[h], cost_bp=D('0.00005'), unit_notional=D('777.7777'))[0][0]
    assert o.realized_pnl == q(Fraction('777.7777')*Fraction('0.0001')/10000,8)-q(Fraction('777.7777')*Fraction('0.00005')/10000,8)
    assert o.realized_pnl != q(Fraction('777.7777')*Fraction(h.horizons[0].net_bp)/10000,8)


@pytest.mark.parametrize('gross,expected', [('-10000',False),('-10001',True)])
def test_adapter_loss_boundary(gross, expected):
    c=candidate()
    assert adapt([c],[lab(c,gross=gross,net=gross)],cost_bp=D('0'))[0][0].loss_exceeds_margin is expected


@pytest.mark.parametrize('policy,barrier', [('stop_first','stop'),('target_first','target')])
def test_adapter_ambiguous_integration(policy, barrier):
    c=candidate()
    candles=[Candle(MS,D('100'),D('103'),D('98'),D('100'))]
    ls=label_candidates([c],{'BTCUSDT':candles},candle_ms=MS,horizons_ms=[MS],cost_bp=D('12'),ambiguous_policy=policy)
    assert ls[0].horizons[0].ambiguous and ls[0].horizons[0].barrier==barrier
    assert adapt([c],ls)[0][0].net_bp == (D('-112') if barrier=='stop' else D('188'))


def test_incomplete_no_regime_and_order():
    cs=[candidate(cid=str(i),signal=MS*(i+1)) for i in range(3)]
    ls=[lab(c,touch=c.signal_time_ms) for c in cs]
    ls[1]=replace(ls[1],horizons=(HorizonLabel(MS,'incomplete',None,False,None,None,None,None),))
    os,n=adapt(cs,ls,regimes={0:'A',2*MS:'B'})
    assert n==1 and [o.position_id for o in os]==['0','2'] and [o.decision_regime for o in os]==['A','B']


ADAPTER_BAD=[('candle_ms',True,'invalid_candle_ms'),('horizon_ms',True,'invalid_horizon'),('cost_bp',1.0,'invalid_cost_bp'),
             ('unit_notional',1.0,'invalid_unit_notional'),('strategy_id','S1','invalid_strategy_id'),('run_id','!','invalid_run_id'),
             ('regimes',{},'missing_regime')]


@pytest.mark.parametrize('key,value,code', ADAPTER_BAD)
def test_adapter_validation(key,value,code):
    c=candidate()
    with pytest.raises(ValueError,match='^'+code+'$'):
        adapt([c],[lab(c)],**{key:value})


@pytest.mark.parametrize('i',range(5))
def test_adapter_error_order_adjacent(i):
    a,b=ADAPTER_BAD[i:i+2]
    c=candidate()
    with pytest.raises(ValueError,match='^'+a[2]+'$'):
        adapt([c],[lab(c)],**{a[0]:a[1],b[0]:b[1]})


@pytest.mark.parametrize('mode',['generator','length','id','symbol','side','horizon_missing','horizon_duplicate','none'])
def test_adapter_later_element_validation(mode):
    cs=[candidate(cid='a'),candidate(cid='b')]; ls=[lab(c) for c in cs]
    code='invalid_labels'
    if mode=='generator':
        args=dict(strategy_id='S07',run_id='test',horizon_ms=MS,candle_ms=MS,cost_bp=D('12'),unit_notional=D('1000'),regimes={0:'R'})
        with pytest.raises(ValueError,match='^invalid_labels$'):
            adapter.outcomes_from_labels(iter(cs),ls,**args)
        return
    if mode=='length': ls.pop()
    elif mode=='id': ls[1]=replace(ls[1],candidate_id='c')
    elif mode=='symbol': ls[1]=replace(ls[1],symbol='ETHUSDT')
    elif mode=='side': ls[1]=replace(ls[1],side=-1)
    elif mode=='none': ls[1]=None
    elif mode=='horizon_missing': ls[1]=replace(ls[1],horizons=()); code='invalid_horizon_in_labels'
    elif mode=='horizon_duplicate': ls[1]=replace(ls[1],horizons=ls[1].horizons*2); code='invalid_horizon_in_labels'
    with pytest.raises(ValueError,match='^'+code+'$'): adapt(cs,ls)


def good_verdict():
    return dict(whole_status='positive',mean_net_bp=D('10'),ci_low=D('1'),ci_high=D('20'),n_folds_with_selection=3,oos_n=100,
                oos_mean_net_bp=D('5'),is_mean_net_bp=D('10'),inverted_mean_net_bp=D('0'),shift_rank_pct=D('95'),
                oos_over_train_min=D('0.5'),min_oos_trades=100,min_folds_with_selection=3,control_percentile_min=D('95'))


@pytest.mark.parametrize('truth',list(itertools.product([False,True],repeat=4)))
def test_verdict_full_truth_table(truth):
    kw=good_verdict()
    for ok,k,v in zip(truth,['ci_low','oos_n','inverted_mean_net_bp','shift_rank_pct'],[D('0'),99,D('1'),D('94.9999')]):
        if not ok: kw[k]=v
    failed=tuple('E'+str(i+1) for i,ok in enumerate(truth) if not ok)
    assert verdict.classify(**kw)==(('EVIDENZA_POSITIVA',()) if all(truth) else ('POSITIVO_INCONCLUDENTE',failed))


@pytest.mark.parametrize('key,value,expected',[
    ('whole_status','insufficient','DATI_INSUFFICIENTI'),('ci_high',D('-1'),'NEGATIVO'),('ci_high',D('0'),'EVIDENZA_POSITIVA'),
    ('mean_net_bp',D('0'),'NULLO'),('mean_net_bp',D('-1'),'NULLO'),('ci_low',D('0'),'POSITIVO_INCONCLUDENTE'),
    ('oos_n',99,'POSITIVO_INCONCLUDENTE'),('n_folds_with_selection',2,'POSITIVO_INCONCLUDENTE'),
    ('oos_mean_net_bp',D('4.999999'),'POSITIVO_INCONCLUDENTE'),('oos_mean_net_bp',D('0'),'POSITIVO_INCONCLUDENTE'),
    ('inverted_mean_net_bp',D('10'),'POSITIVO_INCONCLUDENTE'),('shift_rank_pct',D('94.999999'),'POSITIVO_INCONCLUDENTE')])
def test_verdict_boundaries(key,value,expected):
    kw=good_verdict(); kw[key]=value
    assert verdict.classify(**kw)[0]==expected


@pytest.mark.parametrize('key',['mean_net_bp','ci_low','ci_high','oos_mean_net_bp','is_mean_net_bp','inverted_mean_net_bp','shift_rank_pct'])
def test_verdict_none(key):
    kw=good_verdict(); kw[key]=None
    expected='DATI_INSUFFICIENTI' if key in ('mean_net_bp','ci_low','ci_high') else 'POSITIVO_INCONCLUDENTE'
    assert verdict.classify(**kw)[0]==expected


@pytest.mark.parametrize('key',list(good_verdict()))
def test_verdict_types(key):
    kw=good_verdict(); kw[key]=True
    code='invalid_status' if key=='whole_status' else 'invalid_threshold' if key in ('oos_over_train_min','control_percentile_min') else 'invalid_value'
    with pytest.raises(ValueError,match='^'+code+'$'): verdict.classify(**kw)


def test_verdict_precedence_and_local_context():
    kw=good_verdict(); kw.update(whole_status='insufficient',ci_high=D('-1'))
    assert verdict.classify(**kw)==('DATI_INSUFFICIENTI',())
    kw=good_verdict(); kw.update(ci_high=D('-1'),oos_n=0)
    assert verdict.classify(**kw)==('NEGATIVO',())
    kw=good_verdict(); kw.update(oos_over_train_min=D('0.500000001'),oos_mean_net_bp=D('5'))
    with localcontext() as ctx:
        ctx.prec=2
        assert verdict.classify(**kw)[1]==('E2',)


def bars(n, start=0):
    return [Bar(start+i*MS,D('100'),D('101'),D('99'),D('100'),D('1')) for i in range(n)]


def test_invert_fraction_and_skips():
    cs=[candidate(side=-1,cid='s'),candidate(cid='l'),candidate(entry='1',distance='0.5',target_distance='1.5',cid='tiny'),candidate(cid='a'*126)]
    snapshot=copy.deepcopy(cs)
    out,n=controls.invert_candidates(cs)
    assert n==2 and cs==snapshot
    for c,inv in zip(cs,out):
        assert inv==Candidate('INV:'+c.candidate_id,c.symbol,-c.side,c.signal_time_ms,c.entry_price,
                              q(2*Fraction(c.entry_price)-Fraction(c.stop_price),8),q(2*Fraction(c.entry_price)-Fraction(c.target_price),8))
    assert len(label_candidates(out,{'BTCUSDT':[Candle(MS,D('100'),D('103'),D('97'),D('100'))]},candle_ms=MS,horizons_ms=[MS],cost_bp=D('12'),ambiguous_policy='stop_first'))==2


@pytest.mark.parametrize('bad',[None,[None],iter([])])
def test_invert_bad(bad):
    with pytest.raises(ValueError,match='^invalid_candidates$'): controls.invert_candidates(bad)


@pytest.mark.parametrize('k',[0,1,4,5,9])
def test_shifted_sides_oracle(k):
    sides=[1,0,-1,0,1]; expected=[0]*5
    for i,v in enumerate(sides): expected[(i+k)%5]=v
    assert controls.shifted_sides(sides,k)==expected
    assert sides==[1,0,-1,0,1]


@pytest.mark.parametrize('cs',[[candidate(signal=MS+1)],[candidate(signal=6*MS)],[candidate(cid='a'),candidate(cid='b')]])
def test_sides_invalid(cs):
    with pytest.raises(ValueError,match='^invalid_candidates$'): controls.sides_from_candidates(bars(5),cs,candle_ms=MS)


def test_shifted_sets_oracle_boundaries_determinism():
    segs=[bars(10),bars(9,20*MS),bars(16,40*MS)]
    cs=[candidate(signal=3*MS,cid='a'),candidate(side=-1,signal=48*MS,cid='b')]
    risk=RiskSpec(1,D('1'),D('2'),0)
    kwargs=dict(strategy_id='S07',risk=risk,candle_ms=MS,n_shifts=4,min_shift_bars=5,seed=20261104)
    before=copy.deepcopy((segs,cs))
    got=controls.shifted_candidate_sets('BTCUSDT',segs,cs,**kwargs)
    rng=random.Random('20261104|S07|BTCUSDT'); expected=[]
    for _ in range(4):
        combined=[]
        for s in (segs[0],segs[2]):
            group=[c for c in cs if s[0].open_time_ms<=c.signal_time_ms-MS<=s[-1].open_time_ms]
            sides=controls.sides_from_candidates(s,group,candle_ms=MS)
            k=rng.randrange(5,len(s)-5+1)
            assert 5<=k<=len(s)-5
            rotated=[sides[(i-k)%len(s)] for i in range(len(s))]
            combined.extend(build_candidates('BTCUSDT',s,rotated,strategy_id='S07',risk=risk,candle_ms=MS))
        expected.append(tuple(sorted(combined,key=lambda c:c.signal_time_ms)))
    assert got==tuple(expected)==controls.shifted_candidate_sets('BTCUSDT',segs,cs,**kwargs)
    assert all(len(x)==2 for x in got)
    assert got!=controls.shifted_candidate_sets('BTCUSDT',segs,cs,**dict(kwargs,seed=20261105))
    assert (segs,cs)==before
    assert controls.shifted_candidate_sets('BTCUSDT',[segs[1]],[],**kwargs)==((),)*4


@pytest.mark.parametrize('k,v',[('min_shift_bars',0),('min_shift_bars',True),('n_shifts',0),('n_shifts',True),('seed',True)])
def test_shift_arguments(k,v):
    kw=dict(strategy_id='S07',risk=RiskSpec(1,D('1'),D('2'),0),candle_ms=MS,n_shifts=2,min_shift_bars=1,seed=1);kw[k]=v
    with pytest.raises(ValueError,match='^invalid_shift$'): controls.shifted_candidate_sets('BTCUSDT',[],[],**kw)


def manual_experiment():
    p=small()
    p=replace(p,labeling=replace(p.labeling,primary_horizon_ms=MS),evaluation=replace(p.evaluation,warmup_days=0))
    # 60 bars straddle evaluation start at one day. Index 0 is excluded.
    cs=[]; candles=[]
    gross=[200,-100,25,-100,200,200,-100,25]
    # first candidate is pre-warmup; others post-warmup, mixed directions.
    signals=[DAY-MS]+[DAY+i*3*MS for i in range(7)]
    by_time={b.open_time_ms:Candle(b.open_time_ms,b.open,D('100.1'),D('99.9'),b.close) for b in bars(60,DAY-2*MS)}
    for i,(t,g) in enumerate(zip(signals,gross)):
        side=1 if i%2==0 else -1
        c=candidate(side,signal=t,cid=str(i));cs.append(c)
        if i==3: high,low,close=D('103'),D('97'),D('100')
        elif g==200: high,low,close=(D('102'),D('100'),D('102')) if side==1 else (D('100'),D('98'),D('98'))
        elif g==-100: high,low,close=(D('100'),D('99'),D('99')) if side==1 else (D('101'),D('100'),D('101'))
        else: high,low,close=D('100.3'),D('99.7'),D('100')+side*D('0.25')
        by_time[t]=Candle(t,D('100')+side*D('0.1') if g==25 else D('100'),high,low,close)
    candles=tuple(by_time[t] for t in sorted(by_time))
    regimes={c.signal_time_ms-MS:'RANGE' for c in cs}
    return p,cs,candles,regimes,gross


def test_evaluation_manual_fraction_oracle_calls(monkeypatch):
    p,cs,candles,regimes,gross=manual_experiment()
    original=copy.deepcopy((p,cs,candles,regimes))
    calls=[]; real=evaluate.label_candidates
    def spy(*a,**kw): calls.append(kw);return real(*a,**kw)
    monkeypatch.setattr(evaluate,'label_candidates',spy)
    result=evaluate.evaluate_candidates(p,'S07','BTCUSDT',cs,candles,regimes,[(),()])
    assert len(calls)==1+len(p.labeling.stress_costs_bp)+1+1+2
    net=[Fraction(g-12) for g in gross[1:]]
    assert result['whole']['n']==7
    assert result['whole']['mean_net_bp']==str(q(sum(net)/7))
    assert result['whole']['mean_r']==str(q(sum(net)/700))
    total=peak=dd=Fraction(0)
    for x in net:
        total+=x/100;peak=max(peak,total);dd=max(dd,peak-total)
    assert result['max_dd_r']==str(q(dd))
    assert result['barriers']==dict(target=3,stop=3,timeout=2)
    assert result['ambiguous']==dict(n=1,share=str(q(Fraction(1,8))))
    assert result['entry_gap']==dict(n=7,mean_adverse_gap_bp=str(q(Fraction(20,7))))
    assert result['by_side']['1']['mean_net_bp']==str(q(Fraction(89,3)))
    assert result['by_side']['-1']['mean_net_bp']==str(q(Fraction(-23,4)))
    assert result['stress']['0']['mean_net_bp']==str(q(Fraction(sum(gross[1:]),7)))
    assert result['stress']['20']['mean_net_bp']==str(q(Fraction(sum(gross[1:]),7)-20))
    # Inverse times out at +100 on original stop; original targets hit inverse stop (-100).
    # Timeout reverses 25; ambiguous stop_first hits inverse stop (-100).
    inverse_gross=[100,-25,-100,-100,-100,100,-25]
    assert result['inverted']['cell']['mean_net_bp']==str(q(Fraction(sum(inverse_gross),7)-12))
    assert result['bound']['cell']['mean_net_bp']==str(q((sum(net)+300)/7))
    assert result['shift_control']['n_used']==0 and result['shift_control']['rank_pct'] is None
    assert result['walk_forward']['status']=='no_folds'
    assert evaluate.evaluation_window(p,candles)==(DAY,DAY)
    assert (p,cs,candles,regimes)==original
    assert result==evaluate.evaluate_candidates(p,'S07','BTCUSDT',cs,candles,regimes,[(),()])
    json.dumps(result)


def planted(mode):
    """320 days, 8 independent 12-bar blocks/day, seed preregistered above.

    All excursions return to 100 within a block. Signals at block start know
    the next excursion only in the planted cases. Null signals occur at a
    flat point in the block and time out. Fair random-walk case samples
    independent +/-1 steps (per block); no seed reselection.
    """
    p=small();p=replace(p,labeling=replace(p.labeling,primary_horizon_ms=MS))
    rng=random.Random(20261104)
    n=320*96
    if mode == 'fair':
        # A genuine additive random walk, independent steps and independent sides.
        # Price remains > 900 here; a one-step gross move is < 1.12 bp, so
        # the 12 bp cost dominates without selecting a favourable seed.
        price=D('1000'); bs=[]
        for i in range(n):
            close=price+D(rng.choice([-1,1]))/10
            bs.append(Candle(i*MS,price,max(price,close),min(price,close),close));price=close
        assert min(b.low for b in bs)>900
        def random_entries(indices,prefix):
            out=[]
            for i in indices:
                e=bs[i].open;side=rng.choice([-1,1])
                out.append(Candidate(f'{prefix}{i}','BTCUSDT',side,i*MS,e,e-side*e/D('100'),e+side*e/D('100')))
            return tuple(out)
        cs=random_entries(range(1,n-12,12),'c')
        nulls=[random_entries(sorted(rng.sample(range(1,n-1),len(cs))),f'n{j}') for j in range(2)]
        return p,cs,tuple(bs),{b.open_time_ms:'RANGE' for b in bs},nulls
    bs=[Candle(i*MS,D('100'),D('100'),D('100'),D('100')) for i in range(n)]
    cs=[];null=[]
    for j,i in enumerate(range(1,n-12,12)):
        if mode=='fair': step=rng.choice([-1,1])
        elif mode=='contrary': step=-1
        elif mode=='concentrated': step=1 if i<180*96 else -1
        else: step=1
        delta=D('0.08') if mode=='cost' else D('1')
        close=D('100')+step*delta
        bs[i]=Candle(i*MS,D('100'),max(D('100'),close),min(D('100'),close),close)
        c=candidate(signal=i*MS,cid=f'c{j}',target_distance='1')
        cs.append(c)
        null.append(candidate(signal=(i+5)*MS,cid=f'n{j}',target_distance='1'))
    regimes={b.open_time_ms:'RANGE' for b in bs}
    return p,cs,tuple(bs),regimes,[tuple(null)]*2


@pytest.mark.parametrize('mode,expected',[('edge','EVIDENZA_POSITIVA'),('fair','NEGATIVO'),('contrary','NEGATIVO'),('cost','NEGATIVO'),('concentrated','POSITIVO_INCONCLUDENTE')])
def test_system_planted_verdicts(mode,expected):
    args=planted(mode)
    p,cs,candles,regimes,nulls=args
    result=evaluate.evaluate_candidates(p,'S07','BTCUSDT',cs,candles,regimes,nulls)
    assert result['counts']['in_eval']>=2400
    assert result['verdict']==expected
    if mode=='edge':
        assert D(result['whole']['mean_net_bp'])==88 and result['barriers']['target']==len(cs)
        assert result['walk_forward']['oos_n']>=100 and result['walk_forward']['n_folds_with_selection']>=3
    elif mode=='concentrated':
        assert 'E2' in result['failed'] and D(result['whole']['mean_net_bp'])>0
    else:
        assert D(result['whole']['mean_net_bp'])<0
    assert abs(D(result['stress']['0']['mean_net_bp'])-D(result['whole']['mean_net_bp'])-12)<=D('0.0002')
    assert abs(D(result['whole']['mean_net_bp'])-D(result['stress']['20']['mean_net_bp'])-8)<=D('0.0002')
    print('STRESS', mode, D(result['stress']['0']['mean_net_bp'])-D(result['whole']['mean_net_bp']), D(result['whole']['mean_net_bp'])-D(result['stress']['20']['mean_net_bp']))
    print('SYSTEM',mode,json.dumps({k:result[k] for k in ('counts','whole','verdict','failed','barriers')}))


def test_system_drift_no_information_fails_e4():
    p=small();p=replace(p,labeling=replace(p.labeling,primary_horizon_ms=MS))
    # Noisy positive percentage drift; independently sampled entry times carry no information.
    # Forty independently sampled long controls measure the common market drift.
    rng=random.Random(20261104)
    bs=[]
    with localcontext() as ctx:
        ctx.prec=60
        price=D('100')
        for i in range(320*96):
            close=price*(D('1')+D(rng.randrange(10,51))/D('10000'))
            bs.append(Candle(i*MS,price,close,price,close));price=close
        def entries(indices,prefix):
            return tuple(Candidate(f'{prefix}{i}','BTCUSDT',1,i*MS,bs[i].open,bs[i].open*D('0.99'),bs[i].open*D('1.01')) for i in indices)
        cs=entries(sorted(rng.sample(range(1,len(bs)-1),2400)),'c')
        nulls=[entries(sorted(rng.sample(range(1,len(bs)-1),2400)),f'n{j}') for j in range(40)]
    r=evaluate.evaluate_candidates(p,'S07','BTCUSDT',cs,bs,{b.open_time_ms:'TREND_UP' for b in bs},nulls)
    assert r['verdict']=='POSITIVO_INCONCLUDENTE' and 'E4' in r['failed']
    assert r['barriers']['timeout']==2400 and D(r['whole']['mean_net_bp'])>0
    assert r['shift_control']['n_used']==40 and D(r['shift_control']['rank_pct'])<95
    print('SYSTEM drift',json.dumps({k:r[k] for k in ('counts','whole','verdict','failed','barriers')}))


def test_walkforward_two_calls_keys_and_exact_rank(monkeypatch):
    p,cs,candles,regimes,nulls=planted('edge')
    real=evaluate.walk_forward; keys=[]
    def spy(outcomes,folds,**kw):
        keys.append(kw['key'](outcomes[0]));return real(outcomes,folds,**kw)
    monkeypatch.setattr(evaluate,'walk_forward',spy)
    r=evaluate.evaluate_candidates(p,'S07','BTCUSDT',cs,candles,regimes,nulls)
    assert keys==[('BTCUSDT',1),('BTCUSDT',1,'RANGE',False)]
    assert r['shift_control']['n_used']==2 and r['shift_control']['rank_pct']=='100.0000'


@pytest.mark.parametrize('indexes,lengths',[(list(range(5)),[5]),([0,1,3,4],[2,2]),([0,2,4],[1,1,1]),([0],[1]),([],[])])
def test_split(indexes,lengths):
    bs=bars(5)
    assert [len(s) for s in run.split_contiguous([bs[i] for i in indexes],MS)]==lengths


@pytest.mark.parametrize('indexes',[[1,0],[0,0]])
def test_split_nonincreasing(indexes):
    bs=bars(2)
    with pytest.raises(ValueError,match='^invalid_bars$'):run.split_contiguous([bs[i] for i in indexes],MS)


CSV_HEAD='open_time_ms,open,high,low,close,volume\n'
@pytest.mark.parametrize('body',['0,100,101,99,100,1\n','1,100,101,99,100,1\n'])
def test_csv_valid_unaligned(tmp_path,body):
    f=tmp_path/'bars.csv';f.write_text(CSV_HEAD+body)
    assert len(run.read_candles_csv(f))==1


@pytest.mark.parametrize('body',['0,100,101,99,100\n','0,100,101,99,100,1,2\n','x,100,101,99,100,1\n',
                                  '0,NaN,101,99,100,1\n','0,100,Infinity,99,100,1\n','0,100,99,99,100,1\n',
                                  '0,100,101,101,100,1\n','0,0,101,0,100,1\n','0,100,101,99,100,-1\n',
                                  '0,100,101,99,100,1\n0,100,101,99,100,1\n'])
def test_csv_invalid(tmp_path,body):
    f=tmp_path/'bars.csv';f.write_text(CSV_HEAD+body)
    with pytest.raises(ValueError,match='^invalid_candles_file$'):run.read_candles_csv(f)


def test_csv_header(tmp_path):
    f=tmp_path/'bars.csv';f.write_text('timestamp,open,high,low,close,volume\n')
    with pytest.raises(ValueError,match='^invalid_candles_file$'):run.read_candles_csv(f)


def test_runner_gap_oracle_and_report(monkeypatch):
    p=small();p=replace(p,min_segment_bars=20)
    # Real detectors, oscillating trend over two segments; one short segment discarded.
    rng=random.Random(234)
    bs=bars(220)
    for i,b in enumerate(bs):
        close=D('100')+D(i%31)+D(rng.randrange(5))
        bs[i]=replace(b,open=close,close=close,high=close+1,low=close-1)
    bs=bs[:100]+bs[110:210]+bs[215:]
    segments=[bs[:100],bs[100:200]]
    captured=[]; real=run.evaluate_candidates
    def spy(p,sid,symbol,cs,candles,regimes,nulls):
        captured.append((sid,symbol,cs,len(candles)))
        return real(p,sid,symbol,cs,candles,regimes,nulls)
    monkeypatch.setattr(run,'evaluate_candidates',spy)
    inp={s:bs for s in p.symbols};snapshot=copy.deepcopy(inp)
    result=run.run_lab(p,inp)
    detectors=[run.detect_donchian_breakout,run.detect_bollinger_macd_reversal,run.detect_ema_cross_adx]
    for i,(sid,symbol,cs,n) in enumerate(captured):
        spec=p.strategies[i//2]
        expected=tuple(c for s in segments for c in detectors[i//2](symbol,s,spec.params,p.risk,candle_ms=MS))
        assert cs==expected and n==205
    assert [(r['strategy_id'],r['symbol']) for r in result['results']]==[(s.id,sym) for s in p.strategies for sym in p.symbols]
    assert result['data']['BTCUSDT']['n_segments']==3 and result['data']['BTCUSDT']['n_kept_segments']==2
    assert result['data']['BTCUSDT']['n_missing_bars']==15
    assert 'verdict' not in result and inp==snapshot
    assert result==run.run_lab(p,inp)
    md=run.render_report_md(result)
    assert 'Limiti dichiarati' in md and md.count('DATI_INSUFFICIENTI')>=7
    with pytest.raises(ValueError,match='^missing_symbol$'):run.run_lab(p,{})


def test_main(tmp_path,capsys):
    r=raw();r['evaluation']['wf']['n_boot']=200;r['evaluation']['whole']['n_boot']=200;r['controls']['n_shifts']=1
    file=tmp_path/'p.json';file.write_text(json.dumps(r))
    for symbol in r['symbols']:
        (tmp_path/f'{symbol}_15m.csv').write_text(CSV_HEAD+'0,100,101,99,100,1\n')
    args=['--protocol',str(file),'--data-dir',str(tmp_path),'--out-dir',str(tmp_path/'out')]
    assert run.main(args)==0
    result=json.loads((tmp_path/'out/lab_report.json').read_text())
    assert result['protocol_sha256']==hashlib.sha256(file.read_bytes()).hexdigest()
    assert (tmp_path/'out/lab_report.md').exists()
    assert len(capsys.readouterr().out.strip().splitlines())==6
    file.write_text('{}')
    assert run.main(args)==2 and capsys.readouterr().err.strip()=='invalid_protocol'


class CountList(list):
    def __init__(self,values):super().__init__(values);self.reads=0
    def __iter__(self):
        for x in super().__iter__():self.reads+=1;yield x
    def __getitem__(self,i):self.reads+=1;return super().__getitem__(i)


def test_linear_read_counts():
    counts=[]
    for n in (100,200):
        cs=CountList(candidate(cid=str(i),signal=(i+1)*MS) for i in range(n))
        ls=CountList(lab(c,touch=c.signal_time_ms) for c in cs);cs.reads=0
        adapt(cs,ls);adapter_reads=cs.reads+ls.reads
        cs.reads=0;controls.invert_candidates(cs);inverse_reads=cs.reads
        counts.append((adapter_reads,inverse_reads))
    assert counts[1]==tuple(2*x for x in counts[0])
    assert counts[0][0]<=400 and counts[0][1]<=300
    print('READ_COUNTS',counts)


def test_speed_20000_bars():
    p=small();p=replace(p,symbols=('BTCUSDT',),controls=replace(p.controls,n_shifts=1))
    start=time.perf_counter();r=run.run_lab(p,{'BTCUSDT':bars(20000)});elapsed=time.perf_counter()-start
    assert len(r['results'])==3 and elapsed<120
    print('SPEED_20000',elapsed)


def test_purity_ast_imports_names_and_defaults():
    common={'__future__','collections.abc','dataclasses','decimal','typing','re'}
    for module in (protocol,adapter,controls,verdict,evaluate,run):
        tree=ast.parse(Path(module.__file__).read_text())
        allowed=common|({'random'} if module is controls else set())|({'hashlib','json','csv','argparse','pathlib','sys'} if module is run else set())
        used={n.id for n in ast.walk(tree) if isinstance(n,ast.Name) and isinstance(n.ctx,ast.Load)}
        for node in ast.walk(tree):
            if isinstance(node,(ast.Import,ast.ImportFrom)):
                names=[node.module] if isinstance(node,ast.ImportFrom) else [a.name for a in node.names]
                assert all(name in allowed or name.startswith('backend.v3.') for name in names)
                for a in node.names:
                    if a.name!='annotations':assert (a.asname or a.name.split('.')[0]) in used
            if isinstance(node,ast.Constant):assert not isinstance(node.value,float)
            if isinstance(node,ast.Name):assert node.id not in {'float','time','datetime'}
            if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
                assert not any(isinstance(x,ast.Constant) and isinstance(x.value,(int,float)) for x in node.args.defaults+node.args.kw_defaults if x is not None)


def test_adapter_downstream_acceptance_and_local_context():
    cs=[candidate(signal=(i+1)*DAY,cid=str(i)) for i in range(4)]
    ls=[lab(c,touch=c.signal_time_ms) for c in cs]
    with localcontext() as ctx:
        ctx.prec=2
        os,n=adapt(cs,ls,unit_notional=D('777.7777'))
    assert n==0 and os[0].quantity==q(Fraction('777.7777')/100,8)
    spec=dict(min_trades=1,min_days=2,confidence=D('0.9'),n_boot=200,seed=1)
    assert cell_stats(os,**spec)[0].n==4
    fs=make_folds(start_ms=0,end_ms=6*DAY,train_ms=2*DAY,test_ms=2*DAY,step_ms=2*DAY,embargo_ms=0,expanding=False)
    wf=walk_forward(os,fs,**spec)
    assert wf.oos_n==1 and wf.rest_n==2  # first train has only one distinct day


def test_adapter_and_inversion_overflow_normalized():
    c=candidate()
    with pytest.raises(ValueError,match='^numeric_out_of_range$'):
        adapt([c],[lab(c)],unit_notional=D('1e999999'))
    c=replace(c,entry_price=D('9e999999'),stop_price=D('8e999999'),target_price=D('9.5e999999'))
    with pytest.raises(ValueError,match='^numeric_out_of_range$'):
        controls.invert_candidates([c])
    kw=good_verdict();kw.update(oos_over_train_min=D('9e999999'),is_mean_net_bp=D('9e999999'))
    with pytest.raises(ValueError,match='^numeric_out_of_range$'):verdict.classify(**kw)


def test_adapter_horizon_precedes_missing_regime():
    c=candidate();h=replace(lab(c),horizons=())
    with pytest.raises(ValueError,match='^invalid_horizon_in_labels$'):adapt([c],[h],regimes={})


def test_rank_exact_before_display_and_missing_nulls(monkeypatch):
    p,cs,candles,regimes,gross=manual_experiment()
    seen=[];real=evaluate.classify
    def spy(**kw):seen.append(kw['shift_rank_pct']);return real(**kw)
    monkeypatch.setattr(evaluate,'classify',spy)
    # Inverted mean is lower; two identical controls tie observed and do not count below.
    inverses=controls.invert_candidates(cs)[0]
    r=evaluate.evaluate_candidates(p,'S07','BTCUSDT',cs,candles,regimes,[inverses,tuple(cs),tuple(cs),()])
    with localcontext() as ctx:
        ctx.prec=60
        assert seen==[D('100')/3]
    assert r['shift_control']['n_sets']==4 and r['shift_control']['n_used']==3
    assert r['shift_control']['n_null_below']==1 and r['shift_control']['rank_pct']=='33.3333'


def test_no_folds_other_errors_propagate(monkeypatch):
    p=small()
    def fail(**kw): raise ValueError('unexpected')
    monkeypatch.setattr(evaluate,'make_folds',fail)
    with pytest.raises(ValueError,match='^unexpected$'):evaluate.evaluation_folds(p,0,300*DAY)


def test_no_null_sets_e4_in_positive_sample():
    p,cs,candles,regimes,_=planted('edge')
    r=evaluate.evaluate_candidates(p,'S07','BTCUSDT',cs,candles,regimes,[])
    assert r['verdict']=='POSITIVO_INCONCLUDENTE' and r['failed']==['E4']


def test_report_failed_conditions():
    p,cs,bs,regimes,nulls=planted('edge')
    r=evaluate.evaluate_candidates(p,'S07','BTCUSDT',cs,bs,regimes,nulls)
    r['failed']=['E1','E2','E3','E4']
    report=run.render_report_md(dict(run_id='fixed',results=[r]))
    for c in r['failed']:assert '- '+c+':' in report
    assert report==run.render_report_md(dict(run_id='fixed',results=[r]))


@pytest.mark.parametrize('field', ['mean_net_bp','ci_low','ci_high','oos_mean_net_bp','is_mean_net_bp','inverted_mean_net_bp','shift_rank_pct','oos_over_train_min','control_percentile_min'])
@pytest.mark.parametrize('value', [D('NaN'),D('Infinity')])
def test_verdict_nonfinite(field,value):
    kw=good_verdict();kw[field]=value
    with pytest.raises(ValueError): verdict.classify(**kw)


def test_purity_no_io_in_pure_run_functions():
    tree=ast.parse(Path(run.__file__).read_text())
    for node in tree.body:
        if isinstance(node,ast.FunctionDef) and node.name not in ('main','read_candles_csv'):
            for n in ast.walk(node):
                if isinstance(n,ast.Call):
                    if isinstance(n.func,ast.Name):assert n.func.id not in {'open','print','input','Path'}
                    if isinstance(n.func,ast.Attribute):assert n.func.attr not in {'read_text','write_text','read_bytes','write_bytes','open','mkdir'}


@pytest.mark.parametrize('idx',[0,1,2])
def test_protocol_pair_without_duplicate_confounds(idx):
    r=raw();s=r['strategies'][idx];s['kind']='unregistered';r['strategies']=[s]
    with pytest.raises(ValueError,match='^invalid_protocol$'):protocol.load_protocol(r)


def test_zero_optional_values_are_present_not_missing():
    kw=good_verdict();kw.update(oos_mean_net_bp=D('0'),is_mean_net_bp=D('0'))
    assert verdict.classify(**kw)==('POSITIVO_INCONCLUDENTE',('E2',))
    kw=good_verdict();kw.update(mean_net_bp=D('0'),inverted_mean_net_bp=D('-1'))
    assert verdict.classify(**kw)==('NULLO',())
    p=small();p=replace(p,labeling=replace(p.labeling,primary_cost_bp=D('0'),stress_costs_bp=(D('12'),D('20')),primary_horizon_ms=MS))
    c=candidate();candles=[Candle(i*MS,D('100'),D('100'),D('100'),D('100')) for i in range(3)]
    r=evaluate.evaluate_candidates(p,'S07','BTCUSDT',[c],candles,{0:'RANGE'},[[c]])
    assert r['shift_control']['n_used']==1 and r['shift_control']['null_means']==['0.0000']


def test_r_multiple_never_uses_display_distance():
    c=candidate(entry='100',distance='0.00001234567',target_distance='0.000025')
    label=lab(c,gross='0.0025',net='-11.9975',exit_price='100.000025')
    exact_distance=Fraction('0.00001234567')/100*10000
    expected=q(Fraction('-11.9975')/exact_distance)
    wrong=q(Fraction('-11.9975')/Fraction(q(exact_distance)))
    assert expected!=wrong  # oracle verifies the fixture discriminates double rounding
    assert adapt([c],[label])[0][0].r_multiple==expected
