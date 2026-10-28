"""12 October trading thresholds with informational-only macro, not a full rollback.

No network, no exchange, no live trades. Provider collaboration is unchanged.
"""
import json
from datetime import datetime, timezone
import pytest

from desk import cli, macro_calendar as mc
from desk import deepseek_collab as ds

MS=60000
HOUR=60*MS
T=int(datetime(2026,10,28,18,0,tzinfo=timezone.utc).timestamp()*1000)
EVENT={'ts':T,'title':'Federal Funds Rate','country':'USD','impact':'High','src':'ff'}

def test_oct12_stable_core_params_remain_in_place():
    assert cli.tier_entry_score('BTC')==60
    assert cli.tier_entry_score('ETH')==60
    assert cli.tier_entry_score('NEAR')==70
    assert cli._make_hawk_config().limits.max_open==10
    assert cli._make_bull_config().limits.max_open==3
    assert cli._make_hawk_config().limits.daily_stop==pytest.approx(.12)
    assert cli._make_bull_config().limits.daily_stop==pytest.approx(.12)
    assert cli.CYCLE_S==1800
    assert cli._make_hawk_config().guardrail_lev_forced==15
    assert cli._make_bull_config().guardrail_lev_forced==15

@pytest.mark.parametrize('minute_delta',[-11*60,-1,0,60,120,180])
def test_observe_never_changes_any_entry_gate(minute_delta):
    ts=T+minute_delta*MS
    prior=mc.evaluate([EVENT],ts)
    obs=mc.apply_policy(prior,'observe')
    assert obs['regime']==prior['regime']
    assert obs['next']==prior['next']
    assert obs['blackout'] is False
    assert obs['conf_bonus']==0
    assert obs['enforce'] is False
    assert obs['raw_blackout']==prior['blackout']
    assert obs['raw_conf_bonus']==prior['conf_bonus']
    assert mc.features(obs)['macro_enforce'] is False
    if prior['regime']=='alto':
        lines=' '.join(mc.prompt_lines(obs))
        assert 'CALENDARIO MACRO' in lines
        assert 'NON bloccano' in lines
        assert 'NON aggiungono' in lines

def test_user_selected_observe_mode_preserves_news_and_gates_in_current(tmp_path,monkeypatch):
    # Fixed cached events eliminate remote data dependency and allow a genuine end-to-end policy test.
    obj={'ff':{'ts':T-2*HOUR,'next_try_ms':T+24*HOUR,'events':[EVENT],'error':''},
         'bls':{'ts':0,'next_try_ms':T+24*HOUR,'events':[],'error':''}}
    (tmp_path/'macro_events.json').write_text(json.dumps(obj))
    monkeypatch.setenv('DESK_MACRO_FETCH','0')
    monkeypatch.setenv('DESK_MACRO_POLICY','observe')
    for d in [-11*60,-40,0,90,130]:
        m=mc.current(str(tmp_path),T+d*MS)
        assert m['n_events']==1
        assert m['enforce'] is False
        assert m['blackout'] is False and m['conf_bonus']==0
        assert 'Federal Funds Rate' in ' '.join(mc.prompt_lines(m))
        assert mc.heartbeat_view(m)['enforce'] is False
        assert m['raw_blackout']==(-60<=d<120)
    # Enforced mode remains testable and intentionally opt-in at deploy time.
    monkeypatch.setenv('DESK_MACRO_POLICY','enforce')
    m=mc.current(str(tmp_path),T-40*MS)
    assert m['blackout'] and m['conf_bonus']==5 and m['enforce']

def test_observation_is_still_included_in_deepseek_mandate():
    assert 'INFORMAZIONE di contesto' in ds.SYSTEM
    assert 'non veto' in ds.SYSTEM
    assert '0.16%' in ds.SYSTEM

def test_hard_risk_controls_remain_in_engine():
    from desk.engine import Limits
    assert Limits().kill_equity==450.0
    assert Limits().min_margin>=0
    assert Limits().max_leverage==45
    assert Limits().daily_stop==pytest.approx(.12)

def test_off_switch_is_different_from_observational_mode(tmp_path,monkeypatch):
    monkeypatch.setenv('DESK_MACRO_POLICY','observe')
    monkeypatch.setenv('DESK_MACRO','0')
    m=mc.current(str(tmp_path),T)
    assert m['regime']=='off'
    assert mc.prompt_lines(m)==[]
