"""Regime classifier tests for Brain V3 features.
"""
from decimal import Decimal
from backend.v3.features.indicators import Bar
from backend.v3.features.regime import RegimeParams, regime_labels, REGIME_LABELS

def _bar(t, h, l, c=None, v=1, ms=60000):
    if c is None:
        c = (h + l) / 2
    return Bar(t, Decimal(str(c)), Decimal(str(h)), Decimal(str(l)), Decimal(str(c)), Decimal(str(v)))

def test_control_vector():
    pairs = [
        (101, 99), (103, 100), (101, 99), (104, 100), (102, 99), (104, 100), (102, 99), (103, 100),
        (112, 99), (113, 106), (116, 111), (121, 115), (125, 120), (129, 124), (126, 121), (120, 115),
        (114, 109), (108, 103), (102, 97), (100, 98), (101, 99), (100, 98), (101, 98), (100, 99),
    ]
    bars = [_bar(k * 60000, h, l) for k, (h, l) in enumerate(pairs)]
    params = RegimeParams(Decimal("1.5"), Decimal("100"), Decimal("60"), Decimal("40"))
    labels = regime_labels(bars, 2, 3, 2, params, candle_ms=60000)
    expected = [
        "UNCERTAIN", "UNCERTAIN", "UNCERTAIN", "EXPANSION", "RANGE", "EXPANSION", "RANGE", "RANGE",
        "SHOCK", "TREND_UP", "TREND_UP", "TREND_UP", "TREND_UP", "TREND_UP", "UNCERTAIN", "EXPANSION",
        "EXPANSION", "EXPANSION", "EXPANSION", "TREND_DOWN", "TREND_DOWN", "TREND_DOWN", "RANGE", "RANGE",
    ]
    assert list(labels) == expected

def test_truncation():
    bars = [_bar(k * 60000, 110, 90) for k in range(10)]
    params = RegimeParams(Decimal("2"), Decimal("80"), Decimal("50"), Decimal("30"))
    full = regime_labels(bars, 2, 3, 2, params, candle_ms=60000)
    for m in range(0, 11):
        part = regime_labels(bars[:m], 2, 3, 2, params, candle_ms=60000)
        assert part == full[:m]

def test_validation():
    import pytest
    bars = [_bar(0, 110, 90)]
    params = RegimeParams(Decimal("1.5"), Decimal("80"), Decimal("50"), Decimal("30"))
    with pytest.raises(ValueError, match="invalid_candle_ms"):
        regime_labels(bars, 2, 3, 2, params, candle_ms=True)
    with pytest.raises(ValueError, match="invalid_period"):
        regime_labels(bars, True, 3, 2, params, candle_ms=60000)
    with pytest.raises(ValueError, match="invalid_threshold"):
        regime_labels(bars, 2, 3, 2, {"shock": 1}, candle_ms=60000)

def test_labels_in_set():
    bars = [_bar(k * 60000, 110, 90) for k in range(6)]
    params = RegimeParams(Decimal("2"), Decimal("80"), Decimal("50"), Decimal("30"))
    labels = regime_labels(bars, 2, 3, 2, params, candle_ms=60000)
    assert all(l in REGIME_LABELS for l in labels)

def test_purity():
    import ast
    from pathlib import Path
    import backend.v3.features.regime as reg
    src = Path(reg.__file__).read_text()
    tree = ast.parse(src)
    allowed = {"__future__", "dataclasses", "decimal", "typing", "backend"}
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module and n.module.split(".")[0] not in allowed:
            assert False, f"bad import: {n.module}"
    assert "float(" not in src
