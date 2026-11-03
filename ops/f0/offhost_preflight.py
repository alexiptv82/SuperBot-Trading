#!/usr/bin/env python3
"""Local F0, read-only external-backup metadata comparison.

This preflight does NOT establish that any bytes are held off-host,
that an archive contains Brain or classic files, that it can be decrypted,
or that any restore succeeded. It never reads secrets or opens databases.
Use on the VPS only by a separately authorized operator, not via SSH F0.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

STATUS = Path('/opt/superbot-extbackup/status.json')
SNAPSHOT_MANIFEST = Path('/opt/superbot-v3-backups/f0-brain-20261103T035500Z/manifest.json')
LIMIT = 65536
ARCHIVE_NAME = re.compile(r'superbot-backup-(\d{8}T\d{6}Z)\.tar\.gz\.age\Z')
HEX = re.compile(r'[0-9a-f]{64}\Z')


class UnsafeEvidence(ValueError):
    pass


def _load_limited(path: Path) -> tuple[dict, bytes]:
    """Never follow a final symlink; avoid unbounded read or TOCTOU replace."""
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > LIMIT:
            raise UnsafeEvidence('not_regular_or_oversized')
        with os.fdopen(os.dup(fd), 'rb') as stream:
            raw = stream.read(LIMIT + 1)
        if len(raw) > LIMIT:
            raise UnsafeEvidence('oversized_data')
    finally:
        os.close(fd)
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise UnsafeEvidence('not_json_object')
    return value, raw


def _time(value: object) -> datetime:
    if not isinstance(value, str):
        raise UnsafeEvidence('invalid_time')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as error:
        raise UnsafeEvidence('invalid_time') from error
    if parsed.tzinfo is None:
        raise UnsafeEvidence('time_without_offset')
    return parsed.astimezone(timezone.utc)


def _archive_time(name: object) -> datetime | None:
    """Use timestamp encoded in filename; invalid calendar dates are not evidence."""
    matched = ARCHIVE_NAME.fullmatch(name) if isinstance(name, str) else None
    if not matched:
        return None
    try:
        return datetime.strptime(matched.group(1), '%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _sha(value: object) -> bool:
    return isinstance(value, str) and bool(HEX.fullmatch(value))


def inspect(status_path: Path, manifest_path: Path) -> dict:
    """Return only allowlisted evidence; never echo paths or error strings."""
    result = {
        'schema': 'superbot-f0-backup-preflight-v1',
        'read_only': True,
        'externally_certified': False,
        'restore_verified': False,
        'archive_coverage_verified': False,
        'external_storage_verified': False,
        'legacy_status': 'UNAVAILABLE',
        'brain_manifest': 'UNAVAILABLE',
        'archive_newer_than_brain_snapshot': 'UNKNOWN',
    }
    backup_at = None
    archive_at = None
    snapshot_at = None
    try:
        status, _ = _load_limited(status_path)
        backup_at = _time(status.get('ultimo_successo'))
        name = status.get('archivio')
        archive_at = _archive_time(name)
        name_valid = archive_at is not None
        result['legacy_status'] = 'PARSED'
        result['last_external_backup_success_utc'] = backup_at.strftime('%Y-%m-%dT%H:%M:%SZ')
        result['last_archive_name_expected_format'] = name_valid
        result['last_attempt_error_reported'] = bool(status.get('ultimo_errore'))
    except (OSError, ValueError, TypeError):
        result['legacy_status'] = 'UNAVAILABLE'
    try:
        manifest, raw = _load_limited(manifest_path)
        if manifest.get('schema') != 'superbot-v3-f0-brain-snapshot-v1':
            raise UnsafeEvidence('bad_manifest_schema')
        obs = manifest.get('source_observation')
        snap = manifest.get('snapshot_observation')
        if not isinstance(obs, dict) or not isinstance(snap, dict):
            raise UnsafeEvidence('missing_observation')
        event_count, last_seq = obs.get('event_count'), obs.get('max_event_seq')
        if (type(event_count) is not int or event_count <= 0
                or type(last_seq) is not int or last_seq < event_count
                or not _sha(obs.get('events_sha256'))
                or not _sha(manifest.get('snapshot_db_sha256'))
                or obs != snap):
            raise UnsafeEvidence('invalid_manifest_observation')
        snapshot_at = _time(manifest.get('created_utc'))
        result['brain_manifest'] = 'PARSED_SELF_REPORTED_ONLY'
        result['brain_snapshot_created_utc'] = snapshot_at.strftime('%Y-%m-%dT%H:%M:%SZ')
        result['brain_events_reported'] = event_count
        result['brain_max_event_seq_reported'] = last_seq
        result['brain_manifest_sha256'] = hashlib.sha256(raw).hexdigest()
    except (OSError, ValueError, TypeError):
        result['brain_manifest'] = 'UNAVAILABLE'
    # Never infer archive recency from a successful status timestamp alone:
    # the status may reference an old or invalid archive filename.
    # This still does NOT verify archive bytes, contents, or off-host storage.
    if (backup_at is not None and snapshot_at is not None
            and archive_at is not None and archive_at <= backup_at):
        result['archive_newer_than_brain_snapshot'] = archive_at >= snapshot_at
    result['gate'] = 'NO_GO_EXTERNAL_RESTORE_AND_INDEPENDENT_WITNESS_REQUIRED'
    return result


def main() -> int:
    if os.geteuid() != 0:
        print('{"status":"REFUSED_NONROOT_LOCAL_OPERATOR"}')
        return 3
    print(json.dumps(inspect(STATUS, SNAPSHOT_MANIFEST), sort_keys=True, separators=(',', ':')))
    return 0


if __name__ == '__main__':
    sys.exit(main())
