"""Read-only LONG shadow status projection for SuperBot dashboard.

No trading/broker imports, no state mutation, no networking, no fallback to
market/AI position flags. Caller may only observe statuses.
"""
from __future__ import annotations

from contextlib import closing
import json
import math
import os
from pathlib import Path
import sqlite3
import time

ACCOUNTS = ('hawk', 'bull', 'brain')
SYMBOLS = ('BTCUSDT', 'ETHUSDT')
MAX_JSON_BYTES = 2_000_000
DEFAULT_FRESH_MS = 20 * 60_000

class Unavailable(ValueError):
    pass

def _json_bounded(text):
    if not isinstance(text, str) or len(text.encode('utf8')) > MAX_JSON_BYTES:
        raise Unavailable('invalid_or_oversize_state')
    try:
        data = json.loads(text)
    except (ValueError, TypeError) as exc:
        raise Unavailable('invalid_json') from exc
    if not isinstance(data, dict):
        raise Unavailable('invalid_state')
    return data

def _safe_file(root, filename):
    if root.is_symlink():
        raise Unavailable('symlink_data_dir')
    path = root / filename
    if path.is_symlink() or not path.is_file():
        raise Unavailable('state_not_found')
    if path.stat().st_size > MAX_JSON_BYTES:
        raise Unavailable('oversize_state')
    return path

def _canonical(symbol):
    if not isinstance(symbol, str):
        raise Unavailable('invalid_symbol')
    s = symbol.upper()
    if s in ('BTC', 'ETH'):
        s += 'USDT'
    return s

def _positions(mapping):
    if not isinstance(mapping, dict):
        raise Unavailable('invalid_positions')
    found = {}
    for key, p in mapping.items():
        if not isinstance(p, dict):
            raise Unavailable('invalid_position')
        sym = _canonical(key)
        if 'symbol' in p and _canonical(p['symbol']) != sym:
            raise Unavailable('position_symbol_mismatch')
        side = p.get('side')
        if type(side) is not int or side not in (-1, 1):
            raise Unavailable('invalid_position_side')
        if sym in found:
            raise Unavailable('duplicate_symbol')
        found[sym] = 'LONG' if side == 1 else 'SHORT'
    return found

def _age_ok(ts, now_ms, fresh_ms):
    return type(ts) is int and 0 <= now_ms-ts <= fresh_ms

def _classic(root, consumer, now_ms, fresh_ms):
    path = _safe_file(root, 'state_v2.json')
    state = _json_bounded(path.read_text(encoding='utf8'))
    account = state.get('main')
    if not isinstance(account, dict) or account.get('name') != 'main':
        raise Unavailable('classic_account_mismatch')
    pos = _positions(account.get('positions'))
    seen_ms = path.stat().st_mtime_ns // 1_000_000
    if not _age_ok(seen_ms, now_ms, fresh_ms):
        raise Unavailable('classic_state_stale')
    hb = _json_bounded(_safe_file(root, 'heartbeat.json').read_text(encoding='utf8'))
    tick = hb.get('ts')
    if isinstance(tick, bool) or not isinstance(tick, (int, float)) or not math.isfinite(tick):
        raise Unavailable('heartbeat_missing')
    if not _age_ok(int(tick*1000), now_ms, fresh_ms):
        raise Unavailable('heartbeat_stale')
    return {'account_id':consumer, 'as_of_ms':min(seen_ms,int(tick*1000)),
            'timestamp_provenance':'filesystem_mtime_and_heartbeat_not_market_receipt',
            'positions':[{'symbol':sym,'side':side,'status':'OPEN'}
                         for sym,side in sorted(pos.items())]}

def _brain(root, kind, now_ms, fresh_ms):
    if kind not in ('pilot','free'):
        raise Unavailable('brain_source_not_configured')
    path = _safe_file(root,'brain.sqlite3')
    try:
        with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',
                                    uri=True,timeout=.15)) as db:
            db.execute('PRAGMA query_only=ON')
            db.execute('BEGIN')
            item = db.execute('SELECT body FROM state WHERE id=1').fetchone()
            if item is None:
                raise Unavailable('brain_state_missing')
            state = _json_bounded(item[0])
    except sqlite3.Error as exc:
        raise Unavailable('brain_sqlite_unavailable') from exc
    if kind == 'pilot':
        if state.get('version')!='brain-pilot-v1':
            raise Unavailable('brain_pilot_version_mismatch')
        acc = state.get('account')
        if not isinstance(acc,dict) or acc.get('name')!='brain-paper':
            raise Unavailable('brain_pilot_account_mismatch')
        positions = acc.get('positions')
    else:
        if state.get('account_id')!='brain-free-paper' or state.get('mode')!='paper':
            raise Unavailable('brain_free_account_mismatch')
        positions = state.get('positions')
    pos = _positions(positions)
    # Pilot heartbeat lives in status.json (see desk/brain_view.py); Brain Free
    # stores heartbeat_ms in the SQLite state. Never infer from last_bar.
    if kind == 'pilot':
        beat = _json_bounded(_safe_file(root, 'status.json').read_text(encoding='utf8'))
        if beat.get('mode') != 'paper' or beat.get('applied') is not False:
            raise Unavailable('brain_pilot_heartbeat_identity_mismatch')
        observed = beat.get('ts_ms')
    else:
        observed = state.get('heartbeat_ms')
    if not _age_ok(observed, now_ms, fresh_ms):
        raise Unavailable('brain_state_stale')
    return {'account_id':'brain','as_of_ms':observed,
            'timestamp_provenance':'brain_heartbeat_not_market_receipt',
            'positions':[{'symbol':sym,'side':side,'status':'OPEN'}
                         for sym,side in sorted(pos.items())]}

def wallet_snapshot(consumer, *, roots, now_ms=None, fresh_ms=DEFAULT_FRESH_MS,
                    brain_source=None):
    if consumer not in ACCOUNTS:
        raise ValueError('invalid_consumer')
    now = int(time.time()*1000) if now_ms is None else now_ms
    if type(now) is not int or now<=0 or not isinstance(roots,dict):
        raise ValueError('invalid_clock_or_roots')
    try:
        root=Path(roots[consumer])
        if consumer in ('hawk','bull'):
            snapshot = _classic(root, consumer, now, fresh_ms)
        else:
            snapshot = _brain(root, brain_source, now, fresh_ms)
        return {'status':'ok', 'snapshot':snapshot}
    except (KeyError,OSError,ValueError,UnicodeError) as exc:
        return {'status':'unavailable',
                'reason':str(exc) if isinstance(exc,Unavailable) else 'wallet_unreadable'}

def _shadow_record(root, consumer, now_ms):
    if root.is_symlink():
        raise Unavailable('shadow_dir_symlink')
    path=_safe_file(root,consumer+'.json')
    data=_json_bounded(path.read_text(encoding='utf8'))
    if data.get('schema')!='long-shadow-record-v1' or data.get('consumer')!=consumer:
        raise Unavailable('shadow_identity_mismatch')
    if data.get('authority')!='advisory_only' or data.get('observation_only') is not True:
        raise Unavailable('shadow_authority_invalid')
    if not _age_ok(data.get('as_of_ms'), now_ms, 20*60_000):
        raise Unavailable('shadow_record_stale')
    if data.get('decision') not in ('CANDIDATE','NO_TRADE'):
        raise Unavailable('shadow_invalid_decision')
    if data.get('setup') not in ('CONTINUATION','REVERSAL'):
        raise Unavailable('shadow_invalid_setup')
    if data.get('symbol') not in SYMBOLS:
        raise Unavailable('shadow_invalid_symbol')
    reasons=data.get('reasons')
    if not isinstance(reasons,list) or len(reasons)>12 or not all(
            isinstance(x,str) and len(x)<100 for x in reasons):
        raise Unavailable('shadow_invalid_reasons')
    return {'symbol':data['symbol'],'setup':data['setup'],
            'decision':data['decision'],'reasons':reasons,'as_of_ms':data['as_of_ms'],
            'source':'external_shadow_record_unverified','can_authorize_orders':False}

def read_dashboard(*, roots, shadow_dir, now_ms=None, brain_source=None):
    """DTO for authenticated GET-only API, not a trade decision engine."""
    now=int(time.time()*1000) if now_ms is None else now_ms
    result={'schema':'long-shadow-dashboard-v1','status':'observation_only',
            'engine_running':False,'live_market_ingestion_connected':False,
            'enabled':False,'paper_eligible':False,'can_execute_orders':False,
            'economic_evidence':'INSUFFICIENT','consumers':{}}
    for consumer in ACCOUNTS:
        wallet=wallet_snapshot(consumer,roots=roots,now_ms=now,
                               brain_source=brain_source)
        try:
            advice=_shadow_record(Path(shadow_dir),consumer,now)
            advisory_status='unverified_external_record'
        except (Unavailable,OSError,ValueError,UnicodeError):
            advice=None
            advisory_status='not_available'
        presence={}
        if wallet['status']=='ok':
            positions=wallet['snapshot']['positions']
            presence={sym:{
                'long_open':any(p['symbol']==sym and p['side']=='LONG' for p in positions),
                'short_open':any(p['symbol']==sym and p['side']=='SHORT' for p in positions)}
                for sym in SYMBOLS}
        result['consumers'][consumer]={
            'role':'AI_ADVISOR' if consumer=='brain' else 'CLASSIC_SHADOW',
            'wallet_status':wallet['status'],'wallet_reason':wallet.get('reason'),
            'wallet_as_of_ms':wallet.get('snapshot',{}).get('as_of_ms'),
            'positions':presence,'advisory_status':advisory_status,
            'advice':advice,'orders_enabled':False}
    return result
