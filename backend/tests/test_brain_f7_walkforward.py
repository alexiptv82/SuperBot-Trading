"""Walk-forward tests for Brain V3.
"""
from decimal import Decimal
from backend.v3.learning.walkforward import make_folds, walk_forward, Fold
from backend.v3.outcomes import TradeOutcome

DAY = 86_400_000

def _outcome(**kw):
    base = dict(
        schema_version=1, position_id="p", portfolio_id="brain", run_id="r",
        symbol="BTCUSDT", side=1, originating_ai="test", leverage=1,
        opened_at_ms=1, closed_at_ms=DAY, hold_ms=1,
        entry_price=Decimal("100"), exit_price=Decimal("101"),
        quantity=Decimal("1"), notional_entry=Decimal("100"), margin_used=Decimal("10"),
        gross_pnl=Decimal("1"), fees=Decimal("0.1"), realized_pnl=Decimal("0.9"),
        gross_bp=Decimal("100"), costs_bp=Decimal("10"), net_bp=Decimal("90"),
        stop_distance_bp=Decimal("50"), r_multiple=Decimal("1"),
        exit_reason="take_profit", loss_exceeds_margin=False,
        decision_event_id="e", link_status="linked", decision_regime="TREND_UP",
    )
    base.update(kw)
    return TradeOutcome(**base)

def test_make_folds_rolling():
    folds = make_folds(start_ms=0, end_ms=10*DAY, train_ms=3*DAY, test_ms=2*DAY,
                       step_ms=2*DAY, embargo_ms=0, expanding=False)
    assert len(folds) >= 1
    assert folds[0].train_start_ms == 0
    assert folds[0].train_end_ms == 3*DAY
    assert folds[0].test_start_ms == 3*DAY
    assert folds[0].test_end_ms == 5*DAY

def test_make_folds_expanding():
    folds = make_folds(start_ms=0, end_ms=10*DAY, train_ms=3*DAY, test_ms=2*DAY,
                       step_ms=2*DAY, embargo_ms=0, expanding=True)
    assert folds[0].train_start_ms == 0
    assert folds[1].train_start_ms == 0

def test_make_folds_errors():
    import pytest
    with pytest.raises(ValueError, match="invalid_window"):
        make_folds(start_ms=-1, end_ms=DAY, train_ms=DAY, test_ms=DAY, step_ms=DAY, embargo_ms=0, expanding=False)
    with pytest.raises(ValueError, match="invalid_lengths"):
        make_folds(start_ms=0, end_ms=10*DAY, train_ms=DAY, test_ms=2*DAY, step_ms=DAY, embargo_ms=0, expanding=False)
    with pytest.raises(ValueError, match="no_folds"):
        make_folds(start_ms=0, end_ms=DAY, train_ms=DAY, test_ms=DAY, step_ms=DAY, embargo_ms=0, expanding=False)

def test_walk_forward_basic():
    outcomes = [
        _outcome(position_id="t1", closed_at_ms=DAY, net_bp=Decimal("100")),
        _outcome(position_id="t2", closed_at_ms=2*DAY, net_bp=Decimal("50")),
        _outcome(position_id="t3", closed_at_ms=5*DAY, net_bp=Decimal("80")),
    ]
    folds = make_folds(start_ms=0, end_ms=10*DAY, train_ms=3*DAY, test_ms=2*DAY,
                       step_ms=2*DAY, embargo_ms=0, expanding=False)
    report = walk_forward(outcomes, folds, min_trades=1, min_days=2, confidence=Decimal("0.9"),
                          n_boot=200, seed=42)
    assert report.folds
    assert isinstance(report.is_n, int)

def test_truncation_invariance():
    outcomes = [_outcome(position_id=f"t{i}", closed_at_ms=i*DAY, net_bp=Decimal("50")) for i in range(1, 8)]
    folds = make_folds(start_ms=0, end_ms=10*DAY, train_ms=3*DAY, test_ms=2*DAY,
                       step_ms=2*DAY, embargo_ms=0, expanding=False)
    full = walk_forward(outcomes, folds, min_trades=1, min_days=2, confidence=Decimal("0.9"),
                        n_boot=200, seed=42)
    part = walk_forward(outcomes[:5], folds, min_trades=1, min_days=2, confidence=Decimal("0.9"),
                        n_boot=200, seed=42)
    assert part.folds[0].n_train_outcomes <= full.folds[0].n_train_outcomes

def test_purity():
    import ast
    from pathlib import Path
    import backend.v3.learning.walkforward as wf
    src = Path(wf.__file__).read_text()
    tree = ast.parse(src)
    allowed = {"__future__", "collections", "dataclasses", "decimal", "typing", "backend"}
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module and n.module.split(".")[0] not in allowed:
            assert False, f"bad import: {n.module}"
    assert "float(" not in src
