"""Sonda della web Brain Unico, modalita' candidate, su una run VERA preparata con il profilo B in una cartella
temporanea, con il servizio delle uscite sano e la run in SOLA LETTURA per la web (come il mount :ro).
Nessun Docker, nessuna rete: autenticazione sostituita da una dipendenza di prova (la vera e' provata sul VPS)."""
import importlib.util
import io
import os
import stat
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("bu_probe", HERE / "brain_unico_web_probe.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


@pytest.fixture
def run(tmp_path, monkeypatch):
    from backend.v3.runner import prepare_paper_run
    parent = tmp_path / "runs"
    parent.mkdir()
    cfg = ROOT / "backend/v3/runner/runner_config_brain_unico_paper_b.json"
    monkeypatch.setenv("DESK_MODE", "paper")
    assert prepare_paper_run.main(["--parent", str(parent), "--run-name", "brain-v3-unico-paper-rc1",
                                   "--run-id", probe.RUN_ID, "--config", str(cfg), "--prepare-paper-paused",
                                   "--expected-initial-equity", "2000"]) == 0
    d = parent / "brain-v3-unico-paper-rc1"
    monkeypatch.setattr(probe, "RUN_DIR", str(d))
    env = {"TRADING_MODE": "paper", "V3_CUTOVER_READONLY": "1", "V3_ALLOW_BRAIN_SINGLE_CLOSE": "1",
           "V3_CLOSE_BRIDGE_ONLY": "1", "V3_CLOSE_BRIDGE_SOCKET": "/run/superbot-paper-close/close.sock",
           "V3_RUN_ID": probe.RUN_ID}
    for key, name in (("V3_JOURNAL_PATH", "journal.db"), ("V3_HEARTBEAT_PATH", "heartbeat.json"),
                      ("V3_BUDGET_DB_PATH", "budget.db"), ("V3_PAUSE_FLAG_PATH", "pause.flag"),
                      ("V3_RUNNER_CONFIG_PATH", "runner_config.json"),
                      ("V3_CLOSE_REQUEST_PATH", "close_request.json"), ("V3_CLOSE_RESULT_PATH", "close_result.json")):
        env[key] = str(d / name)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    # autenticazione di prova al posto di quella vera (DB e JWT del VPS): modulo sostituito
    import types
    from fastapi import Header, HTTPException
    auth = types.ModuleType("backend.auth")
    monkeypatch.setitem(sys.modules, "backend.auth", auth)

    async def require(authorization: str = Header(default=None)):
        if authorization != "Bearer prova":
            raise HTTPException(status_code=401)
        return {"scope": "full"}
    auth.require_session = require
    auth.create_session_token = lambda scope="full": "prova"
    monkeypatch.setattr(probe, "_copy_auth_db", lambda: None)
    monkeypatch.setattr(probe, "compile_backend", lambda root="/app/backend": probe.__dict__["_compile_real"](ROOT / "backend"))
    return d


probe._compile_real = probe.compile_backend


def _readonly(d):
    for p in d.iterdir():
        p.chmod(stat.S_IRUSR | (stat.S_IXUSR if p.is_dir() else 0))
    d.chmod(stat.S_IRUSR | stat.S_IXUSR)


def _writable(d):
    d.chmod(0o700)
    for p in d.iterdir():
        p.chmod(0o700 if p.is_dir() else 0o600)


def _candidate(flag):
    out = io.StringIO()
    with redirect_stdout(out):
        try:
            probe.candidate(flag)
            code = 0
        except SystemExit as exc:
            code = exc.code
    return code, out.getvalue()


def test_candidate_reads_the_new_run_and_enables_single_close_with_a_healthy_exit_on_a_read_only_view(run):
    from backend.v3.runner.exit_service import ExitService
    from backend.v3.runner.monitor import MonitorReport
    import time
    svc = ExitService(run_id=probe.RUN_ID, data_dir=run, run_commands=lambda _: None,
                      run_monitor=lambda _: MonitorReport(0, (), ()))
    with svc:
        assert svc.tick(int(time.time() * 1000)).state == "healthy"
        if os.geteuid() != 0:
            _readonly(run)
        try:
            code, out = _candidate(True)
        finally:
            _writable(run)
    assert code in (0, None), out
    assert "RESULT=PASS_CANDIDATE" in out
    assert '"model": "deepseek-flash"' in out and '"run_id": "brain-unico-paper-rc1"' in out
    assert '"close_allowed": true' in out


def test_candidate_refuses_close_when_the_exit_service_is_not_running(run):
    code, out = _candidate(True)
    assert code == 2 and "FAILED_close_not_allowed_with_healthy_exit" in out
    code, out = _candidate(False)
    assert code in (0, None) and "RESULT=PASS_CANDIDATE" in out and '"close_allowed": false' in out


def test_candidate_refuses_a_web_still_on_the_old_run(run, monkeypatch):
    monkeypatch.setenv("V3_RUN_ID", "brain-v3-paper20261111")
    code, out = _candidate(False)
    assert code == 2 and "FAILED_env_V3_RUN_ID" in out
