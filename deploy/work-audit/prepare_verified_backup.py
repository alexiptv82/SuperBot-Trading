"""Prepare NEW protected backup copies; never modify source files or services.
The user's migration instructions explicitly require verified backups before changes.
No credentials or database contents are emitted. No code from a backup is executed.
"""
import datetime, hashlib, io, json, os, pathlib, secrets, sqlite3, stat, subprocess, tarfile, time
P=pathlib.Path

def digest(data): return hashlib.sha256(data).hexdigest()
def inspect(name):
 p=subprocess.run(['docker','inspect',name],capture_output=True,text=True)
 return json.loads(p.stdout)[0] if p.returncode==0 else None

def inventory(root):
 result={}
 for p in sorted(root.rglob('*')):
  if '__pycache__' in p.parts or p.suffix=='.pyc':continue
  s=p.lstat()
  if stat.S_ISREG(s.st_mode):result[str(p.relative_to(root))]=(s.st_ino,s.st_size,s.st_mtime_ns,stat.S_IMODE(s.st_mode),s.st_uid,s.st_gid)
  elif stat.S_ISLNK(s.st_mode):raise RuntimeError('Source symlink requires explicit backup handling')
 return result

def stable_files(root, idle=False):
 for _ in range(40):
  if idle:
   hb=json.loads((root/'heartbeat.json').read_text())
   if hb.get('cycle_running'):
    time.sleep(.2);continue
  before=inventory(root)
  data={n:(root/n).read_bytes() for n in before}
  after=inventory(root)
  if before==after:
   return data,before
  time.sleep(.15)
 raise RuntimeError('Could not capture a stable source window; originals unchanged')

def put(path, data):
 with open(path,'xb') as f:f.write(data)
 os.chmod(path,0o600)


def main():
 os.umask(0o077)
 host=subprocess.check_output(['hostname'],text=True).strip()
 if host not in ('vps-ed34e4ce','vps-a06df2a7'):raise RuntimeError('Unexpected host')
 parent=P('/root/superbot-work-backups'); parent.mkdir(mode=0o700,exist_ok=True)
 if parent.is_symlink():raise RuntimeError('Unexpected backup root symlink')
 os.chmod(parent,0o700)
 base=parent/(datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+secrets.token_hex(4))
 base.mkdir(mode=0o700)
 members={}; metadata={}; states={}
 for bot in ('hawk','bull'):
  source=P('/opt/superbot-desk-data')/bot
  if not source.is_dir():raise RuntimeError('Missing source portfolio')
  c=inspect('superbot-desk-'+bot)
  if not c:raise RuntimeError('Missing engine container metadata')
  env=dict(x.split('=',1) for x in c.get('Config',{}).get('Env',[]) if '=' in x)
  if env.get('DESK_MODE','').strip().lower()!='paper':raise RuntimeError('Engine is not confirmed simulated')
  if host=='vps-ed34e4ce' and (c.get('State',{}).get('Running') or c.get('HostConfig',{}).get('RestartPolicy',{}).get('Name')!='no'):
   raise RuntimeError('Old engines not safely stopped')
  files,info=stable_files(source,idle=bool(c.get('State',{}).get('Running')))
  for name,data in files.items():
   key='portfolios/'+bot+'/'+name
   members[key]=data;metadata[key]=info[name]
  states[bot]={'source_file_count':len(files),'heartbeat_present':'heartbeat.json' in files}
 # Back up exact currently running API sources, its frontend, and selected config.
 api=inspect('superbot')
 if api and api.get('State',{}).get('Running'):
  root=P('/proc')/str(api['State']['Pid'])/'root/app/backend'
  files,info=stable_files(root)
  for name,data in files.items():members['api/backend/'+name]=data;metadata['api/backend/'+name]=info[name]
  frontend=P('/opt/superbot/frontend/build')
  if frontend.is_dir():
   files,info=stable_files(frontend)
   for name,data in files.items():members['api/frontend/'+name]=data;metadata['api/frontend/'+name]=info[name]
  config=P('/etc/nginx/sites-available/superbot')
  if not config.is_file():raise RuntimeError('API nginx config missing')
  members['config/nginx-superbot.conf']=config.read_bytes()
  links={str(p):os.readlink(p) for p in P('/etc/nginx/sites-enabled').iterdir() if p.is_symlink()}
  members['config/nginx-enabled-links.json']=json.dumps(links).encode()
 auth=P('/root/.ssh/authorized_keys')
 if auth.is_file():members['config/root-authorized-keys']=auth.read_bytes()
 # Docker metadata can contain secrets: store protected, never log values.
 containers={name:c for name in ('superbot','superbot-staging','superbot-pool','superbot-desk','superbot-desk-hawk','superbot-desk-bull','hitv-backend') if (c:=inspect(name)) is not None}
 members['config/containers.json']=json.dumps(containers).encode()
 db=P('/opt/superbot/data/superbot.db')
 db_summary=None
 if db.is_file():
  output=base/'superbot.db'
  src=sqlite3.connect(db.as_uri()+'?mode=ro',uri=True,timeout=5)
  dst=sqlite3.connect(str(output))
  try:src.backup(dst)
  finally:dst.close();src.close()
  os.chmod(output,0o600)
  check=sqlite3.connect(output.as_uri()+'?mode=ro',uri=True)
  try:
   if check.execute('PRAGMA integrity_check').fetchall()!=[('ok',)]:raise RuntimeError('Backup database integrity failed')
   tables=check.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
   db_summary={'integrity_ok':True,'table_count':len(tables)}
  finally:check.close()
 # Archive paths are built by us and all contents were captured in a stable window.
 tarpath=base/'snapshot.tar.gz'
 with tarfile.open(tarpath,'x:gz') as tf:
  for name,data in sorted(members.items()):
   ti=tarfile.TarInfo(name);ti.size=len(data);ti.mode=0o600
   if name in metadata:ti.mode=metadata[name][3];ti.uid=metadata[name][4];ti.gid=metadata[name][5]
   tf.addfile(ti,io.BytesIO(data))
 os.chmod(tarpath,0o600)
 manifest={name:{'bytes':len(data),'sha256':digest(data)} for name,data in sorted(members.items())}
 put(base/'manifest.json',json.dumps(manifest,indent=2).encode())
 put(base/'source-metadata.json',json.dumps(metadata).encode())
 # Restore regular files into a NEW directory, without containers, imports or network.
 restore=base/'restore-check';restore.mkdir(mode=0o700)
 with tarfile.open(tarpath,'r:gz') as tf:
  for ti in tf.getmembers():
   if not ti.isfile() or ti.name.startswith('/') or '..' in P(ti.name).parts:raise RuntimeError('Unsafe archive member')
   data=tf.extractfile(ti).read()
   if digest(data)!=manifest[ti.name]['sha256']:raise RuntimeError('Archive checksum failed')
   target=restore/ti.name;target.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
   put(target,data)
   if digest(target.read_bytes())!=manifest[ti.name]['sha256']:raise RuntimeError('Restore checksum failed')
 for bot in ('hawk','bull'):
  for filename in ('state_v2.json','heartbeat.json'):
   json.loads((restore/'portfolios'/bot/filename).read_text())
  for filename in ('trade_history.jsonl','learning_log.jsonl'):
   p=restore/'portfolios'/bot/filename
   if p.is_file():
    for line in p.read_bytes().splitlines():
     if line.strip():json.loads(line)
 # Verify database restoration as separate bytes, never the live database.
 if db_summary:
  copied=restore/'superbot.db';put(copied,(base/'superbot.db').read_bytes())
  check=sqlite3.connect(copied.as_uri()+'?mode=ro',uri=True)
  try:
   if check.execute('PRAGMA integrity_check').fetchall()!=[('ok',)]:raise RuntimeError('Restored database failed')
  finally:check.close()
 summary={'host':host,'backup_directory':str(base),'archive_bytes':tarpath.stat().st_size,
          'archive_sha256':digest(tarpath.read_bytes()),'manifest_entries':len(manifest),
          'portfolios':states,'database':db_summary,'restore_regular_files_verified':True,
          'sources_unchanged':True,'services_not_modified':True}
 put(base/'verification.json',json.dumps(summary,indent=2).encode())
 print(json.dumps(summary))

if __name__=='__main__':
 try:main()
 except Exception as e:
  print(json.dumps({'backup_verified':False,'error_type':type(e).__name__,'message':'Preparation stopped; existing data and services were not modified.'}))
  raise SystemExit(1)
