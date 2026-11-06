"""Brain 2,000 PAPER startup must not silently pick the 1,000 default."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from backend.v3.runner.config import default_config_path, load_runner_config
from backend.v3.runner.exit_worker import (
    build_exit_worker, main as exit_main
)
from backend.v3.runner.prepared_config_guard import verify_prepared_run_config
from backend.v3.runner.prepare_paper_run import prepare_new_paper_run
from backend.v3.runner.wiring import build_runner

BASE = default_config_path()
PROFILE = BASE.with_name("runner_config_brain2000_paper.json")
RUN = "brain-rc-2000-20261106"


def _prepared(tmp_path):
    return prepare_new_paper_run(
        parent=tmp_path, run_name="brain-v3-rc2000-guard", run_id=RUN,
        config_bytes=PROFILE.read_bytes(), desk_mode="paper",
        now_ms=1794000000000, expected_initial_equity="2000"
    )


def test_matching_prepared_config_passes_read_only(tmp_path):
    folder = _prepared(tmp_path)
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
              for p in folder.iterdir() if p.is_file()}
    verify_prepared_run_config(
        data_dir=folder, run_id=RUN, config=load_runner_config(PROFILE.read_bytes()))
    after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
             for p in folder.iterdir() if p.is_file()}
    assert before == after


def test_1000_profile_rejected_before_exit_owner_or_brain(tmp_path):
    folder = _prepared(tmp_path)
    wrong = load_runner_config(BASE.read_bytes())
    with pytest.raises(ValueError, match="prepared_config_mismatch"):
        verify_prepared_run_config(data_dir=folder, run_id=RUN, config=wrong)
    with pytest.raises(ValueError, match="prepared_config_mismatch"):
        build_exit_worker(data_dir=folder, run_id=RUN, config=wrong, get_json=lambda _: [])
    with pytest.raises(ValueError, match="prepared_config_mismatch"):
        build_runner(data_dir=folder, run_id=RUN, config=wrong, exit_mode="sidecar",
                     desk_mode="paper", clock_ms=lambda: 1794000000000,
                     get_json=lambda _: [])


def test_worker_validate_only_requires_matching_2000(tmp_path):
    folder = _prepared(tmp_path)
    args = ["--data-dir", str(folder), "--run-id", RUN, "--validate-only",
            "--config", str(BASE)]
    assert exit_main(args, env={"DESK_MODE":"paper"}) == 2
    args[-1] = str(folder / "runner_config.json")
    assert exit_main(args, env={"DESK_MODE":"paper"}) == 0
    assert (folder / "pause.flag").exists()


def test_tampered_marker_or_profile_never_accepted(tmp_path):
    folder = _prepared(tmp_path)
    cfg = load_runner_config(PROFILE.read_bytes())
    m = folder / "PREPARED_PAUSED_ONLY.json"
    data = json.loads(m.read_text())
    data["initial_equity"] = "1000"
    m.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="prepared_config_mismatch"):
        verify_prepared_run_config(data_dir=folder, run_id=RUN, config=cfg)


def test_missing_marker_does_not_turn_prepared_dir_into_legacy(tmp_path):
    folder = _prepared(tmp_path)
    (folder / "PREPARED_PAUSED_ONLY.json").unlink()
    with pytest.raises(ValueError, match="prepared_config_missing"):
        verify_prepared_run_config(data_dir=folder, run_id=RUN,
                                   config=load_runner_config(PROFILE.read_bytes()))


def test_empty_synthetic_legacy_scope_remains_compatible(tmp_path):
    verify_prepared_run_config(
        data_dir=tmp_path, run_id=RUN,
        config=load_runner_config(BASE.read_bytes()))
