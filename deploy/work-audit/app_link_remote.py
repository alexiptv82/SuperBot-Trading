"""Bounded migration operations, invoked over pinned SSH. Never prints credentials."""
import copy
import hashlib
import http.client
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.request

OLD='vps-ed34e4ce'
SG='vps-a06df2a7'
API_IMAGE='sha256:53bd4d2fee6958044c2c9d4982db46b2fe880254dda21e2ff5ca8bb8450f6b18'
ENGINE_IMAGE='sha256:bc26042b8672ecce4d5c3632f79ca2c4fa85191f6da0078b76768534d7de2369'
ROOT=Path('/opt/superbot-app-link')
PRIVATE_NET='superbot-app-link'
TUNNEL_NET='superbot-api-tunnel-net'

def run(args, *, input=None):
    p=subprocess.run(args,input=input,capture_output=True)
    if p.returncode:
        raise RuntimeError('Remote command failed: '+args[0])
    return p.stdout

def inspect(name):
    p=subprocess.run(['docker','inspect',name],capture_output=True)
    return json.loads(p.stdout)[0] if p.returncode==0 else None

def put(path,data,mode=0o600):
    path=Path(path)
    if path.is_symlink(): raise RuntimeError('Refusing symlink')
    with path.open('xb') as f: f.write(data.encode() if isinstance(data,str) else data)
    path.chmod(mode)

def release(req):
    tag=req['tag']
    if not tag.isalnum(): raise RuntimeError('Invalid release')
    return ROOT/'releases'/tag

def create_release(req):
    os.umask(0o077)
    p=release(req)
    p.mkdir(mode=0o700,parents=True,exist_ok=False)
    for name,data in req['files'].items():
        if Path(name).name!=name or not name.endswith('.py'): raise RuntimeError('Invalid source path')
        put(p/name,data)
    put(p/'gateway.token',req['token'])
    return p

def engines(expected_running):
    out={}
    for b in ('hawk','bull'):
        c=inspect('superbot-desk-'+b)
        if not c or c['State']['Running']!=expected_running: raise RuntimeError('Engine state changed')
        env=dict(e.split('=',1) for e in c['Config']['Env'] if '=' in e)
        if env.get('DESK_MODE')!='paper': raise RuntimeError('Expected PAPER')
        if not expected_running and c['HostConfig']['RestartPolicy']['Name']!='no':
            raise RuntimeError('Unsafe old engine restart policy')
        p=Path('/opt/superbot-desk-data')/b
        hb=json.loads((p/'heartbeat.json').read_text())
        state=json.loads((p/'state_v2.json').read_text())
        if expected_running and (hb.get('exec_mode')!='paper' or time.time()-hb['ts']>90):
            raise RuntimeError('PAPER heartbeat not fresh')
        account=state.get('main') or {}
        limits=account.get('limits') or {}
        out[b]={'id':c['Id'],'restarts':c['RestartCount'],'run_id':state.get('run_no'),
                'day':account.get('day'), 'day_start_equity':account.get('day_start_equity'),
                'daily_stop':limits.get('daily_stop'),
                'heartbeat_ts':hb.get('ts'), 'heartbeat_age_s':round(time.time()-hb['ts'],1)}
        out[b]['histories']={}
        for name in ['trade_history.jsonl','learning_log.jsonl']:
            data=(p/name).read_bytes()
            out[b]['histories'][name]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
    legacy=inspect('superbot-desk')
    if legacy and legacy['State']['Running']: raise RuntimeError('Legacy engine running')
    return out

def auth_fingerprint():
    db=sqlite3.connect('file:/opt/superbot/data/superbot.db?mode=ro',uri=True)
    try:
        if db.execute('PRAGMA integrity_check').fetchall()!=[('ok',)]: raise RuntimeError('Database integrity failed')
        auth=db.execute('SELECT id,password_hash,password_changed_at,token_version,jwt_secret FROM auth_settings ORDER BY id').fetchall()
        creds=db.execute('SELECT id,credential_id,hex(public_key),device_label,created_at FROM webauthn_credentials ORDER BY id').fetchall()
        return hashlib.sha256(json.dumps([auth,creds],sort_keys=True).encode()).hexdigest()
    finally:db.close()

def nginx_fingerprint():
    out={}
    for p in sorted(Path('/etc/nginx/sites-enabled').iterdir()):
        if p.is_file():out[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
    return out

class DockerConnection(http.client.HTTPConnection):
    def __init__(self):super().__init__('localhost',timeout=40)
    def connect(self):
        self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        self.sock.connect('/var/run/docker.sock')

def docker_api(method,path,body=None):
    version_conn=DockerConnection()
    try:
        version_conn.request('GET','/version')
        reply=version_conn.getresponse()
        version=json.loads(reply.read())['ApiVersion']
        if not all(part.isdigit() for part in version.split('.')):raise RuntimeError('Invalid Docker API version')
    finally:version_conn.close()
    c=DockerConnection()
    try:
        c.request(method,'/v'+version+path,body=json.dumps(body) if body is not None else None,
                  headers={'Content-Type':'application/json'})
        r=c.getresponse();data=r.read()
        if r.status>=300:
            error_path=ROOT/('docker-error-'+secrets.token_hex(4)+'.json')
            put(error_path,data)
            raise RuntimeError('Docker API request rejected, status '+str(r.status)+'; protected diagnostic '+error_path.name)
        return json.loads(data) if data else None
    finally:c.close()

def api_config(original,p,entry):
    cfg=copy.deepcopy(original['Config'])
    if cfg.get('Entrypoint'):raise RuntimeError('Unexpected entrypoint')
    command=cfg.get('Cmd') or []
    if sum('backend.server:app' in arg for arg in command)!=1:raise RuntimeError('Unexpected API launch command')
    cfg['Cmd']=[arg.replace('backend.server:app','app_link.'+entry+':app') for arg in command]
    cfg['Image']=original['Image']
    cfg.pop('Hostname',None)
    env=dict(e.split('=',1) for e in cfg['Env'] if '=' in e)
    env.update(DESK_MODE='paper',DESK_REMOTE_BASE_URL=(p/'remote-url').read_text().strip())
    cfg['Env']=[k+'='+v for k,v in env.items()]
    hc=copy.deepcopy(original['HostConfig'])
    if hc['NetworkMode']!='bridge' or hc.get('AutoRemove'):raise RuntimeError('Unsupported API network/lifecycle')
    hc['Binds']=(hc.get('Binds') or [])+[str(p)+':/app/app_link:ro']
    cfg['HostConfig']=hc
    return cfg

def http_json(url,token=None):
    req=urllib.request.Request(url,headers={'X-Superbot-Gateway-Token':token} if token else {})
    with urllib.request.urlopen(req,timeout=20) as r:return json.load(r)

def wait_api(url,token=None):
    for _ in range(30):
        try:return http_json(url,token)
        except Exception:time.sleep(1)
    raise RuntimeError('API readiness failed')

def prepare_old(req):
    if socket.gethostname()!=OLD: raise RuntimeError('Wrong host')
    engines(False)
    c=inspect('superbot')
    if not c or not c['State']['Running'] or c['Image']!=API_IMAGE:raise RuntimeError('API changed since audit')
    if c['NetworkSettings']['Networks']['bridge']['Gateway']!='172.17.0.1':raise RuntimeError('Docker gateway changed')
    for name,digest in req['expected_sources'].items():
        f=Path('/proc')/str(c['State']['Pid'])/'root/app/backend'/name
        if hashlib.sha256(f.read_bytes()).hexdigest()!=digest:raise RuntimeError('Deployed source changed')
    p=create_release(req)
    put(p/'original-container.json',json.dumps(c))
    hitv=inspect('hitv-backend')
    if not hitv or not hitv['State']['Running']:raise RuntimeError('HI-TV not running')
    baseline={'auth':auth_fingerprint(),'nginx':nginx_fingerprint(),'hitv_id':hitv['Id'],'hitv_restarts':hitv['RestartCount']}
    put(p/'baseline.json',json.dumps(baseline))
    keydir=Path('/root/superbot-secrets/app-link')
    keydir.mkdir(mode=0o700,parents=True,exist_ok=True)
    key=keydir/(req['tag']+'.ed25519')
    run(['ssh-keygen','-q','-t','ed25519','-N','','-C','superbot-app-link-'+req['tag'],'-f',str(key)])
    put(keydir/(req['tag']+'.known_hosts'),req['known_hosts'])
    return {'prepared':True,'public_key':key.with_suffix('.ed25519.pub').read_text().strip()}

def prepare_sg(req):
    if socket.gethostname()!=SG:raise RuntimeError('Wrong host')
    before=engines(True)
    previous=inspect('superbot-desk-api')
    if previous:
        if previous['State']['Running'] or 'gateway:production_app' not in (previous['Config'].get('Cmd') or []):
            raise RuntimeError('An active or unrelated gateway exists')
        if not any(str(ROOT/'releases') in bind for bind in previous['HostConfig'].get('Binds',[])):
            raise RuntimeError('Unexpected previous gateway mounts')
        run(['docker','rename','superbot-desk-api','superbot-desk-api-retained-'+req['tag']])
    if any(inspect('superbot-desk-'+b)['Image']!=ENGINE_IMAGE for b in before):raise RuntimeError('Engine image changed')
    p=create_release(req)
    put(p/'engine-baseline.json',json.dumps(before))
    # The build context contains only a Dockerfile, never the gateway token.
    build=p/'build';build.mkdir(mode=0o700)
    base_tag='superbot-work-gateway-base:'+req['tag']
    run(['docker','tag',ENGINE_IMAGE,base_tag])
    dockerfile='FROM '+base_tag+'\nRUN python -m pip install --no-cache-dir fastapi==0.110.0 httpx==0.27.0 uvicorn==0.27.1\n'
    put(build/'Dockerfile',dockerfile)
    image='superbot-work-desk-api:'+req['tag']
    with (p/'build.log').open('xb') as log:
        result=subprocess.run(['docker','build','--pull=false','-t',image,str(build)],stdout=log,stderr=log,timeout=900)
    if result.returncode:raise RuntimeError('Gateway image build failed; private build log retained')
    image_meta=json.loads(run(['docker','image','inspect',image]))[0]
    if image_meta['Config'].get('Entrypoint'):raise RuntimeError('Unexpected gateway base entrypoint')
    for val in image_meta['Config'].get('Env',[]):
        name,_,content=val.partition('=')
        if content and any(x in name.upper() for x in ['TOKEN','SECRET','PASSWORD','API_KEY','PASSPHRASE']):
            raise RuntimeError('Unexpected secret in image defaults')
    # Validate runtime modules without data mounts or an engine command.
    run(['docker','run','--rm','--network','none','--entrypoint','python',image,'-c',
        'import fastapi,httpx,uvicorn,ccxt; print("runtime-ok")'])
    auth=Path('/home/ubuntu/.ssh/authorized_keys')
    old=auth.read_bytes()
    put(p/'ubuntu-authorized-keys.before',old)
    if not req['public_key'].startswith('ssh-ed25519 '):raise RuntimeError('Invalid tunnel public key')
    line='from="51.91.109.45",restrict,port-forwarding,permitopen="127.0.0.1:18002",permitlisten="127.0.0.1:18002",command="/bin/false" '+req['public_key']+'\n'
    with auth.open('ab') as f:f.write(('\n' if old and not old.endswith(b'\n') else '').encode()+line.encode())
    auth.chmod(0o600)
    config={'Image':image,'User':'0:0','Entrypoint':[],'WorkingDir':'/app/app_link','Env':['DESK_MODE=paper','PYTHONPATH=/app/app_link','PYTHONDONTWRITEBYTECODE=1'],
      'Cmd':['python','-m','uvicorn','gateway:production_app','--factory','--host','0.0.0.0','--port','8001','--no-access-log','--workers','1'],
      'ExposedPorts':{'8001/tcp':{}},
      'HostConfig':{'Binds':[str(p)+':/app/app_link:ro']+[str(Path('/opt/superbot-desk-data')/b)+':'+str(Path('/opt/superbot-desk-data')/b)+':rw' for b in before],
        'PortBindings':{'8001/tcp':[{'HostIp':'127.0.0.1','HostPort':'18002'}]},
        'RestartPolicy':{'Name':'unless-stopped'},'ReadonlyRootfs':True,'CapDrop':['ALL'],
        'SecurityOpt':['no-new-privileges:true'],'Tmpfs':{'/tmp':'rw,noexec,nosuid,size=16777216'},'Memory':536870912,'NanoCpus':1000000000}}
    docker_api('POST','/containers/create?name=superbot-desk-api',config)
    run(['docker','start','superbot-desk-api'])
    wait_api('http://127.0.0.1:18002/api/desk/health',req['token'])
    return {'gateway_ready':True,'loopback_only':True,'engine_count':2}

def prepare_tunnel(req):
    p=release(req)
    keydir=Path('/root/superbot-secrets/app-link')
    key=keydir/(req['tag']+'.ed25519')
    known=keydir/(req['tag']+'.known_hosts')
    docker=shutil.which('docker');nsenter=shutil.which('nsenter');ssh=shutil.which('ssh')
    if not all([docker,nsenter,ssh]):raise RuntimeError('Missing tunnel runtime')
    network=subprocess.run(['docker','network','inspect',PRIVATE_NET],capture_output=True)
    if network.returncode:
        run(['docker','network','create','--label','io.superbot.app-link=managed',PRIVATE_NET])
    else:
        info=json.loads(network.stdout)[0]
        if info.get('Labels',{}).get('io.superbot.app-link')!='managed':raise RuntimeError('Unexpected private network')
    sidecar=inspect(TUNNEL_NET)
    if not sidecar:
        docker_api('POST','/containers/create?name='+TUNNEL_NET,{
            'Image':API_IMAGE,'Entrypoint':[],'Cmd':['sleep','infinity'],
            'Labels':{'io.superbot.app-link':'managed'},
            'HostConfig':{'NetworkMode':PRIVATE_NET,'RestartPolicy':{'Name':'unless-stopped'},
              'ReadonlyRootfs':True,'CapDrop':['ALL'],'SecurityOpt':['no-new-privileges:true'],'Memory':33554432}})
    elif sidecar['Config'].get('Labels',{}).get('io.superbot.app-link')!='managed':
        raise RuntimeError('Unexpected tunnel namespace container')
    run(['docker','update','--restart=unless-stopped',TUNNEL_NET])
    run(['docker','start',TUNNEL_NET])
    sidecar=inspect(TUNNEL_NET)
    address=sidecar['NetworkSettings']['Networks'][PRIVATE_NET]['IPAddress']
    if not address:raise RuntimeError('Missing private tunnel address')
    put(p/'remote-url','http://'+address+':18002')
    script=Path('/usr/local/libexec/superbot-api-tunnel.sh')
    script.parent.mkdir(mode=0o755,parents=True,exist_ok=True)
    if script.exists():
        if '# SuperBot app-link managed' not in script.read_text():raise RuntimeError('Unrelated tunnel launcher exists')
        put(p/'previous-tunnel-launcher.sh',script.read_bytes())
    launcher='''#!/bin/sh
# SuperBot app-link managed
set -eu
DOCKER start superbot-api-tunnel-net >/dev/null
task_pid=$(DOCKER inspect --format '{{.State.Pid}}' superbot-api-tunnel-net)
exec NSENTER --target "$task_pid" --net SSH -NT -i KEY -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=KNOWN -o ExitOnForwardFailure=yes -o ConnectTimeout=15 -o ServerAliveInterval=15 -o ServerAliveCountMax=3 -L 0.0.0.0:18002:127.0.0.1:18002 ubuntu@51.79.205.82
'''.replace('DOCKER',docker).replace('NSENTER',nsenter).replace('SSH',ssh).replace('KEY',str(key)).replace('KNOWN',str(known))
    staged=p/'tunnel-launcher.sh';put(staged,launcher,0o700)
    shutil.copyfile(staged,script);script.chmod(0o700)
    unit=Path('/etc/systemd/system/superbot-api-tunnel.service')
    if unit.exists():
        if 'Description=SuperBot private PAPER API channel' not in unit.read_text():raise RuntimeError('Unrelated tunnel unit exists')
        put(p/'previous-tunnel.service',unit.read_bytes())
    config='''[Unit]
Description=SuperBot private PAPER API channel to Singapore
After=network-online.target docker.service
Wants=network-online.target
[Service]
Type=simple
User=root
ExecStart=/usr/local/libexec/superbot-api-tunnel.sh
Restart=always
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=read-only
[Install]
WantedBy=multi-user.target
'''
    staged_unit=p/'tunnel.service';put(staged_unit,config,0o644)
    shutil.copyfile(staged_unit,unit);unit.chmod(0o644)
    run(['systemctl','daemon-reload'])
    run(['systemctl','enable','--now','superbot-api-tunnel.service'])
    wait_api('http://'+address+':18002/api/desk/health',req['token'])
    # Probe from the original API image on the dedicated private network, with no state mounts.
    code='import json,sys,urllib.request; d=json.load(sys.stdin); r=urllib.request.Request(d["url"]+"/api/desk/health",headers={"X-Superbot-Gateway-Token":d["token"]}); print(json.load(urllib.request.urlopen(r,timeout=15))["available"])'
    run(['docker','run','--rm','-i','--network',PRIVATE_NET,'--entrypoint','python',API_IMAGE,'-c',code],
        input=json.dumps({'url':'http://'+address+':18002','token':req['token']}).encode())
    return {'tunnel_ready':True,'reachable_from_backend_image_on_private_network':True,'no_public_port':True}

def activate(req):
    p=release(req)
    old=json.loads((p/'original-container.json').read_text())
    current=inspect('superbot')
    if not current or current['Id']!=old['Id'] or not current['State']['Running']:raise RuntimeError('Original API changed')
    engines(False)
    candidate='superbot-app-candidate-'+req['tag']
    docker_api('POST','/containers/create?name='+candidate,api_config(old,p,'entry'))
    run(['docker','network','connect',PRIVATE_NET,candidate])
    put(p/'activation-started','true')
    run(['docker','update','--restart=no','superbot'])
    run(['docker','stop','--time','20','superbot'])
    run(['docker','rename','superbot','superbot-work-rollback-'+req['tag']])
    run(['docker','rename',candidate,'superbot'])
    run(['docker','start','superbot'])
    status=wait_api('http://127.0.0.1:8002/api/health')
    if status.get('mode')!='paper' or status.get('desk_mode')!='paper':raise RuntimeError('API mode mismatch')
    put(p/'activation-completed','true')
    return {'activated':True,'mode':'paper','old_container_retained_stopped':True}

def verify_old(req):
    p=release(req)
    baseline=json.loads((p/'baseline.json').read_text())
    hitv=inspect('hitv-backend')
    if hitv['Id']!=baseline['hitv_id'] or hitv['RestartCount']!=baseline['hitv_restarts'] or not hitv['State']['Running']:
        raise RuntimeError('HI-TV invariant failed')
    if nginx_fingerprint()!=baseline['nginx']:raise RuntimeError('Nginx changed')
    if auth_fingerprint()!=baseline['auth']:raise RuntimeError('Authentication state changed')
    engines(False)
    # Create a 60-second validation session in memory from existing signing state (read-only SQL).
    # No password, biometrics, token_version, or database row is changed. Token never leaves the container.
    code='''import json,time,sqlite3,urllib.request,urllib.error,jwt
from config import config
db=sqlite3.connect('file:'+config.DB_PATH+'?mode=ro',uri=True)
secret,ver=db.execute('SELECT jwt_secret,token_version FROM auth_settings WHERE id=1').fetchone();db.close()
now=int(time.time()); token=jwt.encode({'sub':'superbot-dashboard','iat':now,'exp':now+60,'scope':'full','ver':ver},secret,algorithm='HS256')
results={}
for base in ['http://127.0.0.1:8001','https://superbot-trading.duckdns.org']:
 for suffix in ['health','status','trades','performance','diary','runs','logs','hours','bull/health','bull/status','bull/trades','bull/performance','bull/diary','bull/runs','bull/logs','bull/hours','live/overview']:
  r=urllib.request.Request(base+'/api/desk/'+suffix,headers={'Authorization':'Bearer '+token})
  with urllib.request.urlopen(r,timeout=25) as reply:
   obj=json.load(reply)
   assert reply.headers.get('x-superbot-desk-source')=='singapore'
   if suffix.endswith('health') or suffix.endswith('status'):results[base+'/'+suffix]={'status':reply.status,'bot_online':obj.get('bot_online'),'heartbeat_age_s':obj.get('heartbeat_age_s'),'run_id':obj.get('run_id')}
 for suffix in ['status','bull/status']:
  try: urllib.request.urlopen(base+'/api/desk/'+suffix,timeout=10);raise AssertionError('Unauthenticated access allowed')
  except urllib.error.HTTPError as e:assert e.code==401
print(json.dumps({'authenticated_get_routes':34,'unauthenticated_rejected':True,'read_results':results}))
'''
    checks=json.loads(run(['docker','exec','superbot','python','-c',code]))
    return {'auth_preserved':True,'database_integrity_ok':True,'nginx_unchanged':True,'hitv_unchanged':True,
            'old_engines_stopped':True,**checks}

def verify_sg(req):
    p=release(req)
    before=json.loads((p/'engine-baseline.json').read_text())
    after=engines(True)
    for bot in before:
        for key in ['id','restarts','run_id','day','day_start_equity','daily_stop']:
            if before[bot][key]!=after[bot][key]:raise RuntimeError('Engine continuity changed: '+bot+'/'+key)
        for name,saved in before[bot]['histories'].items():
            with (Path('/opt/superbot-desk-data')/bot/name).open('rb') as f:prefix=f.read(saved['bytes'])
            if hashlib.sha256(prefix).hexdigest()!=saved['sha256']:raise RuntimeError('Historical prefix changed')
    gateway=inspect('superbot-desk-api')
    if not gateway or not gateway['State']['Running']:raise RuntimeError('Gateway stopped')
    return {'engines_unchanged':True,'mode':'paper','portfolios':after,'gateway_running':True}

def rollback(req):
    p=release(req)
    if not (p/'activation-started').exists():return {'rollback_needed':False}
    original=json.loads((p/'original-container.json').read_text())
    current=inspect('superbot')
    if current:
        run(['docker','update','--restart=no','superbot'])
        if current['State']['Running']:run(['docker','stop','--time','20','superbot'])
        run(['docker','rename','superbot','superbot-work-failed-'+req['tag']])
    docker_api('POST','/containers/create?name=superbot',api_config(original,p,'rollback_entry'))
    run(['docker','start','superbot'])
    wait_api('http://127.0.0.1:8002/api/health')
    try:http_json('http://127.0.0.1:8002/api/desk/health');raise RuntimeError('Rollback did not fail closed')
    except urllib.error.HTTPError as e:
        if e.code!=503:raise
    put(p/'rollback-completed','true')
    return {'rollback_completed':True,'original_api_image_restored':True,'desk_explicitly_unavailable':True,'database_not_restored_or_overwritten':True}

def cleanup(req):
    if socket.gethostname()==OLD:
        if Path('/etc/systemd/system/superbot-api-tunnel.service').exists():
            run(['systemctl','disable','--now','superbot-api-tunnel.service'])
        sidecar=inspect(TUNNEL_NET)
        if sidecar and sidecar['Config'].get('Labels',{}).get('io.superbot.app-link')=='managed':
            run(['docker','update','--restart=no',TUNNEL_NET])
            if sidecar['State']['Running']:run(['docker','stop','--time','5',TUNNEL_NET])
    else:
        c=inspect('superbot-desk-api')
        if c:
            run(['docker','update','--restart=no','superbot-desk-api'])
            if c['State']['Running']:run(['docker','stop','--time','15','superbot-desk-api'])
    return {'new_channel_stopped':True}

def finalize(req):
    p=release(req)
    if socket.gethostname()==SG:
        # Revoke only temporary tunnel keys created by our unsuccessful preparation attempts.
        path=Path('/home/ubuntu/.ssh/authorized_keys')
        lines=path.read_text().splitlines(keepends=True)
        comment='superbot-app-link-'+req['tag']
        if sum(line.strip().split()[-1:]==[comment] for line in lines)!=1:
            raise RuntimeError('Expected exactly one active tunnel key')
        kept=[line for line in lines if not (line.strip().split()[-1:] and
              line.strip().split()[-1].startswith('superbot-app-link-r') and line.strip().split()[-1]!=comment)]
        put(p/'ubuntu-authorized-keys.before-pruning',path.read_bytes())
        st=path.stat();temp=path.parent/('authorized_keys.app-link-'+req['tag'])
        put(temp,''.join(kept));os.chown(temp,st.st_uid,st.st_gid);os.replace(temp,path)
        c=inspect('superbot-desk-api')
        if c['HostConfig']['PortBindings']!={'8001/tcp':[{'HostIp':'127.0.0.1','HostPort':'18002'}]}:
            raise RuntimeError('Gateway is not loopback-only')
        if c['HostConfig']['RestartPolicy']['Name']!='unless-stopped':raise RuntimeError('Gateway persistence mismatch')
    else:
        if run(['systemctl','is-enabled','superbot-api-tunnel.service']).decode().strip()!='enabled':
            raise RuntimeError('Tunnel is not enabled')
        if run(['systemctl','is-active','superbot-api-tunnel.service']).decode().strip()!='active':
            raise RuntimeError('Tunnel is not active')
        c=inspect(TUNNEL_NET)
        if c['HostConfig'].get('PortBindings'):raise RuntimeError('Unexpected published tunnel port')
        if c['HostConfig']['RestartPolicy']['Name']!='unless-stopped':raise RuntimeError('Namespace persistence mismatch')
        keydir=Path('/root/superbot-secrets/app-link')
        # A forced /bin/false session returns 1 after successful key authentication; SSH denial returns 255.
        args=['ssh','-T','-i',str(keydir/(req['tag']+'.ed25519')),'-o','IdentitiesOnly=yes','-o','BatchMode=yes',
          '-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+str(keydir/(req['tag']+'.known_hosts')),
          '-o','ConnectTimeout=15','ubuntu@51.79.205.82','true']
        probe=subprocess.run(args,capture_output=True,timeout=25)
        if probe.returncode!=1:raise RuntimeError('Fresh restricted-key authentication failed')
        if inspect('superbot')['HostConfig']['RestartPolicy']['Name']!='always':raise RuntimeError('API persistence mismatch')
    link=ROOT/'current'
    if link.exists() and not link.is_symlink():raise RuntimeError('Unexpected release marker')
    temp=ROOT/('.current-'+req['tag']);os.symlink(p,temp);os.replace(temp,link)
    put(p/'migration-verified.json',json.dumps({'verified':True,'release':req['tag'],'mode':'paper',
        'verified_at_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'data_not_restored_or_overwritten':True}))
    return {'finalized':True,'persistent_services_verified':True,'secrets_not_logged':True}

def main():
    os.umask(0o077)
    req=json.load(sys.stdin)
    actions={f.__name__:f for f in [prepare_old,prepare_sg,prepare_tunnel,activate,verify_old,verify_sg,rollback,cleanup,finalize]}
    result=actions[req['action']](req)
    print(json.dumps(result))

if __name__=='__main__':
    try:main()
    except Exception as exc:
        # Detailed trace is deliberately not emitted: container metadata and payload contain secrets.
        print(json.dumps({'ok':False,'error_type':type(exc).__name__,'message':str(exc) if isinstance(exc,RuntimeError) else 'Operation failed; inspect protected server state'}))
        raise SystemExit(1)
