"""Continuous LONG observation of append-only Bitget WS capture.

No broker, API keys, or exchange connections. Consumes verified received frames.
A kline update is NEVER treated as a finalized bar. Feed resets on reconnect.
"""
from __future__ import annotations
from collections import defaultdict
from decimal import Decimal, InvalidOperation
import hashlib
import json

TF_MS = {'1m': 60000, '15m': 900000, '1H': 3600000, '4H': 14400000}
TF_INTERNAL = {'1m': '1m', '15m': '15m', '1H': '1h', '4H': '4h'}
SYMBOLS = ('BTCUSDT', 'ETHUSDT')
MAX_FRAME_BYTES = 2_000_000
MIN_BARS = 200


class FeedNotReady(ValueError):
    pass


class ObservedFeed:
    def __init__(self):
        self.session = None
        self.last_receipt_ms = None
        self.snapshots = {}
        self.quotes = {}
        self.provisional_update_count = defaultdict(int)

    def reset(self, session):
        self.session = session
        self.last_receipt_ms = None
        self.snapshots.clear()
        self.quotes.clear()
        self.provisional_update_count.clear()

    def ingest(self, frame):
        """Validate a single capture envelope; return event classification."""
        if not isinstance(frame, dict):
            raise FeedNotReady('invalid_envelope')
        received = frame.get('received_at_ms')
        session = frame.get('session')
        raw = frame.get('raw_frame')
        if type(received) is not int or type(session) is not int or session <= 0:
            raise FeedNotReady('invalid_receipt_or_session')
        if not isinstance(raw, str) or len(raw.encode()) > MAX_FRAME_BYTES:
            raise FeedNotReady('invalid_frame_size')
        if hashlib.sha256(raw.encode()).hexdigest() != frame.get('raw_sha256'):
            raise FeedNotReady('frame_sha_mismatch')
        if self.session != session:
            if self.session is not None and session < self.session:
                raise FeedNotReady('session_reversal')
            self.reset(session)
        if self.last_receipt_ms is not None and received < self.last_receipt_ms:
            self.reset(session)
            raise FeedNotReady('received_time_reversal')
        self.last_receipt_ms = received
        if raw == 'pong':
            return 'HEARTBEAT'
        try:
            event = json.loads(raw)
        except (TypeError, ValueError) as exc:
            raise FeedNotReady('invalid_wire_json') from exc
        if not isinstance(event, dict):
            raise FeedNotReady('invalid_wire_envelope')
        arg = event.get('arg') or {}
        if not isinstance(arg, dict) or arg.get('instType') != 'usdt-futures':
            return 'CONTROL'
        symbol = arg.get('symbol')
        if symbol not in SYMBOLS:
            return 'OTHER'
        data = event.get('data')
        if not isinstance(data, list):
            return 'CONTROL'
        kind = event.get('action')
        if kind not in ('snapshot', 'update'):
            return 'CONTROL'
        if arg.get('topic') == 'books1':
            if not data:
                raise FeedNotReady('empty_bbo')
            try:
                b = Decimal(data[0]['b'][0][0])
                a = Decimal(data[0]['a'][0][0])
                if not (b.is_finite() and a.is_finite() and 0 < b <= a):
                    raise ValueError('bad_bbo')
            except (KeyError, IndexError, TypeError, ValueError, InvalidOperation) as exc:
                raise FeedNotReady('invalid_bbo') from exc
            self.quotes[symbol] = {'bid': float(b), 'ask': float(a), 'available_at_ms': received}
            return 'QUOTE'
        if arg.get('topic') == 'kline' and arg.get('interval') in TF_MS:
            tf = arg['interval']
            if kind == 'update':
                self.provisional_update_count[symbol, tf] += 1
                return 'UNCONFIRMED_KLINE_UPDATE'
            width = TF_MS[tf]
            closed = []
            seen = set()
            for item in data:
                try:
                    start = int(item['start'])
                    if start % width or start in seen:
                        raise ValueError('bad_kline_open')
                    seen.add(start)
                    close = start + width
                    if close > received:
                        continue  # current candle is NOT finalized
                    vals = {k: Decimal(item[k]) for k in ('open', 'high', 'low', 'close', 'volume')}
                    if any(not x.is_finite() for x in vals.values()):
                        raise ValueError('nonfinite_kline')
                    o, h, l, c, v = (vals[k] for k in ('open', 'high', 'low', 'close', 'volume'))
                    if not (0 < l <= min(o, c) <= max(o, c) <= h and v >= 0):
                        raise ValueError('invalid_ohlcv')
                except (KeyError, ValueError, TypeError, InvalidOperation) as exc:
                    raise FeedNotReady('invalid_snapshot_kline') from exc
                closed.append({'open': float(o), 'high': float(h), 'low': float(l), 'close': float(c),
                               'volume': float(v), 'close_ms': close, 'available_at_ms': received,
                               'availability': 'observed_snapshot_receipt'})
            closed.sort(key=lambda r: r['close_ms'])
            closed = closed[-600:]
            if len(closed) < MIN_BARS or any(
                b['close_ms'] - a['close_ms'] != width for a, b in zip(closed, closed[1:])
            ):
                raise FeedNotReady('snapshot_warmup_or_gap')
            self.snapshots[symbol, tf] = (received, closed)
            return 'CLOSED_SNAPSHOT_OBSERVED'
        return 'OTHER'

    def context(self, symbol, as_of_ms, *, max_quote_age_ms=2_000):
        if symbol not in SYMBOLS or type(as_of_ms) is not int:
            raise FeedNotReady('invalid_context_clock_or_symbol')
        if any((symbol, tf) not in self.snapshots for tf in TF_MS):
            raise FeedNotReady('missing_timeframe_snapshot')
        latest_snapshot = max(self.snapshots[symbol, tf][0] for tf in TF_MS)
        q = self.quotes.get(symbol)
        if not q or not (latest_snapshot <= q['available_at_ms'] <= as_of_ms):
            raise FeedNotReady('missing_quote_after_snapshots')
        if as_of_ms - q['available_at_ms'] > max_quote_age_ms:
            raise FeedNotReady('stale_quote')
        bars = {TF_INTERNAL[tf]: self.snapshots[symbol, tf][1] for tf in TF_MS}
        return {'symbol': symbol, 'bars': bars, 'quote': dict(q),
                'source': 'bitget_observed_snapshot_only',
                'live_close_ack_observed': False, 'execution_verified': False}


def consume_frame_lines(lines):
    """Pure iterable diagnostic: no wallet, no engine and no file writes."""
    feed = ObservedFeed()
    results = defaultdict(int)
    for line in lines:
        try:
            result = feed.ingest(json.loads(line))
            results[result] += 1
        except (FeedNotReady, ValueError) as exc:
            results['REJECTED_' + str(exc)] += 1
    return {'session': feed.session, 'events': dict(results),
            'snapshots': len(feed.snapshots),
            'provisional_updates': sum(feed.provisional_update_count.values()),
            'can_execute_orders': False, 'paper_eligible': False}
