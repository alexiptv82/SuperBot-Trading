"""Explicit research-only LONG Shadow watcher. DOES NOT connect to Bitget.

Reads growing public-capture JSONL via CaptureTail and wallets in read-only
mode. Optionally evaluates SHA-pinned frozen LONG engine and publishes ONLY
non-executable advice under a separate, private diagnostic directory.

NO DEFAULT BACKGROUND SERVICE. NO DEPLOY/ORDERS. No secret/key handling.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile
import time

from long_shadow_offline_probe import frozen_engine
from long_shadow_observer import evaluate_observation
from long_shadow_stream_runner import CaptureTail
from long_shadow_rest_closed import RestClosedOverlay, public_candles, FeedNotReady

CONSUMERS = ('hawk', 'bull', 'brain')


def _is_nested(a, b):
    return a == b or a in b.parents or b in a.parents


def guarded_output_directory(output_dir, roots, input_dir):
    out = Path(output_dir)
    if out.is_symlink():
        raise ValueError('output_directory_symlink')
    dst = out.resolve()
    source = Path(input_dir).resolve()
    if _is_nested(dst, source):
        raise ValueError('output_collides_with_input')
    for item in roots.values():
        if _is_nested(dst, Path(item).resolve()):
            raise ValueError('output_collides_with_wallet')
    dst.mkdir(parents=True, exist_ok=True, mode=0o700)
    if dst.is_symlink() or not dst.is_dir():
        raise ValueError('output_directory_not_safe')
    return dst


def _write_json_atomic(directory, basename, content):
    """Only diagnostic output, never writes to the wallet or input collector."""
    if basename not in ('observer_state.json','hawk.json','bull.json','brain.json'):
        raise ValueError('unexpected_output_name')
    payload = (json.dumps(content,sort_keys=True,allow_nan=False)+'\n').encode()
    if len(payload) > 400_000:
        raise ValueError('output_too_large')
    fd, tmp = tempfile.mkstemp(prefix='.shadow.', dir=str(directory))
    try:
        os.chmod(tmp,0o600)
        with os.fdopen(fd,'wb') as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, directory / basename)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def publish_observation(report, directory):
    """Read-only format for /api/long/shadow (external record still unverified)."""
    if (report.get('schema') != 'long-shadow-observer-v1' or
            report.get('can_execute_orders') is not False or
            report.get('paper_eligible') is not False or
            report.get('orders_created') != 0):
        raise ValueError('invalid_observer_report')
    _write_json_atomic(directory,'observer_state.json',report)
    for consumer in CONSUMERS:
        subset = [r for r in report['records'] if r.get('consumer') == consumer]
        if len(subset) != 4 or any(r.get('authority') != 'advisory_only' or
                                  r.get('can_execute_orders') is not False
                                  for r in subset):
            raise ValueError('invalid_consumer_records')
        # The current dashboard accepts one record per account; prefer an
        # observed candidate while retaining ALL records in observer_state.
        chosen = next((r for r in subset if r['decision']=='CANDIDATE'),subset[0])
        _write_json_atomic(directory,consumer+'.json',chosen)


def main():
    parser = argparse.ArgumentParser(
        description='Isolated LONG capture observer; advisory-only, NO ORDERS.')
    parser.add_argument('--input-dir',required=True)
    parser.add_argument('--output-dir',required=True)
    parser.add_argument('--hawk-wallet',required=True)
    parser.add_argument('--bull-wallet',required=True)
    parser.add_argument('--brain-wallet',required=True)
    parser.add_argument('--brain-source',choices=['free','pilot'])
    parser.add_argument('--frozen-engine',help='SHA-pinned engine.py path')
    parser.add_argument('--enable-rest-closed',action='store_true',
                        help='EXPLICIT opt-in to Bitget public HTTPS candle GETs; no private API')
    parser.add_argument('--rest-refresh-seconds',type=int,default=30,
                        help='minimum 15s; refresh 8 public closed candle series')
    parser.add_argument('--enable-advice',action='store_true',
                        help='Opt in to READ-ONLY engine evaluation; NOT trading')
    parser.add_argument('--seconds',type=int,default=60,
                        help='0: loop until operator stops; default 60 seconds')
    parser.add_argument('--poll-seconds',type=float,default=1.0)
    parser.add_argument('--evaluate-every-seconds',type=int,default=30)
    args=parser.parse_args()
    if (args.seconds < 0 or not .1 <= args.poll_seconds <= 30 or
            not 5 <= args.evaluate_every_seconds <= 3600 or
            not 15 <= args.rest_refresh_seconds <= 300):
        parser.error('invalid timing arguments')
    if args.enable_rest_closed and not args.enable_advice:
        parser.error('REST polling requires explicit --enable-advice')
    if args.enable_advice and not args.frozen_engine:
        parser.error('explicit SHA-pinned engine required for advice')
    roots={'hawk':args.hawk_wallet,'bull':args.bull_wallet,'brain':args.brain_wallet}
    output=guarded_output_directory(args.output_dir,roots,args.input_dir)
    # Pinned load or fail BEFORE processing any market/wallet data.
    engine=frozen_engine(args.frozen_engine) if args.enable_advice else None
    tail=CaptureTail(args.input_dir)
    rest=RestClosedOverlay(tail.feed) if args.enable_rest_closed else None
    started=time.monotonic()
    last_eval=None
    last_rest=None
    while args.seconds == 0 or time.monotonic()-started < args.seconds:
        tail.poll()  # raises on corrupt, truncated or symlink parts
        now_ms=int(time.time()*1000)  # never backdate to captured frames
        if rest is not None and (last_rest is None or
                                 time.monotonic()-last_rest>=args.rest_refresh_seconds):
            # 8 sequential PUBLIC GETs only; never private API credentials.
            # Failure invalidates previous REST candles: NO_TRADE thereafter.
            last_rest=time.monotonic()
            try:
                rest.refresh(public_candles)
            except FeedNotReady as exc:
                print(json.dumps({'rest_closed_status':'NOT_READY',
                                  'reason':str(exc),'orders_created':0}),
                      flush=True)
            # New public GETs can take seconds. Re-poll the WS writer to
            # acquire quotes whose receipt is AFTER the latest REST fetch.
            tail.poll()
            now_ms=int(time.time()*1000)
        if last_eval is None or (time.monotonic()-last_eval >= args.evaluate_every_seconds):
            result=evaluate_observation(
                feed=rest if rest is not None else tail.feed,
                now_ms=now_ms, roots=roots,
                brain_source=args.brain_source, engine=engine,
                enabled=args.enable_advice)
            publish_observation(result,output)
            print(json.dumps({'as_of_ms':now_ms,'orders_created':0,
                              'candidates':sum(r['decision']=='CANDIDATE'
                                               for r in result['records']),
                              'no_trade':sum(r['decision']=='NO_TRADE'
                                             for r in result['records'])}),flush=True)
            last_eval=time.monotonic()
        time.sleep(args.poll_seconds)


if __name__=='__main__':
    main()
