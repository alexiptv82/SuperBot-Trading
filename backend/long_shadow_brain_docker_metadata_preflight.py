"""Privacy-preserving Docker metadata PRE-FLIGHT for Brain writer ownership.

Purpose: identify whether Docker has running writer-mount candidates for
the historical Brain Free/Pilot data paths. It DOES NOT prove which process
owns a wallet; it never chooses a Brain automatically.

No ssh, HTTP, Docker writes, environment reads, logs, PnL or trading APIs.
Nothing runs unless a human independently invokes this on a target host.
"""
from __future__ import annotations

import json
import re
import subprocess

FREE_MOUNT='/opt/superbot-brain-free'
PILOT_MOUNT='/opt/superbot-desk-data/brain'
MAX_CONTAINERS=50

def _docker(args):
    try:
        result=subprocess.run(['docker',*args],
                              capture_output=True,text=True,timeout=8,
                              check=False)
    except (OSError,subprocess.TimeoutExpired) as exc:
        raise ValueError('docker_metadata_unavailable') from exc
    if result.returncode:
        raise ValueError('docker_metadata_unavailable')
    if len(result.stdout)>200_000:
        raise ValueError('docker_metadata_oversize')
    return result.stdout

def inspect_running_brain_writer_candidates(docker_reader=_docker):
    """All outputs are aggregate counts; never expose paths, IDs or secrets."""
    names=docker_reader(['ps','--format','{{.Names}}']).splitlines()
    if len(names)>MAX_CONTAINERS:
        raise ValueError('too_many_running_containers')
    totals={'free':0,'pilot':0,'both':0,'unclassified':0,'app_readonly':0}
    for name in names:
        # Only superbot/brain-named containers; no arbitrary inspect.
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}',name):
            raise ValueError('invalid_container_name')
        if not ('brain' in name.lower() or 'superbot' in name.lower()):
            continue
        raw=docker_reader(['inspect','--format','{{json .Mounts}}',name])
        try:
            mounts=json.loads(raw)
        except (ValueError,TypeError) as exc:
            raise ValueError('invalid_docker_mount_metadata') from exc
        if not isinstance(mounts,list):
            raise ValueError('invalid_docker_mount_metadata')
        writing=set()
        ro=set()
        for m in mounts:
            if not isinstance(m,dict):
                raise ValueError('invalid_docker_mount_metadata')
            target=m.get('Destination')
            identity='free' if target==FREE_MOUNT else (
                'pilot' if target==PILOT_MOUNT else None)
            if identity is None:
                continue
            if m.get('RW') is True:
                writing.add(identity)
            elif m.get('RW') is False:
                ro.add(identity)
            else:
                raise ValueError('missing_docker_mount_write_flag')
        if writing=={'free','pilot'}:
            totals['both']+=1
        elif writing=={'free'}:
            totals['free']+=1
        elif writing=={'pilot'}:
            totals['pilot']+=1
        elif ro and not writing:
            totals['app_readonly']+=1
        else:
            totals['unclassified']+=1
    candidates=totals['free']+totals['pilot']+totals['both']
    result=('NO_WRITABLE_BRAIN_MOUNT_CANDIDATE' if candidates==0 else
            'MULTIPLE_OR_AMBIGUOUS_WRITERS' if (
                candidates!=1 or totals['both']>0) else
            'ONE_WRITABLE_MOUNT_CANDIDATE_NOT_PROVEN_OWNER')
    return {'schema':'long-shadow-brain-writer-docker-metadata-v1',
            'status':result,'running_writer_mount_candidate_count':candidates,
            'candidate_counts':totals,
            'active_owner_confirmed':False,
            'brain_source_autoselected':False,
            'deployment_approved':False,'wallets_read':False,
            'balances_exposed':False,'env_inspected':False,
            'orders_created':0,
            'caution':'A writable mount and container name do not certify the process owner. Manual runtime mapping still required.'}

def main():
    print(json.dumps(inspect_running_brain_writer_candidates(),sort_keys=True))

if __name__=='__main__':
    main()
