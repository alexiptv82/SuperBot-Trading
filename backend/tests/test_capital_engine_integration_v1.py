"""Opt-in integration seams in existing PAPER engine; baseline untouched if not enabled."""
from desk.engine import PaperAccount, Limits
from desk.capital_manager import start_day


def bot(botname,budget,*,minimum=30):
    a=PaperAccount(Limits(start_equity=1000,max_margin_trade=350,
                          max_margin_total=1050,min_margin=minimum,
                          daily_stop=0.12,max_open=10),"main")
    a.set_capital_policy(botname,budget)
    return a


def test_bull_open_uses_25_percent_cap_even_if_legacy_limit_is_350():
    a=bot("bull",1000)
    p,msg=a.open("BTC",1,350,10,100,98,105,1,{"BTC":100})
    assert p is not None, msg
    assert p.total_margin==250


def test_hawk_dca_rejected_when_full_10_pct_used():
    a=bot("hawk",1000)
    p,msg=a.open("BTC",1,100,10,100,96,108,1,{"BTC":100},trade_type="medio")
    assert p is not None,msg
    before=a.cash
    result,reason=a.add_dca("BTC",94,None,2,{"BTC":98},"test")
    assert result is None and "percentuale" in reason
    assert a.cash==before
    assert a.positions["BTC"].total_margin==100


def test_split_reserves_whole_position_cap():
    a=bot("hawk",1000)
    p,msg=a.open("BTC",1,100,10,100,98,105,1,{"BTC":100},trade_type="medio",
                 split={"retrace_pct":0.005,"first_frac":0.5})
    assert p is not None,msg
    assert p.total_margin==50
    assert p.pending_split and p.pending_split["margin"]==50
    # An unrelated opening may still use its own cap but reservations count globally.
    gate=a._capital_size("BTC",10,10,new_position=False)
    assert gate is not None and not gate.approved


def test_bull_budget500_legacy_min150_rejects_open():
    a=bot("bull",500,minimum=150)
    p,msg=a.open("BTC",1,200,10,100,98,105,1,{"BTC":100})
    assert p is None and "percentuale" in msg


def test_capital_daily_stop_20_is_opt_in_and_no_changes_baseline():
    legacy=bot("hawk",1000)
    legacy.cash=840
    assert legacy.halted({})=="stop giornaliero raggiunto"  # still 12% baseline
    new=bot("hawk",1000)
    new.set_capital_policy("hawk",1000,start_day("2026-10-24",1000))
    new.cash=840
    assert new.halted({})==""
    new.cash=800
    assert new.halted({})=="stop giornaliero raggiunto"


def test_second_leg_must_fit_remaining_position_cap():
    a=bot("hawk",900)
    p,msg=a.open("BTC",1,90,10,100,98,105,1,{"BTC":100},trade_type="medio",
                 split={"retrace_pct":0.005,"first_frac":0.5})
    assert p is not None,msg
    assert p.pending_split["margin"]==45
    result=a._fill_split(p,3)
    assert result is not None
    assert p.total_margin==90
    assert p.pending_split is None
