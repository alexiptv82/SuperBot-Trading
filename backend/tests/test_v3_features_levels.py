"""Levels tests for Brain V3 features.
"""
from decimal import Decimal
from backend.v3.features.indicators import Bar
from backend.v3.features.levels import (
    supertrend, atr_percentile, vwap_session, opening_range, swing_levels,
)

def _bar(t, o, h, l, c, v=1, ms=60000):
    return Bar(t, Decimal(str(o)), Decimal(str(h)), Decimal(str(l)), Decimal(str(c)), Decimal(str(v)))

def test_swing_control():
    high = [10, 12, 11, 14, 13, 13, 12, 15, 9]
    low = [8, 9, 7, 10, 9, 10, 6, 11, 5]
    bars = [_bar(k * 60000, low[k], high[k], low[k], low[k]) for k in range(9)]
    s = swing_levels(bars, 2, 1, candle_ms=60000)
    assert s.high == (None, None, None, None, Decimal("14"), Decimal("14"), Decimal("14"), Decimal("14"), Decimal("15"))
    assert s.high_time_ms == (None, None, None, None, 180000, 180000, 180000, 180000, 420000)
    assert s.low == (None, None, None, Decimal("7"), Decimal("7"), Decimal("7"), Decimal("7"), Decimal("6"), Decimal("6"))
    assert s.low_time_ms == (None, None, None, 120000, 120000, 120000, 120000, 360000, 360000)

def test_vwap_control():
    high = [10, 12, 11, 14, 13, 13, 12, 15]
    low = [8, 9, 7, 10, 9, 10, 6, 11]
    close = [9, 11, 8, 13, 12, 10, 7, 14]
    vol = [2, 0, 3, 1, 4, 2, 0, 5]
    bars = [_bar(k * 60000, close[k], high[k], low[k], close[k], vol[k]) for k in range(8)]
    v = vwap_session(bars, 4 * 60000, 0, candle_ms=60000)
    assert v[0] == Decimal("9")
    assert v[1] == Decimal("9")
    assert str(v[2])[:3] == "8.8"
    assert str(v[3])[:4] == "9.38"

def test_opening_range_control():
    high = [10, 12, 11, 14, 13, 13, 12, 15]
    low = [8, 9, 7, 10, 9, 10, 6, 11]
    close = [9, 11, 8, 13, 12, 10, 7, 14]
    bars = [_bar(k * 60000, close[k], high[k], low[k], close[k]) for k in range(8)]
    r = opening_range(bars, 4 * 60000, 0, 2, candle_ms=60000)
    assert r.high[1] == Decimal("12")
    assert r.low[1] == Decimal("8")
    assert r.high[4] is None

def test_supertrend_control():
    high = [10, 12, 13, 15, 16, 14, 12, 9, 8, 10, 13, 15]
    low = [8, 9, 11, 12, 14, 11, 9, 6, 5, 7, 10, 12]
    bars = [_bar(k * 60000, low[k], high[k], low[k], low[k]) for k in range(12)]
    s = supertrend(bars, 2, Decimal("1"), candle_ms=60000)
    assert s.direction[1] == -1
    assert s.direction[4] == 1
    assert s.direction[5] == -1

def test_atr_percentile_control():
    high = [10, 12, 13, 15, 16, 14, 12, 9, 8, 10, 13, 15]
    low = [8, 9, 11, 12, 14, 11, 9, 6, 5, 7, 10, 12]
    bars = [_bar(k * 60000, low[k], high[k], low[k], low[k]) for k in range(12)]
    p = atr_percentile(bars, 2, 3, candle_ms=60000)
    assert p[3] == Decimal("100")
    assert str(p[5])[:4] == "33.3"

def test_truncation():
    bars = [_bar(k * 60000, 10, 12, 8, 10) for k in range(10)]
    full = swing_levels(bars, 2, 1, candle_ms=60000)
    for m in range(0, 11):
        part = swing_levels(bars[:m], 2, 1, candle_ms=60000)
        assert part.high == full.high[:m]

def test_validation():
    import pytest
    bars = [_bar(0, 10, 12, 8, 10)]
    with pytest.raises(ValueError, match="invalid_candle_ms"):
        supertrend(bars, 2, Decimal("1"), candle_ms=True)
    with pytest.raises(ValueError, match="invalid_period"):
        supertrend(bars, True, Decimal("1"), candle_ms=60000)

def test_purity():
    import ast
    from pathlib import Path
    import backend.v3.features.levels as lvl
    src = Path(lvl.__file__).read_text()
    tree = ast.parse(src)
    allowed = {"__future__", "dataclasses", "decimal", "typing", "backend"}
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module and n.module.split(".")[0] not in allowed:
            assert False, f"bad import: {n.module}"
    assert "float(" not in src
