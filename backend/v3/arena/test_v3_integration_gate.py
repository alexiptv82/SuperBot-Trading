"""The regular V3 server must not accidentally publish Arena without gates."""
from __future__ import annotations

import os
from unittest import TestCase, main
from unittest.mock import patch

from backend.v3_api import V3Paths, make_router


def _fake_paths():
    return V3Paths(
        journal_path=None, run_id="brain-v3-paper20261111",
        budget_db_path=None, heartbeat_path=None, pause_flag_path=None,
        falco_data_dir="/nonexistent/falco",
        toro_data_dir="/nonexistent/toro",
    )


def _arena_paths(env):
    with patch.dict(os.environ, env, clear=True):
        router = make_router(lambda: "test-session", _fake_paths())
        return [(route.path, sorted(route.methods)) for route in router.routes
                if route.path.endswith("/arena")]


class ArenaIntegrationTests(TestCase):
    def test_no_route_in_default_deployed_configuration(self):
        self.assertEqual(_arena_paths({}), [])

    def test_missing_date_cannot_enable_route(self):
        self.assertEqual(_arena_paths({
            "V3_ARENA_READONLY_ENABLED": "1",
            "DESK_MODE": "paper", "TRADING_MODE": "paper",
        }), [])

    def test_invalid_date_cannot_enable_route(self):
        self.assertEqual(_arena_paths({
            "V3_ARENA_READONLY_ENABLED": "1",
            "DESK_MODE": "paper", "TRADING_MODE": "paper",
            "V3_ARENA_TRIAL_DAY": "2026-02-30",
        }), [])

    def test_non_paper_mode_cannot_enable_route(self):
        self.assertEqual(_arena_paths({
            "V3_ARENA_READONLY_ENABLED": "1",
            "DESK_MODE": "paper", "TRADING_MODE": "live",
            "V3_ARENA_TRIAL_DAY": "2026-11-16",
        }), [])

    def test_valid_explicit_paper_enables_exact_one_get(self):
        routes = _arena_paths({
            "V3_ARENA_READONLY_ENABLED": "1",
            "DESK_MODE": "paper", "TRADING_MODE": "paper",
            "V3_ARENA_TRIAL_DAY": "2026-11-16",
        })
        self.assertEqual(routes, [("/api/v3/arena", ["GET"])])


if __name__ == "__main__":
    main()
