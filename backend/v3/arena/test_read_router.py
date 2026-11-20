"""HTTP contract: Arena is unmounted unless explicitly enabled, always session gated."""
from __future__ import annotations

from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, main

from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from backend.v3.arena.read_router import make_arena_router
from backend.v3.arena.trial_plan import build_trial_plan


def gate(request: Request):
    if request.headers.get("x-test-authorized") != "true":
        raise HTTPException(status_code=401, detail="unauthorized")
    return "synthetic-session"


class TestArenaRouter(TestCase):
    def test_default_no_route_installed(self):
        with TemporaryDirectory() as tmp:
            app = FastAPI()
            app.include_router(make_arena_router(
                gate,
                build_trial_plan(date(2026,11,16), root=Path(tmp) / "arena"),
            ))
            response = TestClient(app).get("/api/v3/arena", headers={
                "x-test-authorized": "true",
            })
            self.assertEqual(response.status_code, 404)

    def test_session_required_even_for_missing_journals(self):
        with TemporaryDirectory() as tmp:
            app = FastAPI()
            app.include_router(make_arena_router(
                gate,
                build_trial_plan(date(2026,11,16), root=Path(tmp) / "arena"),
                enabled=True,
            ))
            cli = TestClient(app)
            self.assertEqual(cli.get("/api/v3/arena").status_code, 401)
            allowed = cli.get("/api/v3/arena", headers={
                "x-test-authorized": "true",
            })
            self.assertEqual(allowed.status_code, 200)
            self.assertEqual(allowed.headers["cache-control"], "no-store")
            body = allowed.json()
            self.assertEqual(body["schema"], "brain_arena_readonly_v1")
            self.assertEqual(body["mode"], "paper")
            self.assertEqual(set(body["portfolios"]),
                             {"deepseek", "qwen", "minimax"})
            self.assertIsNone(body["portfolios"]["qwen"]["equity"])
            self.assertEqual(body["portfolios"]["qwen"]["state"], "not_started")
            self.assertFalse((Path(tmp) / "arena").exists())

    def test_write_methods_not_exposed_by_arena_router(self):
        with TemporaryDirectory() as tmp:
            app = FastAPI()
            app.include_router(make_arena_router(
                gate, build_trial_plan(date(2026,11,16),
                                       root=Path(tmp) / "arena"),
                enabled=True,
            ))
            cli = TestClient(app)
            for method in ("post","put","patch","delete"):
                response = getattr(cli, method)(
                    "/api/v3/arena", headers={"x-test-authorized":"true"}
                )
                self.assertEqual(response.status_code, 405)


if __name__ == "__main__":
    main()
