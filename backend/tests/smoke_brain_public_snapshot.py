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
            account.tick(markets,limits,now)
            before=account.brain.store.load()
            path=Path(tmp)/'snapshot.json'
            atomic_write(path,build_account_snapshot(account,now,markets))
            view=read_published_snapshot(path,now,layout='single')
            assert view['status']=='ok' and view['profiles']['brain']['online']
            assert view['profiles']['brain']['positions']==[]
            stale=read_published_snapshot(path,now+62000,layout='single')
            assert stale['snapshot_stale'] and not stale['profiles']['brain']['online']
            assert account.brain.store.load()==before, 'reader_modified_wallet'
            print(json.dumps({'status':'passed','python':sys.version.split()[0],
                'symbol':'BTC','closed_1m':len([r for r in one if r[0]+60000<=now]),
                'closed_5m':len([r for r in five if r[0]+300000<=now]),
                'quote_age_ms':now-quote['BTC']['ts_ms'],
                'snapshot':'fresh_then_stale','wallet':'temporary_paper_empty',
                'ai_calls':0,'exchange_orders':0}))
        finally:
            account.close()


if __name__=='__main__':
    main()
