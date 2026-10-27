"""Guarded PAPER rollout metadata, backup and postflight; no operational writes."""
import hashlib,json,os,subprocess,time,urllib.request
from pathlib import Path
BASE='89b0dca3e259c548ed82754c2301c7b024d18ff5'
OLD_APP='4cf41d23bb94f7a868b25dd1c89b3e4e8993d9a8'
BOT='27d2bf03fa2fba22f5021ec99f3c6720807d8583'
APP='56dc4bb62f64024d1ea7e5bc84602fbf52ea4ace'
SAVED=Path('/opt/superbot-deploys/classici-vault-20261027-preflight.json')
ROOT=Path('/opt/superbot-desk-data')
FILES=('trade_history.jsonl','lessons.md','errors.md','learning_log.jsonl')
def call(args):
 p=subprocess.run(args,capture_output=True,text=True,timeout=60)
 if p.returncode:raise ValueError('COMMAND_FAILED:'+args[0])
 return p.stdout

def inspect(n):return json.loads(call(['docker','inspect',n]))[0]
def env(i):return dict(x.split('=',1) for x in i['Config'].get('Env',[]) if '=' in x)
def sha(data):return hashlib.sha256(data).hexdigest()
def state(p):return json.loads((ROOT/p/'state_v2.json').read_text())
def hb(p):return json.loads((ROOT/p/'heartbeat.json').read_text())
def inventory():return {n:inspect(n) for n in call(['docker','ps','--format','{{.Names}}']).splitlines()}
def sane(n,i,expected):
 assert i['State']['Running'] and env(i).get('DESK_MODE')=='paper','NOT_RUNNING_PAPER:'+n
 assert i['Config'].get('Labels',{}).get('superbot.sha')==expected,'SOURCE_LABEL:'+n
 if n!='superbot':assert i['State'].get('Health',{}).get('Status')=='healthy','NOT_HEALTHY:'+n
 print('RUNTIME',n,expected,'RUNNING_PAPER')

def preflight():
 assert not SAVED.exists(),'PREFLIGHT_ALREADY_EXISTS'
 inv=inventory()
 for p in ('hawk','bull'):
  n='superbot-desk-'+p;i=inv[n];sane(n,i,BASE)
  assert env(i).get('DESK_CAPITAL_V1','off')=='off','PRIOR_CAPITAL_NOT_OFF'
  h=hb(p);assert h['version']==BASE[:7] and time.time()*1000-h['last_end_ms']<3600000,'STALE_CLASSIC'
  for f in ('cli','engine','signals','brain','market_context','seasonal'):
   expected=sha(subprocess.check_output(['git','show',BASE+':backend/desk/'+f+'.py']))
   actual=call(['docker','exec',n,'sha256sum','/app/backend/desk/'+f+'.py']).split()[0]
   assert actual==expected,'SOURCE_HASH:'+p+':'+f
  assert len([n for n,i in inv.items() if n!='superbot' and any(m['Source']==str(ROOT/p) for m in i.get('Mounts',[]))])==1,'DUPLICATE_WRITER'
  st=state(p);assert 'main' in st and 'cash' in st['main'],'BAD_STATE'
  print('CLASSIC_SOURCE',p,'PASS','positions='+str(len(st['main'].get('positions',{}))),'capital_policy='+str((st.get('capital')or{}).get('policy','none')))
 sane('superbot',inv['superbot'],OLD_APP)
 for n in ('superbot-brain-hawk','superbot-brain-bull'):
  sane(n,inv[n],'129547ed43a9aaec935df31102bb4e8016c38e7c')
 sane('superbot-brain-pilot',inv['superbot-brain-pilot'],'1f2edeb6182029adc96ba7218ad145a7503472a3')
 assert int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))>700*1024,'MEMORY_LOW'
 subprocess.run(['python3','-I','deploy/scripts/backup_brain.py','--root',str(ROOT),'--dir','/opt/superbot-backups','--keep','10','--tag','classici_vault_preflight'],check=True)
 subprocess.run(['python3','-I','deploy/scripts/backup_app_db.py','--src','/opt/superbot/data/superbot.db','--dir','/opt/superbot-backups','--prefix','classici-vault-app','--keep','10'],check=True)
 backup=sorted(Path('/opt/superbot-backups').glob('bots-*-classici_vault_preflight'))[-1]
 manifest=json.loads((backup/'MANIFEST.json').read_text())
 assert manifest['coerenza']['confine_di_ciclo_verificato'],'BACKUP_NOT_VERIFIED'
 saved={'backup':str(backup),'containers':{n:{'id':i['Id'],'started':i['State']['StartedAt']} for n,i in inv.items()},'profiles':{}}
 for p in ('hawk','bull'):
  protected={}
  for f in FILES:
   data=(backup/p/f).read_bytes();protected[f]={'size':len(data),'sha256':sha(data)}
  saved['profiles'][p]={'state':json.loads((backup/p/'state_v2.json').read_text()),'protected':protected}
 SAVED.parent.mkdir(exist_ok=True)
 fd=os.open(str(SAVED),os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
 with os.fdopen(fd,'w') as f:json.dump(saved,f)
 print('PREFLIGHT_BACKUP_RESTORE=PASS',backup.name)
 print('PREFLIGHT=PASS')

def postflight():
 saved=json.loads(SAVED.read_text());inv=inventory()
 for n,old in saved['containers'].items():
  if n in ('superbot','superbot-desk-hawk','superbot-desk-bull'):continue
  assert n in inv and inv[n]['Id']==old['id'] and inv[n]['State']['StartedAt']==old['started'],'UNRELATED_CONTAINER_CHANGED:'+n
 print('BRAINS_AND_OTHER_CONTAINERS_UNCHANGED=PASS')
 for p in ('hawk','bull'):
  n='superbot-desk-'+p;sane(n,inv[n],BOT);h=hb(p)
  assert h['version']==BOT[:7] and h.get('salvadanaio') is True and h.get('capital_v1') is False,'HEARTBEAT_POLICY'
  assert time.time()*1000-h['last_end_ms']<600000 and h.get('last_ok') is True,'CYCLE_NOT_SUCCESSFUL'
  assert inv[n]['RestartCount']==0,'RESTARTED'
  assert env(inv[n]).get('DESK_CAPITAL_V1')=='off','CAPITAL_V1_ENABLED'
  for f,m in saved['profiles'][p]['protected'].items():
   path=ROOT/p/f
   with path.open('rb') as fp:data=fp.read(m['size'])
   assert path.stat().st_size>=m['size'] and sha(data)==m['sha256'],'PROTECTED_PREFIX_CHANGED:'+p+':'+f
  before=saved['profiles'][p]['state'];after=state(p)
  assert after.get('run_started_ms')==before.get('run_started_ms'),'RUN_RESET'
  cap=after['capital'];assert cap['policy']=='salvadanaio-only-v1' and cap['status']=='READY','VAULT_NOT_READY'
  oldpos=before['main'].get('positions',{})
  for sym,pos in oldpos.items():
   if sym in after['main'].get('positions',{}) and after['main']['positions'][sym]['id']==pos['id']:continue
   assert any(t['symbol']==sym and t['id']==pos['id'] for t in after['main'].get('closed',[])),'POSITION_LOST'
  print('CLASSIC_STATE',p,'PRESERVED','vault=READY','positions='+str(len(after['main'].get('positions',{}))))
 sane('superbot',inv['superbot'],APP)
 assert urllib.request.urlopen('http://127.0.0.1:8002/api/health',timeout=10).status==200,'APP_HTTP'
 # Exercise the actual installed read-only dashboard reader, never print balances.
 code="import desk_view; " + "; ".join("s=desk_view.build_status('/opt/superbot-desk-data/"+p+"','"+p+"'); assert s['salvadanaio']['available'] and s['salvadanaio']['ready']" for p in ('hawk','bull')) + "; print('SALVADANAIO_READER=PASS')"
 result=call(['docker','exec','superbot','python','-c',code])
 assert 'SALVADANAIO_READER=PASS' in result,'READER_FAILED'
 print('APP_HTTP_AND_VAULT_READER=PASS')
 print('POSTFLIGHT=PASS')

if __name__=='__main__':
 try:
  {'preflight':preflight,'postflight':postflight}[os.environ['PHASE']]()
 except Exception as e:
  print('ROLLOUT_CHECK_FAILED',type(e).__name__,str(e)[:180] if isinstance(e,AssertionError) else 'sanitized');raise SystemExit(1)
