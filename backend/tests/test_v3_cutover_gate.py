"""Safety contract: login remains accessible, trading commands are forbidden."""
import pytest

from backend.v3.cutover_gate import should_refuse_mutation, classic_single_close_enabled, brain_single_close_enabled


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


@pytest.mark.parametrize("path", (
    "/api/desk/close-position", "/api/desk/bull/close-position",
))
def test_explicit_paper_opt_in_allows_only_single_classic_manual_close(path):
    assert not should_refuse_mutation("POST",path,readonly=True,allow_paper_single_close=True)
    for method in ("PUT", "PATCH", "DELETE"):
        assert should_refuse_mutation(method,path,readonly=True,allow_paper_single_close=True)


@pytest.mark.parametrize("path", (
    "/api/desk/close-all", "/api/desk/bull/close-all",
    "/api/desk/resume", "/api/desk/bull/resume",
    "/api/desk/pause", "/api/desk/bull/pause",
    "/api/bot/start", "/api/desk/reset-portfolio",
    "/api/desk/bull/reset-portfolio", "/api/v3/brain/close",
    "/api/desk/close-position/extra", "/api/desk/bull/close-position/extra",
))
def test_classic_single_only_does_not_unlock_any_other_mutation(path):
    assert should_refuse_mutation("POST",path,readonly=True,allow_paper_single_close=True)


def test_single_close_feature_flag_requires_all_4_paper_readonly_conditions():
    env={"V3_CUTOVER_READONLY":"1", "V3_ALLOW_CLASSIC_SINGLE_CLOSE":"1",
         "TRADING_MODE":"paper","DESK_MODE":"paper"}
    assert classic_single_close_enabled(env)
    for key in env:
        modified=dict(env,**{key:"0" if key.startswith("V3_") else "live"})
        assert not classic_single_close_enabled(modified)
    assert not classic_single_close_enabled({})



def test_brain_paper_manual_close_is_individual_and_explicitly_opted_in():
    env = {'V3_CUTOVER_READONLY':'1','V3_ALLOW_BRAIN_SINGLE_CLOSE':'1',
           'TRADING_MODE':'paper','DESK_MODE':'paper'}
    assert brain_single_close_enabled(env)
    assert not should_refuse_mutation('POST','/api/v3/brain/close',readonly=True,
                                     allow_paper_brain_single_close=True)
    for method in ('PUT','PATCH','DELETE'):
        assert should_refuse_mutation(method,'/api/v3/brain/close',readonly=True,
                                      allow_paper_brain_single_close=True)
    for path in ('/api/v3/brain/close-all','/api/v3/brain/close/extra',
                 '/api/v3/brain/start','/api/v3/brain/reset','/api/bot/start',
                 '/api/desk/resume','/api/desk/close-all'):
        assert should_refuse_mutation('POST',path,readonly=True,
                                      allow_paper_brain_single_close=True)
    for name in env:
        modified=dict(env)
        modified[name]='0' if name.startswith('V3_') else 'live'
        assert not brain_single_close_enabled(modified)
    assert not brain_single_close_enabled({})
