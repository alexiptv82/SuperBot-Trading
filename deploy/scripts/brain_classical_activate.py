"""Explicitly approved first PAPER rollout; never replaces classic containers.

Build immutable source, retain old-position protection, carry API spending,
start new accounts paused, validate warm state/app view, then allow exposure.
No account reset, source DB restore, live connector or credential output.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import time

ROOT=Path('/opt/superbot-brain-adaptive')
OLD=Path('/opt/superbot-desk-data/brain')
NAMES={'hawk':'superbot-brain-hawk','bull':'superbot-brain-bull'}


def run(args,timeout=60):
    p=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
    if p.returncode:raise ValueError('CONTROL_COMMAND_FAILED')
    return p.stdout.strip()


def load_preflight():
    path=Path(__file__).with_name('brain_classical_preflight.py')
    spec=importlib.util.spec_from_file_location('brain_readonly_control',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def quiescent(status,flag_ms,now_ms):
    stamp=status.get('ts_ms',0)
    return (status.get('mode')=='paper' and status.get('applied') is False and
            isinstance(stamp,(int,float)) and not isinstance(stamp,bool) and flag_ms<=stamp<=now_ms+5000 and
            now_ms-stamp<=1800000 and status.get('last_cycle',{}).get('called') is False)


def initial_account(root,profile,now_ms):
    with sqlite3.connect((root/('brain-'+profile)/'brain.sqlite3').as_uri()+'?mode=ro',uri=True) as db:
        row=db.execute('SELECT body FROM state WHERE id=1').fetchone()
        if row is None:return False
        state=json.loads(row[0])
    a=state['desk']['main']
    if state.get('version')!='classical-adaptive-v1' or state.get('profile')!=profile or a.get('name')!='brain-'+profile:
        raise ValueError('NEW_ACCOUNT_IDENTITY_MISMATCH')
    if a['positions'] or a['cash']!=a['limits']['start_equity'] or a['closed']:
        raise ValueError('PAUSED_INITIAL_ACCOUNT_CHANGED')
    status=json.loads((root/('brain-'+profile)/'status.json').read_text())
    if (status.get('mode'),status.get('profile'),status.get('version'),status.get('method_version'))!=('paper',profile,state['version'],state.get('method')):
        return False
    if state.get('operator_paused') is not True or state.get('coverage_unresolved'):
        raise ValueError('INITIAL_PROFILE_NOT_PROTECTED')
    if not 0<=now_ms-status.get('ts_ms',0)<=180000 or not status.get('fresh_fast_data'):
        return False
    return True


def create_private(path,body):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f:f.write(body);f.flush();os.fsync(f.fileno())


def main():
    p=argparse.ArgumentParser()
    for name in ('sha','legacy-sha','classic-sha','app-sha','repo'):p.add_argument('--'+name,required=True)
    args=p.parse_args()
    for sha in (args.sha,args.legacy_sha,args.classic_sha,args.app_sha):
        if not re.fullmatch('[a-f0-9]{40}',sha):raise ValueError('FULL_SHA_REQUIRED')
    if os.getenv('BRAIN_CLASSICAL_ACTIVATE_APPROVED')!='paper:'+args.sha:raise ValueError('EXPLICIT_PAPER_APPROVAL_REQUIRED')
    if not os.getenv('DEEPSEEK_API_KEY'):raise ValueError('MODEL_KEY_REQUIRED')
    repo=Path(args.repo).resolve()
    if run(['git','-C',str(repo),'rev-parse','HEAD'])!=args.sha:raise ValueError('SOURCE_SHA_MISMATCH')
    run(['git','-C',str(repo),'diff','--exit-code',args.classic_sha,args.sha,'--','backend/desk'])
    h=load_preflight()
    names=('superbot-brain-pilot','superbot-desk-hawk','superbot-desk-bull')
    before=[h.inventory(n) for n in names]
    if before[0]['sha']!=args.legacy_sha or any(x['sha']!=args.classic_sha for x in before[1:]) or any(x['health']!='healthy' for x in before):
        raise ValueError('RUNTIME_BASELINE_MISMATCH')
    for x in before[1:]:
        if x['policy_environment'].get('DESK_CAPITAL_V1','off') not in ('off','','0'):
            raise ValueError('CAPITAL_POLICY_REVIEW_REQUIRED')
        for key,value in x['policy_environment'].items():
            if key!='DESK_CAPITAL_V1':raise ValueError('EXPLICIT_CLASSICAL_ENVIRONMENT_REVIEW_REQUIRED')
    app=json.loads(run(['docker','inspect','superbot']))[0]
    if app['Config'].get('Labels',{}).get('superbot.sha')!=args.app_sha:
        raise ValueError('PAIRED_APP_VERSION_REQUIRED')
    if not any(m.get('Source')==str(ROOT) and m.get('Destination')==str(ROOT) and m.get('RW') is False for m in app.get('Mounts',[])):
        raise ValueError('APP_READONLY_PROFILE_MOUNT_REQUIRED')
    for name in NAMES.values():
        check=subprocess.run(['docker','inspect',name],capture_output=True,text=True)
        if check.returncode==0:raise ValueError('EXISTING_TARGET_CONTAINER_REQUIRES_REVIEW')
    if ROOT.is_symlink() or ROOT.exists() and any(ROOT.iterdir()):raise ValueError('NONEMPTY_TARGET_REQUIRES_REVIEW')
    mem={l.split(':')[0]:int(l.split()[1]) for l in Path('/proc/meminfo').read_text().splitlines()}
    if mem['MemAvailable']<1000000:raise ValueError('INSUFFICIENT_AVAILABLE_MEMORY')
    stamp=time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())
    backup=Path('/opt/superbot-backups')/('brain-before-adaptive-'+stamp)
    h.backup(OLD,backup)
    image='superbot-brain-classical:'+args.sha
    run(['docker','build','-q','--label','superbot.sha='+args.sha,'-f',str(repo/'Dockerfile.brainclassical'),'-t',image,str(repo)],timeout=600)
    run(['docker','run','--rm','--read-only','--network','none',image,'--help'])
    flag=OLD/'pause.flag';token='adaptive-rollout:'+args.sha
    created_old_pause=False;created=[];activated=False
    ROOT.mkdir(mode=0o700,parents=True,exist_ok=True);os.chmod(ROOT,0o700)
    try:
        if not flag.exists():create_private(flag,token);created_old_pause=True
        flag_ms=int(flag.stat().st_mtime*1000)
        deadline=time.monotonic()+1200
        while True:
            status=json.loads((OLD/'status.json').read_text())
            if quiescent(status,flag_ms,int(time.time()*1000)):break
            if time.monotonic()>deadline:raise ValueError('LEGACY_API_QUIESCENCE_TIMEOUT')
            time.sleep(10)
        sys.path.insert(0,str(repo/'backend'))
        from director.classical_adaptive.budget import baseline_from_spend
        ledger=OLD/'spend.jsonl';baseline=baseline_from_spend(ledger)
        if hashlib.sha256(ledger.read_bytes()).hexdigest()!=baseline['source_sha256']:
            raise ValueError('LEGACY_SPEND_CHANGED')
        create_private(ROOT/'api_budget_baseline.json',json.dumps(baseline,sort_keys=True,allow_nan=False))
        for profile,name in NAMES.items():
            folder=ROOT/('brain-'+profile);folder.mkdir(mode=0o700)
            create_private(folder/'pause.flag',token)
            run(['docker','run','-d','--name',name,'--restart','unless-stopped','--read-only','--cap-drop','ALL',
                 '--security-opt','no-new-privileges:true','--memory','384m','--cpus','0.5','--pids-limit','128',
                 '--tmpfs','/tmp:rw,noexec,nosuid,size=64m','--label','superbot.sha='+args.sha,
                 '-e','DESK_MODE=paper','-e','BRAIN_PROFILE='+profile,'-e','DEEPSEEK_API_KEY',
                 '-v',str(ROOT)+':/out',image,'--out','/out','--profile',profile,'--initialize-paper'])
            created.append(name)
        deadline=time.monotonic()+600
        while True:
            ready=True
            for profile,name in NAMES.items():
                try:
                    item=h.inventory(name)
                    ready=ready and item['running'] and item['sha']==args.sha and item['health']=='healthy' and initial_account(ROOT,profile,int(time.time()*1000))
                except (ValueError,KeyError,TypeError,OSError,sqlite3.DatabaseError):ready=False
            if ready:break
            if time.monotonic()>deadline:raise ValueError('NEW_PROFILE_WARMUP_TIMEOUT')
            time.sleep(10)
        # Check the actual app reader against its readonly mount before entries.
        code="import sys; sys.path.insert(0,'/app/backend'); from desk.brain_profiles_view import read_profiles; r=read_profiles(); assert r['mode']=='paper' and r['read_only']; assert all(r['profiles'][p]['status']=='ok' for p in ('hawk','bull')); print('PAIRED_APP_READER=PASS')"
        run(['docker','exec','-e','PYTHONDONTWRITEBYTECODE=1','superbot','python','-c',code])
        with sqlite3.connect((ROOT/'brain-api-budget.sqlite3').as_uri()+'?mode=ro',uri=True) as db:
            if db.execute("SELECT COUNT(*) FROM reservations WHERE profile!='legacy'").fetchone()[0]:
                raise ValueError('PAUSED_PROFILES_CONSUMED_API_BUDGET')
        if [h.inventory(n) for n in names]!=before:raise ValueError('BASE_RUNTIME_CHANGED')
        if hashlib.sha256(ledger.read_bytes()).hexdigest()!=baseline['source_sha256']:raise ValueError('OLD_API_SPENDING_RESUMED')
        activated=True
        for profile in NAMES:
            new_flag=ROOT/('brain-'+profile)/'pause.flag'
            if new_flag.read_text()!=token:raise ValueError('OPERATOR_PAUSE_CHANGED')
            new_flag.unlink()
        print(json.dumps({'ok':True,'phase':'paper_profiles_activated','sha':args.sha,'app_sha':args.app_sha,
                          'backup':str(backup),'old_positions_preserved':True,'old_new_exposure_paused':True,
                          'old_spend_sha256':baseline['source_sha256'],'classic_runtimes_unchanged':True,
                          'profiles':[h.inventory(n) for n in NAMES.values()]},sort_keys=True))
    except Exception:
        # Before release: no new exposure/API calls occurred; stop only workers
        # created by this control, retain their data, and restore our old pause.
        # After release: leave protection running, pause new exposure, never
        # restore old financial snapshots or hide budget changes.
        uncertain=False
        for profile,name in NAMES.items():
            if name not in created:continue
            try:
                with sqlite3.connect((ROOT/('brain-'+profile)/'brain.sqlite3').as_uri()+'?mode=ro',uri=True) as db:
                    a=json.loads(db.execute('SELECT body FROM state WHERE id=1').fetchone()[0])['desk']['main']
                uncertain=uncertain or bool(a['positions'] or a['closed'] or a['cash']!=a['limits']['start_equity'])
            except Exception:uncertain=True
        if created:
            try:
                with sqlite3.connect((ROOT/'brain-api-budget.sqlite3').as_uri()+'?mode=ro',uri=True) as db:
                    uncertain=uncertain or db.execute("SELECT COUNT(*) FROM reservations WHERE profile!='legacy'").fetchone()[0]>0
            except Exception:uncertain=True
        if activated or uncertain:
            for profile in NAMES:
                target=ROOT/('brain-'+profile)/'pause.flag'
                if not target.exists():create_private(target,'rollout-protection')
        else:
            for name in created:
                try:
                    if h.inventory(name)['sha']==args.sha:run(['docker','stop','--time','20',name])
                except Exception:pass
            if created_old_pause and flag.exists() and flag.read_text()==token:flag.unlink()
        raise


if __name__=='__main__':
    try:main()
    except Exception as exc:
        code=str(exc) if isinstance(exc,ValueError) and re.fullmatch('[A-Z_]+',str(exc)) else type(exc).__name__
        print('BRAIN_PAPER_ACTIVATION_FAILED='+code);raise SystemExit(1)
