"""Only new opt-in observers; baseline runner is unchanged."""
from decimal import Decimal as D
import pytest
from backend.v3.features.indicators import Bar
from backend.v3.observability.opportunity_scan import scan_closed_minutes, slot_due
from backend.v3.observability.liquidity_quote import assess_book, BookSample

NOW=300_000_000

def candles(now=NOW, symbol='BTCUSDT', up=True, gap=False, stale=False, volume=True):
    end = now // 60_000 * 60_000 - (2*60_000 if stale else 0)
    out=[]
    for i in range(25):
        ts=end-25*60_000+i*60_000
        if gap and i == 10: ts+=1
        close=D('100') + ((D(i)/D(10)) if up else (-D(i)/D(10)))
        out.append(Bar(ts,close,close+D('1'),close-D('1'),close,D('5') if i<20 or not volume else D('15')))
    return out


def book(bid='99.5', ask='100.5', now=NOW):
    return BookSample('BTCUSDT',now-1000,((D(bid),D('2')),(D('99'),D('5'))),
                      ((D(ask),D('2')),(D('101'),D('5'))))


def test_slot_5m_without_waking_ai():
    assert slot_due(NOW,None)==NOW//300000
    assert slot_due(NOW+20000,NOW//300000) is None
    assert slot_due(NOW+300000,NOW//300000)==NOW//300000+1

@pytest.mark.parametrize('now,slot',[(0,None),(-1,None),(NOW,-1),(NOW,1.2)])
def test_invalid_clock(now,slot):
    with pytest.raises(ValueError,match='invalid_scan_clock'): slot_due(now,slot)


def test_scanner_returns_ordered_only_observations():
    data={'BTCUSDT':candles(),'ETHUSDT':candles(up=False)}
    report=scan_closed_minutes(now_ms=NOW,bars_by_symbol=data)
    assert report.observational_only
    assert {x.side_bias for x in report.candidates}=={'LONG','SHORT'}
    assert report.candidates[0].rank_score>=report.candidates[-1].rank_score
    assert report.candidates[0].volume_ratio>1


def test_scanner_no_duplicate_tick():
    assert scan_closed_minutes(now_ms=NOW,bars_by_symbol={'BTCUSDT':candles()},previous_slot=NOW//300000) is None

@pytest.mark.parametrize('problem,reason',[(dict(gap=True),'invalid_candles'),(dict(stale=True),'stale_candles')])
def test_bad_market_is_excluded(problem,reason):
    report=scan_closed_minutes(now_ms=NOW,bars_by_symbol={'BTCUSDT':candles(**problem)})
    assert report.candidates==()
    assert report.excluded==( ('BTCUSDT',reason),)


def test_missing_bar_excluded_and_not_faked():
    report=scan_closed_minutes(now_ms=NOW,bars_by_symbol={'BTCUSDT':candles()[:10]})
    assert report.excluded==( ('BTCUSDT','short_history'),)


def test_unclosed_candle_rejected():
    bars=candles()
    last=bars[-1]
    bars[-1]=Bar(NOW, last.open,last.high,last.low,last.close,last.volume)
    report=scan_closed_minutes(now_ms=NOW,bars_by_symbol={'BTCUSDT':bars})
    assert report.candidates==()
    assert report.excluded[0][1] in ('invalid_candles','unclosed_candle')


def test_invalid_symbol_and_topk():
    with pytest.raises(ValueError):scan_closed_minutes(now_ms=NOW,bars_by_symbol={'abc':candles()})
    with pytest.raises(ValueError):scan_closed_minutes(now_ms=NOW,bars_by_symbol={'BTCUSDT':candles()},top_k=0)


def test_scan_topk_stable():
    a=candles(); b=candles()
    r=scan_closed_minutes(now_ms=NOW,bars_by_symbol={'ETHUSDT':b,'BTCUSDT':a},top_k=1)
    assert len(r.candidates)==1
    assert r.candidates[0].symbol=='BTCUSDT'


def test_book_quote_is_observation_only():
    r=assess_book(now_ms=NOW,book=book(),side='LONG',requested_notional_usdt=D('100'))
    assert r.status=='OBSERVED' and r.observational_only
    assert r.spread_bps>0 and r.impact_bps>0


def test_no_book_is_unknown_not_safe():
    r=assess_book(now_ms=NOW,book=None,side='LONG',requested_notional_usdt=D('100'))
    assert r.status=='UNKNOWN' and r.spread_bps is None


def test_stale_and_future_book_unknown():
    assert assess_book(now_ms=NOW,book=book(now=NOW-4000),side='LONG',requested_notional_usdt=D('10')).status=='UNKNOWN'
    b=book(); b=BookSample(b.symbol,NOW+1,b.bids,b.asks)
    assert assess_book(now_ms=NOW,book=b,side='LONG',requested_notional_usdt=D('10')).status=='UNKNOWN'


def test_crossed_book_invalid():
    assert assess_book(now_ms=NOW,book=book(bid='101',ask='100'),side='LONG',requested_notional_usdt=D('10')).status=='INVALID'


def test_insufficient_depth_is_not_safe():
    q=assess_book(now_ms=NOW,book=book(),side='LONG',requested_notional_usdt=D('100000'))
    assert q.status=='INSUFFICIENT' and q.impact_bps is None


def test_short_uses_bid_depth():
    q=assess_book(now_ms=NOW,book=book(),side='SHORT',requested_notional_usdt=D('100'))
    assert q.status=='OBSERVED'

@pytest.mark.parametrize('wrong', ['10',D(0),D('NaN'),D('-10')])
def test_invalid_notional_rejected(wrong):
    with pytest.raises(ValueError):
        assess_book(now_ms=NOW,book=book(),side='LONG',requested_notional_usdt=wrong)


def test_unsorted_levels_invalid():
    b=book(); b=BookSample(b.symbol,b.timestamp_ms,b.bids,((D('101'),D('5')),(D('100.5'),D('3'))))
    assert assess_book(now_ms=NOW,book=b,side='LONG',requested_notional_usdt=D('100')).status=='INVALID'


def test_no_global_side_effects(tmp_path):
    before=set(tmp_path.iterdir())
    scan_closed_minutes(now_ms=NOW,bars_by_symbol={'BTCUSDT':candles()})
    assess_book(now_ms=NOW,book=book(),side='LONG',requested_notional_usdt=D('10'))
    assert set(tmp_path.iterdir())==before
