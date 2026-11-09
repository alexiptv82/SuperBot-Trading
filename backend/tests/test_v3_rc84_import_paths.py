"""Gli import dei moduli backend si risolvono con PYTHONPATH ASSOLUTO, da qualunque cwd e in qualunque ordine dei test.

La CI imposta PYTHONPATH=<workspace>:<workspace>/backend (equivalente a ".:backend", ma immune ai test che cambiano cwd).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ABS = f"{ROOT}:{ROOT / 'backend'}"
MODULES = ("desk.cli", "desk_view", "live_view", "backend.v3_api", "backend.v3.runner.wiring",
           "backend.v3.runner.exit_worker", "backend.tests.conftest")


def _env(pythonpath):
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env.update(PYTHONPATH=pythonpath, REACT_APP_BACKEND_URL="", SUPERBOT_ALLOW_INTEGRATION="0")
    return env


def test_every_module_imports_with_absolute_pythonpath_from_an_unrelated_directory(tmp_path):
    code = "import " + ", ".join(MODULES) + "; print('ok')"
    proc = subprocess.run([sys.executable, "-c", code], cwd=str(tmp_path), env=_env(ABS),
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0 and "ok" in proc.stdout, proc.stderr


def test_a_relative_pythonpath_breaks_when_the_cwd_changes_which_is_why_the_ci_uses_absolute_paths(tmp_path):
    proc = subprocess.run([sys.executable, "-c", "import desk.cli"], cwd=str(tmp_path), env=_env(".:backend"),
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode != 0 and "No module named 'desk'" in proc.stderr


FILES = ["backend/tests/test_v3_rc80_paper_stop_hardening.py", "backend/tests/test_desk_view.py",
         "backend/tests/test_long_s25.py", "backend/tests/test_v3_exit_service.py"]


@pytest.mark.parametrize("order", [FILES, FILES[::-1], FILES[1:] + FILES[:1], [FILES[2], FILES[0], FILES[3], FILES[1]]],
                         ids=["forward", "reverse", "rotated", "shuffled"])
def test_results_do_not_depend_on_the_order_in_which_test_files_run(order):
    proc = subprocess.run([sys.executable, "-m", "pytest", *order, "-q", "-p", "no:cacheprovider", "--strict-markers",
                           "-m", "not integration"], cwd=str(ROOT), env=_env(ABS), capture_output=True, text=True,
                          timeout=600)
    assert proc.returncode == 0, proc.stdout[-1500:] + proc.stderr[-500:]
    assert " failed" not in proc.stdout and " error" not in proc.stdout


def test_auth_and_profiles_before_the_subprocess_lock_tests_in_both_orders():
    pytest.importorskip("sqlalchemy")        # dichiarata in requirements.txt: nella CI e' sempre presente
    auth = ["backend/tests/test_auth_flow.py", "backend/tests/test_profiles_engine.py"]
    lock = ["backend/tests/test_v3_rc80_paper_stop_hardening.py"]
    for order in (auth + lock, lock + auth):
        proc = subprocess.run([sys.executable, "-m", "pytest", *order, "-q", "-p", "no:cacheprovider"],
                              cwd=str(ROOT), env=_env(ABS), capture_output=True, text=True, timeout=600)
        assert proc.returncode == 0, proc.stdout[-1500:] + proc.stderr[-500:]
