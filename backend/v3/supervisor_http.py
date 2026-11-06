"""Optional S2 dashboard router. No journal or process mutation, no new orders.

Mount only after S0 trace.py and S1 evidence.py have passed CI on a common branch.
The absent prerequisites produce an explicit HTTP 503, not fabricated cards.
"""
from __future__ import annotations

import sqlite3
import re
from pathlib import Path
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from backend.v3.events import EventJournal
from backend.v3.supervisor.terminal import project_timeline

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")


def _error(status: int, code: str) -> HTTPException:
    return HTTPException(status, detail={'code': code}, headers={
        'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
    })


def make_router(require_session: Callable, journal_path: str | None, run_id: str,
                *, s0_reader=None, s1_reader=None) -> APIRouter:
    """Injectable sources for isolated tests. Defaults are S0 and S1 modules.

    Never call EventJournal.init_schema. An absent journal is 'not_started'.
    """
    router = APIRouter(prefix='/api/v3')

    @router.get('/brain/decision-timeline')
    def decision_timeline(response: Response, limit: int = Query(default=50, ge=1, le=100),
                          symbol: str | None = None, reason: str | None = None,
                          session=Depends(require_session)):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        if type(run_id) is not str or not _ID.fullmatch(run_id):
            raise _error(503, 'supervisor_not_configured')
        if symbol is not None and (not symbol or len(symbol) > 32):
            raise _error(422, 'invalid_filter')
        try:
            # Filters are validated by the pure projection too; do it before DB reads.
            project_timeline({'run_id': run_id, 'portfolio_id': 'brain', 'decisions': []}, (),
                             run_id=run_id, limit=limit, symbol=symbol, reason=reason)
        except ValueError:
            raise _error(422, 'invalid_filter') from None
        if not journal_path or not Path(journal_path).is_file():
            return {'schema_version': 1, 'portfolio_id': 'brain', 'run_id': run_id,
                    'state': 'not_started', 'source_window_limited': False,
                    'matched_in_window': 0, 'has_more': False, 'decisions': []}
        try:
            if s0_reader is None or s1_reader is None:
                from backend.v3.supervisor.trace import read_brain_timeline
                from backend.v3.supervisor.evidence import read_evidence
            else:
                read_brain_timeline, read_evidence = s0_reader, s1_reader
        except ImportError:
            raise _error(503, 'supervisor_not_integrated') from None
        try:
            journal = EventJournal(journal_path)
            base = read_brain_timeline(journal, run_id=run_id, limit=500)
            ev = read_evidence(journal, run_id=run_id)
            result = project_timeline(base, ev, run_id=run_id, limit=limit, symbol=symbol, reason=reason)
            return {**result, 'state': 'ready'}
        except (OSError, ValueError, sqlite3.Error):
            raise _error(503, 'supervisor_data_unavailable') from None

    return router
