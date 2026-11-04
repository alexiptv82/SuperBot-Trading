"""Safety quotes for PAPER-only V3: no order execution, no live accounts."""
from decimal import Decimal

from v3.risk import RiskPolicy, RiskRequest, quote_paper_risk


def d(s):
    return Decimal(str(s))


def policy():
    # Test fixture only; these values are NOT approved trading settings.
    return RiskPolicy(
        max_loss_fraction=d("0.015"),
        max_open_risk_fraction=d("0.06"),
        max_position_margin_fraction=d("0.25"),
        max_total_margin_fraction=d("0.70"),
        minimum_equity=d("450"),
        estimated_roundtrip_cost_bp=d("16"),
        liquidation_buffer_fraction=d("0.50"),
    )


def req(**overrides):
    fields = dict(
        equity=d(1000), available_cash=d(1000),
        margin_used=d(0), existing_open_risk=d(0),
        entry_price=d(100), stop_price=d(99), side=1,
        requested_leverage=10, exchange_leverage_limit=20,
        quantity_step=d("0.1"), minimum_notional=d(5),
        maintenance_fraction=d("0.005"), market_data_fresh=True,
        paused=False, daily_loss_latched=False,
    )
    fields.update(overrides)
    return RiskRequest(**fields)


def test_long_quote_limits_loss_at_stop_including_cost_buffer():
    q = quote_paper_risk(policy(), req())
    assert q.allowed, q.reason
    assert q.reason == "quote_only"
    assert q.worst_case_loss_estimate <= d(15)
    assert q.quantity > 0
    assert q.quantity % d("0.1") == 0
    assert q.margin <= d(250)
    assert q.notional == q.quantity * d(100)


def test_short_quote_and_no_trade_when_stop_wrong_side():
    q = quote_paper_risk(policy(), req(side=-1, stop_price=d(101)))
    assert q.allowed, q.reason
    assert q.worst_case_loss_estimate <= d(15)
    assert quote_paper_risk(policy(), req(side=-1, stop_price=d(99))).reason == "stop_wrong_side"
    assert quote_paper_risk(policy(), req(side=1, stop_price=d(101))).reason == "stop_wrong_side"


def test_pause_stale_data_daily_latch_and_floor_fail_closed():
    assert quote_paper_risk(policy(), req(paused=True)).reason == "portfolio_locked"
    assert quote_paper_risk(policy(), req(daily_loss_latched=True)).reason == "portfolio_locked"
    assert quote_paper_risk(policy(), req(market_data_fresh=False)).reason == "stale_market_data"
    assert quote_paper_risk(policy(), req(equity=d(450))).reason == "equity_floor_reached"


def test_open_risk_budget_and_hard_floor():
    no_room = req(existing_open_risk=d(60))
    assert quote_paper_risk(policy(), no_room).reason == "risk_budget_exhausted"
    # Approaching 450 absolute floor: cannot plan a $15 loss from equity 453.
    q = quote_paper_risk(policy(), req(equity=d(453), available_cash=d(453)))
    assert q.allowed
    assert q.worst_case_loss_estimate <= d(3)


def test_position_and_portfolio_margin_caps():
    q = quote_paper_risk(policy(), req(
        existing_open_risk=d(0), margin_used=d(690),
        available_cash=d(600),
    ))
    assert q.allowed
    assert q.margin <= d(10)
    assert q.worst_case_loss_estimate <= d(15)


def test_leverage_liquidation_buffer_and_cash():
    assert quote_paper_risk(policy(), req(requested_leverage=50)).reason == "invalid_leverage"
    assert quote_paper_risk(policy(), req(stop_price=d(90), requested_leverage=20)).reason == "stop_near_liquidation"
    assert quote_paper_risk(policy(), req(available_cash=d(0))).reason == "margin_budget_exhausted"


def test_reject_non_finite_and_invalid_policy():
    assert quote_paper_risk(policy(), req(entry_price=d("NaN"))).reason == "invalid_numeric_input"
    p = RiskPolicy(d("0.1"), d("0.06"), d("0.25"), d("0.70"),
                   d(450), d(16), d("0.5"))
    assert quote_paper_risk(p, req()).reason == "invalid_policy_or_market"


def test_rounding_never_exceeds_stop_risk_limit():
    for equity in (d("550"), d("1000"), d("3000")):
        for lev in (1, 3, 10, 20):
            for distance in (d("0.001"), d("0.005"), d("0.02")):
                price = d(100)
                stop = price * (1-distance)
                q = quote_paper_risk(policy(), req(
                    equity=equity, available_cash=equity,
                    entry_price=price, stop_price=stop,
                    requested_leverage=lev,
                    quantity_step=d("0.001"),
                ))
                if q.allowed:
                    assert q.worst_case_loss_estimate <= q.risk_budget
                    assert q.margin <= equity * d("0.25")
                    assert q.margin <= equity * d("0.70")
                    assert q.quantity > 0
                    assert q.notional > 0
