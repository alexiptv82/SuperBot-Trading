"""Pinned paired PAPER upgrade. No classic/legacy restart or financial restore."""
import argparse
import copy
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

ROOT=Path('/opt/superbot-brain-adaptive')
BACKUPS=Path('/opt/superbot-backups')
NAMES={p:'superbot-brain-'+p for p in ('hawk','bull')}
OLD='5024fbdfe3a9719098f905b28eac5d0feb9848e6'
TARGET='129547ed43a9aaec935df31102bb4e8016c38e7c'


def emit(phase,**values):print('BRAIN_UPDATE='+json.dumps(dict(phase=phase,**values),sort_keys=True),flush=True)

def run(args,input=None,timeout=60):
    p=subprocess.run(args,input=input,capture_output=True,text=True,timeout=timeout)
    if p.returncode:raise ValueError('CONTROL_COMMAND_FAILED')
    return p.stdout.strip()

def inspect(name):return json.loads(run(['docker','inspect',name]))[0]

def inventory(name,expected=None):
    d=inspect(name);env=dict(v.split('=',1) for v in d['Config'].get('Env',[]) if '=' in v)
    if env.get('DESK_MODE')!='paper' or not d['State']['Running']:raise ValueError('RUNNING_PAPER_REQUIRED')
    sha=d['Config'].get('Labels',{}).get('superbot.sha')
    if expected and sha!=expected:raise ValueError('RUNTIME_SHA_MISMATCH')
    return {'name':name,'sha':sha,'started_at':d['State']['StartedAt'],'restarts':d.get('RestartCount'),
            'health':d['State'].get('Health',{}).get('Status','unknown')}

def dbread(folder):
    with sqlite3.connect((folder/'brain.sqlite3').as_uri()+'?mode=ro',uri=True) as db:
        db.execute('BEGIN')
        state=json.loads(db.execute('SELECT body FROM state WHERE id=1').fetchone()[0])
        events=db.execute('SELECT seq,kind,body FROM events ORDER BY seq').fetchall()
    return state,events

def validate_state(s,profile):
    if (s.get('version'),s.get('profile'),s.get('desk',{}).get('main',{}).get('name'))!=('classical-adaptive-v1',profile,'brain-'+profile):
        raise ValueError('PROFILE_STATE_MISMATCH')
    if not re.fullmatch('[a-f0-9]{64}',str(s.get('method'))):raise ValueError('INVALID_OLD_METHOD')

def clone_db(source,dest):
    with sqlite3.connect(source.as_uri()+'?mode=ro',uri=True) as db:
        with sqlite3.connect(dest) as target:
            db.backup(target)
            if target.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('BACKUP_INTEGRITY_FAILED')
    os.chmod(dest,0o600)

def archive(source,dest):
    dest.mkdir(mode=0o700)
    for p in source.iterdir():
        if p.is_symlink() or not p.is_file():raise ValueError('UNEXPECTED_PROFILE_FILE')
        if p.name not in ('brain.sqlite3','brain.sqlite3-wal','brain.sqlite3-shm','writer.lock'):
            shutil.copy2(p,dest/p.name);os.chmod(dest/p.name,0o600)
    clone_db(source/'brain.sqlite3',dest/'brain.sqlite3')
    # Independently reopen a restored DB, compare every state/event row.
    restore=dest/'restore-check';restore.mkdir(mode=0o700)
    clone_db(dest/'brain.sqlite3',restore/'brain.sqlite3')
    if dbread(dest)!=dbread(restore):raise ValueError('BACKUP_RESTORE_COMPARISON_FAILED')

def create_flag(path,token):
    if path.exists():return False
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f:f.write(token);f.flush();os.fsync(f.fileno())
    return True

def wait_until(probe,seconds,code):
    end=time.monotonic()+seconds
    while True:
        if probe():return
        if time.monotonic()>=end:raise ValueError(code)
        time.sleep(5)

def paired_app():
    code="import sys,json;sys.path.insert(0,'/app/backend');from desk.brain_profiles_view import read_profiles;r=read_profiles();assert r['mode']=='paper' and r['read_only'];assert all(r['profiles'][p]['status']=='ok' for p in ('hawk','bull'));print(json.dumps({p:{'portfolio':r['profiles'][p]['portfolio'],'execution':r['profiles'][p]['execution']} for p in ('hawk','bull')}))"
    return json.loads(run(['docker','exec','-e','PYTHONDONTWRITEBYTECODE=1','superbot','python','-c',code]))

def migrated_state(before,after,method):
    expected=copy.deepcopy(before);expected['method']=method
    if expected!=after:raise ValueError('MIGRATION_CHANGED_NONMETHOD_STATE')

def history_preserved(before,events,s,after_events):
    if after_events[:len(events)]!=events:raise ValueError('HISTORY_REWRITTEN')
    old_positions=before['desk']['main']['positions'];current=s['desk']['main']['positions']
    closed={(json.loads(body).get('symbol'),json.loads(body).get('id')) for _,kind,body in after_events[len(events):] if kind=='trade' and not json.loads(body).get('partial',False)}
    for sym,p in old_positions.items():
        if not (sym in current and current[sym]['id']==p['id']) and (sym,p['id']) not in closed:
            raise ValueError('POSITION_DISAPPEARED_WITHOUT_TRADE')
    if any(sym not in old_positions or p['id']!=old_positions[sym]['id'] for sym,p in current.items()):
        raise ValueError('NEW_EXPOSURE_DURING_PAUSED_WARMUP')

def main(args):
    repo=Path(args.repo).resolve();oldrepo=Path(args.old_repo).resolve()
    if run(['git','-C',str(repo),'rev-parse','HEAD'])!=TARGET or run(['git','-C',str(oldrepo),'rev-parse','HEAD'])!=OLD:
        raise ValueError('PINNED_SOURCE_MISMATCH')
    if any(p.is_symlink() for p in (ROOT,*ROOT.parents)):raise ValueError('SYMLINK_ROOT')
    isolated=('superbot-desk-hawk','superbot-desk-bull','superbot-brain-pilot','superbot')
    unchanged=[inventory(n) for n in isolated]
    originals={p:inventory(n,OLD) for p,n in NAMES.items()}
    if any(x['health']!='healthy' for x in originals.values()):raise ValueError('OLD_WORKER_NOT_HEALTHY')
    for p,n in NAMES.items():
        d=inspect(n)
        if not any(m.get('Source')==str(ROOT) and m.get('Destination')=='/out' and m.get('RW') is True for m in d['Mounts']):
            raise ValueError('PROFILE_MOUNT_MISMATCH')
        env=dict(v.split('=',1) for v in d['Config'].get('Env',[]) if '=' in v)
        if any(k.startswith('DESK_') and k!='DESK_MODE' for k in env):raise ValueError('POLICY_ENVIRONMENT_REVIEW_REQUIRED')
        s,_=dbread(ROOT/('brain-'+p));validate_state(s,p)
    app=inspect('superbot')
    if not any(m.get('Source')==str(ROOT) and not m.get('RW') for m in app['Mounts']):raise ValueError('READONLY_APP_MOUNT_REQUIRED')
    paired_app()
    if not os.getenv('DEEPSEEK_API_KEY'):raise ValueError('MODEL_KEY_REQUIRED')
    mem={l.split(':')[0]:int(l.split()[1]) for l in Path('/proc/meminfo').read_text().splitlines()}
    if mem['MemAvailable']<750000:raise ValueError('INSUFFICIENT_MEMORY')
    stamp=time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())
    backup=BACKUPS/('brain-paired-update-'+stamp)
    backup.mkdir(mode=0o700)
    emit('preflight',target=TARGET,profiles=list(originals.values()),untouched=unchanged,backup=str(backup))
    for p in NAMES:archive(ROOT/('brain-'+p),backup/('live-'+p))
    clone_db(ROOT/'brain-api-budget.sqlite3',backup/'live-budget.sqlite3')
    emit('live_backups_restore_verified')
    image='superbot-brain-classical:'+TARGET
    run(['docker','build','-q','--label','superbot.sha='+TARGET,'-f',str(repo/'Dockerfile.brainclassical'),'-t',image,str(repo)],timeout=600)
    run(['docker','run','--rm','--read-only','--network','none',image,'--help'])
    emit('target_image_built',target=TARGET)
    if args.action=='preflight':return
    if os.getenv('BRAIN_UPDATE_APPROVED')!='paper:'+TARGET:raise ValueError('EXPLICIT_PAPER_APPROVAL_REQUIRED')
    token='paired-update:'+TARGET
    own_flags={};renamed={};new_containers=[];snapshots={};released=False;phase_start=int(time.time()*1000)
    old_label={p:NAMES[p]+'-previous-'+stamp for p in NAMES}
    def migration(profile,expected,dry=False,rollback=False):
        source=oldrepo if rollback else repo
        script="import importlib.util;from pathlib import Path;s=importlib.util.spec_from_file_location('m','/migration/migrate_method_digest.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m);m.REPO_ROOT=Path('/source');import json;print(json.dumps(m.migrate('"+profile+"','"+expected+"',dry_run="+str(dry)+",source_sha='"+(OLD if rollback else TARGET)+"')))"
        result=run(['docker','run','--rm','--read-only','--network','none','--cap-drop','ALL','--security-opt','no-new-privileges:true','--entrypoint','python',
                    '-e','PYTHONDONTWRITEBYTECODE=1','-e','DESK_MODE=paper','-v',str(ROOT)+':'+str(ROOT),'-v',str(repo)+':/migration:ro','-v',str(source)+':/source:ro',image,'-c',script],timeout=60)
        return json.loads(result)
    try:
        for p in NAMES:own_flags[p]=create_flag(ROOT/('brain-'+p)/'pause.flag',token)
        def quiescent():
            for p in NAMES:
                folder=ROOT/('brain-'+p);s,_=dbread(folder)
                beat=json.loads((folder/'status.json').read_text())
                if not s.get('operator_paused') or s.get('last_step_ms',0)<phase_start or beat.get('ts_ms',0)<phase_start:return False
            return True
        wait_until(quiescent,200,'OLD_PAUSE_CYCLE_TIMEOUT')
        emit('old_new_exposure_paused_protection_running')
        # Stop only the two adaptives; the next backup is now fully quiescent.
        for p,n in NAMES.items():run(['docker','stop','--time','30',n],timeout=45)
        emit('two_adaptive_workers_stopped')
        for p in NAMES:
            folder=ROOT/('brain-'+p);archive(folder,backup/('stopped-'+p));snapshots[p]=dbread(folder)
            if snapshots[p]!=dbread(backup/('stopped-'+p)):raise ValueError('FINAL_BACKUP_SOURCE_MISMATCH')
        clone_db(ROOT/'brain-api-budget.sqlite3',backup/'stopped-budget.sqlite3')
        budget_hash=hashlib.sha256((ROOT/'api_budget_baseline.json').read_bytes()).hexdigest()
        emit('final_backups_restore_verified')
        for p in NAMES:
            old=snapshots[p][0]['method'];preview=migration(p,old,True);actual=migration(p,old)
            if preview['to_method']!=actual['to_method']:raise ValueError('DRYRUN_ACTUAL_DIGEST_MISMATCH')
            s,ev=dbread(ROOT/('brain-'+p));migrated_state(snapshots[p][0],s,actual['to_method'])
            if ev[:len(snapshots[p][1])]!=snapshots[p][1]:raise ValueError('MIGRATION_HISTORY_REWRITTEN')
            emit('method_migrated',profile=p,old_method=old,new_method=actual['to_method'])
            source=repo/'brain'/'backtest_seed'/p/'backtest_seed.json';dest=ROOT/('brain-'+p)/'backtest_seed.json'
            body=source.read_bytes();seed=json.loads(body)
            if seed.get('profile')!=p or not str(seed.get('source','')).startswith('synthetic_backtest'):raise ValueError('SEED_PROVENANCE_MISMATCH')
            tmp=dest.with_name('.backtest_seed.update');fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'wb') as f:f.write(body);f.flush();os.fsync(f.fileno())
            os.replace(tmp,dest)
            if dest.read_bytes()!=body:raise ValueError('SEED_COPY_MISMATCH')
        for p,n in NAMES.items():
            run(['docker','rename',n,old_label[p]]);renamed[p]=True
            run(['docker','run','-d','--name',n,'--restart','unless-stopped','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true',
                 '--memory','384m','--cpus','0.5','--pids-limit','128','--tmpfs','/tmp:rw,noexec,nosuid,size=64m','--label','superbot.sha='+TARGET,
                 '-e','DESK_MODE=paper','-e','BRAIN_PROFILE='+p,'-e','DEEPSEEK_API_KEY','-v',str(ROOT)+':/out',image,'--out','/out','--profile',p])
            new_containers.append(p)
        emit('new_workers_started_paused')
        start_ms=int(time.time()*1000)
        def warmed():
            for p,n in NAMES.items():
                d=inventory(n,TARGET);s,events=dbread(ROOT/('brain-'+p));status=json.loads((ROOT/('brain-'+p)/'status.json').read_text())
                if d['health']!='healthy' or status.get('ts_ms',0)<start_ms or not status.get('fresh_fast_data') or not s.get('operator_paused'):return False
                if s.get('coverage_unresolved'):raise ValueError('FAST_COVERAGE_REVIEW_REQUIRED')
                if any(kind=='journal' and json.loads(body).get('kind')=='entry_cycle_failed' and json.loads(body).get('ts_ms',0)>=start_ms for _,kind,body in events):raise ValueError('NEW_ENTRY_CYCLE_FAILED')
            return True
        wait_until(warmed,360,'NEW_WARMUP_TIMEOUT')
        for p in NAMES:
            s,events=dbread(ROOT/('brain-'+p));history_preserved(*snapshots[p],s,events)
        view=paired_app()
        if any(not view[p]['execution']['fresh_fast_data'] or not view[p]['execution']['operator_paused'] for p in NAMES):raise ValueError('APP_WARMUP_VIEW_FAILED')
        if [inventory(n) for n in isolated]!=unchanged:raise ValueError('UNRELATED_RUNTIME_CHANGED')
        if hashlib.sha256((ROOT/'api_budget_baseline.json').read_bytes()).hexdigest()!=budget_hash:raise ValueError('BUDGET_BASELINE_CHANGED')
        with sqlite3.connect((ROOT/'brain-api-budget.sqlite3').as_uri()+'?mode=ro',uri=True) as a,sqlite3.connect(backup/'stopped-budget.sqlite3') as b:
            if a.execute('SELECT * FROM reservations ORDER BY id').fetchall()!=b.execute('SELECT * FROM reservations ORDER BY id').fetchall():raise ValueError('API_SPENDING_DURING_PAUSED_WARMUP')
        release_ms=int(time.time()*1000)
        for p in NAMES:
            flag=ROOT/('brain-'+p)/'pause.flag'
            if own_flags[p]:
                if flag.read_text()!=token:raise ValueError('OPERATOR_FLAG_CHANGED')
                flag.unlink()
        released=True
        def resumed():
            for p in NAMES:
                s,_=dbread(ROOT/('brain-'+p))
                if s.get('last_step_ms',0)<release_ms or s.get('operator_paused') is not (not own_flags[p]):return False
            return True
        wait_until(resumed,200,'POSTRELEASE_CYCLE_TIMEOUT')
        view=paired_app()
        if [inventory(n) for n in isolated]!=unchanged:raise ValueError('UNRELATED_RUNTIME_CHANGED')
        emit('update_complete',target=TARGET,backup=str(backup),profiles=[inventory(n,TARGET) for n in NAMES.values()],
             seed_paths=[str(ROOT/('brain-'+p)/'backtest_seed.json') for p in NAMES],old_containers_retained=list(old_label.values()),app=view,unrelated_unchanged=True)
    except Exception:
        emit('update_failed_preserving_all_financial_data',released=released)
        for p in NAMES:create_flag(ROOT/('brain-'+p)/'pause.flag','update-failure-protection')
        if released:
            # Never undo financial outcomes after release; leave protection active.
            raise
        # Revert code identity only; preserve every protective close and budget row.
        for p in new_containers:
            run(['docker','stop','--time','30',NAMES[p]],timeout=45)
            run(['docker','rename',NAMES[p],NAMES[p]+'-failed-'+stamp])
        for p in NAMES:
            s,_=dbread(ROOT/('brain-'+p))
            if p in snapshots and s['method']!=snapshots[p][0]['method']:
                result=migration(p,s['method'],rollback=True)
                if result['to_method']!=snapshots[p][0]['method']:raise ValueError('ROLLBACK_DIGEST_MISMATCH')
            if renamed.get(p):run(['docker','rename',old_label[p],NAMES[p]])
            run(['docker','start',NAMES[p]])
        emit('previous_workers_restarted_paused_no_financial_restore')
        raise

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--repo',required=True);parser.add_argument('--old-repo',required=True);parser.add_argument('--action',choices=['preflight','apply'],required=True)
    try:main(parser.parse_args())
    except Exception as exc:
        code=str(exc) if isinstance(exc,ValueError) and re.fullmatch('[A-Z_]+',str(exc)) else type(exc).__name__
        emit('failed',code=code);raise SystemExit(1)
