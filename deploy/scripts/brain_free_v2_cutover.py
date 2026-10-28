"""Explicitly approved, same-account PAPER replacement; no reset or history deletion."""
import argparse,hashlib,json,os,pathlib,shutil,sqlite3,subprocess,tempfile,time,uuid
ROOT=pathlib.Path('/opt/superbot-brain-free')
NAME='superbot-brain-free'
OLD='a914803a15c2d8a5fa01021f11c4def4caf82a76'
NEW='e0021488b47e8b245954a708b139bc4785a4b644'
TABLES=('state','events','requests','outbox')
def command(args,timeout=120):
    p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=timeout)
    if p.returncode:raise RuntimeError('command_failed:'+args[0])
    return p.stdout

def inspect(name):return json.loads(command(['docker','inspect',name]))[0]
def read_state(path=ROOT/'brain.sqlite3'):
    with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as db:
        return json.loads(db.execute('SELECT body FROM state WHERE id=1').fetchone()[0])
def backup(root,destination):
    assert root.is_dir() and not root.is_symlink() and not destination.exists()
    assert not any(p.is_symlink() for p in root.rglob('*'))
    destination.mkdir(mode=0o700,parents=True)
    with sqlite3.connect((root/'brain.sqlite3').resolve().as_uri()+'?mode=ro',uri=True) as src,sqlite3.connect(destination/'brain.sqlite3') as dst:
        src.backup(dst)
        assert dst.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    for p in root.rglob('*'):
        if p.is_file() and p.name not in ('brain.sqlite3','brain.sqlite3-wal','brain.sqlite3-shm','writer.lock'):
            target=destination/p.relative_to(root);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
    with tempfile.TemporaryDirectory(dir=destination) as temporary:
        restored=pathlib.Path(temporary)/'restored.sqlite3';shutil.copy2(destination/'brain.sqlite3',restored)
        with sqlite3.connect(restored) as check,sqlite3.connect(destination/'brain.sqlite3') as copied:
            assert check.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            for table in TABLES:assert check.execute('SELECT * FROM '+table+' ORDER BY 1').fetchall()==copied.execute('SELECT * FROM '+table+' ORDER BY 1').fetchall()
    manifest={str(p.relative_to(destination)):hashlib.sha256(p.read_bytes()).hexdigest() for p in destination.rglob('*') if p.is_file()}
    (destination/'manifest.json').write_text(json.dumps(manifest,sort_keys=True))
    print('BACKUP_RESTORE_PASS',str(destination),flush=True)

def flatten(root,expected_sha,quotes,now):
    from director.brain_free.store import Store
    from director.brain_free.execution import fresh,close
    from director.brain_free.config import Config
    assert (root/'pause.flag').is_file()
    store=Store(root)
    try:
        state=store.load()
        assert state['mode']=='paper' and state['account_id']=='brain-free-paper'
        assert state['build_sha']==expected_sha and state['paused'] is True
        # Validate EVERY quote before closing ANY position. Never fill from a stale cached price.
        for symbol in state['positions']:assert fresh(quotes.get(symbol),now,Config()),'fresh_quote_required'
        rows=[]
        for symbol in list(state['positions']):
            event=close(state,symbol,quotes[symbol]['price'],now,'OPERATOR: approved V1 close before V2 scalp restart')
            event['source']='operator';event['quote_ts_ms']=quotes[symbol]['ts_ms']
            rows.append(('operator-close:'+str(uuid.uuid4()),'trade_closed',now,event))
        state['last_ms']=now
        store.commit(state,rows)
        print('OPERATOR_CLOSE_PASS',json.dumps({'closed':len(rows),'cash':state['cash'],'events':[{'symbol':e[3]['symbol'],'net':e[3]['net'],'fees':e[3]['fees'],'exit':e[3]['exit']} for e in rows]}),flush=True)
        return state
    finally:store.close()

def inside():
    from director.brain_free.feeds import quotes
    from director.brain_free.reframe import migrate
    path=pathlib.Path('/out')
    before=read_state(path/'brain.sqlite3')
    live=quotes(symbols=tuple(before['positions'])) if before['positions'] else {}
    flatten(path,OLD,live,int(time.time()*1000))
    result=migrate(path,pathlib.Path('/backup')/'migration',OLD,NEW)
    print('MIGRATION_PASS',json.dumps(result),flush=True)

def preserved(snapshot,current):
    with sqlite3.connect(snapshot) as old,sqlite3.connect(current.resolve().as_uri()+'?mode=ro',uri=True) as new:
        for table in ('events','requests'):
            cols=[r[1] for r in old.execute('PRAGMA table_info('+table+')')]
            old_rows=old.execute('SELECT * FROM '+table+' ORDER BY 1').fetchall()
            current_rows=new.execute('SELECT * FROM '+table+' ORDER BY 1').fetchall()
            assert all(row in current_rows for row in old_rows),'history_changed:'+table
        # Delivery acknowledgments may advance, but old message identity/body remain.
        assert all(row in new.execute('SELECT id,body FROM outbox').fetchall() for row in old.execute('SELECT id,body FROM outbox'))

def apply(source):
    assert os.getenv('DESK_MODE')=='paper' and command(['git','rev-parse','HEAD']).strip()==NEW
    before={n:inspect(n) for n in command(['docker','ps','--format','{{.Names}}']).splitlines()}
    old=before[NAME];env=dict(x.split('=',1) for x in old['Config']['Env'] if '=' in x)
    assert old['State']['Running'] and old['Config']['Labels']['superbot.sha']==OLD
    assert env['DESK_MODE']=='paper' and env.get('DEEPSEEK_API_KEY')
    assert (ROOT/'pause.flag').is_file() and read_state()['paused'] is True
    assert read_state()['build_sha']==OLD
    for name,item in before.items():
        if name==NAME:continue
        assert not any(m['Source']==str(ROOT) and m['RW'] for m in item.get('Mounts',[])),'duplicate_writer'
        if name in ('superbot-brain-hawk','superbot-brain-bull','superbot-brain-pilot'):raise ValueError('old_brain_still_active')
    for name in ('superbot-desk-hawk','superbot-desk-bull'):
        assert before[name]['Config']['Labels']['superbot.sha']=='dc16e0169932c3885908625ce5be321a33b09a0f'
    tag='superbot-brain-free:sha-'+NEW[:12]
    command(['docker','build','--label','superbot.sha='+NEW,'-t',tag,'-f','Dockerfile.brainfree','.'],900)
    print('DOCKER_BUILD_PASS',flush=True)
    archive=pathlib.Path('/opt/superbot-backups')/('brain-free-v2-'+time.strftime('%Y%m%dT%H%M%SZ',time.gmtime()))
    archive.mkdir(mode=0o700)
    backup(ROOT,archive/'online')
    (archive/'before-inventory.json').write_text(json.dumps({n:{'Id':i['Id'],'StartedAt':i['State']['StartedAt']} for n,i in before.items()}))
    command(['docker','stop','-t','150',NAME],180)
    renamed=False;new_started=False
    try:
        backup(ROOT,archive/'final-v1')
        # Source is pinned control code, mounted read-only; worker lock enforces exclusive mutation.
        output=command(['docker','run','--rm','-e','DESK_MODE=paper','-v',str(ROOT)+':/out','-v',str(archive)+':/backup','-v',str(source)+':/ops/cutover.py:ro','--entrypoint','python',tag,'/ops/cutover.py','--inside'],180)
        print(output,flush=True)
        assert not read_state()['positions'] and read_state()['build_sha']==NEW
        preserved(archive/'final-v1/brain.sqlite3',ROOT/'brain.sqlite3')
        previous=NAME+'-v1-'+archive.name.removeprefix('brain-free-v2-')
        command(['docker','rename',NAME,previous]);renamed=True
        (archive/'previous-container.txt').write_text(previous)
        env['BRAIN_FREE_CODE_SHA']=NEW;env['DESK_MODE']='paper'
        envfile=archive/'runtime.env'
        assert all('\n' not in k+v for k,v in env.items())
        envfile.write_text('\n'.join(k+'='+v for k,v in env.items())+'\n');envfile.chmod(0o600)
        args=['docker','run','-d','--name',NAME,'--restart','unless-stopped','--memory','512m','--cpus','0.5','--stop-timeout','150','--env-file',str(envfile)]
        for mount in old['Mounts']:
            assert mount['Type']=='bind'
            args+=['-v',mount['Source']+':'+mount['Destination']+('' if mount['RW'] else ':ro')]
        try:command(args+[tag,'--root','/out']);new_started=True
        finally:envfile.unlink(missing_ok=True)
        for _ in range(90):
            state=read_state()
            if state.get('fresh_quote_count',0)>=20 and state.get('instrument_count',0)>=20 and state.get('paused') is True and 0<=time.time()*1000-state.get('heartbeat_ms',0)<20000:break
            time.sleep(3)
        else:raise ValueError('paused_feed_warmup_failed')
        assert state['runtime_capacity']=={'max_slots':5,'max_margin':1750.0}
        assert state['build_sha']==NEW and state['previous_run_id']==read_state(archive/'final-v1/brain.sqlite3')['experiment_id']
        preserved(archive/'final-v1/brain.sqlite3',ROOT/'brain.sqlite3')
        for n,item in before.items():
            if n!=NAME:
                current=inspect(n);assert current['Id']==item['Id'] and current['State']['StartedAt']==item['State']['StartedAt'],'unrelated_changed'
        assert not inspect(previous)['State']['Running']
        backup(ROOT,archive/'v2-paused')
        # Refresh the activation marker for the V2 digest; migration records the new evaluation epoch.
        command(['docker','exec',NAME,'python','-c',"from pathlib import Path; Path('/out/activate.flag').write_text('"+state['config_hash']+"')"])
        (ROOT/'pause.flag').unlink()
        for _ in range(100):
            state=read_state()
            with sqlite3.connect((ROOT/'brain.sqlite3').resolve().as_uri()+'?mode=ro',uri=True) as db:
                count=db.execute("SELECT count(*) FROM events WHERE kind='ai_decision' AND ts>=?",(state['verified_start_ms'],)).fetchone()[0]
            if state['paused'] is False and count and 0<=time.time()*1000-state.get('heartbeat_ms',0)<20000:break
            time.sleep(3)
        else:raise ValueError('first_ai_response_not_verified')
        for _ in range(20):
            if (inspect(NAME)['State'].get('Health') or {}).get('Status')=='healthy':break
            time.sleep(3)
        assert (inspect(NAME)['State'].get('Health') or {}).get('Status')=='healthy'
        preserved(archive/'final-v1/brain.sqlite3',ROOT/'brain.sqlite3')
        backup(ROOT,archive/'postflight')
        result={k:state.get(k) for k in ('mode','build_sha','experiment_id','previous_run_id','v2_start_equity','cash','runtime_capacity','paused','cycles','verified_start_ms','provider_status','fresh_quote_count')}
        result.update(open_count=len(state['positions']),backup=str(archive),old_container=previous,other_containers_unchanged=True)
        (archive/'POSTFLIGHT.json').write_text(json.dumps(result,sort_keys=True))
        print('BRAIN_V2_POSTFLIGHT_PASS',json.dumps(result),flush=True)
    except BaseException:
        (ROOT/'pause.flag').touch()
        if new_started:
            # Preserve native stop/target protection if the first AI cycle already opened a position.
            if not inspect(NAME)['State']['Running']:command(['docker','start',NAME])
        state=read_state()
        if state.get('build_sha')==OLD and not renamed:command(['docker','start',NAME])
        # Never overwrite new financial events with an older DB or activate two writers.
        print('CUTOVER_FAILED_REMAINS_PAUSED_DATA_RETAINED',str(archive),flush=True)
        raise
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--inside',action='store_true');p.add_argument('--approved',default='no');p.add_argument('--control-script')
    args=p.parse_args();os.umask(0o077)
    if args.inside:inside()
    else:
        assert args.approved=='yes'
        apply(pathlib.Path(args.control_script).resolve())
