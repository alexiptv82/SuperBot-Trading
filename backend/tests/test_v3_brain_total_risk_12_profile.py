"""Brain PAPER 2k: delegated 12% aggregate risk / 55% total margin.

No strategy changes, broker connections or VPS side effects. Uses actual
V3 RiskPolicy, config loader and official quote_paper_risk.
"""
from dataclasses import replace
from decimal import Decimal as D
from pathlib import Path
import json

from backend.v3.risk import quote_paper_risk
from backend.v3.runner.config import load_default_config, load_runner_config
from backend.tests.test_v3_brain_risk_75_profile import request

PROFILE = Path(__file__).resolve().parents[1] / 'v3' / 'runner' / 'runner_config_brain2000_paper.json'


def policy():
    return load_runner_config(PROFILE.read_bytes()).risk_policy


def test_requested_total_risk_is_twelve_percent_with_complementary_margin_cap():
    c=load_runner_config(PROFILE.read_bytes());p=c.risk_policy
    assert c.initial_equity == D('2000')
    assert p.max_open_risk_fraction == D('0.12')
    assert p.max_total_margin_fraction == D('0.55')
    assert D('2000')*p.max_open_risk_fraction == D('240')
    assert D('2000')*p.max_total_margin_fraction == D('1100')
    assert D('2000')*p.max_position_margin_fraction == D('400')
    assert p.min_leverage == 20 and p.max_leverage == 50
    assert p.max_loss_margin_fraction == D('0.214285714285714285')
    assert c.daily_loss_warn == D('0.35') and c.daily_loss_halt == D('0.50')
    assert p.minimum_equity == D('450')


def test_multiple_350_margin_trades_are_no_longer_blocked_by_total_risk():
    p=policy();used_margin=D(0); used_risk=D(0)
    # The stop is selected by the model; an example close enough to give
    # virtually the full $75 worst-case loss per $350 margin, INCLUDING costs.
    lev=D(20)
    stop=D(100)*(D(1)-((p.max_loss_margin_fraction-D('0.000000001'))/lev-D('.0016')))
    for i in range(3):
        money=D(350)
        cash_budget=money*(D(1)+lev*D('.0016'))
        r=quote_paper_risk(p,request(
            stop_price=stop,available_cash=cash_budget,
            margin_used=used_margin,existing_open_risk=used_risk))
        assert r.allowed, (i,r.reason)
        assert D('349.9') < r.margin <= money
        assert r.worst_case_loss_estimate <= D(75)
        used_margin += r.margin
        used_risk += r.worst_case_loss_estimate
    assert D('1049.7') < used_margin <= D(1050)
    assert D('224.8') < used_risk <= D(225)
    assert used_margin <= D(1100) and used_risk <= D(240)
    # Existing 40% total margin cap would have made the third impossible at 350.
    old_cap=replace(p,max_total_margin_fraction=D('0.40'))
    blocked=quote_paper_risk(old_cap,request(
        stop_price=stop,available_cash=D(350)*(D(1)+lev*D('.0016')),
        margin_used=used_margin-r.margin,existing_open_risk=used_risk-r.worst_case_loss_estimate))
    assert blocked.allowed and blocked.margin < D(150)


def test_total_risk_12_still_fails_closed_if_budget_consumed():
    p=policy()
    q=quote_paper_risk(p,request(existing_open_risk=D('240')))
    assert q.allowed is False and q.reason == 'risk_budget_exhausted'
    partial=quote_paper_risk(p,request(existing_open_risk=D('200')))
    assert partial.allowed
    assert partial.worst_case_loss_estimate <= D('40')


def test_no_changes_to_default_profile_or_other_brain_parameters():
    regular=load_default_config(); chosen=load_runner_config(PROFILE.read_bytes())
    assert regular.risk_policy.max_open_risk_fraction == D('0.05')
    assert regular.risk_policy.max_total_margin_fraction == D('0.3')
    assert chosen.initial_equity == D('2000')
    assert chosen.max_tokens == regular.max_tokens
    assert chosen.model == regular.model
    assert chosen.cycle_minutes == regular.cycle_minutes
    assert chosen.daily_cap_usd == regular.daily_cap_usd


def test_aggregate_losses_are_estimates_not_liquidation_guarantee():
    # The risk engine quotes stop-distance + an estimated fee buffer, and
    # never claims to bound unexpected slippage / gap losses.
    q=quote_paper_risk(policy(),request())
    assert q.allowed and q.worst_case_loss_estimate > D(0)
    assert q.worst_case_loss_estimate <= q.risk_budget
