"""Rotte autenticate, separate, per la chiusura manuale PAPER di UNA posizione di UNA AI dell'Arena.

POST /arena/{provider}/close                         {"position_id", "request_id"}  -> canale host
GET  /arena/{provider}/close/{request_id}            stato (lettura diretta, sola lettura)
POST /arena/{provider}/close/{request_id}/annotation {"reason", "note"?}           -> canale host
GET  /arena/{provider}/annotations                   motivazioni registrate (sola lettura)

Mai inoltrate a ``/api/v3/brain/close``. Senza ``arena_manual_close_enabled`` le rotte non esistono.
"""
from __future__ import annotations

import time
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from backend.v3.arena import manual_close as MC
from backend.v3.arena.close_bridge import PROVIDERS, ArenaBridgeError

PROVIDER_RE = "^(deepseek|qwen|minimax)$"
REQUEST_RE = "^[A-Za-z0-9-]{16,64}$"


def _fail(status: int, code: str):
    return HTTPException(status_code=status, detail={"ok": False, "code": code})


def make_arena_close_router(require_session: Callable, plans, *, send: Callable,
                            now_fn: Callable[[], int] = lambda: int(time.time() * 1000)) -> APIRouter:
    by_provider = {p.provider: p for p in plans if p.provider in PROVIDERS}
    router = APIRouter()

    async def _body(request: Request) -> dict:
        try:
            body = await request.json()
        except (ValueError, UnicodeError):
            body = None
        if type(body) is not dict:
            raise _fail(422, "invalid_request")
        return body

    def _relay(op: str, provider: str, body: dict) -> dict:
        if provider not in by_provider:
            raise _fail(422, "invalid_provider")
        try:
            return send(op, provider, body)
        except ArenaBridgeError as exc:
            raise _fail(exc.status, exc.code) from None

    @router.post("/arena/{provider}/close")
    async def close(provider: str, request: Request, response: Response, session=Depends(require_session)):
        response.headers["Cache-Control"] = "no-store"
        body = await _body(request)
        if set(body) != {"position_id", "request_id"}:
            raise _fail(422, "single_position_only")      # niente chiusure di massa
        return _relay("close", provider, body)

    @router.get("/arena/{provider}/close/{request_id}")
    def status(provider: str, request_id: str, response: Response, session=Depends(require_session)):
        response.headers["Cache-Control"] = "no-store"
        code, payload = MC.dispatch(by_provider, "status", provider, {"request_id": request_id}, now_fn())
        if code != 200:
            raise _fail(code, payload["code"])
        return payload

    @router.post("/arena/{provider}/close/{request_id}/annotation")
    async def annotation(provider: str, request_id: str, request: Request, response: Response,
                         session=Depends(require_session)):
        response.headers["Cache-Control"] = "no-store"
        body = await _body(request)
        if not {"reason"} <= set(body) <= {"reason", "note"}:
            raise _fail(422, "invalid_request")
        return _relay("annotate", provider, dict(body, request_id=request_id))

    @router.get("/arena/{provider}/annotations")
    def annotations(provider: str, response: Response, session=Depends(require_session)):
        response.headers["Cache-Control"] = "no-store"
        plan = by_provider.get(provider)
        if plan is None:
            raise _fail(422, "invalid_provider")
        try:
            rows = MC.read_annotations(plan)
        except MC.ArenaCloseError as exc:
            raise _fail(exc.status, exc.code) from None
        return {"ok": True, "provider": provider, "manual_close_ready": MC.manual_close_ready(plan, now_fn()),
                "annotations": [{k: r.get(k) for k in ("position_id", "close_event_id", "reason", "note",
                                                       "annotated_ms")} for r in rows]}

    return router
