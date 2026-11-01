"""Offline Bitget v3 capture -> causal LONG context for SHADOW research only.

Never contacts exchange/broker, never executes orders. Only first observed
snapshots; later updates are NOT assumed to be finalized candles. The Frozen
LONG engine remains an external, independently hashed laboratory dependency.
"""
from __future__ import annotations
from collections import defaultdict
from decimal import Decimal
import hashlib
import json
import zipfile

TF_MS = {'1m': 60_000,'15m': 900_000,'1H': 3_600_000,'4H': 14_400_000}
TF_INTERNAL = {'1m':'1m','15m':'15m','1H':'1h','4H':'4h'}
SYMBOLS = ('BTCUSDT','ETHUSDT')

class FeedUnavailable(ValueError):
    pass

def _manifest(archive, prefix):
    listing = archive.read(prefix+'/SHA256SUMS.txt').decode().splitlines()
    seen = set()
    for line in listing:
        sha, sep, rel = line.partition('  ')
        if sep != '  ' or len(sha)!=64 or '/' in rel or rel in seen:
            raise FeedUnavailable('bad_manifest')
        seen.add(rel)
        if hashlib.sha256(archive.read(prefix+'/'+rel)).hexdigest()!=sha:
            raise FeedUnavailable('manifest_hash_mismatch')
    return seen

def startup_contexts(capture_zip):
    """Only infer what had arrived at first valid quotes after 4 TF snapshots.

    Startup closed history is *observed at snapshot receipt*, not at its
    historical period close. No fabricated quote, candle or wallet state.
    """
    snapshots = {}
    quotes = defaultdict(list)
    with zipfile.ZipFile(capture_zip) as z:
        dirs = {i.filename.split('/',1)[0] for i in z.infolist() if '/' in i.filename}
        dirs = {d for d in dirs if d.startswith('mtf_')}
        if len(dirs)!=1:
            raise FeedUnavailable('capture_folder_ambiguous')
        directory=next(iter(dirs))
        files=_manifest(z,directory)
        summ=json.loads(z.read(directory+'/capture_summary.json'))
        if summ.get('schema')!='live_mtf_capture_01' or summ.get('duration_completed') is not True:
            raise FeedUnavailable('capture_incomplete')
        if summ.get('errors') or summ.get('ever_acked_subscriptions')!=10:
            raise FeedUnavailable('capture_errors_or_missing_acks')
        for part in summ.get('raw_parts',[]):
            if part not in files:
                raise FeedUnavailable('missing_manifested_raw_part')
            for ln in z.open(directory+'/'+part):
                record=json.loads(ln)
                raw=record.get('raw_frame')
                if not isinstance(raw,str) or hashlib.sha256(raw.encode()).hexdigest()!=record.get('raw_sha256'):
                    raise FeedUnavailable('frame_hash_mismatch')
                ts=record.get('received_at_ms')
                if type(ts) is not int:
                    raise FeedUnavailable('frame_receipt_missing')
                try:
                    payload=json.loads(raw)
                except (ValueError,TypeError):
                    continue  # literal 'pong' is not a market event
                if not isinstance(payload,dict):
                    continue
                arg=payload.get('arg') or {}
                symbol=arg.get('symbol')
                if symbol not in SYMBOLS:continue
                action=payload.get('action')
                if arg.get('topic')=='kline' and action=='snapshot' and arg.get('interval') in TF_MS:
                    key=(symbol,arg['interval'])
                    if key not in snapshots:
                        if not isinstance(payload.get('data'),list):
                            raise FeedUnavailable('malformed_snapshot')
                        snapshots[key]=(ts,payload['data'])
                elif arg.get('topic')=='books1' and action in ('snapshot','update'):
                    for item in payload.get('data') or []:
                        try:
                            bid=Decimal(item['b'][0][0]);ask=Decimal(item['a'][0][0])
                        except (TypeError,KeyError,ValueError,IndexError) as exc:
                            raise FeedUnavailable('malformed_bbo') from exc
                        if not 0<bid<=ask:raise FeedUnavailable('crossed_bbo')
                        quotes[symbol].append((ts,float(bid),float(ask)))
    result={}
    for sym in SYMBOLS:
        if any((sym,tf) not in snapshots for tf in TF_MS):
            raise FeedUnavailable('missing_tf_snapshot')
        ready=max(snapshots[sym,tf][0] for tf in TF_MS)
        matches=[q for q in quotes[sym] if ready<=q[0]<=ready+2000]
        if not matches:raise FeedUnavailable('quote_not_observed_at_startup')
        as_of,bid,ask=matches[0]
        bars={}
        for tf,width in TF_MS.items():
            receipt,entries=snapshots[sym,tf]
            clean=[]
            opens=set()
            for row in entries:
                if not isinstance(row,dict):
                    raise FeedUnavailable('malformed_kline')
                try:
                    start=int(row['start'])
                    values={k:float(Decimal(row[k])) for k in ('open','high','low','close','volume')}
                except (ValueError,TypeError,KeyError) as exc:
                    raise FeedUnavailable('malformed_kline') from exc
                close=start+width
                if close>receipt:continue # Still forming at snapshot receipt
                if start%width or start in opens or not (
                    values['low']>0 and values['low']<=min(values['open'],values['close'])
                    and values['high']>=max(values['open'],values['close']) and values['volume']>=0):
                    raise FeedUnavailable('invalid_historical_snapshot')
                opens.add(start)
                clean.append({**values,'close_ms':close,'available_at_ms':receipt,
                              'availability':'observed_snapshot_receipt'})
            clean.sort(key=lambda x:x['close_ms'])
            if len(clean)<200 or any(b['close_ms']-a['close_ms']!=width
                                   for a,b in zip(clean,clean[1:])):
                raise FeedUnavailable('slow_warmup_or_gap')
            bars[TF_INTERNAL[tf]]=clean
        result[sym]={'symbol':sym,'bars':bars,
                     'quote':{'bid':bid,'ask':ask,'available_at_ms':as_of},
                     'source':'bitget_verified_capture_startup_snapshots',
                     'live_close_ack_observed':False,'execution_verified':False}
    return result
