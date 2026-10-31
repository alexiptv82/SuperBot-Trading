"""Explicit public-network smoke; temporary PAPER wallet, no AI or credentials.

Run with backend and the pinned app backend on PYTHONPATH.
Not collected by pytest: requires public Bitget availability.
"""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
import time

from director.brain_free.feeds import candles,contracts,quotes
from director.brain_scalp.config import HAWK
from director.brain_scalp.coordinator import BrainAccount
from director.brain_scalp.market_bridge import validate_feed_snapshot
from director.brain_scalp.snapshot import build_account_snapshot,atomic_write
from director.brain_scalp.position_review import build_position_review
from brain_scalp_snapshot_view import read_published_snapshot


def main():
    with ThreadPoolExecutor(3) as pool:
        contract_job=pool.submit(contracts,symbols=('BTC',))
        minute_job=pool.submit(candles,'BTC','1m')
        five_job=pool.submit(candles,'BTC','5m')
        limits=contract_job.result()
        one=minute_job.result();five=five_job.result()
    quote=quotes(symbols=('BTC',))
    now=time.time_ns()//1_000_000
    assert 'BTC' in limits and 'BTC' in quote
    assert 0<=now-quote['BTC']['ts_ms']<=3000, 'quote_not_fresh'
    for rows,duration in ((one,60000),(five,300000)):
        closed=[r for r in rows if r[0]+duration<=now]
        assert len(closed)>=100, 'not_enough_closed_bars'
        assert all(b[0]-a[0]==duration for a,b in zip(closed,closed[1:])), 'candle_gap'
        assert 0<=now-(closed[-1][0]+duration)<duration, 'stale_candles'
    markets,limits=validate_feed_snapshot(
        {'BTC':{'bars':{'1m':one,'5m':five},'quote':quote['BTC']}},limits)
    spec=replace(HAWK,name='brain',account_id='brain-scalp-single-paper',
                 start_cash=2000,max_margin_total=1600)
    with tempfile.TemporaryDirectory(prefix='brain-public-smoke-') as tmp:
        account=BrainAccount(tmp,spec=spec,initialize=True,now_ms=now)
        try:
            px=quote['BTC']['price']
            # Explicit synthetic proposal at the real quote; no model decision.
            proposal={'plan_id':'publicsmokebtc','symbol':'BTC','side':1,
                'created_ms':quote['BTC']['ts_ms'],'expires_ms':now+240000,'trigger':'break_above',
                'trigger_price':px,'stop':px*.998,'target':px*1.02,
                'margin':110.,'leverage':10,'hold_max_ms':3600000,
                'protect_after_usd':5.,'take_net_usd':10.,
                'reason':'Synthetic proposal for public feed plumbing test',
                'invalidation':'Temporary test account only'}
            account.brain.submit(proposal,now,limits,quote)
            tick=account.tick(markets,limits,now)
            before=account.brain.store.load()
            assert 'BTC' in before['positions'], ('temporary_position_not_opened',tick)
            path=Path(tmp)/'snapshot.json'
            atomic_write(path,build_account_snapshot(account,now,markets))
            view=read_published_snapshot(path,now,layout='single')
            assert view['status']=='ok' and view['profiles']['brain']['online']
            position=view['profiles']['brain']['positions'][0]
            assert position['symbol']=='BTC' and position['price_status']=='fresh'
            assert position['net_close_estimate'] is not None
            request=build_position_review(account,markets,now,now+30000)
            assert request is not None
            for unavailable in ({}, {'BTC':{'quote':dict(quote['BTC'],ts_ms=now-11000)}}):
                degraded=build_account_snapshot(account,now,unavailable)
                atomic_write(path,degraded)
                broken=read_published_snapshot(path,now,layout='single')
                item=broken['profiles']['brain']['positions'][0]
                assert item['price_status']=='unavailable'
                assert item['net_close_estimate'] is None
                try:
                    build_position_review(account,unavailable,now,now+30000)
                except ValueError as exc:
                    assert str(exc)=='review_no_fresh_positions'
                else:
                    raise AssertionError('review_accepted_missing_or_stale_quote')
            atomic_write(path,build_account_snapshot(account,now,markets))
            stale=read_published_snapshot(path,now+62000,layout='single')
            assert stale['snapshot_stale'] and not stale['profiles']['brain']['online']
            assert account.brain.store.load()==before, 'reader_modified_wallet'
            print(json.dumps({'status':'passed','python':sys.version.split()[0],
                'symbol':'BTC','closed_1m':len([r for r in one if r[0]+60000<=now]),
                'closed_5m':len([r for r in five if r[0]+300000<=now]),
                'quote_age_ms':now-quote['BTC']['ts_ms'],
                'snapshot':'fresh_missing_quote_stale_quote_expired',
                'wallet':'temporary_paper_one_synthetic_position',
                'ai_calls':0,'exchange_orders':0}))
        finally:
            account.close()


if __name__=='__main__':
    main()
