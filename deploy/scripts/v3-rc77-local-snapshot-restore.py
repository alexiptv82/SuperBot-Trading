#!/usr/bin/env python3
"""RC77: local PAPER-only legacy snapshot + isolated restore verification.

Never starts/stops Docker, modifies account data, sends exchange orders,
changes services, or touches the running web application. The only persistent
writes are NEW files under /opt/superbot-backups/rc77-*. Fail closed otherwise.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import time

DATA_ROOT = Path('/opt/superbot-desk-data')
BACKUP_ROOT = Path('/opt/superbot-backups')
NAMES = ('hawk', 'bull')
REQUIRED = ('state_v2.json', 'trade_history.jsonl', 'learning_log.jsonl', 'lessons.md')
PENDING = ('reset.flag','reset.flag.work','close_position.flag','close_position.flag.work')
EXPECTED_OPEN = {'hawk': 0, 'bull': 0}
ARB_CLOSED_ID = {'hawk': 62, 'bull': 19}
VOLATILE_ROOT = frozenset(('exit_only_heartbeat.json', '.exit_only_writer.lock', 'heartbeat.json'))
MAX_FILES = 100_000
MAX_BYTES = 1_500_000_000
MIN_FREE = 800_000_000


class Refused(RuntimeError):
    pass


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1048576), b''):
            h.update(chunk)
    return h.hexdigest()


def read_state(path: Path) -> int:
    try:
        state = json.loads(path.read_text('utf-8'))
        positions = state.get('main', {}).get('positions')
        if not isinstance(positions, dict):
            raise ValueError('missing_position_map')
        return len(positions)
    except (OSError, ValueError, AttributeError, TypeError):
        raise Refused('invalid_legacy_state') from None


def check_owner() -> None:
    """Both original bot containers stopped, restart=no, DESK_MODE=paper."""
    for name in NAMES:
        try:
            cmd = subprocess.run(['docker','inspect','superbot-desk-'+name],
                                 capture_output=True,text=True,timeout=10,check=False)
            if cmd.returncode:
                raise Refused('missing_original_container_'+name)
            info = json.loads(cmd.stdout)[0]
            env = dict(s.split('=',1) for s in info.get('Config',{}).get('Env',[]) if '=' in s)
            if (info.get('State',{}).get('Running') is not False
                    or info.get('HostConfig',{}).get('RestartPolicy',{}).get('Name') not in ('no','')
                    or env.get('DESK_MODE') != 'paper'):
                raise Refused('legacy_not_stopped_disabled_paper_'+name)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            raise Refused('docker_owner_unverifiable_'+name) from None


def inventory(root: Path) -> dict:
    if root.is_symlink() or not root.is_dir():
        raise Refused('legacy_dir_unavailable')
    if not (root/'pause.flag').is_file():
        raise Refused('legacy_not_paused')
    if any((root/f).exists() for f in PENDING):
        raise Refused('unreconciled_close_request')
    if any((root/f).is_symlink() or not (root/f).is_file() for f in REQUIRED):
        raise Refused('essential_legacy_files_missing')
    open_count = read_state(root/'state_v2.json')
    if open_count != EXPECTED_OPEN[root.name]:
        raise Refused('legacy_open_count_changed')
    expected_id=ARB_CLOSED_ID[root.name]
    close_matches=[]
    try:
        with (root/'trade_history.jsonl').open('r',encoding='utf-8') as history:
            for line in history:
                if not line.strip():continue
                record=json.loads(line)
                if (isinstance(record,dict) and record.get('symbol')=='ARB'
                    and record.get('id')==expected_id and record.get('closed_by')=='utente'
                    and isinstance(record.get('close_ms'),int) and record['close_ms']>=1794077000000
                    and isinstance(record.get('net'),(int,float))):
                    close_matches.append(record)
    except (OSError,ValueError,UnicodeError):
        raise Refused('arb_closure_history_unverifiable') from None
    if len(close_matches)!=1:
        raise Refused('arb_manual_close_not_unique_or_missing')
    files = {}
    total = 0
    for parent, dirs, names in os.walk(root, followlinks=False):
        for d in dirs:
            p = Path(parent)/d
            if p.is_symlink():
                raise Refused('directory_symlink_not_allowed')
        for name in names:
            file = Path(parent)/name
            if Path(parent)==root and name in VOLATILE_ROOT:
                continue
            info = file.lstat()
            if not stat.S_ISREG(info.st_mode):
                raise Refused('nonregular_source_file')
            rel = str(file.relative_to(root))
            total += info.st_size
            if len(files) >= MAX_FILES or total > MAX_BYTES:
                raise Refused('snapshot_volume_limit')
            files[rel] = (info.st_size, info.st_mtime_ns, sha256(file))
    for n in REQUIRED:
        if n not in files:
            raise Refused('essential_file_not_in_inventory')
    return {'count': len(files), 'total_bytes': total, 'files': files, 'open_count': open_count}


def equal_files(source: Path, copy: Path, listed: dict) -> None:
    for rel, meta in listed['files'].items():
        original, replica = source/rel, copy/rel
        if not replica.is_file() or replica.is_symlink():
            raise Refused('snapshot_file_missing')
        if (original.stat().st_mtime_ns != meta[1]
                or original.stat().st_size != meta[0]
                or sha256(original) != meta[2] or sha256(replica) != meta[2]):
            raise Refused('snapshot_sha_or_source_changed')


def main() -> int:
    os.umask(0o077)
    if (BACKUP_ROOT.is_symlink() or not BACKUP_ROOT.is_dir()
            or BACKUP_ROOT.resolve() == DATA_ROOT.resolve()
            or not DATA_ROOT.is_dir()):
        raise Refused('backup_or_data_root_invalid')
    check_owner()
    sources = {name:DATA_ROOT/name for name in NAMES}
    before = {name:inventory(root) for name,root in sources.items()}
    total = sum(v['total_bytes'] for v in before.values())
    free = shutil.disk_usage(BACKUP_ROOT).free
    if free < max(MIN_FREE, total*3 + 250_000_000):
        raise Refused('insufficient_disk_free')
    stamp = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())
    # Only unique new folder, mode 0700. Existing backups are never overwritten.
    dest = BACKUP_ROOT / ('rc77-paper-legacy-'+stamp+'-'+str(os.getpid()))
    dest.mkdir(mode=0o700)
    print('RC77_SNAPSHOT_DIR_CREATED=True', flush=True)
    try:
        for name,root in sources.items():
            shutil.copytree(root, dest/name, symlinks=False, copy_function=shutil.copy2,
                            ignore=lambda folder, names: [n for n in names if Path(folder)==root and n in VOLATILE_ROOT])
            # Restrict any inherited source permission bits inside the backup.
            for parent,dirs,files in os.walk(dest/name,followlinks=False):
                os.chmod(parent,0o700)
                for filename in files:
                    os.chmod(Path(parent)/filename,0o600)
            check_owner()
            equal_files(root, dest/name, before[name])
        check_owner()
        for name,root in sources.items():
            after=inventory(root)
            if after != before[name]:
                raise Refused('legacy_data_changed_during_snapshot')
        # Restore rehearsal in an isolated directory, never into running bot volumes.
        with tempfile.TemporaryDirectory(prefix='.rc77-test-restore-',dir=BACKUP_ROOT) as tmp:
            location=Path(tmp)
            for name in NAMES:
                shutil.copytree(dest/name,location/name)
                equal_files(sources[name],location/name,before[name])
                if read_state(location/name/'state_v2.json') != EXPECTED_OPEN[name]:
                    raise Refused('restore_state_mismatch')
        manifest={
            'schema':'rc77-paper-local-snapshot-v1',
            'created_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'scope':'hawk,bull PAPER only; Brain unchanged',
            'source_data_unchanged':True,'restore_rehearsal':'PASS',
            'portfolios':{
                name:{'open_positions':before[name]['open_count'],
                      'files':before[name]['count'],
                      'total_bytes':before[name]['total_bytes'],
                      'hashes':{rel:meta[2] for rel,meta in before[name]['files'].items()}}
                for name in NAMES
            },
        }
        for name in NAMES:
            if type(manifest['portfolios'][name]['open_positions']) is not int or manifest['portfolios'][name]['open_positions'] != EXPECTED_OPEN[name]:
                raise Refused('snapshot_manifest_position_count_invalid')
        (dest/'MANIFEST.json').write_text(json.dumps(manifest,sort_keys=True,indent=2)+'\n',encoding='utf-8')
        os.chmod(dest/'MANIFEST.json',0o600)
        # Do not print any sensitive filenames, contents, or hashes to CI logs.
        for name in NAMES:
            print('RC77_'+name.upper()+'_OPEN_POSITIONS='+str(before[name]['open_count']))
            print('RC77_'+name.upper()+'_FILES_BACKED_UP='+str(before[name]['count']))
            print('RC77_'+name.upper()+'_HASHES_VERIFIED=True')
            print('RC77_'+name.upper()+'_RESTORE_TEST=PASS')
        print('RC77_MANIFEST_WRITTEN=True')
        print('RC77_SOURCE_TOUCHED=False')
        print('RC77_NO_DOCKER_RESTART=True')
        print('RC77_SNAPSHOT_SUCCESS=True')
        return 0
    except BaseException:
        # Preserve incomplete snapshot for forensic review; do not claim it usable.
        print('RC77_SNAPSHOT_INCOMPLETE=True',flush=True)
        raise


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Refused as exc:
        print('RC77_REFUSED='+str(exc), file=sys.stderr)
        sys.exit(2)
