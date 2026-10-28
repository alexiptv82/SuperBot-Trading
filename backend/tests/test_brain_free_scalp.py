"""Offline cost-aware Brain V2 mandate, sizing and causal 5m market context tests."""
import json
import pytest

from director.brain_free.config import Config
from director.brain_free.execution import initial,apply,margin
from director.brain_free.feeds import candles,summary
from director.brain_free.prompt_builder import build
from director.brain_free.mandate import SYSTEM

NOW=1800000000000
CFG=Config()
QUOTE={"price":100.0,"mark":100.0,"ts_ms":NOW}
CONTRACT={"status":"normal","max_leverage":50,"qty_step":.001,"price_step":.01,
          "min_qty":.001,"min_notional":1.0,"maintenance":.005}


def new_account():
    s=initial(NOW,"offline-v2");s["verified_start_ms"]=NOW
    return s


def choice(symbol,margin_usd,leverage):
    return {"symbol":symbol,"action":"open_long","margin":margin_usd,"leverage":leverage,
            "stop":99.5,"target":101.0,"reason":"closed-bar momentum",
            "invalidation":"support breaks"}


def test_v2_five_slots_and_1750_usd_margin_are_hard_physical_limits():
    assert CFG.start_cash==2000 and CFG.max_slots==5 and CFG.max_margin==1750
    st=new_account()
    for sym in CFG.symbols[:5]:
        st,events=apply(st,choice(sym,350,30),{sym:QUOTE},{sym:CONTRACT},NOW,CFG)
        assert events[0]["kind"]=="open"
    assert len(st["positions"])==5
    assert 1749<margin(st)<=1750
    assert st["cash"]>=0
    sixth=CFG.symbols[5]
    with pytest.raises(ValueError,match="slots_full"):
        apply(st,choice(sixth,350,30),{sixth:QUOTE},{sixth:CONTRACT},NOW,CFG)


def test_v2_200_to_350_and_30x_are_preferences_not_trade_gates():
    st=new_account()
    st,ev=apply(st,choice("BTC",70,10),{"BTC":QUOTE},{"BTC":CONTRACT},NOW,CFG)
    assert 69 < ev[0]["margin_added"] <= 70
    assert ev[0]["leverage"]==pytest.approx(10)
    st,ev=apply(st,choice("ETH",350,30),{"ETH":QUOTE},{"ETH":CONTRACT},NOW,CFG)
    assert 349<ev[0]["margin_added"]<=350
    assert ev[0]["leverage"]==30


def test_prompt_has_provenance_and_explicit_roundtrip_friction():
    s=new_account()
    system,payload=build(s,{}, {},{},[],[],"full",NOW,CFG)
    body=json.loads(payload)
    assert body["account"]["free_slots"]==5
    assert body["account"]["margin_remaining"]==1750
    assert body["execution_costs"]["roundtrip_friction_on_notional"]==pytest.approx(.0016)
    assert body["sizing_preference_nonbinding"]["typical_margin_usd"]==[200,350]
    assert "No enforced minimum margin" in system
    assert "NET profit" in system
    assert "stop-before-liquidation" in system


def test_5m_structure_uses_closed_bars_and_labels_vwap_approximation():
    raw=[[0,100,105,95,101,100],[300000,101,104,99,102,200],
         [600000,102,300,1,120,500]]
    out=summary(raw,now=750000,duration=300000)
    assert out["status"]=="available"
    assert out["last_close_ms"]==600000
    structure=out["structure_24_closed_bars"]
    assert structure["support_low"]==95
    assert structure["resistance_high"]==105
    assert structure["bars"]==2
    assert 95<structure["typical_price_vwap_approx"]<105
    # The in-progress extreme at 300 must never influence signal levels.


def test_public_5m_adapter_uses_timestamp_aligned_bitget_bars():
    captured=[]
    def fetcher(path):
        captured.append(path)
        return {"code":"00000","data":[
            ["300000","101","104","99","102","200"],
            ["0","100","105","95","101","100"]]}
    bars=candles("BTC","5m",limit=120,fetcher=fetcher)
    assert len(bars)==2 and bars[0][0]==0
    assert "granularity=5m" in captured[0]
    assert len(CFG.symbols)==26


def test_reframe_is_not_a_hidden_minimum_trade_or_profit_quota():
    assert "There is never a quota of trades" in SYSTEM
    assert "PREFERENCE ONLY" in SYSTEM
    assert CFG.analysis_ms==300000 and CFG.management_ms==120000
