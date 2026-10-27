#!/usr/bin/env python3
"""Future approved cutover only. Defaults to an offline plan; never resets data.

Run from a pinned checkout on Singapore, via the dedicated GitHub workflow.
The UI must already have the RO mount. No classic services are stopped/recreated.
"""
import argparse,hashlib,json,os,re,shutil,sqlite3,subprocess,tempfile,time,urllib.request
from pathlib import Path

OLD={'superbot-brain-hawk':'129547ed43a9aaec935df31102bb4e8016c38e7c',
     'superbot-brain-bull':'129547ed43a9aaec935df31102bb4e8016c38e7c',
     'superbot-brain-pilot':'1f2edeb6182029adc96ba7218ad145a7503472a3'}
CLASSICS={'superbot-desk-hawk':'3abf1f808b09bf9066d96a1d16f945d65601ba02',
          'superbot-desk-bull':'3abf1f808b09bf9066d96a1d16f945d65601ba02'}
ROOT=Path('/opt/superbot-brain-free')
SOURCES=(Path('/opt/superbot-brain-adaptive'),Path('/opt/superbot-desk-data/brain'))

def run(args,timeout=300):
    p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=timeout)
    if p.returncode:raise ValueError('command_failed:'+args[0])
    return p.stdout

def inspect(name):return json.loads(run(['docker','inspect',name]))[0]
def environment(item):return dict(x.split('=',1) for x in item['Config'].get('Env',[]) if '=' in x)

def check_inputs(approved,sha,app_sha):
    if approved!='yes':raise ValueError('separate_explicit_deploy_approval_required')
    if not re.fullmatch('[0-9a-f]{40}',sha or '') or not re.fullmatch('[0-9a-f]{40}',app_sha or ''):raise ValueError('immutable_sha_required')
    if os.getenv('DESK_MODE','paper')!='paper':raise ValueError('paper_required')
    if not os.getenv('DEEPSEEK_API_KEY'):raise ValueError('missing_deepseek_secret')

def snapshot_tree(source,dest):
    """Quiescent trees after stop; online SQLite backup + independent restore proof."""
    if not source.is_dir() or source.is_symlink():raise ValueError('backup_source_missing_or_symlink')
    dest.mkdir(mode=0o700)
    for p in source.rglob('*'):
        if p.is_symlink():raise ValueError('backup_symlink')
        rel=p.relative_to(source);target=dest/rel
        if p.is_dir():target.mkdir(exist_ok=True,mode=0o700);continue
        if p.name.endswith(('-wal','-shm')):continue
        target.parent.mkdir(parents=True,exist_ok=True)
        if p.suffix in ('.sqlite3','.sqlite','.db'):
            with sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True) as src,sqlite3.connect(target) as backup:
                src.backup(backup)
                if backup.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('backup_integrity')
                # Independent restored file; compare all tables with the copied DB.
                with tempfile.TemporaryDirectory(dir=dest) as tmp:
                    restored=Path(tmp)/'restore.sqlite3';shutil.copy2(target,restored)
                    with sqlite3.connect(restored) as test:
                        if test.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('restore_integrity')
                        tables=[x[0] for x in backup.execute("SELECT name FROM sqlite_master WHERE type='table'")]
                        for table in tables:
                            quoted='"'+table.replace('"','""')+'"'
                            if backup.execute('SELECT * FROM '+quoted).fetchall()!=test.execute('SELECT * FROM '+quoted).fetchall():raise ValueError('restore_table_mismatch')
        else:
            shutil.copy2(p,target)
            if hashlib.sha256(p.read_bytes()).digest()!=hashlib.sha256(target.read_bytes()).digest():raise ValueError('backup_hash')
    manifest={str(p.relative_to(dest)):hashlib.sha256(p.read_bytes()).hexdigest() for p in dest.rglob('*') if p.is_file()}
    (dest/'BACKUP_MANIFEST.json').write_text(json.dumps(manifest,sort_keys=True))

def preflight(sha,app_sha):
    if run(['git','rev-parse','HEAD']).strip()!=sha:raise ValueError('checkout_not_approved_sha')
    if ROOT.is_symlink() or any(p.is_symlink() for p in ROOT.parents):raise ValueError('symlink_new_root')
    for required in (SOURCES[0]/'brain-hawk/brain.sqlite3',SOURCES[0]/'brain-bull/brain.sqlite3',SOURCES[0]/'brain-api-budget.sqlite3',SOURCES[1]/'brain.sqlite3',SOURCES[1]/'spend.jsonl'):
        if not required.is_file() or required.is_symlink():raise ValueError('required_old_data_missing')
    if ROOT.exists() and any(ROOT.iterdir()):raise ValueError('new_account_directory_not_empty_no_reset')
    inventory={n:inspect(n) for n in run(['docker','ps','--format','{{.Names}}']).splitlines()}
    for n,expected in {**OLD,**CLASSICS,'superbot':app_sha}.items():
        item=inventory[n]
        if environment(item).get('DESK_MODE')!='paper' or not item['State']['Running']:raise ValueError('runtime_not_paper')
        if item['Config'].get('Labels',{}).get('superbot.sha')!=expected:raise ValueError('runtime_source_changed')
    app=inventory['superbot']
    if not any(m['Source']==str(ROOT) and not m['RW'] for m in app['Mounts']):raise ValueError('app_readonly_mount_missing')
    if 'superbot-brain-free' in inventory:raise ValueError('new_brain_already_running')
    for name in OLD:
        mounts=inventory[name].get('Mounts',[])
        sources={m['Source'] for m in mounts}
        for other,item in inventory.items():
            if other in OLD or other=='superbot':continue
            if any(m['Source'] in sources for m in item.get('Mounts',[])):raise ValueError('unexpected_old_brain_writer')
    # Read provider availability; never print or persist account balances.
    req=urllib.request.Request('https://api.deepseek.com/user/balance',headers={'Authorization':'Bearer '+os.environ['DEEPSEEK_API_KEY']})
    with urllib.request.urlopen(req,timeout=15) as r:
        if not json.loads(r.read(100000)).get('is_available'):raise ValueError('provider_credit_unavailable')
    return inventory

def apply(sha,app_sha):
    inventory=preflight(sha,app_sha)
    tag='superbot-brain-free:sha-'+sha[:12]
    run(['docker','build','--label','superbot.sha='+sha,'-t',tag,'-f','Dockerfile.brainfree','.'],timeout=900)
    backup=Path('/opt/superbot-backups')/('brain-free-cutover-'+time.strftime('%Y%m%dT%H%M%SZ',time.gmtime()))
    backup.mkdir(mode=0o700)
    # Verified online snapshots precede any stop. Final snapshots follow quiescence.
    for i,source in enumerate(SOURCES):snapshot_tree(source,backup/('online-'+str(i)))
    old_stopped=[];new_started=False
    try:
        for name in OLD:run(['docker','stop','-t','150',name],timeout=180);old_stopped.append(name)
        for name in OLD:
            if inspect(name)['State']['Running']:raise ValueError('old_writer_not_stopped')
        for i,source in enumerate(SOURCES):snapshot_tree(source,backup/('final-'+str(i)))
        ROOT.mkdir(mode=0o700,exist_ok=True)
        run(['docker','run','--rm','--network','none','-e','DESK_MODE=paper','-e','BRAIN_FREE_CODE_SHA='+sha,
             '-v',str(ROOT)+':/out',tag,'--root','/out','--initialize'])
        run(['docker','run','-d','--name','superbot-brain-free','--restart','unless-stopped',
             '--memory','512m','--cpus','0.5','--stop-timeout','150','-e','DESK_MODE=paper',
             '-e','BRAIN_FREE_CODE_SHA='+sha,'-e','DEEPSEEK_API_KEY','-e','TELEGRAM_BOT_TOKEN','-e','TELEGRAM_CHAT_ID',
             '-v',str(ROOT)+':/out','-v','/opt/superbot-desk-data/hawk:/classics/hawk:ro',
             '-v','/opt/superbot-desk-data/bull:/classics/bull:ro',tag,'--root','/out'])
        new_started=True
        ready=None
        for _ in range(36):
            try:
                with sqlite3.connect((ROOT/'brain.sqlite3').resolve().as_uri()+'?mode=ro',uri=True) as db:
                    ready=json.loads(db.execute('SELECT body FROM state WHERE id=1').fetchone()[0])
                if ready.get('instrument_count',0)>0 and ready.get('fresh_quote_count',0)>0 and time.time()*1000-ready.get('heartbeat_ms',0)<30000:break
            except (OSError,sqlite3.Error,ValueError,TypeError):pass
            time.sleep(5)
        else:raise ValueError('feed_warmup_failed')
        (ROOT/'activate.flag').write_text(ready['config_hash'])
        for _ in range(48):
            with sqlite3.connect((ROOT/'brain.sqlite3').resolve().as_uri()+'?mode=ro',uri=True) as db:
                state=json.loads(db.execute('SELECT body FROM state WHERE id=1').fetchone()[0])
                decision=db.execute("SELECT COUNT(*) FROM events WHERE kind='ai_decision'").fetchone()[0]
            if state['verified_start_ms'] is not None and decision:break
            time.sleep(5)
        else:raise ValueError('ai_response_not_verified')
        for name,old in inventory.items():
            if name in OLD:continue
            current=inspect(name)
            if current['Id']!=old['Id'] or current['State']['StartedAt']!=old['State']['StartedAt']:raise ValueError('unrelated_container_changed')
        if any(inspect(n)['State']['Running'] for n in OLD):raise ValueError('old_brain_running')
        if inspect('superbot-brain-free')['Config']['Labels']['superbot.sha']!=sha:raise ValueError('new_source_mismatch')
        report={'sha':sha,'app_sha':app_sha,'backup':str(backup),'verified_start_ms':state['verified_start_ms'],
                'mode':'paper','old_brains_retained_stopped':list(OLD),'config_hash':state['config_hash']}
        (backup/'ROLLOUT.json').write_text(json.dumps(report,sort_keys=True))
        print('BRAIN_FREE_ROLLOUT=PASS')
    except BaseException:
        if new_started:run(['docker','stop','-t','150','superbot-brain-free'],timeout=180)
        if ROOT.is_dir():(ROOT/'retired.flag').write_text('rollout_failed_data_preserved')
        for name in old_stopped:run(['docker','start',name])
        # No deletion or database restoration. Failed new data remain for review.
        raise

def main():
    p=argparse.ArgumentParser();p.add_argument('--action',choices=['plan','apply'],default='plan')
    p.add_argument('--approved',default='no');p.add_argument('--sha');p.add_argument('--app-sha');a=p.parse_args()
    if a.action=='plan':
        print('PLAN_ONLY: app RO mount; verified backups; build; stop/archive three old Brains; initialize NEW PAPER2000; warm feeds; activate; verify AI; preserve classic containers. NO ACTIONS.');return
    check_inputs(a.approved,a.sha,a.app_sha);os.umask(0o077);apply(a.sha,a.app_sha)

if __name__=='__main__':
    try:main()
    except Exception as e:print('BRAIN_FREE_ROLLOUT=BLOCKED',type(e).__name__);raise SystemExit(1)
