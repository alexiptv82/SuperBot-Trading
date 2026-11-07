#!/usr/bin/env bash
# RC69 Singapore: READ ONLY readiness for historic PAPER closes and V3 app.
# No Docker start/stop, no modification to state, no file creation on VPS.
set -euo pipefail
python3 - <<'PY'
import hashlib, json, os, shutil, subprocess, time
from pathlib import Path
now=time.time()
base=Path('/opt/superbot-desk-data')
backups=Path('/opt/superbot-backups')
required=('state_v2.json','trade_history.jsonl','learning_log.jsonl','lessons.md')
pending=('reset.flag','reset.flag.work','close_position.flag','close_position.flag.work')

def sha(f):
    h=hashlib.sha256()
    with f.open('rb') as src:
        for b in iter(lambda:src.read(1024*1024),b''):
            h.update(b)
    return h.hexdigest()

def docker(name):
    try:
        r=subprocess.run(['docker','inspect',name],text=True,capture_output=True,timeout=6,check=False)
        if r.returncode:
            return None
        data=json.loads(r.stdout)[0]
        cfg=data.get('Config') or {}
        env=dict(x.split('=',1) for x in (cfg.get('Env') or []) if '=' in x)
        return {'running': data.get('State',{}).get('Running'),
                'restart':data.get('HostConfig',{}).get('RestartPolicy',{}).get('Name'),
                'mode':env.get('DESK_MODE','UNSET'),
                'mounts':[m.get('Source','') for m in data.get('Mounts') or []],
                'configured_v3_journal':bool(env.get('V3_JOURNAL_PATH')),
                'configured_v3_run':bool(env.get('V3_RUN_ID')),
                'configured_v3_config':bool(env.get('V3_RUNNER_CONFIG_PATH')),
                'configured_v3_close':bool(env.get('V3_CLOSE_REQUEST_PATH'))}
    except (OSError,ValueError,subprocess.TimeoutExpired):
        return None

def directories(root, max_depth=5, max_dirs=2000):
    if not root.is_dir() or root.is_symlink():
        return []
    found=[]
    visited=0
    for parent, ds, fs in os.walk(root, followlinks=False):
        ds[:]=[d for d in ds if not (Path(parent)/d).is_symlink()]
        depth=len(Path(parent).relative_to(root).parts)
        if depth>=max_depth:
            ds[:]=[]
        visited+=1
        if visited>max_dirs:
            break
        if all((Path(parent)/n).is_file() and not (Path(parent)/n).is_symlink() for n in required):
            found.append(Path(parent))
        if len(found)>=80:
            break
    return found

print('RC69_MODE=READ_ONLY')
print('RC69_TIMESTAMP_UTC='+time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()))
try:
    usage=shutil.disk_usage('/opt')
    print('RC69_DISK_FREE_MIB='+str(usage.free//1048576))
except OSError:
    print('RC69_DISK_FREE_MIB=UNKNOWN')
print('RC69_BACKUP_ROOT_PRESENT='+str(backups.is_dir() and not backups.is_symlink()))
snap_dirs=directories(backups)
print('RC69_UNCOMPRESSED_SNAPSHOT_CANDIDATES='+str(len(snap_dirs)))
archives=0
if backups.is_dir() and not backups.is_symlink():
    for parent, dirs, files in os.walk(backups,followlinks=False):
        dirs[:]=[d for d in dirs if not (Path(parent)/d).is_symlink()]
        if len(Path(parent).relative_to(backups).parts)>=3:
            dirs[:]=[]
        archives+=sum(name.endswith(('.tgz','.tar.gz','.tar.zst','.tar')) for name in files)
        if archives>500:
            archives=501
            break
print('RC69_ARCHIVE_CANDIDATES='+str(archives))
for portfolio in ('hawk','bull'):
    root=base/portfolio
    who=portfolio.upper()
    runtime=docker('superbot-desk-'+portfolio)
    print(who+'_CONTAINER_RUNNING='+str(runtime.get('running') if runtime else 'UNKNOWN'))
    print(who+'_RESTART_POLICY='+str(runtime.get('restart') if runtime else 'UNKNOWN'))
    print(who+'_CONFIGURED_MODE='+str(runtime.get('mode') if runtime else 'UNKNOWN'))
    print(who+'_OWNER_STOPPED_AND_DISABLED='+str(bool(runtime and runtime['running'] is False and runtime['restart'] in ('no',''))))
    print(who+'_PAUSE_PRESENT='+str((root/'pause.flag').is_file()))
    print(who+'_PENDING_REQUEST='+str(any((root/n).exists() for n in pending)))
    is_valid=all((root/n).is_file() and not (root/n).is_symlink() for n in required)
    print(who+'_REQUIRED_ALL_PRESENT='+str(is_valid))
    print(who+'_DATA_MOUNT_PRESENT='+str(bool(runtime and any(x==str(root) for x in runtime['mounts']))))
    try:
        state=json.loads((root/'state_v2.json').read_text())
        positions=(state.get('main') or {}).get('positions')
        print(who+'_OPEN_PAPER_POSITIONS='+str(len(positions) if isinstance(positions,dict) else 'INVALID'))
    except (OSError,ValueError,AttributeError):
        print(who+'_OPEN_PAPER_POSITIONS=INVALID')
    matches=0
    if is_valid:
        current={n:sha(root/n) for n in required}
        for cand in snap_dirs:
            if cand==root:
                continue
            try:
                if all(sha(cand/n)==current[n] for n in required):
                    matches+=1
            except OSError:
                pass
    print(who+'_EXACT_FOUR_FILE_SNAPSHOT_MATCHES='+str(matches))
    print(who+'_RESTORE_PROVED_BY_THIS_AUDIT=False')
print('RC69_APP_RUNNING='+str((docker('superbot') or {}).get('running','UNKNOWN')))
app=docker('superbot')
for f in ('configured_v3_journal','configured_v3_run','configured_v3_config','configured_v3_close'):
    print('RC69_APP_'+f.upper()+'='+str(app.get(f) if app else 'UNKNOWN'))
print('RC69_APP_HAWK_SOURCE_MOUNT='+str(bool(app and str(base/'hawk') in app['mounts'])))
print('RC69_APP_BULL_SOURCE_MOUNT='+str(bool(app and str(base/'bull') in app['mounts'])))
print('RC69_COMPLETED_READ_ONLY=True')
PY
