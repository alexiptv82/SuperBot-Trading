"""Lo script Termius di preparazione, eseguito davvero in un prefisso /tmp con systemctl finto. Nessun servizio."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "deploy" / "scripts" / "arena-prepare-paused-runs-20261118.sh"


def _fake_systemctl(bin_dir: Path, brain="active", arena="inactive"):
    bin_dir.mkdir()
    (bin_dir / "systemctl").write_text(f"""#!/bin/bash
case "$2" in superbot-v3-paper-brain-*) echo {brain};; superbot-arena-*) echo {arena};; *) echo unknown;; esac
""")
    os.chmod(bin_dir / "systemctl", 0o755)


@pytest.fixture
def env(tmp_path):
    prefix = Path("/tmp") / f"arena-prep-{os.getpid()}-{tmp_path.name}"
    (prefix / "opt" / "superbot-ai-arena-paper").mkdir(parents=True, mode=0o700)
    os.chmod(prefix / "opt" / "superbot-ai-arena-paper", 0o700)
    stage = prefix / "opt" / "superbot-arena-stage"
    subprocess.run(["git", "clone", "-q", "--no-hardlinks", str(REPO), str(stage)], check=True)
    sha = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    subprocess.run(["git", "-C", str(stage), "checkout", "-q", "--detach", sha], check=True)
    # i file del ramo non ancora committati non sono nello stage: lo stage deve riflettere ESATTAMENTE il commit
    (stage / ".venv" / "bin").mkdir(parents=True)
    os.symlink(sys.executable, stage / ".venv" / "bin" / "python3")
    _fake_systemctl(tmp_path / "bin")
    e = {"PATH": f"{tmp_path / 'bin'}:/usr/bin:/bin", "ARENA_PREP_TEST_PREFIX": str(prefix), "HOME": str(tmp_path)}
    yield prefix, sha, e
    subprocess.run(["rm", "-rf", str(prefix)])


def _run(args, e):
    return subprocess.run(["bash", str(SCRIPT), *args], capture_output=True, text=True, env=e, timeout=120)


def test_refuses_without_sha_and_test_prefix_outside_tmp(env):
    prefix, sha, e = env
    assert "SHA_REQUIRED" in _run(["--inspect"], e).stdout
    bad = dict(e, ARENA_PREP_TEST_PREFIX="/opt/x")
    assert "TEST_PREFIX_OUTSIDE_TMP" in _run(["--inspect", "--sha", sha], bad).stdout


def test_prepare_paused_end_to_end_then_refuses_a_second_time(env):
    prefix, sha, e = env
    if not (prefix / "opt" / "superbot-arena-stage" / "backend" / "v3" / "arena" / "trial_setup.py").exists():
        pytest.skip("trial_setup non ancora nel commit HEAD")
    r = _run(["--prepare-paused", "--sha", sha, "--day", "2026-11-18"], e)
    assert "ARENA_PREP_RESULT=THREE_RUNS_PREPARED_PAUSED_NO_T0" in r.stdout, r.stdout + r.stderr
    root = prefix / "opt" / "superbot-ai-arena-paper"
    for p in ("deepseek", "qwen", "minimax"):
        run = root / p / f"brain-{p}-paper20261118"
        assert (run / "pause.flag").is_file() and not (run / "arena_t0.json").exists()
        assert json.loads((run / "mandate.json").read_text())["approved"] is False
    env_file = (prefix / "etc" / "superbot-arena" / "trial.env").read_text()
    assert "ARENA_DAY_COMPACT=20261118" in env_file
    again = _run(["--prepare-paused", "--sha", sha, "--day", "2026-11-18"], e)
    assert "REFUSED=PREPARE_REFUSED" in again.stdout and "run_already_exists" in again.stdout
    other = _run(["--prepare-paused", "--sha", sha, "--day", "2026-11-19"], e)
    assert "TRIAL_ENV_DIFFERENT_DAY" in other.stdout


def test_refuses_when_brain_is_down_or_an_arena_unit_runs(env, tmp_path):
    prefix, sha, e = env
    for brain, arena, code in (("inactive", "inactive", "BRAIN_HISTORICAL_NOT_ACTIVE"),
                               ("active", "active", "ARENA_UNIT_RUNNING")):
        b = tmp_path / f"bin-{brain}-{arena}"
        _fake_systemctl(b, brain, arena)
        r = _run(["--prepare-paused", "--sha", sha, "--day", "2026-11-18"], dict(e, PATH=f"{b}:/usr/bin:/bin"))
        assert f"REFUSED={code}" in r.stdout
    assert list((prefix / "opt" / "superbot-ai-arena-paper").iterdir()) == []


def test_stage_at_a_different_sha_is_refused(env):
    prefix, sha, e = env
    r = _run(["--prepare-paused", "--sha", "0" * 40, "--day", "2026-11-18"], e)
    assert "STAGE_NOT_AT_SHA" in r.stdout
