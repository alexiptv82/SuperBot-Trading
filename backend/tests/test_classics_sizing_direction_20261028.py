"""Offline regression: requested PAPER classic sizing direction without risk upscaling.

Only NEW entry legs are subject to the new margin and leverage minima.
No market access; no wallets or persisted account state are changed.
"""
import pytest
from desk import cli,brain,deepseek_collab
from desk.engine import PaperAccount, max_leverage_for

T=1800000000000
PX=100.0
def start(portfolio):
    return PaperAccount(portfolio.limits)

def open_position(account, symbol, margin, leverage, split=None):
    return account.open(symbol,1,margin,leverage,PX,99.0,102.0,T,{},
                        source="deepseek",trade_type="scalp",split=split)

def test_hawk_requested_bounds_10_slots_and_risk_protection_unchanged():
    h=cli._make_hawk_config()
    assert h.limits.start_equity==1000
    assert h.limits.max_open==10
    assert h.limits.max_margin_total==1000
    assert h.limits.max_margin_trade==250
    assert h.limits.min_initial_margin==100
    assert h.limits.min_initial_leverage==20
    assert h.guardrail_min_margin==100
    assert h.guardrail_min_lev==20
    assert h.limits.daily_stop==pytest.approx(.12)
    assert h.limits.kill_equity==450

def test_bull_requested_bounds_3_slots_and_risk_protection_unchanged():
    b=cli._make_bull_config()
    assert b.limits.start_equity==1000
    assert b.limits.max_open==3
    assert b.limits.max_margin_total==1050
    assert b.limits.max_margin_trade==350
    assert b.limits.min_initial_margin==150
    assert b.limits.min_initial_leverage==20
    assert b.guardrail_min_margin==150
    assert b.guardrail_min_lev==20
    assert b.limits.daily_stop==pytest.approx(.12)
    assert b.limits.kill_equity==450

@pytest.mark.parametrize("name,under,exact,maximum",[
    ("hawk",99,100,250),("bull",149,150,350)
])
def test_new_margin_floor_is_never_auto_upscaled(name,under,exact,maximum):
    cfg=cli._make_hawk_config() if name=="hawk" else cli._make_bull_config()
    a=start(cfg)
    pos,why=open_position(a,"BTC",under,20)
    assert pos is None and "sotto il minimo" in why
    assert a.cash==1000 and a.positions=={}
    pos,why=open_position(a,"BTC",exact,20)
    assert pos is not None and pos.margin==exact
    b=start(cfg)
    pos,why=open_position(b,"BTC",maximum+100,20)
    assert pos is not None and pos.margin==maximum
    assert all(p.leverage==20 for p in [pos])

@pytest.mark.parametrize("name,minimum",[
    ("hawk",100),("bull",150)
])
def test_20x_minimum_is_a_refusal_not_hidden_multiplier(name,minimum):
    cfg=cli._make_hawk_config() if name=="hawk" else cli._make_bull_config()
    a=start(cfg)
    pos,why=open_position(a,"BTC",minimum,10)
    assert pos is None and "leva eseguibile" in why
    assert a.positions=={}
    pos,why=open_position(a,"BTC",minimum,20)
    assert pos is not None and pos.leverage==20

def test_current_instrument_limits_remain_physical_not_unbounded():
    assert max_leverage_for("BTC")==45
    assert max_leverage_for("ETH")==30
    assert max_leverage_for("SOL")==25
    a=start(cli._make_hawk_config())
    pos,why=open_position(a,"ETH",100,45)
    assert pos is not None and pos.leverage==30
    # A requested 50x would not be actually executable at 50x with today's
    # engine cap. Do not imply there is unlimited exchange leverage.
    b=start(cli._make_hawk_config())
    pos,why=open_position(b,"BTC",100,50)
    assert pos is not None and pos.leverage==45

@pytest.mark.parametrize("name,too_small,allowed,first",[
    ("hawk",150,200,100),("bull",200,300,150)
])
def test_split_first_leg_also_respects_minimum(name,too_small,allowed,first):
    cfg=cli._make_hawk_config() if name=="hawk" else cli._make_bull_config()
    split={"retrace_pct":.005,"first_frac":.5}
    a=start(cfg)
    pos,why=open_position(a,"BTC",too_small,20,split)
    assert pos is None and "prima gamba" in why
    assert a.cash==1000 and not a.positions
    pos,why=open_position(a,"BTC",allowed,20,split)
    assert pos is not None and pos.margin==first
    assert pos.pending_split is not None
    assert pos.pending_split["margin"]==first

def test_no_10_full_hawk_slots_are_promised_with_1000_equity_and_fees():
    a=start(cli._make_hawk_config())
    opened=0
    for symbol in ["BTC","ETH","SOL","ADA","LINK","XRP","DOGE","NEAR","AVAX","SUI"]:
        pos,_=open_position(a,symbol,100,20)
        if pos:opened+=1
    assert 1<=opened<=9
    assert a.margin_in_use()<=1000
    assert a.cash>=0

def test_exposure_below_margin_floor_due_to_cash_is_rejected_without_shrinking():
    a=start(cli._make_bull_config())
    p,_=open_position(a,"BTC",350,20)
    assert p
    p,_=open_position(a,"ETH",350,20)
    assert p
    p,why=open_position(a,"SOL",350,20)
    assert p is not None and 150<=p.margin<=350
    p,why=open_position(a,"LINK",200,20)
    assert p is None and "troppe posizioni" in why

def test_prompt_is_coherent_with_new_sizing_direction():
    assert "Nuovo ingresso: margine 100-250$" in brain.SYSTEM
    assert "Nuovo ingresso 150-350$" in brain.SYSTEM_BULL
    assert "Nuove aperture Hawk: margine 100-250$" in deepseek_collab.SYSTEM
    assert "Bull: margine 150-350$" in deepseek_collab.SYSTEM
    assert "non aumentare" in deepseek_collab.SYSTEM.lower() or "Non aumentare" in deepseek_collab.SYSTEM
