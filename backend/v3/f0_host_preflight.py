"""F0 passive VPS preflight: metadata only, no DB connections or writes.

This is an *observation*, not authorization to capture a running database or
proof of stopped services. Run manually via an approved console; never attach
it to an SSH-root GitHub Action. Output excludes file contents and secrets.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

TRADING_WORDS = ("superbot", "brain", "hawk", "bull", "pool", "sidecar",
                 "turbo", "deepseek", "shadow", "desk")
KNOWN_SOURCES = {
    "brain": ("/opt/superbot-brain-free/brain.sqlite3", "file"),
    "hawk": ("/opt/superbot-desk-data/hawk", "directory"),
    "bull": ("/opt/superbot-desk-data/bull", "directory"),
}
REQUIRED_CLASSIC = ("state_v2.json", "trade_history.jsonl",
                    "learning_log.jsonl", "lessons.md")


def _cmd(args: list[str]) -> tuple[bool, str]:
    try:
        res = subprocess.run(args, capture_output=True, text=True,
                             check=False, timeout=8)
    except (OSError, subprocess.SubprocessError):
        return False, ""
    if res.returncode != 0 or len(res.stdout) > 64 * 1024:
        return False, ""
    return True, res.stdout


def _metadata(path: Path, required_type: str) -> dict:
    if path.is_symlink():
        return {"present": True, "valid": False, "symlink": True}
    if required_type == "file":
        valid = path.is_file()
    else:
        valid = path.is_dir()
    if not valid:
        return {"present": path.exists(), "valid": False, "symlink": False}
    if required_type == "file":
        return {"present": True, "valid": True, "symlink": False,
                "bytes": path.stat().st_size}
    return {"present": True, "valid": True, "symlink": False}


def _related(name: str) -> bool:
    lowered = name.lower()
    return any(word in lowered for word in TRADING_WORDS)


def examine_sources(base_map: dict[str, tuple[str, str]]) -> dict:
    result = {}
    for key, (raw, category) in sorted(base_map.items()):
        path = Path(raw)
        entry = _metadata(path, category)
        if key == "brain":
            for ext in ("-wal", "-shm", "-journal"):
                entry[ext.lstrip("-")] = _metadata(Path(str(path) + ext), "file")
        elif entry["valid"]:
            entry["required"] = {
                name: _metadata(path / name, "file")
                for name in REQUIRED_CLASSIC
            }
            errors = path / "errors.md"
            entry["optional_errors_md"] = _metadata(errors, "file")
            archive = path / "archive"
            archive_meta = _metadata(archive, "directory")
            if archive_meta["valid"]:
                children = list(archive.iterdir())
                archive_meta["entry_count"] = len(children)
                archive_meta["unsafe_entries"] = sum(
                    1 for item in children
                    if item.is_symlink() or not item.is_dir()
                )
            entry["archive"] = archive_meta
        result[key] = entry
    return result


def build_report(sources: dict, docker_ok: bool, running_containers: list[str],
                 systemd_ok: bool, running_units: list[str]) -> dict:
    trading_containers = sorted({x for x in running_containers if _related(x)})
    trading_units = sorted({x for x in running_units if _related(x)})
    issues = []
    if not docker_ok:
        issues.append("DOCKER_STATUS_UNAVAILABLE")
    elif trading_containers:
        issues.append("RELATED_DOCKER_CONTAINERS_RUNNING")
    if not systemd_ok:
        issues.append("SYSTEMD_STATUS_UNAVAILABLE")
    elif trading_units:
        issues.append("RELATED_SYSTEMD_SERVICES_RUNNING")
    for key, value in sources.items():
        if not value["valid"]:
            issues.append("SOURCE_MISSING_OR_UNSAFE_" + key.upper())
        if key in ("hawk", "bull") and value["valid"]:
            for name, meta in value["required"].items():
                if not meta["valid"]:
                    issues.append("MANDATORY_FILE_MISSING_OR_UNSAFE_" +
                                  key.upper() + "_" + name.replace(".", "_").upper())
            archive = value["archive"]
            if not archive["valid"] or archive.get("unsafe_entries", 0):
                issues.append("ARCHIVE_MISSING_OR_UNSAFE_" + key.upper())
    return {
        "schema": "superbot-v3-f0-vps-preflight-v1",
        "source_metadata": sources,
        "active_related_container_names": trading_containers,
        "active_related_systemd_unit_names": trading_units,
        "status": "PREFLIGHT_BLOCKED" if issues else "PRECHECK_OK_NOT_CERTIFIED",
        "issues": sorted(set(issues)),
        "read_only_metadata_only": True,
        "no_sqlite_open_or_wal_replay": True,
        "no_backup_or_copy_performed": True,
    }


def inspect_host(source_map: dict[str, tuple[str, str]] = KNOWN_SOURCES) -> dict:
    docker_ok, containers = _cmd(
        ["docker", "ps", "--format", "{{.Names}}"]
    )
    systemd_ok, units = _cmd(
        ["systemctl", "list-units", "--type=service", "--state=running",
         "--no-pager", "--no-legend", "--plain"]
    )
    names = containers.splitlines() if docker_ok else []
    unit_names = ([s.split()[0] for s in units.splitlines() if s.strip()]
                  if systemd_ok else [])
    return build_report(examine_sources(source_map),
                        docker_ok, names, systemd_ok, unit_names)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="Machine-readable output")
    args = ap.parse_args(argv)
    try:
        result = inspect_host()
    except (OSError, ValueError) as exc:
        result = {"schema": "superbot-v3-f0-vps-preflight-v1",
                  "status": "PREFLIGHT_BLOCKED",
                  "issues": ["LOCAL_METADATA_ERROR_" + type(exc).__name__]}
    print(json.dumps(result, sort_keys=True, indent=2 if args.json else None))
    return 0 if result["status"] == "PRECHECK_OK_NOT_CERTIFIED" else 2


if __name__ == "__main__":
    sys.exit(main())
