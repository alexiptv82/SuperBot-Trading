"""Opportunity labeling tests with independent oracle.
"""
import random
from decimal import Decimal

import pytest
from fractions import Fraction
from backend.v3.learning.opportunity import (
    Candle, Candidate, label_candidates,
)

def _c(t, o, h, l, c):
    return Candle(t, Decimal(str(o)), Decimal(str(h)), Decimal(str(l)), Decimal(str(c)))

def _cand(id, sym, side, ts, entry, stop, target):
    return Candidate(id, sym, side, ts, Decimal(str(entry)), Decimal(str(stop)), Decimal(str(target)))

def test_control_long_target():
    candles = {"BTC": [_c(1000, 100, 110, 95, 105), _c(2000, 105, 120, 100, 115)]}
    c = _cand("c1", "BTC", 1, 500, 100, 90, 115)
    r = label_candidates([c], candles, candle_ms=1000, horizons_ms=[2000], cost_bp=Decimal("10"), ambiguous_policy="stop_first")
    assert r[0].horizons[0].barrier == "target"
    assert str(r[0].horizons[0].net_bp) == "1490.0000"

def test_control_long_stop():
    candles = {"BTC": [_c(1000, 100, 105, 85, 90)]}
    c = _cand("c1", "BTC", 1, 500, 100, 90, 115)
    r = label_candidates([c], candles, candle_ms=1000, horizons_ms=[1000], cost_bp=Decimal("10"), ambiguous_policy="stop_first")
    assert r[0].horizons[0].barrier == "stop"
    assert str(r[0].horizons[0].net_bp) == "-1010.0000"

def test_control_long_timeout():
    candles = {"BTC": [_c(1000, 100, 105, 95, 102)]}
    c = _cand("c1", "BTC", 1, 500, 100, 90, 115)
    r = label_candidates([c], candles, candle_ms=1000, horizons_ms=[1000], cost_bp=Decimal("10"), ambiguous_policy="stop_first")
    assert r[0].horizons[0].barrier == "timeout"
    assert str(r[0].horizons[0].net_bp) == "190.0000"

def test_control_short_target():
    candles = {"BTC": [_c(1000, 100, 105, 85, 90)]}
    c = _cand("c1", "BTC", -1, 500, 100, 110, 85)
    r = label_candidates([c], candles, candle_ms=1000, horizons_ms=[1000], cost_bp=Decimal("10"), ambiguous_policy="stop_first")
    assert r[0].horizons[0].barrier == "target"
    assert str(r[0].horizons[0].net_bp) == "1490.0000"

def test_control_short_stop():
    candles = {"BTC": [_c(1000, 100, 115, 95, 110)]}
    c = _cand("c1", "BTC", -1, 500, 100, 110, 85)
    r = label_candidates([c], candles, candle_ms=1000, horizons_ms=[1000], cost_bp=Decimal("10"), ambiguous_policy="stop_first")
    assert r[0].horizons[0].barrier == "stop"
    assert str(r[0].horizons[0].net_bp) == "-1010.0000"

def test_control_short_timeout():
    candles = {"BTC": [_c(1000, 100, 105, 95, 98)]}
    c = _cand("c1", "BTC", -1, 500, 100, 110, 85)
    r = label_candidates([c], candles, candle_ms=1000, horizons_ms=[1000], cost_bp=Decimal("10"), ambiguous_policy="stop_first")
    assert r[0].horizons[0].barrier == "timeout"
    assert str(r[0].horizons[0].net_bp) == "190.0000"

def test_signal_on_boundary_included():
    candles = {"BTC": [_c(1000, 100, 120, 95, 110)]}
    c = _cand("c1", "BTC", 1, 1000, 100, 90, 115)
    r = label_candidates([c], candles, candle_ms=1000, horizons_ms=[1000], cost_bp=Decimal("0"), ambiguous_policy="stop_first")
    assert r[0].horizons[0].barrier in ("target", "stop")

@pytest.mark.xfail(strict=True, reason="attesa errata (consegna di Grok): la candela 2000 ha high=115 == target=115, quindi il tocco c'e' ed e' 'target', non 'timeout'. Il confine e' coperto da TestWindow in test_brain_f7_opportunity_oracle.py")
def test_signal_after_boundary_excluded():
    candles = {"BTC": [_c(1000, 100, 120, 95, 110), _c(2000, 110, 115, 100, 112)]}
    c = _cand("c1", "BTC", 1, 1001, 100, 90, 115)
    r = label_candidates([c], candles, candle_ms=1000, horizons_ms=[1000], cost_bp=Decimal("0"), ambiguous_policy="stop_first")
    assert r[0].horizons[0].barrier == "timeout"

def test_gap_incomplete():
    candles = {"BTC": [_c(1000, 100, 105, 95, 100), _c(3000, 100, 105, 95, 100)]}
    c = _cand("c1", "BTC", 1, 500, 100, 90, 115)
    r = label_candidates([c], candles, candle_ms=1000, horizons_ms=[3000], cost_bp=Decimal("0"), ambiguous_policy="stop_first")
    assert r[0].horizons[0].status == "incomplete"

def test_missing_symbol_incomplete():
    c = _cand("c1", "ETH", 1, 500, 100, 90, 115)
    r = label_candidates([c], {}, candle_ms=1000, horizons_ms=[1000], cost_bp=Decimal("0"), ambiguous_policy="stop_first")
    assert r[0].horizons[0].status == "incomplete"

def test_ambiguous_policies():
    candles = {"BTC": [_c(1000, 100, 120, 80, 100)]}
    c = _cand("c1", "BTC", 1, 500, 100, 90, 115)
    r1 = label_candidates([c], candles, candle_ms=1000, horizons_ms=[1000], cost_bp=Decimal("0"), ambiguous_policy="stop_first")
    r2 = label_candidates([c], candles, candle_ms=1000, horizons_ms=[1000], cost_bp=Decimal("0"), ambiguous_policy="target_first")
    assert r1[0].horizons[0].ambiguous and r1[0].horizons[0].barrier == "stop"
    assert r2[0].horizons[0].ambiguous and r2[0].horizons[0].barrier == "target"

def test_horizon_consistency():
    candles = {"BTC": [_c(1000, 100, 120, 95, 110), _c(2000, 110, 115, 100, 112), _c(3000, 112, 118, 105, 115)]}
    c = _cand("c1", "BTC", 1, 500, 100, 90, 115)
    r = label_candidates([c], candles, candle_ms=1000, horizons_ms=[1000, 2000, 3000], cost_bp=Decimal("0"), ambiguous_policy="stop_first")
    h1, h2, h3 = r[0].horizons
    assert h1.barrier == h2.barrier == h3.barrier == "target"
    assert h1.touch_time_ms == h2.touch_time_ms == h3.touch_time_ms

def test_validation_order():
    import pytest
    c = _cand("c1", "BTC", 1, 500, 100, 90, 115)
    with pytest.raises(ValueError, match="invalid_candle_ms"):
        label_candidates([c], {}, candle_ms=True, horizons_ms=[1000], cost_bp=Decimal("0"), ambiguous_policy="stop_first")
    with pytest.raises(ValueError, match="invalid_horizons"):
        label_candidates([c], {}, candle_ms=1000, horizons_ms=[500], cost_bp=Decimal("0"), ambiguous_policy="stop_first")
    with pytest.raises(ValueError, match="invalid_cost_bp"):
        label_candidates([c], {}, candle_ms=1000, horizons_ms=[1000], cost_bp=Decimal("NaN"), ambiguous_policy="stop_first")
    with pytest.raises(ValueError, match="invalid_ambiguous_policy"):
        label_candidates([c], {}, candle_ms=1000, horizons_ms=[1000], cost_bp=Decimal("0"), ambiguous_policy="maybe")
    with pytest.raises(ValueError, match="invalid_candidate"):
        label_candidates(None, {}, candle_ms=1000, horizons_ms=[1000], cost_bp=Decimal("0"), ambiguous_policy="stop_first")
    with pytest.raises(ValueError, match="invalid_candidate"):
        label_candidates([c, c], {}, candle_ms=1000, horizons_ms=[1000], cost_bp=Decimal("0"), ambiguous_policy="stop_first")

def test_order_irrelevant():
    candles = {"BTC": [_c(1000, 100, 120, 95, 110)]}
    c1 = _cand("c1", "BTC", 1, 500, 100, 90, 115)
    c2 = _cand("c2", "BTC", -1, 500, 100, 110, 85)
    a = label_candidates([c1, c2], candles, candle_ms=1000, horizons_ms=[1000], cost_bp=Decimal("0"), ambiguous_policy="stop_first")
    b = label_candidates([c2, c1], candles, candle_ms=1000, horizons_ms=[1000], cost_bp=Decimal("0"), ambiguous_policy="stop_first")
    assert a[0].candidate_id == "c1" and b[0].candidate_id == "c2"
    assert a[0].horizons[0].barrier == b[1].horizons[0].barrier

def test_no_mutation():
    candles = {"BTC": [_c(1000, 100, 120, 95, 110)]}
    c = _cand("c1", "BTC", 1, 500, 100, 90, 115)
    orig = c.entry_price
    label_candidates([c], candles, candle_ms=1000, horizons_ms=[1000], cost_bp=Decimal("0"), ambiguous_policy="stop_first")
    assert c.entry_price == orig

@pytest.mark.xfail(strict=True, reason="difettoso (consegna di Grok): legge un percorso relativo (dipende dalla cwd) e la whitelist degli import omette collections.abc, che e' libreria standard. La purezza e' coperta da TestPublicContractAndPurity in test_brain_f7_opportunity_oracle.py")
def test_purity():
    import ast
    from pathlib import Path
    src = Path("backend/v3/learning/opportunity.py").read_text()
    tree = ast.parse(src)
    imports = [n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
    for n in imports:
        if isinstance(n, ast.ImportFrom) and n.module and not n.module.startswith(("decimal", "dataclasses", "typing", "re", "__future__")):
            assert False, f"non-stdlib import: {n.module}"
    assert "float(" not in src

def _oracle(candidates, candles, candle_ms, horizons_ms, cost_bp, policy):
    out = []
    for c in candidates:
        series = candles.get(c.symbol, [])
        by_time = {cn.open_time_ms: cn for cn in series}
        horizons = []
        for h in horizons_ms:
            n = h // candle_ms
            start = ((c.signal_time_ms + candle_ms - 1) // candle_ms) * candle_ms
            window_times = [start + i * candle_ms for i in range(n)]
            window = [by_time.get(t) for t in window_times]
            if any(w is None for w in window):
                horizons.append((h, "incomplete", None, False, None, None, None, None))
                continue
            barrier = None
            ambiguous = False
            touch = None
            exit_p = None
            for cn in window:
                if c.side == 1:
                    sh = cn.low <= c.stop_price
                    th = cn.high >= c.target_price
                else:
                    sh = cn.high >= c.stop_price
                    th = cn.low <= c.target_price
                if sh or th:
                    ambiguous = sh and th
                    if ambiguous:
                        barrier = "stop" if policy == "stop_first" else "target"
                    elif sh:
                        barrier = "stop"
                    else:
                        barrier = "target"
                    exit_p = c.stop_price if barrier == "stop" else c.target_price
                    touch = cn.open_time_ms
                    break
            if barrier is None:
                barrier = "timeout"
                exit_p = window[-1].close
                touch = None
            gross = Fraction(c.side) * (Fraction(exit_p) - Fraction(c.entry_price)) / Fraction(c.entry_price) * 10000
            net = gross - Fraction(cost_bp)
            horizons.append((h, "complete", barrier, ambiguous, touch, exit_p, gross, net))
        out.append((c.candidate_id, horizons))
    return out

@pytest.mark.xfail(strict=True, reason="difettoso (consegna di Grok): genera candele non valide (close fino a high+1) che il modulo rifiuta con invalid_candles, e il suo 'oracolo' ricopia l'algoritmo del modulo. Sostituito da TestAgainstOracle in test_brain_f7_opportunity_oracle.py")
def test_oracle_random():
    rng = random.Random(42)
    has_amb = has_gap = has_timeout = False
    for trial in range(20):
        candle_ms = rng.choice([1000, 5000])
        n = rng.randint(5, 15)
        candles_list = []
        t = 0
        for i in range(n):
            if rng.random() < 0.1:
                t += candle_ms * 2
                has_gap = True
            else:
                t += candle_ms
            o = Decimal(str(rng.randint(90, 110)))
            h = o + Decimal(str(rng.randint(0, 20)))
            l = o - Decimal(str(rng.randint(0, 20)))
            c = Decimal(str(rng.randint(int(l), int(h)+1)))
            candles_list.append(Candle(t, o, h, l, c))
        candles = {"BTC": candles_list}
        cands = []
        for j in range(3):
            entry = Decimal("100")
            side = rng.choice([-1, 1])
            if side == 1:
                stop, target = Decimal("90"), Decimal("115")
            else:
                stop, target = Decimal("110"), Decimal("85")
            ts = rng.randint(1, t)
            cands.append(Candidate(f"c{trial}-{j}", "BTC", side, ts, entry, stop, target))
        horizons = [candle_ms, candle_ms * 2]
        cost = Decimal(str(rng.randint(0, 20)))
        policy = rng.choice(["stop_first", "target_first"])
        got = label_candidates(cands, candles, candle_ms=candle_ms, horizons_ms=horizons, cost_bp=cost, ambiguous_policy=policy)
        exp = _oracle(cands, candles, candle_ms, horizons, cost, policy)
        for g, e in zip(got, exp):
            assert g.candidate_id == e[0]
            for gh, eh in zip(g.horizons, e[1]):
                assert gh.horizon_ms == eh[0]
                assert gh.status == eh[1]
                assert gh.barrier == eh[2]
                assert gh.ambiguous == eh[3]
                if gh.ambiguous:
                    has_amb = True
                if gh.barrier == "timeout":
                    has_timeout = True
    assert has_amb or has_gap or has_timeout
