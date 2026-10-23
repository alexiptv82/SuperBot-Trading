"""Synthetic-only Capital Management V1 contract tests; no VPS/API or live trading."""
from decimal import Decimal
import pytest
from desk.capital_manager import (CapitalInvariantError, DayReference, dec, start_day,
                                  risk_view, latch_risk, add_capital_flow, eligible_rollover)
from desk.vault_manager import (VaultState, manual_withdraw, rollover, settle_pending,
                                journal_record)
from desk.position_sizer import cap_for, size_request


def v(name, **kwargs):
    return kwargs[name]


@pytest.mark.parametrize("budget,h,b", [(1000,100,250),(900,90,225),
                                         (800,80,200),(500,50,125)])
def test_percentual_position_caps(budget,h,b):
    assert cap_for("hawk",budget)==h
    assert cap_for("bull",budget)==b


def test_daily_stop_20_percent_latched_no_manual_topup_unlock():
    ref=start_day("2026-10-24",900)
    assert risk_view(ref,720).stop_latched
    assert risk_view(ref,720).reason == "daily_stop"
    locked=latch_risk(ref,720)
    assert locked.stop_latched
    with_flow=add_capital_flow(locked,50)
    assert with_flow.day_budget==900
    assert risk_view(with_flow,800).stop_latched
    assert risk_view(with_flow,800).reason=="daily_stop"
    assert risk_view(with_flow,800).day_pnl==-150  # equity 800 - 900 - 50
    assert not eligible_rollover(locked,"2026-10-24")
    assert eligible_rollover(locked,"2026-10-25")


def test_transfer_neutrality_for_daily_pnl():
    ref=start_day("2026-10-24",1000)
    before=risk_view(ref,1000)
    moved=add_capital_flow(ref,-120)
    after=risk_view(moved,880)
    assert before.day_pnl == after.day_pnl == 0
    assert after.budget==1000


def test_kill_equity_450_even_if_percent_stop_lower():
    ref=start_day("2026-10-24",500)
    assert risk_view(ref,450).reason=="kill_equity"
    assert risk_view(ref,449).reason=="kill_equity"


def test_flat_1120_rolls_120_into_vault():
    r=rollover(VaultState(),utc_day="2026-10-24",equity=1120,cash=1120,
               committed_margin=0,unrealized=0)
    assert r.cash_delta==-120
    assert r.state.balance==120
    assert r.state.pending_total==0
    assert r.state.last_rollover_day=="2026-10-24"
    repeated=rollover(r.state,utc_day="2026-10-24",equity=1000,cash=1000,
                      committed_margin=0,unrealized=0)
    assert repeated.cash_delta==0 and repeated.state==r.state
    assert (1000+r.state.balance)==1120


def test_900_does_not_pull_from_vault():
    r=rollover(VaultState(balance=Decimal("50")),utc_day="2026-10-24",
               equity=900,cash=900,committed_margin=0,unrealized=0)
    assert r.cash_delta==0 and r.state.balance==50 and r.state.pending_total==0


def test_unrealized_not_locked_into_vault_until_close():
    before=rollover(VaultState(),utc_day="2026-10-24",
                    equity=1150,cash=1000,committed_margin=0,unrealized=150)
    assert before.cash_delta==0 and before.state.balance==0
    assert before.state.pending_total==150
    after=settle_pending(before.state,equity=1120,cash=1120,
                         committed_margin=0,unrealized=0,event_id="close:A")
    assert after.cash_delta==-120 and after.state.balance==120
    assert after.state.pending_total==0


def test_pending_evaporates_after_market_loss():
    before=rollover(VaultState(),utc_day="2026-10-24",equity=1150,cash=1000,
                    committed_margin=0,unrealized=150)
    after=settle_pending(before.state,equity=950,cash=950,
                         committed_margin=0,unrealized=0,event_id="close:loss")
    assert after.cash_delta==0 and after.state.pending_total==0


def test_manual_withdraw_only_paper_and_balanced_journal():
    vault=VaultState(balance=Decimal("120"),revision=2)
    result=manual_withdraw(vault,50,event_id="user:withdraw-A",
                           expected_revision=2,paper_mode=True)
    assert result.state.balance==70 and result.cash_delta==50
    rec=journal_record(result,bot="hawk",previous_revision=2,account_cash_before=900)
    assert Decimal(rec["cash_after"])==950 and Decimal(rec["vault"]["balance"])==70
    with pytest.raises(CapitalInvariantError):
        manual_withdraw(vault,30,event_id="X",expected_revision=2,paper_mode=False)
    with pytest.raises(CapitalInvariantError):
        manual_withdraw(vault,121,event_id="X",expected_revision=2,paper_mode=True)
    with pytest.raises(CapitalInvariantError):
        manual_withdraw(vault,30,event_id="X",expected_revision=1,paper_mode=True)


def test_no_cap_bypass_by_dca_split_reservation():
    kw=dict(bot="hawk",day_budget=1000,total_committed_margin=100,
            already_in_position=80,pending_same_position=20,
            available_cash=700,reserved_cash=0,request=20,minimum_executable=5,
            fee_fraction=0.001,n_open=1,is_new=False)
    r=size_request(**kw)
    assert not r.approved and r.reason=="below_minimum"
    kw.update(already_in_position=65,pending_same_position=20,total_committed_margin=85)
    r=size_request(**kw)
    assert r.approved and r.amount==15 and r.reason=="reduced"
    kw.update(day_budget=900)
    r=size_request(**kw)
    assert r.approved and r.amount==5


def test_25_pct_bull_under_legacy_forced_150():
    kw=dict(bot="bull",day_budget=500,total_committed_margin=0,
            already_in_position=0,pending_same_position=0,
            available_cash=500,reserved_cash=0,request=200,minimum_executable=150,
            fee_fraction=0.001,n_open=0,is_new=True)
    assert size_request(**kw).reason=="below_minimum"


def test_no_silent_reduction_when_false():
    kw=dict(bot="bull",day_budget=1000,total_committed_margin=0,
            already_in_position=0,pending_same_position=0,
            available_cash=1000,reserved_cash=0,request=350,minimum_executable=30,
            fee_fraction=0.001,n_open=0,is_new=True,allow_reduction=False)
    assert size_request(**kw).reason=="exceeds_cap"


def test_validation_rejects_bad_numbers():
    for x in ("NaN","Infinity",float("inf"),-1):
        with pytest.raises(CapitalInvariantError):
            cap_for("hawk",x)
    with pytest.raises(CapitalInvariantError):
        rollover(VaultState(),utc_day="2026-10-24",equity=1120,cash=100,
                 committed_margin=0,unrealized=0)


def test_idempotent_manual_withdrawal_receipt():
    vault=VaultState(balance=Decimal("120"),revision=2)
    first=manual_withdraw(vault,50,event_id="user:withdraw-A",
                          expected_revision=2,paper_mode=True)
    again=manual_withdraw(first.state,50,event_id="user:withdraw-A",
                          expected_revision=2,paper_mode=True)
    assert again.reason=="already_applied" and again.cash_delta==0
    assert again.state==first.state
    with pytest.raises(CapitalInvariantError):
        manual_withdraw(first.state,60,event_id="user:withdraw-A",
                        expected_revision=3,paper_mode=True)


def test_manual_deposit_not_a_new_earned_surplus():
    r=rollover(VaultState(),utc_day="2026-10-24",
               equity=1050,cash=1050,committed_margin=0,unrealized=0,
               excluded_external_funds=50)
    assert r.cash_delta==0
    assert r.state.balance==0 and r.state.pending_total==0
    r2=rollover(VaultState(),utc_day="2026-10-24",
                equity=1200,cash=1050,committed_margin=0,unrealized=150,
                excluded_external_funds=50)
    assert r2.cash_delta==0 and r2.state.pending_total==150


def test_pending_close_idempotent_and_no_duplicate_claim_on_next_day():
    start=rollover(VaultState(),utc_day="2026-10-24",
                   equity=1150,cash=1000,committed_margin=0,unrealized=150)
    nextday=rollover(start.state,utc_day="2026-10-25",
                     equity=1150,cash=1000,committed_margin=0,unrealized=150)
    assert nextday.state.pending_total==150
    assert len(nextday.state.pending)==1
    close=settle_pending(nextday.state,equity=1120,cash=1120,
                         committed_margin=0,unrealized=0,event_id="close:abc")
    again=settle_pending(close.state,equity=1120,cash=1000,
                         committed_margin=0,unrealized=120,event_id="close:abc")
    assert again.cash_delta==0 and again.state==close.state
