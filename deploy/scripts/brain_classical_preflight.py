"""Read-only runtime inventory and verified old-Brain backup, no activation.

Only writes a new private backup directory. Never sets flags, starts/stops
containers, changes budgets, modifies a source DB or initializes new accounts.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import time

LEGACY='superbot-brain-pilot'
SOURCE=Path('/opt/superbot-desk-data/brain')


def archive_helper():
    path=Path(__file__).with_name('brain_pilot_upgrade.py')
    spec=importlib.util.spec_from_file_location('brain_archive_helper',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def inventory(name):
    proc=subprocess.run(['docker','inspect',name],capture_output=True,text=True,timeout=20)
    if proc.returncode:raise ValueError('CONTAINER_INSPECTION_FAILED')
    items=json.loads(proc.stdout)
    if len(items)!=1:raise ValueError('UNEXPECTED_CONTAINER_COUNT')
    item=items[0]
    env=dict(v.split('=',1) for v in item['Config'].get('Env',[]) if '=' in v)
    if env.get('DESK_MODE')!='paper':raise ValueError('PAPER_REQUIRED')
    sha=item['Config'].get('Labels',{}).get('superbot.sha')
    if not isinstance(sha,str) or not re.fullmatch('[a-f0-9]{40}',sha):raise ValueError('VERSION_LABEL_MISSING')
    result={'name':name,'mode':'paper','sha':sha,'running':item['State'].get('Running') is True,
            'health':item['State'].get('Health',{}).get('Status','unknown'),
            'restarts':item.get('RestartCount'),'started_at':item['State'].get('StartedAt')}
    controls=('DESK_CAPITAL_V1','DESK_SCORE_PROFILE','DESK_REGIME_V1','DESK_REGIME_RATCHET','DESK_REGIME_FLIP',
              'DESK_REGIME_RANGE_EXTRA','DESK_BULL_MAX_OPEN_RISK','DESK_BULL_SHORT_VETO_BTC_24H','DESK_ENTRY_SCORE')
    result['policy_environment']={k:env[k] for k in controls if k in env}
    if name==LEGACY:
        if not any(m.get('Source')==str(SOURCE) and m.get('Destination')=='/out' for m in item.get('Mounts',[])):
            raise ValueError('LEGACY_SOURCE_MOUNT_MISMATCH')
    return result


def backup(root,destination):
    helper=archive_helper();root=Path(root).resolve();destination=Path(destination)
    if destination.exists():raise ValueError('BACKUP_DESTINATION_EXISTS')
    # The existing upgrader's clone uses SQLite's online backup API for the
    # authoritative DB/WAL and copies append-only exports without rewriting them.
    destination.mkdir(parents=True,mode=0o700)
    os.chmod(destination,0o700)
    helper.clone_data(root,destination)
    helper.validate_jsonl(destination)
    state,events=helper.read_database(destination)
    if state.get('version')!='brain-pilot-v1' or state.get('account',{}).get('name')!='brain-paper':
        raise ValueError('LEGACY_STATE_IDENTITY_MISMATCH')
    # Actually restore/reopen the static snapshot into an independent DB and
    # compare state/events exactly. Never restore over live financial data.
    restore=destination/'restore-check';restore.mkdir(mode=0o700)
    with sqlite3.connect((destination/'brain.sqlite3').as_uri()+'?mode=ro',uri=True) as source:
        with sqlite3.connect(restore/'brain.sqlite3') as target:source.backup(target)
    restored,restored_events=helper.read_database(restore)
    if restored!=state or restored_events!=events:raise ValueError('RESTORE_COMPARISON_FAILED')
    manifest=helper.file_manifest(destination)
    # status/logs may be newer/older than the atomic DB snapshot while the old
    # runtime is running. This archive is not a frozen activation-spend baseline.
    report={'backup_integrity':'pass','restore_comparison':'pass','state_version':state['version'],
            'events':len(events),'open_positions':len(state['account']['positions']),
            'manifest':manifest,'activation_spend_baseline_frozen':False}
    fd=os.open(destination/'verification.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f:
        json.dump(report,f,sort_keys=True,allow_nan=False);f.flush();os.fsync(f.fileno())
    return report


def main():
    p=argparse.ArgumentParser();p.add_argument('--expected-legacy-sha',required=True)
    p.add_argument('--backup-parent',default='/opt/superbot-backups');args=p.parse_args()
    if not re.fullmatch('[a-f0-9]{40}',args.expected_legacy_sha):raise ValueError('FULL_EXPECTED_SHA_REQUIRED')
    before=[inventory(n) for n in (LEGACY,'superbot-desk-hawk','superbot-desk-bull')]
    if before[0]['sha']!=args.expected_legacy_sha or not all(x['running'] for x in before):
        raise ValueError('RUNTIME_BASELINE_MISMATCH')
    directory=Path(args.backup_parent)/('brain-adaptive-preflight-'+time.strftime('%Y%m%dT%H%M%SZ',time.gmtime()))
    report=backup(SOURCE,directory)
    after=[inventory(n) for n in (LEGACY,'superbot-desk-hawk','superbot-desk-bull')]
    if before!=after:raise ValueError('RUNTIME_CHANGED_DURING_READONLY_BACKUP')
    free=shutil.disk_usage('/opt').free//(1024*1024)
    memory={line.split(':')[0]:int(line.split()[1]) for line in Path('/proc/meminfo').read_text().splitlines()}
    print(json.dumps({'ok':True,'action':'readonly_inventory_and_backup','runtimes':after,
                      'backup_directory':str(directory),'backup_integrity':report['backup_integrity'],
                      'restore_comparison':report['restore_comparison'],'open_paper_positions':report['open_positions'],
                      'available_memory_kib':memory['MemAvailable'],'free_disk_mib':free,
                      'previous_brain_paused':(SOURCE/'pause.flag').exists(),
                      'activation_spend_baseline_frozen':False},sort_keys=True))


if __name__=='__main__':
    try:main()
    except Exception as exc:
        # Never print raw inspect/environment/provider data or arbitrary errors.
        code=str(exc) if isinstance(exc,ValueError) and re.fullmatch('[A-Z_]+',str(exc)) else type(exc).__name__
        print('BRAIN_READONLY_PREFLIGHT_FAILED='+code);raise SystemExit(1)
