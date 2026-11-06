"""Verify that a prepared PAPER run uses its exact recorded configuration.

Prevents a Brain V3 sidecar and its OPEN runner from silently selecting the
default 1,000 USDT configuration when the prepared run was created for 2,000.
Pure read-only validation: no journal writes, no time or network dependencies.
Legacy synthetic runs with neither preparation file remain compatible.
"""
from __future__ import annotations

import hashlib
import json
import stat
from pathlib import Path

from backend.v3.runner.config import RunnerConfig, load_runner_config


def verify_prepared_run_config(*, data_dir: Path, run_id: str,
                               config: RunnerConfig) -> None:
    """Raise a fixed refusal when a prepared run's config does not match.

    The bootstrap writes both files before its PREPARED_PAUSED_ONLY.json marker.
    A run with one of the two present but not the other is never trusted.
    """
    if (not isinstance(data_dir, Path) or not data_dir.is_absolute()
            or data_dir.is_symlink() or not data_dir.is_dir()
            or type(run_id) is not str or not run_id
            or type(config) is not RunnerConfig):
        raise ValueError("prepared_config_invalid")
    marker = data_dir / "PREPARED_PAUSED_ONLY.json"
    cfg_path = data_dir / "runner_config.json"
    try:
        marker_exists = marker.exists() or marker.is_symlink()
        cfg_exists = cfg_path.exists() or cfg_path.is_symlink()
        if not marker_exists and not cfg_exists:
            return  # existing synthetic/legacy test run, no V3 RC marker
        if not marker_exists or not cfg_exists:
            raise ValueError("prepared_config_missing")
        for path in (marker, cfg_path):
            mode = path.lstat().st_mode
            if not stat.S_ISREG(mode) or path.is_symlink() or mode & 0o022:
                raise ValueError("prepared_config_unsafe")
        raw = cfg_path.read_bytes()
        marker_raw = marker.read_bytes()
        if not 1 <= len(raw) <= 131072 or not 1 <= len(marker_raw) <= 8192:
            raise ValueError("prepared_config_invalid")
        saved = load_runner_config(raw)
        details = json.loads(marker_raw.decode("utf-8"))
        if (type(details) is not dict or
                set(details) != {"run_id", "portfolio_id", "paper_only",
                                 "paused", "mandate_approved", "config_sha256",
                                 "initial_equity"} or
                details["run_id"] != run_id or
                details["portfolio_id"] != "brain" or
                details["paper_only"] is not True or
                details["paused"] is not True or
                details["mandate_approved"] is not False or
                details["initial_equity"] != str(saved.initial_equity) or
                details["config_sha256"] != hashlib.sha256(raw).hexdigest() or
                saved != config):
            raise ValueError("prepared_config_mismatch")
    except ValueError:
        raise
    except (OSError, UnicodeError, TypeError, KeyError):
        raise ValueError("prepared_config_invalid") from None
