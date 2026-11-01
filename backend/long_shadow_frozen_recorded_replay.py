"""Offline REAL Bitget capture + genuine frozen LONG V6.1.1 replay.

Inputs are explicit external files, NEVER fetched or fabricated. This script
performs no network requests, no wallet reads/writes and no order operations.
It intentionally uses clearly synthetic position flags for three consumers.
The historical event clock is derived from observed WS receipts; this is not
an executable or present-time trading signal.

Usage:
 PYTHONPATH=backend python backend/long_shadow_frozen_recorded_replay.py \
   --capture /research/SuperBot_LONG_LIVE_MTF_RESULT_20261101T161618Z.zip \
   --engine /research/frozen_v611/superbot_long_lab/engine.py
"""
from __future__ import annotations

import argparse
from collections import defaultdict, Counter
import hashlib
import json
from pathlib import Path
import zipfile

from long_shadow_offline_probe import frozen_engine, PINNED_ENGINE_SHA256
from long_shadow_rest_closed import (
    parse_closed_response, INTERVALS, SYMBOLS, TF_INTERNAL,
)

def _archive_inputs(path):
    with zipfile.ZipFile(path) as z:
        files = z.namelist()
        roots = {n.rsplit('/rest_responses.jsonl',1)[0]
                 for n in files if n.endswith('/rest_responses.jsonl')}
        if len(roots) != 1:
            raise ValueError('missing_or_ambiguous_rest_capture')
        root = next(iter(roots))
        snapshots = {}
        for line in z.open(root+'/rest_responses.jsonl'):
            record = json.loads(line)
            if record.get('error') is not None:
                raise ValueError('recorded_rest_error')
            raw = record['raw_response']
            if hashlib.sha256(raw.encode()).hexdigest()!=record['response_sha256']:
                raise ValueError('rest_raw_sha_mismatch')
            symbol = record['symbol']
            interval = record['interval']
            if symbol not in SYMBOLS or interval not in INTERVALS:
                raise ValueError('unexpected_capture_symbol_interval')
            key = symbol,interval
            if key in snapshots:
                raise ValueError('duplicate_rest_capture')
            start = int(record['request_wall_ns']) // 1_000_000
            received = int(record['response_wall_ns']) // 1_000_000
            payload = json.loads(raw)
            bars = parse_closed_response(payload,symbol,interval,
                                         started_ms=start,received_ms=received)
            snapshots[key] = received,bars
        if set(snapshots)!={(s,t) for s in SYMBOLS for t in INTERVALS}:
            raise ValueError('incomplete_captured_rest_series')
        quotes = defaultdict(list)
        names = [n for n in files if n.startswith(root+'/ws_raw_frames_')
                 and n.endswith('.jsonl')]
        if not names:
            raise ValueError('missing_capture_ws_frames')
        for name in sorted(names):
            for line in z.open(name):
                item = json.loads(line)
                raw = item['raw_frame']
                if hashlib.sha256(raw.encode()).hexdigest()!=item['raw_sha256']:
                    raise ValueError('ws_raw_sha_mismatch')
                if raw == 'pong':
                    continue
                event = json.loads(raw)
                arg = event.get('arg') or {}
                symbol = arg.get('symbol')
                if arg.get('topic') != 'books1' or symbol not in SYMBOLS:
                    continue
                for quote in event.get('data',[]):
                    bid = float(quote['b'][0][0])
                    ask = float(quote['a'][0][0])
                    if not 0 < bid <= ask:
                        raise ValueError('invalid_historical_bbo')
                    quotes[symbol].append((item['received_at_ms'],bid,ask))
    return snapshots,quotes

def replay(capture,engine_file):
    # This loader refuses ANY modified version of the original frozen file.
    engine = frozen_engine(engine_file)
    snapshots,quotes = _archive_inputs(capture)
    records = []
    for symbol in SYMBOLS:
        last_rest = max(snapshots[symbol,tf][0] for tf in INTERVALS)
        matching = next(((time,bid,ask) for time,bid,ask in quotes[symbol]
                         if last_rest <= time <= last_rest+75000),None)
        if matching is None:
            raise ValueError('no_actual_post_rest_ws_quote')
        as_of,bid,ask = matching
        frames = {TF_INTERNAL[tf]: snapshots[symbol,tf][1]
                  for tf in INTERVALS}
        for consumer in ('hawk','bull','brain'):
            # Explicit synthetic wallet conditions, NOT actual balances.
            flags = {
                'short_open': consumer=='hawk' and symbol=='BTCUSDT',
                'long_open': consumer=='bull' and symbol=='ETHUSDT',
            }
            for setup in ('CONTINUATION','REVERSAL'):
                p = engine.Parameters(
                    mode='advisory' if consumer=='brain' else 'shadow',
                    setup=setup)
                result = engine.evaluate_long(
                    {'symbol':symbol,'bars':frames,
                     'quote':{'bid':bid,'ask':ask,
                              'available_at_ms':as_of},**flags},
                    as_of,p)
                if (result.get('authority')!='advisory_only' or
                    result.get('symbol')!=symbol or
                    result.get('mode')!=p.mode or
                    result.get('setup')!=setup or
                    result.get('decision') not in ('CANDIDATE','NO_TRADE') or
                    any(result.get(k) is not False for k in (
                        'may_authorize_entry','may_block_entry',
                        'may_modify_scores','may_execute_exit'))):
                    raise ValueError('frozen_engine_authority_contract_fail')
                records.append({
                    'symbol':symbol,'consumer':consumer,'setup':setup,
                    'decision':result['decision'],'reasons':result['reasons'],
                    'data_grade':result['data_grade'],
                    'quote_received_at_ms':as_of,
                    'last_rest_received_at_ms':last_rest,
                    'wallet_source':'EXPLICIT_SYNTHETIC_FLAGS_ONLY',
                    'can_execute_orders':False,
                })
    return {
        'schema':'superbot-frozen-v611-real-captured-rest-ws-replay-v1',
        'frozen_engine_sha256':PINNED_ENGINE_SHA256,
        'capture_provenance':'RECORDED_REAL_BITGET_PUBLIC',
        'historical_clock_not_live':True,
        'real_frozen_engine_was_evaluated':True,
        'wallet_provenance':'THREE_SYNTHETIC_PAPER_SCENARIOS',
        'orders_created':0,'paper_eligible':False,
        'records':records,
    }

def main():
    p = argparse.ArgumentParser(
        description='Offline frozen LONG replay, no API keys/market orders')
    p.add_argument('--capture',required=True)
    p.add_argument('--engine',required=True)
    args=p.parse_args()
    r=replay(args.capture,args.engine)
    print(json.dumps({'schema':r['schema'],
                      'real_frozen_engine_was_evaluated':True,
                      'engine_sha':r['frozen_engine_sha256'],
                      'records':len(r['records']),
                      'decisions':dict(Counter(x['decision'] for x in r['records'])),
                      'reasons':dict(Counter(
                         reason for x in r['records'] for reason in x['reasons'])),
                      'orders_created':0,'paper_eligible':False},
                     sort_keys=True))

if __name__=='__main__':
    main()
