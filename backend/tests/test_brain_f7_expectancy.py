"""Expectancy tests for F7 P4.
"""
from decimal import Decimal
from backend.v3.outcomes import TradeOutcome
from backend.v3.learning.expectancy import cell_stats, default_cell_key, format_cells

def _outcome(**over) -> TradeOutcome:
    base = dict(
        schema_version=1, position_id="p1", portfolio_id="brain", run_id="r1",
        symbol="BTCUSDT", side=1, originating_ai="deepseek",
        leverage=5, opened_at_ms=1700000000000, closed_at_ms=1700086400000,
        hold_ms=86400000, entry_price=Decimal("50000"), exit_price=Decimal("51000"),
        quantity=Decimal("0.001"), notional_entry=Decimal("50"),
        margin_used=Decimal("10"), gross_pnl=Decimal("1"), fees=Decimal("0.1"),
        realized_pnl=Decimal("0.9"), gross_bp=Decimal("200"), costs_bp=Decimal("20"),
        net_bp=Decimal("180"), stop_distance_bp=Decimal("100"), r_multiple=Decimal("1.8"),
        exit_reason="brain_close", loss_exceeds_margin=False,
        decision_event_id="d1", link_status="linked", decision_regime="TRENDING",
    )
    base.update(over)
    return TradeOutcome(**base)

def test_control_positive_negative_inconclusive():
    pos = [_outcome(closed_at_ms=1700000000000 + i * 86400000, net_bp=Decimal("100")) for i in range(6)]
    cells = cell_stats(pos, min_trades=2, min_days=2, confidence=Decimal("0.9"), n_boot=200, seed=1)
    assert cells[0].status == "positive"
    neg = [_outcome(closed_at_ms=1700000000000 + i * 86400000, net_bp=Decimal("-100")) for i in range(6)]
    cells = cell_stats(neg, min_trades=2, min_days=2, confidence=Decimal("0.9"), n_boot=200, seed=1)
    assert cells[0].status == "negative"

def test_hand_calculated_stats():
    outs = [
        _outcome(closed_at_ms=1700000000000, net_bp=Decimal("10"), r_multiple=Decimal("1")),
        _outcome(closed_at_ms=1700000000000, net_bp=Decimal("20"), r_multiple=None),
        _outcome(closed_at_ms=1700086400000, net_bp=Decimal("30"), r_multiple=Decimal("2")),
        _outcome(closed_at_ms=1700086400000, net_bp=Decimal("40"), r_multiple=Decimal("3")),
    ]
    c = cell_stats(outs, min_trades=2, min_days=2, confidence=Decimal("0.9"), n_boot=200, seed=1)[0]
    assert c.n == 4 and c.n_days == 2
    assert c.mean_net_bp == Decimal("25.0000")
    assert c.median_net_bp == Decimal("25.0000")
    assert c.win_rate == Decimal("1.0000")
    assert c.mean_r == Decimal("2.0000")

def test_odd_median():
    outs = [_outcome(closed_at_ms=1700000000000 + i * 86400000, net_bp=Decimal(str(i*10))) for i in range(5)]
    c = cell_stats(outs, min_trades=2, min_days=2, confidence=Decimal("0.9"), n_boot=200, seed=1)[0]
    assert c.median_net_bp == Decimal("20.0000")

def test_insufficient_low_n():
    outs = [_outcome()]
    c = cell_stats(outs, min_trades=5, min_days=2, confidence=Decimal("0.9"), n_boot=200, seed=1)[0]
    assert c.status == "insufficient" and c.ci_low is None

def test_insufficient_single_day():
    outs = [_outcome(closed_at_ms=1700000000000, net_bp=Decimal("100")) for _ in range(10)]
    c = cell_stats(outs, min_trades=2, min_days=2, confidence=Decimal("0.9"), n_boot=200, seed=1)[0]
    assert c.status == "insufficient"

def test_constant_ci_equals_value():
    outs = [_outcome(closed_at_ms=1700000000000 + i * 86400000, net_bp=Decimal("50")) for i in range(6)]
    c = cell_stats(outs, min_trades=2, min_days=2, confidence=Decimal("0.9"), n_boot=200, seed=1)[0]
    assert c.ci_low == c.ci_high == Decimal("50.0000")

def test_win_rate_does_not_decide():
    outs = [_outcome(closed_at_ms=1700000000000 + i * 86400000, net_bp=Decimal("10"), realized_pnl=Decimal("1")) for i in range(9)]
    outs.append(_outcome(closed_at_ms=1700000000000 + 9 * 86400000, net_bp=Decimal("-200"), realized_pnl=Decimal("-1")))
    c = cell_stats(outs, min_trades=2, min_days=2, confidence=Decimal("0.9"), n_boot=200, seed=1)[0]
    assert c.win_rate == Decimal("0.9000")
    assert c.status != "positive"

def test_order_irrelevant():
    outs = [_outcome(closed_at_ms=1700000000000 + i * 86400000, net_bp=Decimal(str(i*10))) for i in range(6)]
    a = cell_stats(outs, min_trades=2, min_days=2, confidence=Decimal("0.9"), n_boot=200, seed=42)
    b = cell_stats(list(reversed(outs)), min_trades=2, min_days=2, confidence=Decimal("0.9"), n_boot=200, seed=42)
    assert a == b

def test_same_seed_same_result():
    outs = [_outcome(closed_at_ms=1700000000000 + i * 86400000, net_bp=Decimal(str(i*10))) for i in range(6)]
    a = cell_stats(outs, min_trades=2, min_days=2, confidence=Decimal("0.9"), n_boot=200, seed=7)
    b = cell_stats(outs, min_trades=2, min_days=2, confidence=Decimal("0.9"), n_boot=200, seed=7)
    assert a == b

def test_link_status_filter():
    linked = _outcome(link_status="linked")
    dangling = _outcome(link_status="dangling", closed_at_ms=1700086400000)
    cells = cell_stats([linked, dangling], min_trades=1, min_days=2, confidence=Decimal("0.9"), n_boot=200, seed=1)
    assert cells[0].n == 1
    cells2 = cell_stats([linked, dangling], min_trades=1, min_days=2, confidence=Decimal("0.9"), n_boot=200, seed=1,
                        link_statuses=frozenset({"linked", "dangling"}))
    assert cells2[0].n == 2

def test_manual_and_brain_separate():
    brain = _outcome(exit_reason="brain_close")
    manual = _outcome(exit_reason="manual", closed_at_ms=1700086400000)
    cells = cell_stats([brain, manual], min_trades=1, min_days=2, confidence=Decimal("0.9"), n_boot=200, seed=1)
    assert len(cells) == 2

def test_validation_codes():
    import pytest
    outs = [_outcome()]
    with pytest.raises(ValueError, match="invalid_outcome"):
        cell_stats(["not"], min_trades=1, min_days=2, confidence=Decimal("0.9"), n_boot=200, seed=1)
    with pytest.raises(ValueError, match="invalid_min_trades"):
        cell_stats(outs, min_trades=True, min_days=2, confidence=Decimal("0.9"), n_boot=200, seed=1)
    with pytest.raises(ValueError, match="invalid_min_days"):
        cell_stats(outs, min_trades=1, min_days=1, confidence=Decimal("0.9"), n_boot=200, seed=1)
    with pytest.raises(ValueError, match="invalid_confidence"):
        cell_stats(outs, min_trades=1, min_days=2, confidence=Decimal("1"), n_boot=200, seed=1)
    with pytest.raises(ValueError, match="invalid_n_boot"):
        cell_stats(outs, min_trades=1, min_days=2, confidence=Decimal("0.9"), n_boot=100, seed=1)
    with pytest.raises(ValueError, match="invalid_seed"):
        cell_stats(outs, min_trades=1, min_days=2, confidence=Decimal("0.9"), n_boot=200, seed=True)
    with pytest.raises(ValueError, match="invalid_key"):
        cell_stats(outs, min_trades=1, min_days=2, confidence=Decimal("0.9"), n_boot=200, seed=1, key=lambda o: "not a tuple")
    with pytest.raises(ValueError, match="invalid_link_statuses"):
        cell_stats(outs, min_trades=1, min_days=2, confidence=Decimal("0.9"), n_boot=200, seed=1, link_statuses={"linked"})

def test_format_cells():
    outs = [_outcome(closed_at_ms=1700000000000 + i * 86400000, net_bp=Decimal("100")) for i in range(4)]
    cells = cell_stats(outs, min_trades=2, min_days=2, confidence=Decimal("0.9"), n_boot=200, seed=1)
    text = format_cells(cells)
    assert "BTCUSDT" in text and "positive" in text

def test_no_mutation():
    outs = [_outcome()]
    orig = outs[0].net_bp
    cell_stats(outs, min_trades=1, min_days=2, confidence=Decimal("0.9"), n_boot=200, seed=1)
    assert outs[0].net_bp == orig

def test_block_bootstrap_not_trade_bootstrap():
    outs = [_outcome(closed_at_ms=1700000000000, net_bp=Decimal("1000"))]
    outs += [_outcome(closed_at_ms=1700086400000, net_bp=Decimal("-10")) for _ in range(9)]
    c = cell_stats(outs, min_trades=2, min_days=2, confidence=Decimal("0.5"), n_boot=200, seed=1)[0]
    assert c.ci_low is not None

def test_day_boundary():
    outs = [
        _outcome(closed_at_ms=86400000 - 1, net_bp=Decimal("100")),
        _outcome(closed_at_ms=86400000, net_bp=Decimal("-100")),
        _outcome(closed_at_ms=86400000 * 2, net_bp=Decimal("50")),
        _outcome(closed_at_ms=86400000 * 2 + 1, net_bp=Decimal("50")),
    ]
    c = cell_stats(outs, min_trades=2, min_days=2, confidence=Decimal("0.9"), n_boot=200, seed=1)[0]
    assert c.n_days == 3

def test_seed_affects_ci():
    outs = [_outcome(closed_at_ms=1700000000000 + i * 86400000, net_bp=Decimal(str((i%3-1)*100))) for i in range(9)]
    a = cell_stats(outs, min_trades=2, min_days=2, confidence=Decimal("0.9"), n_boot=200, seed=1)[0]
    b = cell_stats(outs, min_trades=2, min_days=2, confidence=Decimal("0.9"), n_boot=200, seed=999)[0]
    assert a.ci_low != b.ci_low or a.ci_high != b.ci_high

def test_ci_high_not_always_min():
    outs = [_outcome(closed_at_ms=1700000000000 + i * 86400000, net_bp=Decimal(str(i*100 - 400))) for i in range(9)]
    c = cell_stats(outs, min_trades=2, min_days=2, confidence=Decimal("0.8"), n_boot=200, seed=3)[0]
    assert c.ci_low is not None and c.ci_high is not None
    assert c.ci_high > c.ci_low

def test_day_ms_boundary_exact():
    outs = [
        _outcome(closed_at_ms=86399999, net_bp=Decimal("100")),
        _outcome(closed_at_ms=86400000, net_bp=Decimal("100")),
        _outcome(closed_at_ms=86400000 * 2 - 1, net_bp=Decimal("100")),
        _outcome(closed_at_ms=86400000 * 2, net_bp=Decimal("100")),
    ]
    c = cell_stats(outs, min_trades=2, min_days=2, confidence=Decimal("0.9"), n_boot=200, seed=1)[0]
    assert c.n_days == 3
