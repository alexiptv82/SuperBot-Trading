"""One-shot public market + SYNTHETIC wallet LONG staging probe.

Never reads actual accounts or production secrets. Eight real public Bitget
REST candle GETs, followed by fresh public WebSocket books1 for BTC and ETH.
Feeds the read-only pipeline with three self-created PAPER wallet fixtures.

The engine used here is an explicit NO_TRADE STUB, not frozen V6.1.1.
This test verifies public market/network/wallet/API contract integration,
NOT the profitability or performance of the frozen LONG strategy.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time

import websocket

from long_shadow_stream import ObservedFeed, FeedNotReady
from long_shadow_rest_closed import RestClosedOverlay, public_candles
from long_shadow_observer import evaluate_observation
from long_shadow_observer_runner import publish_observation
from long_shadow_readonly import read_dashboard

WS_ENDPOINT = 'wss://ws.bitget.com/v3/ws/public'
SUBSCRIPTIONS = [
    {'instType':'usdt-futures','topic':'books1','symbol':'BTCUSDT'},
    {'instType':'usdt-futures','topic':'books1','symbol':'ETHUSDT'},
]


@dataclass(frozen=True)
class _StubParameters:
    mode: str
    setup: str


class _StagingStub:
    """Explicit research stub; must not be confused with real LONG V6.1.1."""
    Parameters = _StubParameters

    def evaluate_long(self, context, now, parameters):
        assert context['symbol'] in ('BTCUSDT','ETHUSDT')
        assert context['long_open'] in (False,True)
        assert context['short_open'] in (False,True)
        assert set(context['bars']) == {'1m','15m','1h','4h'}
        assert context['quote']['available_at_ms'] <= now
        return {
            'authority':'advisory_only','symbol':context['symbol'],
            'setup':parameters.setup,'mode':parameters.mode,
            'decision':'NO_TRADE','reasons':['STAGING_STUB_NOT_FROZEN_ENGINE'],
            'may_authorize_entry':False,'may_block_entry':False,
            'may_modify_scores':False,'may_execute_exit':False,
            'data_grade':'analysis','data_cutoff_ms':None,
        }


def _synthetic_wallets(parent, now):
    """Use same on-disk formats as app, but ONLY under isolated tmp root."""
    roots={a:parent/a for a in ('hawk','bull','brain')}
    for root in roots.values():
        root.mkdir(parents=True,mode=0o700)
    for name in ('hawk','bull'):
        data=roots[name]
        positions=({'BTC':{'symbol':'BTC','side':-1}}
                   if name=='hawk' else {'ETH':{'symbol':'ETH','side':1}})
        state=data/'state_v2.json'
        state.write_text(json.dumps({'main':{'name':'main','positions':positions}}))
        os.utime(state,ns=(now*1_000_000,now*1_000_000))
        (data/'heartbeat.json').write_text(json.dumps({'ts':now/1000}))
    with sqlite3.connect(roots['brain']/'brain.sqlite3') as db:
        db.execute('CREATE TABLE state(id INTEGER PRIMARY KEY,body TEXT)')
        db.execute('INSERT INTO state VALUES(1,?)',(json.dumps({
            'account_id':'brain-free-paper','mode':'paper',
            'positions':{},'heartbeat_ms':now}),))
    return roots


def _fresh_books_after_rest(feed, overlay):
    """Open a NEW WS socket AFTER REST to avoid buffered/stale market quotes."""
    socket=websocket.create_connection(
        WS_ENDPOINT,timeout=8,
        origin='https://www.bitget.com',
        enable_multithread=False)
    try:
        socket.settimeout(8)
        socket.send(json.dumps({'op':'subscribe','args':SUBSCRIPTIONS}))
        ack=set()
        deadline=time.monotonic()+25
        frames=0
        while time.monotonic() < deadline:
            raw=socket.recv()
            if not isinstance(raw,str):
                raise FeedNotReady('non_text_public_ws')
            received=int(time.time()*1000)
            wrapper={'raw_frame':raw,
                     'raw_sha256':hashlib.sha256(raw.encode()).hexdigest(),
                     'session':1,'received_at_ms':received}
            classification=feed.ingest(wrapper)
            frames+=1
            if raw!='pong':
                payload=json.loads(raw)
                if payload.get('event')=='error':
                    raise FeedNotReady('public_subscription_rejected')
                arg=payload.get('arg') or {}
                if payload.get('event')=='subscribe' and arg.get('topic')=='books1':
                    ack.add(arg.get('symbol'))
            if len(ack)==2:
                now=int(time.time()*1000)
                try:
                    contexts={s:overlay.context(s,now)
                              for s in ('BTCUSDT','ETHUSDT')}
                    return contexts,now,frames
                except FeedNotReady:
                    pass
        raise FeedNotReady('books1_both_fresh_quotes_not_observed')
    finally:
        socket.close()


def main():
    ws_feed=ObservedFeed()
    ws_feed.reset(1)  # new research session, no prior buffered prices
    closed=RestClosedOverlay(ws_feed)
    rest_status=closed.refresh(public_candles)  # eight public HTTPS GETs
    if rest_status.get('closed_series')!=8:
        raise FeedNotReady('not_all_public_rest_timeframes_ready')
    contexts,now,frames=_fresh_books_after_rest(ws_feed,closed)
    with tempfile.TemporaryDirectory(prefix='long-shadow-staging-synthetic-') as tmp:
        base=Path(tmp)
        roots=_synthetic_wallets(base/'wallets',now)
        report=evaluate_observation(
            feed=closed,now_ms=now,roots=roots,brain_source='free',
            engine=_StagingStub(),enabled=True)
        output=base/'only-diagnostic-output'
        output.mkdir(mode=0o700)
        publish_observation(report,output)
        dashboard=read_dashboard(roots=roots,shadow_dir=output,
                                 brain_source='free',now_ms=now)
        if (len(report['records'])!=12 or
                any(r['decision']!='NO_TRADE' for r in report['records']) or
                any(r['reasons']!=['STAGING_STUB_NOT_FROZEN_ENGINE']
                    for r in report['records']) or
                any(c['wallet_status']!='ok'
                    for c in dashboard['consumers'].values()) or
                any(c['advisory_status']!='unverified_external_record'
                    for c in dashboard['consumers'].values()) or
                report['orders_created']!=0 or report['can_execute_orders'] or
                dashboard['can_execute_orders'] or dashboard['enabled'] is not False):
            raise AssertionError('staging_readonly_contract_failed')
        if not dashboard['consumers']['hawk']['positions']['BTCUSDT']['short_open']:
            raise AssertionError('hawk_short_fixture_not_visible')
        if not dashboard['consumers']['bull']['positions']['ETHUSDT']['long_open']:
            raise AssertionError('bull_long_fixture_not_visible')
        if any(v['short_open'] or v['long_open']
               for v in dashboard['consumers']['brain']['positions'].values()):
            raise AssertionError('brain_empty_fixture_not_visible')

        summary={
            'schema':'long-shadow-public-data-synthetic-wallet-e2e-v1',
            'status':'PASS','source':'LIVE_PUBLIC_BITGET_MARKET',
            'wallets':'SYNTHETIC_PAPER_ONLY',
            'engine':'STUB_NO_TRADE_NOT_REAL_V611',
            'frozen_engine_evaluated':False,
            'rest_closed_series':rest_status['closed_series'],
            'books1_ack_count':2,'books1_received_frames':frames,
            'evaluated_records':len(report['records']),
            'visible_consumer_count':len(dashboard['consumers']),
            'wallets_modified':False,'orders_created':0,
            'paper_eligible':False,
            'limitations':'no real wallets, no frozen engine, no VPS/deploy'}
        print(json.dumps(summary,sort_keys=True),flush=True)


if __name__=='__main__':
    main()
