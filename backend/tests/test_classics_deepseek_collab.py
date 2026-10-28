"""Hawk/Bull DeepSeek operator-window, cost, arbitration and risk regressions.

All tests offline; no provider credentials and no exchange orders.
"""
import json
import os
import pathlib
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest
from desk import deepseek_collab as ds

def ms(y,m,d,h,minute=0):
    return int(datetime(y,m,d,h,minute,tzinfo=timezone.utc).timestamp()*1000)

def test_rome_window_including_winter_dst_weekends():
    # 28 October (CET): 08 Rome=07 UTC, 20 Rome=19 UTC.
    for moment,expected in [
        (ms(2026,10,28,6,59),False),
        (ms(2026,10,28,7,0),True),
        (ms(2026,10,28,18,59),True),
        (ms(2026,10,28,19,0),False),
        (ms(2027,7,5,5,59),False),
        (ms(2027,7,5,6,0),True),
        (ms(2027,7,5,17,59),True),
        (ms(2027,7,5,18,0),False),
        (ms(2026,11,1,7,0),True),
    ]:
        assert ds.in_window(moment)==expected
    assert not ds.in_window(ms(2026,10,28,10),enabled=False)

def test_deepseek_default_off_and_paper_only(monkeypatch):
    monkeypatch.delenv('DESK_DEEPSEEK_CLASSICS',raising=False)
    monkeypatch.setenv('DESK_MODE','paper')
    assert not ds.configured()
    monkeypatch.setenv('DESK_DEEPSEEK_CLASSICS','paper')
    assert ds.configured()
    monkeypatch.setenv('DESK_MODE','live')
    assert not ds.configured()

def test_cost_budget_is_saved_before_call_and_per_portfolio():
    a,b={},{}
    audit=[]
    now=ms(2026,10,28,7)
    def persist(x):
        audit.append(json.loads(json.dumps(x)))
    assert ds.reserve(a,now,persist)
    assert audit[0]['deepseek_budget']['reserved']==pytest.approx(ds.RESERVATION)
    assert 'deepseek_budget' not in b
    expected=ds.estimate({'prompt_tokens':12000,'prompt_cache_hit_tokens':2000,
          'prompt_cache_miss_tokens':10000,'completion_tokens':2000},now)*1.25
    cost=ds.settle(a,now,{'prompt_tokens':12000,'prompt_cache_hit_tokens':2000,
          'prompt_cache_miss_tokens':10000,'completion_tokens':2000},persist,True)
    assert cost==pytest.approx(expected)
    assert a['deepseek_budget']['reserved']==0
    assert a['deepseek_budget']['calls']==1
    assert len(audit)==2
    assert ds.reserve(b,now,lambda _:None)
    assert ds.budget_state(b,now)['calls']==0

def test_failure_reservation_not_refunded_and_limit_blocks():
    st={};now=ms(2026,10,28,9)
    for _ in range(6):
        assert ds.reserve(st,now,lambda _:None)
        assert ds.settle(st,now,persist=lambda _:None,success=False)==ds.RESERVATION
    assert not ds.reserve(st,now,lambda _:None)
    assert st['deepseek_budget']['spent']==pytest.approx(.24)
    assert ds.reserve(st,now+86400000,lambda _:None)
    assert st['deepseek_budget']['total_spent']==pytest.approx(.24)
    assert st['deepseek_budget']['spent']==0

def test_counterexample_no_cache_cost_double_count():
    u={'prompt_tokens':10000,'prompt_cache_hit_tokens':0,'prompt_cache_miss_tokens':10000,
       'completion_tokens':1200,'completion_tokens_details':{'reasoning_tokens':900}}
    normal=ds.estimate(u,ms(2026,10,31,12))
    peak=ds.estimate(u,ms(2026,10,28,7))
    assert peak==pytest.approx(2*normal)
    assert normal==pytest.approx((10000*.15+1200*.60)/1e6)
    with pytest.raises(ValueError,match='invalid_usage'):
        ds.estimate({**u,'prompt_cache_miss_tokens':9000},ms(2026,10,31,12))

def test_safe_deepseek_client_schema_response_no_network():
    class Stream:
        def __enter__(self):return self
        def __exit__(self,*a):return False
        def read(self,n):return json.dumps({'choices':[{'finish_reason':'stop',
            'message':{'content':'{"decisions":[]}'}}],'usage':{
            'prompt_tokens':300,'prompt_cache_hit_tokens':0,
            'prompt_cache_miss_tokens':300,'completion_tokens':8}}).encode()
    seen={}
    def opener(request,timeout):
        seen['payload']=json.loads(request.data)
        seen['timeout']=timeout
        return Stream()
    answer,usage=ds.call('dummy',"BTC 15m closed bars; score 67",opener=opener)
    assert json.loads(answer)=={'decisions':[]}
    assert usage['completion_tokens']==8
    assert seen['payload']['model']==ds.MODEL
    assert seen['payload']['response_format']=={'type':'json_object'}
    assert len(seen['payload']['messages'])==2
    assert 'netto' in ds.SYSTEM.lower()

def test_second_opinion_can_veto_but_not_create_or_flip_positions():
    proposals=[{'symbol':'BTC','action':'open_long','leverage':30,'confidence':62},
               {'symbol':'ETH','action':'open_short','leverage':12,'confidence':80},
               {'symbol':'SOL','action':'hold'}]
    assert ds.review_requested(proposals,lambda _:60)
    kept,veto=ds.apply_claude_review(proposals,
         [{'symbol':'BTC','action':'open_short'},
          {'symbol':'ETH','action':'hold'},
          {'symbol':'XRP','action':'open_long'}])
    assert veto==['BTC']
    assert kept==proposals[1:]
    kept2,veto2=ds.apply_claude_review(proposals,[{'symbol':'BTC','action':'skip'}])
    assert veto2==['BTC']
    assert all(x['symbol']!='XRP' for x in kept2)

def test_existing_classical_risk_tiers_are_unchanged():
    from desk import cli
    assert cli.tier_entry_score('BTC')==60
    assert cli.tier_entry_score('ETH')==60
    assert cli.tier_entry_score('NEAR')==70
    assert cli.tier_entry_score('SOL')==70
    assert cli.SCALP_COOLDOWN_MS==600000
    assert cli.MEDIO_COOLDOWN_MS==3600000
    assert cli.CYCLE_S==1800
    assert cli._make_bull_config().limits.max_open==3
    assert cli._make_hawk_config().limits.max_open==10
