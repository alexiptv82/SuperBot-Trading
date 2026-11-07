"""V3 unified PAPER dashboard with authenticated manual-close request channel.

Only POST /brain/close can write a close_request.json, atomically. No journal
updates, live execution authority or schema initialization. EventJournal uses
SQLite mode=ro; the budget ledger uses a read-only SQLite connection.
"""
from __future__ import annotations

import asyncio
import fcntl
import json
import os
import re
import sqlite3
import threading
import tempfile
import time
from dataclasses import dataclass
from contextlib import closing
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

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
_POSITION_RE = re.compile(r'^[A-Za-z0-9_.:-]{1,64}$')
_CLOSE_RESULT_MAX_AGE_MS = 600_000
_CLOSE_RESULT_STATUSES = frozenset({'done', 'expired', 'invalid_request'})
_CLOSE_LOCK = threading.Lock()


@dataclass(frozen=True)
class V3Paths:
    journal_path: str | None
    run_id: str
    budget_db_path: str | None
    heartbeat_path: str | None
    pause_flag_path: str | None
    falco_data_dir: str
    toro_data_dir: str
    close_request_path: str | None = None
    close_result_path: str | None = None

    def __post_init__(self):
        """Default command files live beside the configured heartbeat, never /opt."""
        if self.heartbeat_path:
            home = Path(self.heartbeat_path).parent
            if self.close_request_path is None:
                object.__setattr__(self, 'close_request_path', str(home / 'close_request.json'))
            if self.close_result_path is None:
                object.__setattr__(self, 'close_result_path', str(home / 'close_result.json'))

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
            close_request_path=os.environ.get('V3_CLOSE_REQUEST_PATH'),
            close_result_path=os.environ.get('V3_CLOSE_RESULT_PATH'),
        )


def _exists(path: str | None) -> bool:
    return bool(path and Path(path).is_file())


def _manual_learning_label(is_manual: bool, net) -> str | None:
    """Learning evidence only: not a trading rule or verified exit strategy."""
    if not is_manual:
        return None
    try:
        value = Decimal(str(net))
        if not value.is_finite():
            return None
        return ('profit_protection_example' if value > 0 else
                'loss_reduction_example' if value < 0 else 'break_even_example')
    except (TypeError, ValueError, InvalidOperation):
        return None


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
    # Desk's existing view is the authority for open positions / close capability.
    detail = dv.build_status(data_dir, 'hawk' if portfolio_id == 'falco' else 'bull', now=now_s)
    classic_positions = [
        {'symbol': p['symbol'], 'side': p.get('side'), 'leverage': p.get('leverage'),
         'entry': _safe_decimal(p.get('entry')), 'stop': _safe_decimal(p.get('sl')) if p.get('sl') is not None else None,
         'price': (_safe_decimal(p.get('price')) if p.get('price_source') != 'entry' else None),
         'price_source': p.get('price_source') if p.get('price_source') in ('live', 'bot', 'entry') else None,
         'margin': _safe_decimal(p.get('margin')), 'quantity': _safe_decimal(p.get('qty')),
         'take_profit': _safe_decimal(p.get('tp')) if p.get('tp') is not None else None,
         'liquidation': _safe_decimal(p.get('liq')) if p.get('liq') is not None else None,
         'trade_type': p.get('trade_type'), 'opened_at_ms': p.get('open_ms'),
         'unrealized_pnl': _safe_decimal(p.get('pnl')),
         'roi_pct': _safe_decimal(p.get('pnl_pct'))}
        for p in detail.get('positions', ()) if type(p) is dict and type(p.get('symbol')) is str
    ]
    # Keep the new page aligned with the existing classic trade history.
    recent = dv.build_trades(data_dir, limit=20) if state else []
    closed = [
        {'symbol': t.get('symbol'), 'side': t.get('side'), 'leverage': t.get('leverage'),
         'entry': _safe_decimal(t.get('entry_price')) if t.get('entry_price') is not None else None,
         'exit': _safe_decimal(t.get('exit_price')) if t.get('exit_price') is not None else None,
         'margin': _safe_decimal(t.get('margin')) if t.get('margin') is not None else None,
         'realized_pnl': _safe_decimal(t.get('pnl')) if t.get('pnl') is not None else None,
         'closed_at_ms': t.get('close_ms'), 'close_reason': str(t.get('close_reason') or '')[:120],
         'trade_type': t.get('trade_type'), 'partial': t.get('partial') is True,
         'closed_by': t.get('closed_by'),
         'manual_learning': (
             t.get('manual_learning')
             if t.get('manual_learning') in (
                 'profit_protection_example', 'loss_reduction_example', 'break_even_example')
             else _manual_learning_label(t.get('closed_by') == 'utente', t.get('pnl')))}

        for t in recent if type(t) is dict
    ]
    return {'id': portfolio_id, 'kind': 'classic', 'state': mode,
            'positions': classic_positions, 'closed_trades': closed,
            'can_close_position': detail.get('can_close_position') is True,
            'close_worker_mode': detail.get('close_worker_mode', 'offline'),
            'close_pending': detail.get('close_position_pending') or [],
            'last_action': detail.get('last_action'),
            'open_positions': len(positions),
            'realized_pnl': _safe_decimal(perf['total_pnl'] if perf and perf.get('available') else 0),
            'margin_in_use': str(margin), 'last_event_ms': last_ms,
            'heartbeat_age_s': age,
            'equity': _safe_decimal(detail.get('equity')) if detail.get('available') else None,
            'cash': _safe_decimal(detail.get('cash')) if detail.get('available') else None,
            'day_pnl': _safe_decimal(detail.get('day_pnl')) if detail.get('available') else None,
            'unrealized_pnl': _safe_decimal(detail.get('unrealized_pnl')) if detail.get('available') else None,
            'start_equity': _safe_decimal(detail.get('start_equity')) if detail.get('available') else None,
            'total_closed': detail.get('total_closed', 0),
            'win_rate': _safe_decimal(perf.get('win_rate')) if perf and perf.get('available') else None}


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
    n_closed = len(s.closed_trades) if s is not None else 0
    wins = sum(1 for t in s.closed_trades if t.realized_pnl > 0) if s is not None else 0
    entries.append({'id': 'brain', 'kind': 'brain', 'state': state,
                    'open_positions': len(s.open_positions) if s is not None else 0,
                    'realized_pnl': str(s.realized_pnl) if s is not None else '0',
                    'margin_in_use': str(s.margin_in_use) if s is not None else '0',
                    'total_closed': n_closed,
                    'win_rate': str((Decimal(wins) * 100 / n_closed).quantize(Decimal('0.1'))) if n_closed else None,
                    'last_event_ms': s.last_event_ms if s is not None else None,
                    'heartbeat_age_s': max(0, (now_ms - hb['ts_ms']) // 1000) if hb else None})
    return {'generated_at_ms': now_ms, 'portfolios': entries}


def _scoreboard(paths: V3Paths, now_ms: int) -> dict:
    outcomes = list(_outcomes(paths))
    scores = []
    for regime in sorted({o.decision_regime for o in outcomes if o.decision_regime in REGIMES}):
        scores.append(build_scoreboard(outcomes, regime=regime, params=load_default_params()))
    return {'generated_at_ms': now_ms, 'regimes': scores}


async def _ticker_mark(get_ticker, pos):
    """Return a real price mark and unrealized PnL together, or two unknowns.

    In particular NEVER pass off entry price as the latest traded price.
    """
    if get_ticker is None:
        return None, None
    try:
        result = get_ticker(pos.symbol)
        if asyncio.iscoroutine(result):
            result = await asyncio.wait_for(result, timeout=4)
        last = Decimal(str(result['price']))
        if not last.is_finite() or last <= 0:
            return None, None
        return str(last), str((last - pos.fill_price) * pos.quantity * pos.side)
    except Exception:
        return None, None


async def _ticker_pnl(get_ticker, pos):
    """Keep the existing private PnL helper available to other callers."""
    return (await _ticker_mark(get_ticker, pos))[1]


async def _trades(paths: V3Paths, limit: int, get_ticker) -> dict:
    outcomes = sorted(_outcomes(paths), key=lambda o: o.closed_at_ms, reverse=True)[:limit]
    closed = [{'position_id': o.position_id, 'symbol': o.symbol, 'side': o.side,
               'strategy_id': o.strategy_id or None, 'strategy_origin': o.strategy_origin or None,
               'regime': o.decision_regime or None, 'net_bp': str(o.net_bp),
               'exit_reason': o.exit_reason, 'hold_ms': o.hold_ms,
               'leverage': o.leverage, 'margin': str(o.margin_used),
               'entry': str(o.entry_price), 'exit': str(o.exit_price),
               'fees': str(o.fees), 'realized_pnl': str(o.realized_pnl),
               'manual_learning': _manual_learning_label(o.is_manual, o.realized_pnl),
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
        mark, pnl = await _ticker_mark(get_ticker, pos)
        roi = (str(Decimal(pnl) / pos.margin_used * 100)
               if pnl is not None and pos.margin_used > 0 else None)
        opened.append({'position_id': pos.position_id, 'symbol': pos.symbol, 'side': pos.side,
                       'entry': str(pos.fill_price), 'stop': str(pos.stop_price),
                       'price': mark, 'price_source': 'ticker' if mark is not None else None,
                       'margin': str(pos.margin_used), 'quantity': str(pos.quantity),
                       'opened_at_ms': pos.opened_at_ms,
                       'leverage': pos.leverage, 'strategy_id': labels.get(pos.position_id),
                       'unrealized_pnl': pnl, 'roi_pct': roi})
    return {'open_positions': opened, 'closed_trades': closed,
            'close_pending': _close_inflight(paths)}


def _close_error(status: int, code: str, message: str) -> HTTPException:
    """Stable machine code + clear Italian message; never leak server paths."""
    return HTTPException(status_code=status, detail={'code': code, 'message': message},
                         headers={'Cache-Control': 'no-store'})


def _close_body(body: object) -> tuple[str | None, bool]:
    """Only one exact shape: {'position_id': id} OR {'all': true}."""
    if type(body) is not dict:
        raise _close_error(422, 'richiesta_non_valida', 'Richiesta di chiusura non valida.')
    if set(body) == {'all'} and body['all'] is True:
        return None, True
    if (set(body) == {'position_id'} and type(body['position_id']) is str
            and _POSITION_RE.fullmatch(body['position_id'])):
        return body['position_id'], False
    raise _close_error(422, 'richiesta_non_valida', 'Indica una posizione valida o conferma Chiudi tutte.')


def _close_request(paths: V3Paths, body: object, now_ms: int) -> dict:
    """Validate first; atomically publish one PAPER-only command file.

    A directory flock serializes requests from multiple backend workers without
    creating a second persistent control file. The runner consumes the request.
    """
    position_id, close_all = _close_body(body)
    hb = _heartbeat(paths)
    if (hb is None or not paths.journal_path or not paths.run_id or
            not _exists(paths.journal_path) or now_ms - hb['ts_ms'] > _HEARTBEAT_STALE_MS
            or hb['ts_ms'] > now_ms + _CLOSE_RESULT_MAX_AGE_MS
            or hb['run_id'] != paths.run_id):
        raise _close_error(409, 'brain_non_risponde', 'Il Brain non risponde: riprova quando è collegato.')
    summary = _summary(paths)
    if summary is None:
        raise _close_error(409, 'brain_non_risponde', 'Il registro del Brain non è disponibile.')
    open_ids = {p.position_id for p in summary.open_positions}
    if close_all:
        if not open_ids:
            raise _close_error(409, 'nessuna_posizione', 'Non ci sono posizioni aperte da chiudere.')
    elif position_id not in open_ids:
        raise _close_error(404, 'posizione_non_aperta', 'La posizione non è più aperta.')
    if not paths.close_request_path:
        raise _close_error(409, 'brain_non_risponde', 'Il canale di chiusura del Brain non è configurato.')
    target = Path(paths.close_request_path)
    payload = {'ts_ms': now_ms, 'all': True} if close_all else {'ts_ms': now_ms, 'position_ids': [position_id]}
    tmp_name = None
    try:
        with _CLOSE_LOCK:
            # A lock on the existing directory (Linux) also coordinates distinct uvicorn workers.
            dirfd = os.open(str(target.parent), os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
            try:
                fcntl.flock(dirfd, fcntl.LOCK_EX)
                if target.exists() or (target.parent / '.close_request.work').exists():
                    raise _close_error(409, 'richiesta_in_corso', 'Una chiusura è già in corso.')
                fd, tmp_name = tempfile.mkstemp(prefix='.close_request.', suffix='.tmp', dir=target.parent)
                with os.fdopen(fd, 'w', encoding='utf-8') as writer:
                    json.dump(payload, writer, sort_keys=True)
                    writer.flush()
                    os.fsync(writer.fileno())
                os.replace(tmp_name, target)
                tmp_name = None
            finally:
                fcntl.flock(dirfd, fcntl.LOCK_UN)
                os.close(dirfd)
    except HTTPException:
        raise
    except OSError:
        raise _close_error(409, 'brain_non_risponde', 'Impossibile inviare la richiesta al Brain.') from None
    finally:
        if tmp_name is not None:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
    return {'ok': True, 'pending': True, 'ts_ms': now_ms}



def _close_inflight(paths: V3Paths) -> bool:
    if not paths.close_request_path:
        return False
    target = Path(paths.close_request_path)
    return target.is_file() or (target.parent / '.close_request.work').is_file()


def _close_result(paths: V3Paths, now_ms: int) -> dict:
    """Display only recent sanitized engine results; do not echo arbitrary file text."""
    raw = _json_read(paths.close_result_path)
    result = None
    if raw is not None:
        req_ts, done_ms = raw.get('request_ts_ms'), raw.get('done_ms')
        closed, failed, status = raw.get('closed'), raw.get('failed'), raw.get('status')
        valid = (type(req_ts) is int and 0 < req_ts <= now_ms + _CLOSE_RESULT_MAX_AGE_MS
                 and now_ms - req_ts <= _CLOSE_RESULT_MAX_AGE_MS
                 and type(done_ms) is int and done_ms >= 0
                 and type(status) is str and status in _CLOSE_RESULT_STATUSES
                 and type(closed) is list and type(failed) is list
                 and all(type(i) is str and _POSITION_RE.fullmatch(i) for i in closed)
                 and all(type(pair) is list and len(pair) == 2
                         and type(pair[0]) is str and (pair[0] == '*' or _POSITION_RE.fullmatch(pair[0]))
                         and type(pair[1]) is str and _CODE_RE.fullmatch(pair[1]) for pair in failed))
        if valid:
            result = {'request_ts_ms': req_ts, 'done_ms': done_ms, 'status': status,
                      'closed': closed, 'failed': failed}
    return {'result': result, 'pending': _close_inflight(paths)}


def make_router(require_session: Callable, paths: V3Paths, get_ticker=None) -> APIRouter:
    """Create session-gated dashboard and PAPER-only manual-close endpoints."""
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

    @router.post('/brain/close')
    async def brain_close(request: Request, response: Response, session=Depends(require_session)):
        response.headers['Cache-Control'] = 'no-store'
        try:
            body = await request.json()
        except (ValueError, UnicodeError):
            body = None
        return _close_request(paths, body, int(time.time() * 1000))

    @router.get('/brain/close-result')
    def brain_close_result(response: Response, session=Depends(require_session)):
        response.headers['Cache-Control'] = 'no-store'
        return _close_result(paths, int(time.time() * 1000))

    return router
