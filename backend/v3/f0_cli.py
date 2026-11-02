"""Offline F0 operator entrypoint for independently witnessed PAPER backups.

No SSH, network, Docker, subprocess, repository writes, secrets or remote actions.
Use ONLY on stopped, authorized source copies. Never run against active bots.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import re
import sys

from .backup_certification import (
    capture_brain_copy,
    observe_brain_source_readonly,
    verify_brain_offhost,
)
from .f0_classic_certificate import (
    observe_classic_source_readonly,
    verify_classic_offhost,
)

_HEX64 = re.compile(r"^[a-f0-9]{64}$")


def _safe_witness(path: str, restore_root: Path) -> dict:
    """Witness must be externally stored, not bundled with the restored DB."""
    filename = Path(path)
    if filename.is_symlink() or not filename.is_file():
        raise ValueError("external_witness_missing_or_symlink")
    if filename.stat().st_size > 32768:
        raise ValueError("external_witness_too_large")
    if filename.resolve().is_relative_to(restore_root.resolve()):
        raise ValueError("witness_must_be_outside_restored_directory")
    body = json.loads(filename.read_text(encoding="utf-8"))
    if not isinstance(body, dict):
        raise ValueError("invalid_witness_json")
    return body


def _nonempty_sha(value: str) -> str:
    if not _HEX64.fullmatch(value):
        raise ValueError("invalid_manifest_sha256")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="SuperBot V3 F0 — local PAPER backup witness/restore checks, no SSH"
    )
    sub = parser.add_subparsers(dest="action", required=True)

    brain_obs = sub.add_parser("observe-brain",
                               help="Observe stopped Brain PAPER SQLite including WAL")
    brain_obs.add_argument("--source", required=True)

    brain_capture = sub.add_parser("capture-brain",
                                   help="Copy stopped Brain via SQLite backup API")
    brain_capture.add_argument("--source", required=True)
    brain_capture.add_argument("--new-directory", required=True)

    brain_verify = sub.add_parser("verify-brain",
                                  help="Check independently stored source witness against restored copy")
    brain_verify.add_argument("--restored-directory", required=True)
    brain_verify.add_argument("--external-witness", required=True)
    brain_verify.add_argument("--external-manifest-sha256", required=True)

    classic_obs = sub.add_parser("observe-classic",
                                 help="Read-only archived-run witness for Hawk/Bull")
    classic_obs.add_argument("--source", required=True)
    classic_obs.add_argument("--portfolio", required=True, choices=("hawk", "bull"))

    classic_verify = sub.add_parser("verify-classic",
                                    help="Check restored classic archive against external witness")
    classic_verify.add_argument("--restored-directory", required=True)
    classic_verify.add_argument("--external-witness", required=True)
    classic_verify.add_argument("--portfolio", required=True, choices=("hawk", "bull"))
    return parser


def run(argv: list[str] | None = None) -> dict:
    args = build_parser().parse_args(argv)
    if args.action == "observe-brain":
        result = observe_brain_source_readonly(args.source)
        return {"schema": "superbot-v3-f0-brain-source-v1",
                "source_observation": result}

    if args.action == "capture-brain":
        receipt = capture_brain_copy(args.source, args.new_directory)
        return {"schema": "superbot-v3-f0-brain-capture-v1",
                "event_count": receipt.event_count,
                "max_event_seq": receipt.max_event_seq,
                "manifest_sha256": receipt.manifest_sha256,
                "externally_certified": False,
                "warning": "The capture is NOT certified until offhost restore is independently verified."}

    if args.action == "verify-brain":
        root = Path(args.restored_directory)
        witness = _safe_witness(args.external_witness, root)
        if witness.get("schema") != "superbot-v3-f0-brain-source-v1":
            raise ValueError("wrong_brain_witness_schema")
        observation = witness.get("source_observation")
        if not isinstance(observation, dict) or any(
            type(observation.get(name)) is not int
            for name in ("event_count", "max_event_seq")
        ):
            raise ValueError("invalid_brain_witness")
        result = verify_brain_offhost(
            root,
            expected_manifest_sha256=_nonempty_sha(
                args.external_manifest_sha256),
            expected_events_sha256=observation.get("events_sha256"),
            expected_event_count=observation["event_count"],
            expected_max_event_seq=observation["max_event_seq"],
        )
        if result.event_count <= 0 or not result.externally_certified:
            raise ValueError("offhost_verification_incomplete")
        return {"schema": "superbot-v3-f0-brain-verify-v1", "verified": True,
                "event_count": result.event_count,
                "max_event_seq": result.max_event_seq,
                "note": "Witness origin and independent storage require human attestation."}

    if args.action == "observe-classic":
        witness = observe_classic_source_readonly(args.source, args.portfolio)
        return {"schema": "superbot-v3-f0-classic-source-v1",
                **asdict(witness)}

    if args.action == "verify-classic":
        root = Path(args.restored_directory)
        witness = _safe_witness(args.external_witness, root)
        if witness.get("schema") != "superbot-v3-f0-classic-source-v1":
            raise ValueError("wrong_classic_witness_schema")
        if witness.get("portfolio_id") != args.portfolio:
            raise ValueError("wrong_classic_witness_portfolio")
        result = verify_classic_offhost(
            root, args.portfolio,
            expected_files_sha256=witness.get("files_sha256"),
            expected_total_closed=witness.get("total_closed"),
            expected_historical_runs=witness.get("historical_run_count"),
            expected_current_run=witness.get("current_run"),
        )
        return {"schema": "superbot-v3-f0-classic-verify-v1",
                "verified": True,
                "portfolio": result.portfolio_id,
                "total_closed": result.total_closed,
                "note": "Witness origin and independent storage require human attestation."}
    raise ValueError("unsupported_action")


def main(argv: list[str] | None = None) -> int:
    try:
        result = run(argv)
    except (ValueError, OSError, json.JSONDecodeError, sqlite3.Error) as exc:
        print(json.dumps({"verified": False, "error_code": type(exc).__name__,
                          "status": "F0_BLOCKED"}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    # Imported late to avoid subprocess/network dependencies.
    import sqlite3
    sys.exit(main())
