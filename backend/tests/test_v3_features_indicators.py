"""Indicator tests for Brain V3 features.
"""
from decimal import Decimal
from backend.v3.features.indicators import (
    Bar, sma, ema, rma, true_range, atr, rsi, macd, bollinger, donchian, adx, check_bars,
)

def _bar(t, o, h, l, c, v=1):
    return Bar(t, Decimal(str(o)), Decimal(str(h)), Decimal(str(l)), Decimal(str(c)), Decimal(str(v)))

def test_sma_control():
    vals = [Decimal("10"), Decimal("12"), Decimal("11"), Decimal("15")]
    assert sma(vals, 2) == (None, Decimal("11"), Decimal("11.5"), Decimal("13"))

def test_ema_control():
    vals = [Decimal("10"), Decimal("12"), Decimal("11"), Decimal("15")]
    assert ema(vals, 3) == (None, None, Decimal("11"), Decimal("13"))

def test_rma_control():
    vals = [Decimal("10"), Decimal("12"), Decimal("11"), Decimal("15")]
    assert rma(vals, 2) == (None, Decimal("11"), Decimal("11"), Decimal("13"))

def test_true_range_gap():
    bars = [_bar(0, 10, 12, 9, 11), _bar(1000, 15, 16, 14, 15)]
    tr = true_range(bars, candle_ms=1000)
    assert tr[0] == Decimal("3")
    assert tr[1] == Decimal("5")

def test_rsi_control():
    bars = [_bar(i*1000, c, c+1, c-1, c) for i, c in enumerate([10, 11, 10, 12])]
    r = rsi(bars, 2, candle_ms=1000)
    assert r[0] is None and r[1] is None
    assert r[2] == Decimal("50")

def test_truncation():
    bars = [_bar(i*1000, 10+i, 12+i, 9+i, 11+i) for i in range(6)]
    full = ema([b.close for b in bars], 3)
    for m in range(0, 7):
        assert ema([b.close for b in bars[:m]], 3) == full[:m]

def test_validation_order():
    import pytest
    with pytest.raises(ValueError, match="invalid_candle_ms"):
        true_range([], candle_ms=True)
    with pytest.raises(ValueError, match="invalid_period"):
        sma([Decimal("1")], True)

def test_purity():
    import ast
    from pathlib import Path
    import backend.v3.features.indicators as ind
    src = Path(ind.__file__).read_text()
    tree = ast.parse(src)
    allowed = {"__future__", "dataclasses", "decimal", "collections.abc", "typing", "math"}
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module and n.module.split(".")[0] not in allowed:
            assert False, f"bad import: {n.module}"
    assert "float(" not in src
