"""Optional, authenticated, read-only HTTP endpoint for AI Arena portfolios.

Intentionally not mounted by the existing V3 app: a future deployment must
explicitly enable it after review of the three distinct journal bind mounts.
No write routes, no model API calls, no close-position dispatch.
"""
from __future__ import annotations

import time
from typing import Callable

from fastapi import APIRouter, Depends, Response

from backend.v3.arena.read_view import read_arena
from backend.v3.arena.trial_plan import WalletPlan


def make_arena_router(
    require_session: Callable,
    plans: tuple[WalletPlan, ...],
    *,
    enabled: bool = False,
    nested: bool = False,
) -> APIRouter:
    router = APIRouter(prefix="" if nested else "/api/v3")
    if enabled is not True:
        return router

    @router.get("/arena")
    def arena(response: Response, session=Depends(require_session)):
        response.headers["Cache-Control"] = "no-store"
        return read_arena(plans, int(time.time() * 1000))

    return router
