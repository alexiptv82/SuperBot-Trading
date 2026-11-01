"""Read-only Docker inventory of possible Brain wallet writers.

No wallet files, environment variables, secrets, logs or container commands
are accessed. Every running container is inspected, even if its name is not
related to Brain; otherwise an unexpected writer could be missed.

This is a PRE-FLIGHT, NOT runtime ownership attestation. The caller must
separately verify the actual writer process and wallet format on the VPS.
No autoselection, restart, deploy, or trading side effects.
"""
from __future__ import annotations

import json
from pathlib import PurePosixPath
import re
import subprocess

FREE_MOUNT = '/opt/superbot-brain-free'
PILOT_MOUNT = '/opt/superbot-desk-data/brain'
MAX_CONTAINERS = 100
MAX_MOUNTS_PER_CONTAINER = 100


def _docker(args):
    if not (args == ['ps', '--format', '{{.Names}}'] or (
        len(args) == 4 and args[:3] == ['inspect', '--format', '{{json .Mounts}}']
    )):
        raise ValueError('unapproved_docker_read_command')
    try:
        result = subprocess.run(
            ['docker', *args], capture_output=True, text=True,
            timeout=8, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError('docker_metadata_unavailable') from exc
    if result.returncode:
        raise ValueError('docker_metadata_unavailable')
    if len(result.stdout) > 200_000:
        raise ValueError('docker_metadata_oversize')
    return result.stdout


def _mount_scope(mount):
    """Return potentially touched Brain wallets; broad mounts fail ambiguous."""
    if not isinstance(mount, dict):
        raise ValueError('invalid_docker_mount_metadata')
    sources = (mount.get('Source'), mount.get('Destination'))
    if any(not isinstance(v, str) or not v.startswith('/') for v in sources):
        raise ValueError('invalid_docker_mount_metadata')
    if type(mount.get('RW')) is not bool:
        raise ValueError('missing_docker_mount_write_flag')
    affected = set()
    broad = False
    for family, secret_root in (('free', FREE_MOUNT), ('pilot', PILOT_MOUNT)):
        root = PurePosixPath(secret_root)
        for field in sources:
            current = PurePosixPath(field)
            if current == root or current in root.parents or root in current.parents:
                affected.add(family)
                # A bind on /opt, /opt/superbot-desk-data, or a nested file
                # cannot certify exact root ownership; count as ambiguous.
                broad |= current != root
    return affected, broad


def inspect_running_brain_writer_candidates(docker_reader=_docker):
    """Return ONLY aggregate sanitised diagnostics, never a process identity."""
    names = docker_reader(['ps', '--format', '{{.Names}}']).splitlines()
    if len(names) > MAX_CONTAINERS:
        raise ValueError('too_many_running_containers')
    if len(set(names)) != len(names):
        raise ValueError('duplicate_container_metadata')
    totals = {
        'free': 0, 'pilot': 0, 'both': 0,
        'unexpected_writer': 0, 'web_app_writer': 0,
        'broad_rw': 0, 'app_readonly': 0, 'unclassified': 0,
    }
    for name in names:
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', name):
            raise ValueError('invalid_container_name')
        raw = docker_reader(['inspect', '--format', '{{json .Mounts}}', name])
        try:
            mounts = json.loads(raw)
        except (ValueError, TypeError) as exc:
            raise ValueError('invalid_docker_mount_metadata') from exc
        if not isinstance(mounts, list) or len(mounts) > MAX_MOUNTS_PER_CONTAINER:
            raise ValueError('invalid_docker_mount_metadata')
        writing = set()
        readonly = set()
        broad_write = False
        for mount in mounts:
            affected, broad = _mount_scope(mount)
            if mount['RW']:
                writing.update(affected)
                broad_write |= bool(affected) and broad
            else:
                readonly.update(affected)
        if writing == {'free', 'pilot'}:
            totals['both'] += 1
        elif writing == {'free'}:
            totals['free'] += 1
        elif writing == {'pilot'}:
            totals['pilot'] += 1
        elif readonly:
            totals['app_readonly'] += 1
        else:
            totals['unclassified'] += 1
        if writing and not ('brain' in name.lower() or 'superbot' in name.lower()):
            totals['unexpected_writer'] += 1
        if writing and name == 'superbot':
            totals['web_app_writer'] += 1
        if broad_write:
            totals['broad_rw'] += 1

    candidates = totals['free'] + totals['pilot'] + totals['both']
    if not candidates:
        state = 'NO_KNOWN_WRITABLE_MOUNT_CANDIDATE'
    elif (candidates != 1 or totals['both'] or totals['broad_rw'] or
          totals['unexpected_writer'] or totals['web_app_writer']):
        state = 'AMBIGUOUS_OR_UNEXPECTED_WRITER_MOUNT'
    else:
        state = 'ONE_EXACT_WRITABLE_MOUNT_CANDIDATE_NOT_PROVEN_OWNER'
    return {
        'schema': 'long-shadow-brain-writer-docker-metadata-v2',
        'status': state,
        'running_writer_mount_candidate_count': candidates,
        'running_containers_examined': len(names),
        'candidate_counts': totals,
        'coverage': 'all_running_docker_containers_known_brain_paths',
        'active_owner_confirmed': False,
        'brain_source_autoselected': False,
        'deployment_approved': False,
        'wallets_read': False,
        'balances_exposed': False,
        'env_inspected': False,
        'orders_created': 0,
        'caution': 'Mounts alone cannot identify writer processes, host services or non-Docker writers.',
    }


def main():
    print(json.dumps(inspect_running_brain_writer_candidates(), sort_keys=True))


if __name__ == '__main__':
    main()
