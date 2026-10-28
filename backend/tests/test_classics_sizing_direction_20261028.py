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
    assert h.limits.min_initial_leverage==10
    assert h.guardrail_min_margin==100
    assert h.guardrail_min_lev==10
    assert h.limits.daily_stop==pytest.approx(.12)
    assert h.limits.kill_equity==450

def test_bull_requested_bounds_3_slots_and_risk_protection_unchanged():
    b=cli._make_bull_config()
    assert b.limits.start_equity==1000
    assert b.limits.max_open==3
    assert b.limits.max_margin_total==1050
    assert b.limits.max_margin_trade==350
    assert b.limits.min_initial_margin==150
    assert b.limits.min_initial_leverage==10
    assert b.guardrail_min_margin==150
    assert b.guardrail_min_lev==10
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
def test_flexible_10x_floor_is_a_refusal_not_hidden_multiplier(name,minimum):
    cfg=cli._make_hawk_config() if name=="hawk" else cli._make_bull_config()
    a=start(cfg)
    pos,why=open_position(a,"BTC",minimum,9)
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


def test_automatic_rule_fallback_generates_compliant_proposals_without_legacy_behavior_change():
    from types import SimpleNamespace
    from desk.brain import rules_decisions
    r=SimpleNamespace(symbol="ETH",side=1,score=60,trade_type="scalp",
                      sl_pct=.004,tp_pct=.008,why=["valid 1h breakout"])
    legacy=rules_decisions([r],[],set(),entry_score=60)
    assert legacy and legacy[0]['leverage']==15
    next_hawk=rules_decisions([r],[],set(),entry_score=60,
                              min_leverage=20,min_margin=100)
    assert next_hawk and next_hawk[0]['leverage']>=20
    assert 100<=next_hawk[0]['margin_usd']<=250
    r2=SimpleNamespace(symbol="SOL",side=-1,score=70,trade_type="medio",
                       sl_pct=.005,tp_pct=.01,why=["structure rejected resistance"])
    next_bull=rules_decisions([r2],[],set(),entry_score=60,
                              min_leverage=20,min_margin=150)
    assert next_bull and next_bull[0]['leverage']>=20
    assert next_bull[0]['margin_usd']>=150


def test_existing_10x_trade_survives_new_rules_and_can_close_with_fee_accounting():
    # Open a legacy position FIRST; its leverage must not change merely
    # because new openings after a deploy must be >= 20x.
    from desk.engine import Limits
    old=PaperAccount(Limits(start_equity=1000))
    legacy,why=old.open("BTC",1,50,10,100,99,102,T,{},
                        source="deepseek",trade_type="scalp")
    assert legacy and legacy.margin==50 and legacy.leverage==10
    saved=old.to_dict()
    newer=PaperAccount.from_dict(saved)
    newer.limits=cli._make_hawk_config().limits
    still=newer.positions["BTC"]
    assert still.margin==50 and still.leverage==10
    rec=newer.close("BTC",102,T+60000,"test legacy protection")
    assert rec and not newer.positions
    assert rec["net"]<rec["gross"]
    assert len(newer.closed)==1


def test_saved_legacy_account_reloads_with_new_limits_without_clearing_run():
    original=PaperAccount()
    p,why=original.open("BTC",1,75,10,100,99,102,T,{},trade_type="medio")
    assert p is not None
    state={"main":original.to_dict(),"run_no":7,"deepseek_budget":{"spent":.15},
           "some_other_history":"preserve"}
    from unittest.mock import patch
    with patch.object(cli,"PORTFOLIO",cli._make_hawk_config()):
        recovered=cli.make_account(state)
    assert recovered.positions["BTC"].margin==75
    assert recovered.positions["BTC"].leverage==10
    assert recovered.limits.min_initial_leverage==10
    assert recovered.limits.min_initial_margin==100
    assert state["run_no"]==7
    assert state["deepseek_budget"]["spent"]==.15
    assert state["some_other_history"]=="preserve"
    # New request below minimum is rejected, older trade is untouched.
    pos,why=open_position(recovered,"SOL",99,20)
    assert pos is None and "sotto il minimo" in why
    assert "BTC" in recovered.positions


def test_no_unsafe_new_opening_when_stop_too_wide_at_20x():
    a=start(cli._make_hawk_config())
    pos,reason=a.open("BTC",1,250,20,100,95,107,T,{},
                       trade_type="scalp",source="deepseek")
    assert pos is None and "liquidazione" in reason
    assert a.cash==1000 and not a.positions


@pytest.mark.parametrize('name,minimum', [('hawk', 100), ('bull', 150)])
@pytest.mark.parametrize('side', [1, -1])
def test_legacy_management_dca_partial_and_stop_survive_new_entry_floors(name, minimum, side):
    from desk.engine import Limits
    old = PaperAccount(Limits())
    p, why = old.open('BTC', side, 75, 10, 100, 100-side*3, 100+side*6,
                      T, {}, trade_type='medio')
    assert p, why
    # Simulate a JSON state written before the new Limits fields existed.
    import json
    saved = old.to_dict()
    saved['limits'].pop('min_initial_margin')
    saved['limits'].pop('min_initial_leverage')
    saved = json.loads(json.dumps(saved))
    cfg = cli._make_hawk_config() if name == 'hawk' else cli._make_bull_config()
    from unittest.mock import patch
    with patch.object(cli, 'PORTFOLIO', cfg):
        a = cli.make_account({'main': saved})
    p = a.positions['BTC']
    result, why = a.add_dca('BTC', 100-side*5, None, T+1000, {'BTC': 100-side})
    assert result is p, why
    assert p.leverage == 10 and p.sl == 100-side*3
    assert p.dca_levels[-1]['margin'] == 30 < minimum
    rec = a.partial_close('BTC', 100, T+2000, .5)
    assert rec and p.total_margin < minimum
    # The remaining historical position must still close on a protective stop.
    bar = (T//900000+1)*900000
    rec = a.on_bar('BTC', bar, 100, 104, 96, 100, 900000)
    assert rec and rec['why'] == 'stop loss'
    assert not a.positions
    assert a.cash == pytest.approx(1000 + sum(r['net'] for r in a.closed), abs=.001)


@pytest.mark.parametrize('side', [1, -1])
def test_legacy_pending_split_below_new_floor_can_still_fill(side):
    from desk.engine import Limits
    a = PaperAccount(Limits())
    p, why = a.open('BTC', side, 100, 10, 100, 100-side*2, 100+side*4,
                    T, {}, split={'retrace_pct': .005, 'first_frac': .5})
    assert p, why
    a = PaperAccount.from_dict(a.to_dict())
    a.limits = cli._make_bull_config().limits
    p = a.positions['BTC']
    ev = a._fill_split(p, T+1000)
    assert ev and p.total_margin == 100 and p.leverage == 10
    assert p.pending_split is None


@pytest.mark.parametrize('field', ['margin', 'leverage', 'price', 'sl', 'tp'])
@pytest.mark.parametrize('bad', [float('nan'), float('inf'), -float('inf')])
def test_invalid_numeric_proposals_cannot_corrupt_account(field, bad):
    a = start(cli._make_hawk_config())
    before = a.to_dict()
    args = dict(symbol='BTC', side=1, margin=100, leverage=20, price=100,
                sl=99, tp=102, now_ms=T, prices={})
    args[field] = bad
    p, why = a.open(**args)
    assert p is None and why
    assert a.to_dict() == before


def test_configured_leverage_ceiling_cannot_be_bypassed_by_asset_tier():
    from dataclasses import replace
    limits = replace(cli._make_hawk_config().limits, max_leverage=8)
    a = PaperAccount(limits)
    p, why = open_position(a, 'BTC', 100, 45)
    assert p is None and 'leva eseguibile 8x' in why
    assert a.cash == 1000


def test_dca_cannot_exceed_portfolio_margin_even_when_cash_has_grown():
    from dataclasses import replace
    a = PaperAccount(replace(cli._make_hawk_config().limits, max_margin_total=250))
    a.cash = 1500
    p, why = a.open('BTC', 1, 250, 20, 100, 98, 104, T, {}, trade_type='medio')
    assert p, why
    before = a.to_dict()
    result, why = a.add_dca('BTC', 98, None, T+1, {'BTC': 99})
    assert result is None and 'tetto margine totale' in why
    assert a.to_dict() == before


@pytest.mark.parametrize('method', ['dca', 'split'])
def test_daily_stop_blocks_added_risk_but_never_blocks_exits(method):
    a = start(cli._make_hawk_config())
    p, why = a.open('BTC', 1, 200, 20, 100, 98, 104, T, {},
                    trade_type='medio', split={'retrace_pct': .005} if method=='split' else None)
    assert p, why
    a.cash -= 130  # realized loss elsewhere, same trading day
    before_margin = a.margin_in_use()
    if method == 'dca':
        result, why = a.add_dca('BTC', 98, None, T+1, {'BTC': 99.5})
        assert result is None and 'stop giornaliero' in why
    else:
        assert a._fill_split(p, T+1) is None
        assert p.pending_split is None
        assert 'stop giornaliero' in a.events[-1]['reason']
    assert a.margin_in_use() == before_margin
    assert a.close('BTC', 99.5, T+2)


def test_parser_discards_overflowing_leverage_instead_of_crashing_cycle():
    answer = brain.parse_decisions('{"decisions":[{"symbol":"BTC","action":"open_long",'
                                    '"leverage":1e999,"margin_usd":100}]}')
    assert answer == {'decisions': [], 'note': ''}


@pytest.mark.parametrize('name,margin,leverage', [
    ('hawk', 99, 20), ('hawk', 150, 9), ('bull', 149, 20), ('bull', 200, 9),
])
def test_cycle_logs_small_ai_proposal_without_upscaling_or_fallback(name, margin, leverage, monkeypatch):
    from test_desk import _sandbox, _decisions_stub, _dec, NOW
    from desk import learning
    cfg = cli._make_hawk_config() if name=='hawk' else cli._make_bull_config()
    monkeypatch.setattr(cli, 'PORTFOLIO', cfg)
    monkeypatch.setattr(cli.time, 'sleep', lambda _: None)
    monkeypatch.setenv('DESK_DEEPSEEK_CLASSICS', '0')
    proposal = _dec('BTC', 'open_long', margin_usd=margin, leverage=leverage)
    with _sandbox(_decisions_stub(proposal)) as (directory, calls):
        state = {'run_no': 7, 'memo': 'keep'}
        cli.run_cycle(state, NOW)
        account = cli.make_account(state)
        assert account.cash == 1000 and not account.positions
        assert state['memo'] == 'keep' and state['run_no'] == 7
        events = learning.read_events(directory, 'candidate')
        assert len(events) == 1 and events[0]['status'] == 'sizing_sotto_minimo'
        assert events[0]['features']['dec_margin'] == margin
        assert events[0]['features']['dec_lev'] == leverage
        assert not learning.read_events(directory, 'open')
        assert len(calls) == 1


@pytest.mark.parametrize('name,minimum', [('hawk',100),('bull',150)])
def test_cash_reduction_below_floor_is_atomic(name, minimum):
    a = start(cli._make_hawk_config() if name=='hawk' else cli._make_bull_config())
    # Lower cash but keep equity through an existing legacy position; this
    # specifically exercises sizing rather than the equity kill/daily stop.
    from desk.engine import Limits
    old = PaperAccount(Limits())
    p, why = old.open('ETH', 1, 400, 10, 100, 98, 104, T, {})
    assert p, why
    a.positions = old.positions
    a.cash = minimum
    a.day_start_equity = 400 + minimum
    before = a.to_dict()
    result, why = open_position(a, 'BTC', minimum, 20)
    assert result is None and 'sotto il minimo' in why
    assert a.to_dict() == before
