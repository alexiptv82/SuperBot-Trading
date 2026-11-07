"""Safety contract: login remains accessible, trading commands are forbidden."""
import pytest

from backend.v3.cutover_gate import should_refuse_mutation


@pytest.mark.parametrize("path", (
    "/api/bot/start", "/api/bot/stop",
    "/api/desk/close-all", "/api/desk/close-position",
    "/api/desk/bull/close-all", "/api/desk/hawk/trading/enable",
    "/api/desk/bull/reset-portfolio", "/api/v3/brain/close",
    "/api/v3/brain/close-position", "/api/brain/unknown",
    "/api/supervisor/restart",
))
def test_readonly_blocks_every_trading_command(path):
    for method in ("POST","PUT","PATCH","DELETE"):
        assert should_refuse_mutation(method,path,readonly=True)


@pytest.mark.parametrize("path", (
    "/api/auth/login", "/api/auth/change-password", "/api/auth/forgot",
    "/api/auth/webauthn/login/options", "/api/auth/webauthn/login/verify",
    "/api/auth/webauthn/register/verify",
))
def test_login_and_auth_controls_are_not_blocked(path):
    assert not should_refuse_mutation("POST",path,readonly=True)


@pytest.mark.parametrize("path", (
    "/api/v3/overview", "/api/v3/brain/status",
    "/api/desk/status", "/api/desk/bull/trades",
    "/api/bot/status",
))
def test_readonly_allows_authenticated_queries(path):
    assert not should_refuse_mutation("GET",path,readonly=True)


def test_guard_is_explicit_opt_in_and_path_boundary_aware():
    assert not should_refuse_mutation("POST","/api/desk/close-all",readonly=False)
    assert not should_refuse_mutation("POST","/api/deskman",readonly=True)
    assert not should_refuse_mutation("POST","/api/botanical",readonly=True)
    assert not should_refuse_mutation("POST","/api/auth/login",readonly=True)
