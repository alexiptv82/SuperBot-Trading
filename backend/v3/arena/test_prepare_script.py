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


def test_failed_preparation_leaves_no_trial_env(env):
    prefix, sha, e = env
    if not (prefix / "opt" / "superbot-arena-stage" / "backend" / "v3" / "arena" / "trial_setup.py").exists():
        pytest.skip("trial_setup non ancora nel commit HEAD")
    blocker = prefix / "opt" / "superbot-ai-arena-paper" / "qwen" / "brain-qwen-paper20261118"
    blocker.mkdir(parents=True)                               # una run preesistente: la preparazione rifiuta
    r = _run(["--prepare-paused", "--sha", sha, "--day", "2026-11-18"], e)
    assert "REFUSED=PREPARE_REFUSED" in r.stdout
    assert not (prefix / "etc" / "superbot-arena" / "trial.env").exists()
    assert blocker.is_dir() and list(blocker.iterdir()) == []              # la run preesistente non e' toccata


# ---------------------------------------------------------------- PR #110: sostituzione delle run sul VPS
def _stateful_systemctl(bin_dir: Path, log: Path, brain="active", runner="inactive"):
    bin_dir.mkdir()
    state = bin_dir / "state"
    state.write_text("")
    (bin_dir / "systemctl").write_text(f"""#!/bin/bash
echo "$@" >> {log}
case "$1" in
  stop) echo "$2=inactive" >> {state}; exit 0;;
  start) echo "$2=active" >> {state}; exit 0;;
  is-active)
    case "$2" in superbot-v3-paper-brain-*) echo {brain}; exit 0;;
      superbot-arena-runner@*) echo {runner}; exit 0;; esac
    v=$(grep "^$2=" {state} | tail -1 | cut -d= -f2); echo ${{v:-active}}; exit 0;;
esac
exit 0
""")
    os.chmod(bin_dir / "systemctl", 0o755)


def _old_runs(prefix: Path):
    """Tre run preparate come sul VPS: tetto 0,75 USD e stime 2/8 per Qwen e MiniMax."""
    from datetime import date
    from backend.v3.arena import trial_setup as TS
    from backend.v3.arena.prepare import config_path

    def old(p):
        c = json.loads(config_path(p).read_bytes())
        c["daily_cap_usd"] = "0.75"
        if p != "deepseek":
            c["input_usd_per_million_tokens"], c["output_usd_per_million_tokens"] = "2.00", "8.00"
        return json.dumps(c).encode()
    root = prefix / "opt" / "superbot-ai-arena-paper"
    TS.prepare_paused(root, date(2026, 11, 18), now_ms=1_795_000_000_000, desk_mode="paper",
                      confirm=TS.PREPARE_PHRASE, config_loader=old)
    etc = prefix / "etc" / "superbot-arena"
    etc.mkdir(parents=True)
    (etc / "trial.env").write_text("ARENA_DAY=2026-11-18\nARENA_DAY_COMPACT=20261118\nV3_ARENA_TRIAL_DAY=2026-11-18\n")
    (prefix / "opt" / "superbot-v3-backups").mkdir()
    return root


def test_replace_prepared_restores_old_runs_if_new_exit_services_are_unhealthy(env, tmp_path):
    prefix, sha, e = env
    if not (prefix / "opt" / "superbot-arena-stage" / "backend" / "v3" / "arena" / "trial_setup.py").read_text() \
            .count("supersede_prepared"):
        pytest.skip("supersede non ancora nel commit HEAD")
    root = _old_runs(prefix)
    old_cfg = (root / "qwen" / "brain-qwen-paper20261118" / "runner_config.json").read_bytes()
    log = tmp_path / "systemctl.log"
    _stateful_systemctl(tmp_path / "sbin", log)
    e2 = dict(e, PATH=f"{tmp_path / 'sbin'}:/usr/bin:/bin", ARENA_PREP_TEST_SOURCE=str(REPO), ARENA_PREP_HEALTH_WAIT_S="1")
    r = _run(["--replace-prepared", "--sha", sha], e2)
    out = r.stdout
    assert "ZERO_POSITIONS_VERIFIED=TRUE" in out and "OLD_RUNS_ARCHIVED=" in out, out + r.stderr
    assert "NEW_RUNS_PREPARED_PAUSED_NO_T0=TRUE" in out
    assert "REFUSED=EXITS_NOT_HEALTHY_COUNT_0" in out          # nessun servizio uscite vero in questo ambiente
    assert "ROLLBACK_RESTORED=TRUE" in out, out + r.stderr
    # Un'uscita non sana AFTER il nuovo prepare non lascia le run nuove attive nel percorso operativo.
    restored = root / "qwen" / "brain-qwen-paper20261118"
    assert (restored / "runner_config.json").read_bytes() == old_cfg
    archived = list((prefix / "opt" / "superbot-v3-backups").glob("arena-superseded-*/SUPERSEDED-ROLLED-BACK.json"))
    assert len(archived) == 1
    quarantined = list((prefix / "opt" / "superbot-v3-backups").glob("arena-replace-failed-*/qwen/brain-qwen-paper20261118"))
    assert len(quarantined) == 1
    new_cfg = json.loads((quarantined[0] / "runner_config.json").read_text())
    assert new_cfg["daily_cap_usd"] == "2.00" and new_cfg["input_usd_per_million_tokens"] == "0.32"
    calls = log.read_text().splitlines()
    stops = [i for i, x in enumerate(calls) if x.startswith("stop superbot-arena-exit@")]
    starts = [i for i, x in enumerate(calls) if x.startswith("start superbot-arena-exit@")]
    assert len(stops) == 6 and len(starts) == 6 and min(stops) < min(starts)
    assert not any("brain" in c and c.split()[0] in ("stop", "start", "restart") for c in calls)
    assert not any("runner@" in c and c.split()[0] in ("stop", "start") for c in calls)
    assert (prefix / "opt" / "superbot-arena-stage" / ".git").is_dir()  # stage vecchio ripristinato
    assert list(prefix.glob("opt/superbot-arena-stage.failed-*"))            # stage nuovo non cancellato


def test_replace_prepared_refuses_with_active_runner_or_down_brain_and_restarts_exits_on_failure(env, tmp_path):
    prefix, sha, e = env
    if not (prefix / "opt" / "superbot-arena-stage" / "backend" / "v3" / "arena" / "trial_setup.py").read_text() \
            .count("supersede_prepared"):
        pytest.skip("supersede non ancora nel commit HEAD")
    root = _old_runs(prefix)
    for name, kw, code in (("r", {"runner": "active"}, "ARENA_RUNNER_ACTIVE"),
                           ("b", {"brain": "inactive"}, "BRAIN_HISTORICAL_NOT_ACTIVE")):
        log = tmp_path / f"{name}.log"
        _stateful_systemctl(tmp_path / f"sbin-{name}", log, **kw)
        r = _run(["--replace-prepared", "--sha", sha],
                 dict(e, PATH=f"{tmp_path / f'sbin-{name}'}:/usr/bin:/bin", ARENA_PREP_TEST_SOURCE=str(REPO)))
        assert f"REFUSED={code}" in r.stdout
        assert not any(c.startswith(("stop", "start")) for c in log.read_text().splitlines())
    # archivio impossibile (cartella dei backup assente): le vecchie run restano, uscite riavviate
    (prefix / "opt" / "superbot-v3-backups").rmdir()
    log = tmp_path / "f.log"
    _stateful_systemctl(tmp_path / "sbin-f", log)
    r = _run(["--replace-prepared", "--sha", sha],
             dict(e, PATH=f"{tmp_path / 'sbin-f'}:/usr/bin:/bin", ARENA_PREP_TEST_SOURCE=str(REPO)))
    assert "SUPERSEDE_REFUSED_OLD_RUNS_KEPT_EXITS_RESTARTED" in r.stdout
    calls = log.read_text().splitlines()
    assert sum(c.startswith("stop superbot-arena-exit@") for c in calls) == 6
    assert sum(c.startswith("start superbot-arena-exit@") for c in calls) == 6
    assert "ROLLBACK_RESTORED=TRUE" in r.stdout
    assert json.loads((root / "qwen" / "brain-qwen-paper20261118" / "runner_config.json").read_text())[
        "daily_cap_usd"] == "0.75"


@pytest.mark.parametrize("failpoint", ("after_archive", "after_stage_saved", "after_new_prepared"))
def test_replace_prepared_rolls_back_every_failure_after_archive(env, tmp_path, failpoint):
    """No loss of immutable pre-trial history, even after stage switched or new run created."""
    prefix, sha, e = env
    root = _old_runs(prefix)
    old = {}
    for p in ("deepseek", "qwen", "minimax"):
        old[p] = (root / p / f"brain-{p}-paper20261118" / "runner_config.json").read_bytes()
    stage = prefix / "opt" / "superbot-arena-stage"
    original_sha = subprocess.check_output(
        ["git", "-C", str(stage), "rev-parse", "HEAD"], text=True).strip()
    log = tmp_path / (failpoint + ".log")
    sbin = tmp_path / ("sbin-" + failpoint)
    _stateful_systemctl(sbin, log)
    e2 = dict(e, PATH=f"{sbin}:/usr/bin:/bin",
              ARENA_PREP_TEST_SOURCE=str(REPO), ARENA_PREP_HEALTH_WAIT_S="1",
              ARENA_PREP_TEST_FAILPOINT=failpoint)
    result = _run(["--replace-prepared", "--sha", sha], e2)
    assert result.returncode != 0
    assert f"REFUSED=INJECTED_FAILURE_{failpoint.upper()}" in result.stdout
    assert "ROLLBACK_RESTORED=TRUE" in result.stdout, result.stdout + result.stderr
    assert subprocess.check_output(
        ["git", "-C", str(stage), "rev-parse", "HEAD"], text=True).strip() == original_sha
    for p in ("deepseek", "qwen", "minimax"):
        run = root / p / f"brain-{p}-paper20261118"
        assert (run / "runner_config.json").read_bytes() == old[p]
        assert (run / "pause.flag").is_file()
        assert not (run / "arena_t0.json").exists()
    backup = prefix / "opt" / "superbot-v3-backups"
    assert len(list(backup.glob("arena-superseded-*/SUPERSEDED-ROLLED-BACK.json"))) == 1
    if failpoint == "after_new_prepared":
        assert len(list(backup.glob("arena-replace-failed-*/qwen/brain-qwen-paper20261118"))) == 1
    calls = log.read_text().splitlines()
    assert not any("brain" in x and x.split()[0] in ("stop", "start", "restart") for x in calls)
    assert not any("runner@" in x and x.split()[0] in ("stop", "start") for x in calls)
