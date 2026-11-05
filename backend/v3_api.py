"""V3 unified PAPER dashboard: read-only FastAPI endpoints.

No write path, no schema initialization, no live execution authority. All
journal reads use EventJournal.list_run (SQLite mode=ro); the budget ledger is
bound to a read-only SQLite connection, never constructed normally.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sqlite3
import threading
import time
from dataclasses import dataclass
from contextlib import closing
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable

from fastapi import APIRouter, Depends, Query, Response

import desk_view as dv
from backend.v3.budget import BudgetLedger
from backend.v3.brain_view.params import load_default_params
from backend.v3.brain_view.view import build_scoreboard
from backend.v3.dashboard import build_summary
from backend.v3.events import EventJournal
from backend.v3.outcomes import REGIMES, extract_outcomes
from backend.v3.runner.config import load_default_config

_MICRO_DOLLAR = Decimal('1000000')
_HEARTBEAT_STALE_MS = 3 * 900 * 1000  # UI freshness, NOT trading/strategy limits
_CODE_RE = re.compile(r'^[A-Za-z0-9_.:-]{1,96}$')


@dataclass(frozen=True)
class V3Paths:
    journal_path: str | None
    run_id: str
    budget_db_path: str | None
    heartbeat_path: str | None
    pause_flag_path: str | None
    falco_data_dir: str
    toro_data_dir: str

    @classmethod
    def from_env(cls, falco_data_dir: str, toro_data_dir: str) -> 'V3Paths':
        """No guessed /opt paths: release owner provides V3_* environment variables."""
        return cls(
            journal_path=os.environ.get('V3_JOURNAL_PATH'),
            run_id=os.environ.get('V3_RUN_ID', ''),
            budget_db_path=os.environ.get('V3_BUDGET_DB_PATH'),
            heartbeat_path=os.environ.get('V3_HEARTBEAT_PATH'),
            pause_flag_path=os.environ.get('V3_PAUSE_FLAG_PATH'),
            falco_data_dir=falco_data_dir, toro_data_dir=toro_data_dir,
        )


def _exists(path: str | None) -> bool:
    return bool(path and Path(path).is_file())


def _safe_decimal(value, default='0') -> str:
    try:
        number = Decimal(str(value))
        return str(number) if number.is_finite() else default
    except (ValueError, TypeError, InvalidOperation):
        return default


def _json_read(path: str | None) -> dict | None:
    if not _exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as handle:
            obj = json.load(handle)
        return obj if type(obj) is dict else None
    except (OSError, ValueError, UnicodeError):
        return None


def _heartbeat(paths: V3Paths) -> dict | None:
    obj = _json_read(paths.heartbeat_path)
    if obj is None or type(obj.get('ts_ms')) is not int or obj['ts_ms'] <= 0:
        return None
    if type(obj.get('cycle')) is not int or obj['cycle'] < 0:
        return None
    if obj.get('state') not in ('running', 'paused', 'halted'):
        return None
    if type(obj.get('run_id')) is not str:
        return None
    raw = obj.get('last_error')
    # Only closed error tokens, never arbitrary provider text in a UI.
    codes = [s for s in raw.split(';') if _CODE_RE.fullmatch(s)] if type(raw) is str else []
    return {'ts_ms': obj['ts_ms'], 'cycle': obj['cycle'], 'state': obj['state'],
            'last_error': ';'.join(codes) if codes else None, 'run_id': obj['run_id']}


def _brain_state(paths: V3Paths, hb: dict | None, now_ms: int) -> str:
    if hb is None:
        return 'not_started'
    if hb['state'] == 'halted':
        return 'halted'
    if hb['state'] == 'paused' or _exists(paths.pause_flag_path):
        return 'paused'
    if now_ms - hb['ts_ms'] > _HEARTBEAT_STALE_MS:
        return 'stale'
    return 'running'


def _journal(paths: V3Paths) -> EventJournal | None:
    if not paths.run_id or not _exists(paths.journal_path):
        return None
    return EventJournal(paths.journal_path)


def _summary(paths: V3Paths):
    journal = _journal(paths)
    if journal is None:
        return None
    try:
        return build_summary(journal, 'brain', paths.run_id)
    except (ValueError, sqlite3.Error, OSError):
        return None


def _events(paths: V3Paths):
    journal = _journal(paths)
    if journal is None:
        return []
    try:
        return journal.list_run('brain', paths.run_id)
    except (ValueError, sqlite3.Error, OSError):
        return []


def _outcomes(paths: V3Paths):
    journal = _journal(paths)
    if journal is None:
        return ()
    try:
        return extract_outcomes(journal, 'brain', paths.run_id).outcomes
    except (ValueError, sqlite3.Error, OSError, RuntimeError):
        return ()


def _spend(paths: V3Paths) -> dict | None:
    """Uses BudgetLedger's public read methods against a query-only connection.

    The normal constructor creates tables and enables WAL, so it is forbidden
    here. session_spend is process-local and cannot be recovered from disk;
    day/month use the persisted ledger only.
    """
    if not _exists(paths.budget_db_path):
        return None
    try:
        uri = Path(paths.budget_db_path).resolve().as_uri().replace('file://', 'file:') + '?mode=ro'
        with closing(sqlite3.connect(uri, uri=True)) as db:
            db.execute('PRAGMA query_only=ON')
            ledger = BudgetLedger.__new__(BudgetLedger)
            ledger._lock = threading.Lock()
            ledger._conn = db
            ledger._session_spend = {}  # not a real, persisted measurement
            day = ledger.daily_spend('deepseek')
            records = ledger.all_spend('deepseek')
            month_prefix = datetime.now(timezone.utc).strftime('%Y-%m')
            month = sum(r['units'] for r in records
                        if type(r.get('units')) is int and str(r.get('occurred_at', '')).startswith(month_prefix))
        limit = None
        try:
            limit = str(Decimal(load_default_config().daily_cap_units) / _MICRO_DOLLAR)
        except (ValueError, OSError):
            pass
        return {'day': str(Decimal(day) / _MICRO_DOLLAR),
                'day_limit': limit,
                'month': str(Decimal(month) / _MICRO_DOLLAR)}
    except (sqlite3.Error, OSError, TypeError, ValueError, KeyError):
        return None


def _classic(portfolio_id: str, data_dir: str, now_s: float) -> dict:
    """Reuse desk_view's state, heartbeat, pause and performance readers."""
    state = dv.read_state(data_dir)
    hb = dv.read_heartbeat(data_dir, now=now_s)
    paused = dv.pause_requested(data_dir)
    main = state.get('main') or {}
    positions = main.get('positions') or {}
    if not isinstance(positions, dict):
        positions = {}
    margin = sum((Decimal(_safe_decimal((p or {}).get('total_margin', (p or {}).get('margin'))))
                  for p in positions.values() if isinstance(p, dict)), Decimal('0'))
    latest = state.get('last_prices_ms')
    last_ms = latest if type(latest) is int and latest > 0 else None
    if hb and hb.get('ts') is not None:
        try:
            hb_ms = int(Decimal(str(hb['ts'])) * 1000)
            last_ms = max(last_ms or 0, hb_ms) or None
        except (ValueError, TypeError, InvalidOperation):
            pass
    age = int(hb['age_s']) if hb and hb.get('age_s') is not None else None
    if not state and hb is None:
        mode = 'not_started'
    elif state.get('halt') is True or (hb or {}).get('halted') is True:
        mode = 'halted'
    elif paused:
        mode = 'paused'
    elif hb is None or not hb.get('age_s', float('inf')) < dv.HEARTBEAT_FRESH_S:
        mode = 'stale'
    else:
        mode = 'running'
    perf = dv.build_performance(data_dir, portfolio_id) if state else None
    return {'id': portfolio_id, 'kind': 'classic', 'state': mode,
            'open_positions': len(positions),
            'realized_pnl': _safe_decimal(perf['total_pnl'] if perf and perf.get('available') else 0),
            'margin_in_use': str(margin), 'last_event_ms': last_ms,
            'heartbeat_age_s': age}


def _brain_status(paths: V3Paths, now_ms: int) -> dict:
    hb = _heartbeat(paths)
    state = _brain_state(paths, hb, now_ms)
    events = _events(paths)
    decisions = [e for e in events if e.event.kind == 'brain_decision']
    last = decisions[-1] if decisions else None
    last_decision = None
    if last is not None:
        p = last.event.payload
        last_decision = {
            'kind': p.get('kind'), 'status': p.get('status'), 'symbol': p.get('symbol'),
            'regime': p.get('regime'), 'strategy_id': p.get('strategy_id'),
            'ts_ms': last.event.occurred_at_ms}
    return {'state': state, 'run_id': paths.run_id or None,
            'heartbeat': ({k: hb[k] for k in ('ts_ms', 'cycle', 'state', 'last_error')}
                          if hb is not None else None),
            'paused': _exists(paths.pause_flag_path),
            'regime': last_decision['regime'] if last_decision else None,
            'last_decision': last_decision, 'spend': _spend(paths)}


def _overview(paths: V3Paths, now_ms: int) -> dict:
    now_s = now_ms / 1000
    entries = [_classic('falco', paths.falco_data_dir, now_s),
               _classic('toro', paths.toro_data_dir, now_s)]
    s = _summary(paths)
    hb = _heartbeat(paths)
    state = _brain_state(paths, hb, now_ms)
    entries.append({'id': 'brain', 'kind': 'brain', 'state': state,
                    'open_positions': len(s.open_positions) if s is not None else 0,
                    'realized_pnl': str(s.realized_pnl) if s is not None else '0',
                    'margin_in_use': str(s.margin_in_use) if s is not None else '0',
                    'last_event_ms': s.last_event_ms if s is not None else None,
                    'heartbeat_age_s': max(0, (now_ms - hb['ts_ms']) // 1000) if hb else None})
    return {'generated_at_ms': now_ms, 'portfolios': entries}


def _scoreboard(paths: V3Paths, now_ms: int) -> dict:
    outcomes = list(_outcomes(paths))
    scores = []
    for regime in sorted({o.decision_regime for o in outcomes if o.decision_regime in REGIMES}):
        scores.append(build_scoreboard(outcomes, regime=regime, params=load_default_params()))
    return {'generated_at_ms': now_ms, 'regimes': scores}


async def _ticker_pnl(get_ticker, pos):
    if get_ticker is None:
        return None
    try:
        # Market data read only. This optional callback may be network-backed.
        result = get_ticker(pos.symbol)
        if asyncio.iscoroutine(result):
            result = await asyncio.wait_for(result, timeout=4)
        last = Decimal(str(result['price']))
        if not last.is_finite() or last <= 0:
            return None
        return str((last - pos.fill_price) * pos.quantity * pos.side)
    except Exception:
        # An unavailable market-price provider never breaks read-only trades.
        return None


async def _trades(paths: V3Paths, limit: int, get_ticker) -> dict:
    outcomes = sorted(_outcomes(paths), key=lambda o: o.closed_at_ms, reverse=True)[:limit]
    closed = [{'position_id': o.position_id, 'symbol': o.symbol, 'side': o.side,
               'strategy_id': o.strategy_id or None, 'strategy_origin': o.strategy_origin or None,
               'regime': o.decision_regime or None, 'net_bp': str(o.net_bp),
               'exit_reason': o.exit_reason, 'hold_ms': o.hold_ms,
               'closed_at_ms': o.closed_at_ms} for o in outcomes]
    summary = _summary(paths)
    events = _events(paths)
    decisions = {s.event.event_id: s.event.payload for s in events if s.event.kind == 'brain_decision'}
    labels = {}
    for s in events:
        if s.event.kind == 'paper_open':
            p = s.event.payload
            d = decisions.get(p.get('decision_event_id'), {})
            labels[p.get('position_id')] = d.get('strategy_id')
    opened = []
    for pos in summary.open_positions if summary is not None else ():
        opened.append({'position_id': pos.position_id, 'symbol': pos.symbol, 'side': pos.side,
                       'entry': str(pos.fill_price), 'stop': str(pos.stop_price),
                       'leverage': pos.leverage, 'strategy_id': labels.get(pos.position_id),
                       'unrealized_pnl': await _ticker_pnl(get_ticker, pos)})
    return {'open_positions': opened, 'closed_trades': closed}


def make_router(require_session: Callable, paths: V3Paths, get_ticker=None) -> APIRouter:
    """Create a GET-only router, session-gated, with explicit no-store responses."""
    if type(paths) is not V3Paths:
        raise ValueError('invalid_paths')
    router = APIRouter(prefix='/api/v3')

    @router.get('/overview')
    def overview(response: Response, session=Depends(require_session)):
        response.headers['Cache-Control'] = 'no-store'
        return _overview(paths, int(time.time() * 1000))

    @router.get('/brain/status')
    def brain_status(response: Response, session=Depends(require_session)):
        response.headers['Cache-Control'] = 'no-store'
        return _brain_status(paths, int(time.time() * 1000))

    @router.get('/brain/scoreboard')
    def brain_scoreboard(response: Response, session=Depends(require_session)):
        response.headers['Cache-Control'] = 'no-store'
        return _scoreboard(paths, int(time.time() * 1000))

    @router.get('/brain/trades')
    async def brain_trades(response: Response, limit: int = Query(50, ge=1, le=200),
                           session=Depends(require_session)):
        response.headers['Cache-Control'] = 'no-store'
        return await _trades(paths, limit, get_ticker)

    return router
