"""Only supplemental trend information for Claude; no changes to trade logic."""

import numpy as np
import pytest

from desk.brain import build_prompt
from desk.signals import Reading, ema, read_symbol
from desk.trend_change import H4_MS, HOUR_MS, advisory


def bars(n, period, end, start=100, last=None):
    # n complete, contiguous candles ending exactly at `end` UTC ms.
    t = end - np.arange(n, 0, -1, dtype=np.int64) * period
    c = np.full(n, float(start))
    if last is not None:
        c[-1] = last
    return np.column_stack([t, c, c * 1.01, c * .99, c, np.full(n, 10.)])


NOW = 20_000 * H4_MS


@pytest.mark.parametrize('close,expected',[(110, 'UP_CROSS'),(90, 'DOWN_CROSS'),(100,'NONE')])
def test_1h_cross_on_closed_bar(close,expected):
    one=bars(60,HOUR_MS,NOW,last=close)
    four=bars(200,H4_MS,NOW)
    out=advisory(one,four,NOW,ema_fn=ema)
    assert out == {'event':expected,'h4_bias':'NEUTRAL','asof_ms':NOW}


def test_4h_bias_reports_direction_without_creating_trade():
    one=bars(60,HOUR_MS,NOW,last=110)
    for last,expect in [(130,'UP'),(70,'DOWN')]:
        a=advisory(one,bars(200,H4_MS,NOW,last=last),NOW,ema_fn=ema)
        assert a['event']=='UP_CROSS'
        assert a['h4_bias']==expect


def test_does_not_read_unclosed_hour_or_count_it_as_cross():
    one=bars(60,HOUR_MS,NOW)
    future=np.array([[NOW,100,112,99,110,10.]],dtype=float)
    out=advisory(np.vstack([one,future]),bars(200,H4_MS,NOW),NOW+HOUR_MS//2,ema_fn=ema)
    assert out['event']=='NONE'
    assert out['asof_ms']==NOW


@pytest.mark.parametrize('problem', ['missing','stale','gap','nan','bad_ohlc','short'])
def test_fail_to_unknown_never_invents_change(problem):
    one=bars(60,HOUR_MS,NOW,last=110)
    now=NOW
    if problem=='missing':one=one[:0]
    if problem=='short':one=one[-59:]
    if problem=='stale':now=NOW+HOUR_MS
    if problem=='gap':one[-2,0]-=HOUR_MS
    if problem=='nan':one[-1,4]=float('nan')
    if problem=='bad_ohlc':one[-1,2]=1
    out=advisory(one,bars(200,H4_MS,NOW),now,ema_fn=ema)
    assert out['event']=='UNKNOWN'
    assert out['asof_ms'] is None


def test_four_hour_history_insufficient_does_not_hide_valid_hour_cross():
    out=advisory(bars(60,HOUR_MS,NOW,last=110),bars(60,H4_MS,NOW),NOW,ema_fn=ema)
    assert out['event']=='UP_CROSS'
    assert out['h4_bias']=='UNKNOWN'


def test_evidence_is_only_passed_into_existing_claude_prompt():
    reading=Reading(symbol='BTCUSDT',price=100.,side=-1,score=72,long_score=25,short_score=72,
                    facts={'rsi1h':45,'ema50_200_4h':'giu','daily_trend':'trend 1d bear',
                           'vol_ratio':1.,'trend_change':'UP_CROSS','trend_change_h4':'DOWN',
                           'trend_change_asof_ms':NOW})
    snap={'equity':1000,'cash':1000,'margin':0,'n_open':0,'day_pnl':0,'halt':''}
    prompt=build_prompt(snap,[reading],[],[],"")
    assert 'SHORT 72/100 (L25/S72)' in prompt
    assert 'cambio_trend_1h=UP_CROSS' in prompt
    assert 'contesto_trend_4h=DOWN' in prompt
    assert 'solo consultivo: non forzare LONG/SHORT' in prompt
    reading.facts.pop('trend_change')
    assert 'cambio_trend_1h=' not in build_prompt(snap,[reading],[],[],"")


def test_read_symbol_scores_independent_of_advisory(monkeypatch):
    from desk import trend_change
    # 15m bars ~60 full 4h+; use valid OHLCV and last bar in completed 15m.
    arr=bars(60*16,900_000,NOW,last=110)
    original=read_symbol('BTCUSDT',arr,NOW)
    assert original is not None
    assert original.facts['trend_change'] in ('UP_CROSS','DOWN_CROSS','NONE','UNKNOWN')
    monkeypatch.setattr(trend_change,'advisory',lambda *a,**kw:
                        {'event':'DOWN_CROSS','h4_bias':'UP','asof_ms':NOW})
    changed=read_symbol('BTCUSDT',arr,NOW)
    assert (original.side,original.score,original.long_score,original.short_score,
            original.sl_pct,original.tp_pct,original.trade_type) == (
            changed.side,changed.score,changed.long_score,changed.short_score,
            changed.sl_pct,changed.tp_pct,changed.trade_type)
    assert changed.facts['trend_change']=='DOWN_CROSS'


def test_advisory_never_accepts_nonnumeric_time():
    x=advisory(bars(60,HOUR_MS,NOW),bars(200,H4_MS,NOW),True,ema_fn=ema)
    assert x['event']=='UNKNOWN'
