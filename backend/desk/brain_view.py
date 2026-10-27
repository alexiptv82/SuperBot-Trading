"""Observation only. Never import Pilot/Store (both are writers).

Source: brain_pilot/pilot.py Store: brain.sqlite3, state(id, body),
events(seq, kind, body). No state.db/state_json compatibility guesswork.
"""
from __future__ import annotations

from collections import deque
from contextlib import closing
import json
import math
import os
from pathlib import Path
import sqlite3
import time

QUERY_SECONDS = 2.0
MAX_JSON_BYTES = 2 * 1024 * 1024
TAIL_BYTES = 256 * 1024
FRESH_MS = 45 * 60 * 1000  # same tolerance as the pilot's own healthcheck


class Unavailable(ValueError):
    pass


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise Unavailable("invalid_data")
    return value


def _positive_optional(value):
    # New display-only fields may be absent in legacy records. Never guess leverage.
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        return None
    return value


def _text(value):
    return value[:4000] if isinstance(value, str) else None


def _json(body):
    if len(body) > MAX_JSON_BYTES:
        raise Unavailable("data_too_large")
    value = json.loads(body)
    if not isinstance(value, dict):
        raise Unavailable("invalid_data")
    return value


def _check(deadline):
    if time.monotonic() >= deadline:
        raise Unavailable("query_timeout")


def _tail(path, deadline):
    """Bounded tail, text read mode only; ignore a writer's incomplete final line."""
    records = deque(maxlen=20)
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as stream:
            end = stream.seek(0, os.SEEK_END)
            start = max(0, end - TAIL_BYTES)
            stream.seek(start)
            if start:
                stream.readline()  # discard potentially truncated first line
            body = stream.read(TAIL_BYTES)
    except FileNotFoundError:
        return [], "missing"
    for line in body.splitlines(keepends=True):
        _check(deadline)
        if not line.endswith('\n'):
            continue
        try:
            records.append(_trade(_json(line)))
        except (ValueError, TypeError, KeyError):
            continue  # do not expose malformed/provider text
    return list(reversed(records)), "tail_256k"


def _trade(row):
    side = _number(row['side'])
    if side not in (-1, 1):
        raise Unavailable("invalid_data")
    why = row.get('why', '')
    reason = ('stop_loss' if why in ('stop', 'stop loss', 'stop_loss') else
              'take_profit' if why in ('take profit', 'take_profit') else
              'ai_close' if why in ('ai_close', 'ai', 'AI close', 'brain: close', 'brain: save_profit', 'brain: early_close') else _text(why))
    return {'symbol': _text(row['symbol']), 'side': 'LONG' if side == 1 else 'SHORT',
            'pnl': _number(row['net']), 'reason': reason,
            'closed_ms': _number(row['close_ms']), 'partial': row.get('partial') is True}


def read_status(data_dir=None, *, now_ms=None):
    """Return only an allowlist of PAPER data. No socket, shell, network or writes."""
    root = Path(data_dir or os.getenv('BRAIN_DATA_DIR', '/opt/superbot-desk-data/brain'))
    now = int(time.time() * 1000) if now_ms is None else now_ms
    deadline = time.monotonic() + QUERY_SECONDS
    try:
        db_path = root / 'brain.sqlite3'
        if not db_path.is_file():
            raise Unavailable('missing_database')
        # mode=ro observes committed WAL; immutable=1 would miss live WAL writes.
        with closing(sqlite3.connect(db_path.resolve().as_uri() + '?mode=ro',
                                    uri=True, check_same_thread=False,
                                    timeout=max(0, deadline - time.monotonic()))) as db:
            db.set_progress_handler(lambda: int(time.monotonic() >= deadline), 100)
            db.execute('PRAGMA query_only=ON')
            db.execute('BEGIN')  # one consistent state/events snapshot, released before JSONL
            found = db.execute('SELECT body FROM state WHERE id=1').fetchone()
            if found is None:
                raise Unavailable('missing_state')
            state = _json(found[0])
            account = state['account']
            if account.get('name') != 'brain-paper' or state.get('version') != 'brain-pilot-v1':
                raise Unavailable('unsupported_state')
            cycles = 0
            last_call = None
            last_cycle = None
            first_cycle = None
            groups = {}
            realized = 0
            for kind, body in db.execute('SELECT kind,body FROM events ORDER BY seq'):
                _check(deadline)
                row = _json(body)
                if kind == 'trade':
                    _trade(row)  # validates native schema
                    key = (_text(row['symbol']), row['id'], row['open_ms'])
                    item = groups.setdefault(key, {'net': 0, 'closed': False})
                    item['net'] += row['net']
                    realized += row['net']
                    item['closed'] |= row.get('partial') is not True
                elif kind == 'journal':
                    if row.get('kind') == 'cycle':
                        cycles += 1
                        last_cycle = row
                        if first_cycle is None:
                            first_cycle = row.get('ts_ms')
                    elif row.get('kind') == 'model_attempt':
                        last_call = row.get('ts_ms')
            _check(deadline)
        closed = [v['net'] for v in groups.values() if v['closed']]
        prices = state.get('last_prices', {})
        last_bar = state.get('last_bar')
        valued_ms = _number(last_bar) + 900000 if last_bar is not None else None
        mark_times = []
        positions = []
        margin = 0
        floating = 0
        priced = True
        thesis = []
        for symbol, pos in sorted(account['positions'].items()):
            _check(deadline)
            entry, qty, side = (_number(pos[k]) for k in ('entry', 'qty', 'side'))
            if side not in (-1, 1) or entry <= 0 or qty <= 0:
                raise Unavailable('invalid_data')
            price = prices.get(symbol)
            if price is None:
                pnl = None
                priced = False
            else:
                price = _number(price)
                if price <= 0:
                    raise Unavailable('invalid_data')
                pnl = side * (price - entry) * qty
                floating += pnl
            position_margin = _number(pos['total_margin'])
            if position_margin < 0:
                raise Unavailable('invalid_data')
            margin += position_margin
            mark = pos.get('last_bar_ms', last_bar)
            mark_ms = _number(mark) + 900000 if mark is not None else None
            if mark_ms is not None:
                mark_times.append(mark_ms)
            positions.append({'symbol': symbol, 'side': 'LONG' if side == 1 else 'SHORT',
                              'entry': entry, 'price': price, 'floating_pnl': pnl,
                              'margin': position_margin, 'leverage': _positive_optional(pos.get('leverage')),
                              'notional_entry': entry * qty,
                              'floating_margin_roi_pct': pnl / position_margin * 100 if pnl is not None and position_margin > 0 else None,
                              'valued_ms': mark_ms,
                              'stale': mark_ms is None or not -5000 <= now - mark_ms <= FRESH_MS})
            features = pos.get('features') or {}
            if features.get('bull_scenario') and features.get('bear_scenario'):
                thesis.append((pos['open_ms'], symbol, features, 'open_position'))
        for order in state.get('pending', []):
            if order.get('bull_scenario') and order.get('bear_scenario'):
                thesis.append((order['execute_t'], order['symbol'], order, 'pending_decision'))
        cash = _number(account['cash'])
        equity = cash + margin + floating if priced else None
        if mark_times and valued_ms is not None:
            valued_ms = min(valued_ms, *mark_times)
        age = now - valued_ms if valued_ms is not None else None
        stale = age is None or age < -5000 or age > FRESH_MS
        daily = account.get('brain_daily') or {}
        today = time.strftime('%Y-%m-%d', time.gmtime(now / 1000))
        current_day = daily.get('day') == today
        start = daily.get('start_equity')
        drawdown = (max(0, (1 - equity / _number(start)) * 100)
                    if current_day and equity is not None and start is not None and _number(start) > 0 else None)
        trades, coverage = _tail(root / 'trade_history.jsonl', deadline)
        reasoning = {'last_call_ms': last_call, 'bull_scenario': None, 'bear_scenario': None,
                     'verdict': None, 'decision_ms': None, 'symbol': None, 'source': None,
                     'market_view': _text((last_cycle or {}).get('market_view')),
                     'note': 'Ultima tesi conservata; il pilot non archivia ogni risposta completa.'}
        if thesis:
            stamp, symbol, fields, source = max(thesis, key=lambda x: x[0])
            reasoning.update({k: _text(fields.get(k)) for k in ('bull_scenario', 'bear_scenario', 'verdict')})
            reasoning.update(decision_ms=stamp, symbol=symbol, source=source)
        heartbeat = None
        try:
            with open(root / 'status.json', 'r', encoding='utf-8') as stream:
                beat = _json(stream.read(MAX_JSON_BYTES + 1))
            if beat.get('mode') == 'paper' and beat.get('applied') is False:
                heartbeat = _number(beat['ts_ms'])
        except (OSError, ValueError, KeyError, TypeError):
            pass
        _check(deadline)
        result = {'status': 'ok', 'mode': 'paper', 'read_only': True,
                  'portfolio': {'equity': equity, 'cash': cash, 'starting_equity': 1000,
                                'pnl': equity - 1000 if equity is not None else None,
                                'pnl_pct': (equity / 1000 - 1) * 100 if equity is not None else None,
                                'cycles': cycles, 'margin_in_use': margin, 'valued_ms': valued_ms, 'stale': stale},
                  'positions': positions, 'trades': trades, 'trades_coverage': coverage,
                  'stats': {'closed_trades': len(closed),
                            'win_rate_pct': 100 * sum(n > 0 for n in closed) / len(closed) if closed else None,
                            'average_pnl': sum(closed) / len(closed) if closed else None,
                            'realized_pnl': realized, 'partial_records_included': True},
                  'daily_stop': {'limit_pct': 20, 'day': daily.get('day'),
                                 'state': 'current' if current_day else 'awaiting_utc_rollover',
                                 'stopped': daily.get('stopped') if current_day else None,
                                 'drawdown_pct': drawdown,
                                 'used_limit_pct': drawdown / 20 * 100 if drawdown is not None else None},
                  'reasoning': reasoning,
                  'system': {'container': 'superbot-brain-pilot', 'health': 'unknown',
                             'sha': None, 'uptime_seconds': None, 'heartbeat_ms': heartbeat,
                             'heartbeat': ('fresh' if -5000 <= now - heartbeat <= FRESH_MS else 'stale') if heartbeat is not None else 'unknown',
                             'first_recorded_cycle_ms': first_cycle,
                             'note': 'Salute Docker, SHA e uptime non presenti nei dati del pilot.'}}
        json.dumps(result, allow_nan=False)
        return result
    except Unavailable as exc:
        return {'status': 'unavailable', 'reason': str(exc)}
    except sqlite3.OperationalError as exc:
        msg = str(exc).lower()
        reason = 'locked' if 'locked' in msg or 'busy' in msg else 'query_timeout' if 'interrupted' in msg else 'database_unavailable'
        return {'status': 'unavailable', 'reason': reason}
    except (sqlite3.DatabaseError, OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError):
        return {'status': 'unavailable', 'reason': 'invalid_or_unreadable_data'}


def register_fastapi(app, require_session):
    """Register before the SPA catch-all; reuse existing authenticated session."""
    from fastapi import Depends
    from fastapi.responses import JSONResponse

    @app.get('/api/brain/status')
    def brain_status(session=Depends(require_session)):
        return JSONResponse(read_status(), headers={'Cache-Control': 'no-store'})

    @app.get('/api/brain/profiles')
    def brain_profiles(session=Depends(require_session)):
        from .brain_profiles_view import read_profiles
        return JSONResponse(read_profiles(), headers={'Cache-Control': 'no-store'})
