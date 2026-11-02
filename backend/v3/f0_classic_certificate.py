"""F0 source-witness/restore verification for frozen classic PAPER directories.

Never writes to classic files or performs imports. This verifies archived
runs plus current cash bookkeeping, and binds the check to a separately
recorded complete-source digest. Witness authenticity is an external gate.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re

from .legacy_archives import audit_classic_archives
from .legacy_accounting import audit_classic_books
from .legacy_multirun import audit_classic_multirun
from .offline_import import _source_hashes

_HEX = re.compile("[a-f0-9]{64}\\Z")


@dataclass(frozen=True)
class ClassicSourceWitness:
    portfolio_id: str
    files_sha256: str
    total_closed: int
    historical_run_count: int
    current_run: int


def observe_classic_source_readonly(
    directory: str | Path, portfolio_id: str
) -> ClassicSourceWitness:
    """Build a source-side witness after all classic archive gates PASS."""
    root = Path(directory)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("unsafe_classic_source")
    report = audit_classic_multirun(root, portfolio_id)
    books = audit_classic_books(root, portfolio_id)
    archive = audit_classic_archives(root, portfolio_id)
    if (not report.eligible or not books.cash_formula_pass
            or not books.multirun_pass or books.issues or not archive.eligible):
        raise ValueError("classic_archive_or_accounting_failed")
    hashes = _source_hashes(root)
    canonical = json.dumps(hashes, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=True).encode("utf-8")
    return ClassicSourceWitness(
        portfolio_id=portfolio_id,
        files_sha256=sha256(canonical).hexdigest(),
        total_closed=report.history_closes,
        historical_run_count=len(archive.verified_runs),
        current_run=report.current_run,
    )


def verify_classic_offhost(
    directory: str | Path, portfolio_id: str,
    *,
    expected_files_sha256: str,
    expected_total_closed: int,
    expected_historical_runs: int,
    expected_current_run: int,
) -> ClassicSourceWitness:
    """Require a witness obtained separately from the restored data."""
    if (not isinstance(expected_files_sha256, str)
            or not _HEX.fullmatch(expected_files_sha256)
            or type(expected_total_closed) is not int
            or expected_total_closed < 1
            or type(expected_historical_runs) is not int
            or expected_historical_runs < 0
            or type(expected_current_run) is not int
            or expected_current_run <= 0):
        raise ValueError("invalid_classic_external_witness")
    actual = observe_classic_source_readonly(directory, portfolio_id)
    if (actual.files_sha256 != expected_files_sha256
            or actual.total_closed != expected_total_closed
            or actual.historical_run_count != expected_historical_runs
            or actual.current_run != expected_current_run):
        raise ValueError("classic_external_source_witness_mismatch")
    return actual
