"""Forensic COPY only: verified snapshot, engine code, filtered metadata and sanitized logs.
No engine imports, commands, state updates, service changes or secret output.
Transport is captured by the runner and encrypted before any log output.
"""
import base64,datetime,hashlib,io,json,os,pathlib,re,socket,sqlite3,subprocess,sys,tarfile
P=pathlib.Path
req=json.load(sys.stdin)
host=socket.gethostname()
if host not in ('vps-a06df2a7','vps-ed34e4ce'):raise RuntimeError('Unexpected host')
backup=P(req['backup'])
if backup.parent!=P('/root/superbot-work-backups'):raise RuntimeError('Unexpected backup')
verification=json.loads((backup/'verification.json').read_text())
if not verification['restore_regular_files_verified']:raise RuntimeError('Unverified backup')
members={};manifest={};secret_values=set();meta={'host':host,'captured_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
 'backup_verification':verification,'containers':{},'source_redactions':{}}

def digest(b):return hashlib.sha256(b).hexdigest()
def command(args):
 p=subprocess.run(args,capture_output=True)
 if p.returncode:raise RuntimeError('Read command failed: '+args[0])
 return p.stdout
def safe(data,name):
 original=digest(data);count=0
 for value in sorted(secret_values,key=len,reverse=True):
  if value in data:
   n=data.count(value);data=data.replace(value,b'[REDACTED]');count+=n
 # Defense for old keys which may no longer be in the current container environment.
 for pattern in [rb'sk-ant-[A-Za-z0-9_-]{20,}',rb'(?i)Bearer\s+[A-Za-z0-9._-]{24,}',
                 rb'bot[0-9]{6,}:[A-Za-z0-9_-]{20,}']:
  data,n=re.subn(pattern,b'[REDACTED]',data);count+=n
 meta['source_redactions'][name]={'source_sha256':original,'redactions':count}
 return data
def put(name,data,redact=True):
 if name.startswith('/') or '..' in P(name).parts:raise RuntimeError('Unsafe bundle path')
 if any(x in P(name).name.lower() for x in ['.env','private','credential','authorized_keys']):raise RuntimeError('Secret file excluded')
 if len(data)>25000000:raise RuntimeError('Individual file exceeds forensic size limit')
 data=safe(data,name) if redact else data
 members[name]=data;manifest[name]={'bytes':len(data),'sha256':digest(data)}

for bot in ['hawk','bull']:
 c=json.loads(command(['docker','inspect','superbot-desk-'+bot]))[0]
 env=dict(x.split('=',1) for x in c['Config']['Env'] if '=' in x)
 if env.get('DESK_MODE')!='paper':raise RuntimeError('Expected PAPER')
 for k,v in env.items():
  if any(x in k.upper() for x in ['KEY','TOKEN','SECRET','PASSWORD','PASSPHRASE']) and len(v)>=12:secret_values.add(v.encode())
 meta['containers'][bot]={'id':c['Id'],'created':c['Created'],'image':c['Image'],
  'running':c['State']['Running'],'started_at':c['State'].get('StartedAt'),'finished_at':c['State'].get('FinishedAt'),
  'restarts':c['RestartCount'],'restart_policy':c['HostConfig']['RestartPolicy'],
  'safe_environment':{k:v for k,v in env.items() if (k.startswith('DESK_') or k=='PYTHON_VERSION') and
   not any(x in k.upper() for x in ['KEY','TOKEN','SECRET','PASSWORD','PASSPHRASE','CHAT','CREDENTIAL'])},
  'mounts':[{'source':m['Source'],'destination':m['Destination'],'rw':m['RW']} for m in c.get('Mounts',[])],
  'log_config':c['HostConfig'].get('LogConfig'), 'log_driver':c.get('LogPath','').split('/')[-1]}
 if host=='vps-a06df2a7' and not c['State']['Running']:raise RuntimeError('Engine stopped unexpectedly')
 if host=='vps-ed34e4ce' and c['State']['Running']:raise RuntimeError('Old engine unexpectedly running')

source_manifest=json.loads((backup/'manifest.json').read_text())
with tarfile.open(backup/'snapshot.tar.gz','r:gz') as tf:
 for ti in tf.getmembers():
  if not ti.name.startswith('portfolios/') or not ti.isfile():continue
  data=tf.extractfile(ti).read()
  if digest(data)!=source_manifest[ti.name]['sha256']:raise RuntimeError('Snapshot checksum mismatch')
  put(ti.name,data)

for bot in ['hawk','bull']:
 name='superbot-desk-'+bot
 for candidate in ['/app/backend/desk','/app/desk']:
  p=subprocess.run(['docker','cp',name+':'+candidate,'-'],capture_output=True)
  if p.returncode:continue
  with tarfile.open(fileobj=io.BytesIO(p.stdout),mode='r:*') as tf:
   for ti in tf.getmembers():
    if ti.isfile() and ti.name.endswith('.py') and '__pycache__' not in ti.name:
     put('code/'+bot+'/'+ti.name,tf.extractfile(ti).read())
  break
 else:raise RuntimeError('Cannot copy actual engine source')
 p=subprocess.run(['docker','logs','--timestamps','--since','2026-10-16T00:00:00Z',
                   '--until',meta['captured_at_utc'],name],capture_output=True)
 if p.returncode:raise RuntimeError('Cannot capture engine logs')
 put('logs/'+bot+'.stdout.log',p.stdout)
 put('logs/'+bot+'.stderr.log',p.stderr)

if host=='vps-a06df2a7':
 cut=P('/home/ubuntu/superbot-final-staging/cutover-final-20261017T231817Z/hawk-bull-data.tar.gz')
 if cut.is_file():
  meta['cutover_archive']={'sha256':digest(cut.read_bytes()),'bytes':cut.stat().st_size}
  with tarfile.open(cut,'r:gz') as tf:
   for ti in tf.getmembers():
    if ti.isfile():put('cutover/'+ti.name.lstrip('./'),tf.extractfile(ti).read())
 for root in [P('/opt/superbot-prestart-backups')]:
  inventory=[]
  if root.is_dir():
   for p in sorted(root.rglob('*')):
    if not p.is_file() or p.is_symlink():continue
    if p.name in ['state_v2.json','heartbeat.json','trade_history.jsonl','learning_log.jsonl']:
     put('prestart/'+str(p.relative_to(root)),p.read_bytes())
    inventory.append({'path':str(p.relative_to(root)),'bytes':p.stat().st_size})
  meta['prestart_inventory']=inventory

db=P('/opt/superbot/data/superbot.db')
if db.is_file():
 con=sqlite3.connect(db.as_uri()+'?mode=ro',uri=True)
 try:
  meta['database']={'integrity_check':con.execute('PRAGMA integrity_check').fetchall(),
     'tables':{name:con.execute('SELECT COUNT(*) FROM "'+name.replace('"','""')+'"').fetchone()[0]
      for (name,) in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}}
 finally:con.close()

# Include original file inventory without including any private API/database configuration.
put('source-inventory.json',json.dumps({k:v for k,v in source_manifest.items() if k.startswith('portfolios/')},indent=2).encode(),False)
put('metadata.json',json.dumps(meta,indent=2).encode(),False)
put('manifest.json',json.dumps(manifest,indent=2).encode(),False)
data=io.BytesIO()
with tarfile.open(fileobj=data,mode='w:gz') as tf:
 for name,content in sorted(members.items()):
  ti=tarfile.TarInfo(name);ti.size=len(content);ti.mode=0o600;tf.addfile(ti,io.BytesIO(content))
bundle=data.getvalue()
folder=backup/'weekend-evidence';folder.mkdir(mode=0o700)
archive=folder/'evidence.tar.gz'
with archive.open('xb') as f:f.write(bundle)
archive.chmod(0o600)
# Verify the preserved evidence by isolated extraction, hashing every member.
restore=folder/'restore-check';restore.mkdir(mode=0o700)
with tarfile.open(archive,'r:gz') as tf:
 for ti in tf.getmembers():
  content=tf.extractfile(ti).read()
  if content!=members[ti.name]:raise RuntimeError('Evidence restore verification failed')
  p=restore/ti.name;p.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
  with p.open('xb') as f:f.write(content)
  p.chmod(0o600)
print(json.dumps({'tar_b64':base64.b64encode(bundle).decode(),'sha256':digest(bundle),'bytes':len(bundle),
 'host':host,'evidence_path':str(archive),'restore_verified':True}))
