"""Runner orchestration. SSH keys and gateway tokens are never logged or uploaded."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import shlex
import subprocess
import tempfile
import time
import urllib.request

HERE=Path(__file__).resolve().parent
PIN='51.91.109.45 ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIIRVdMCm9yUh7bW5aPvQl119hPlB94cM1NMGqPZ1Mf4Y\n'
REMOTE=(HERE/'app_link_remote.py').read_text()
BACKUP=(HERE/'prepare_verified_backup.py').read_text()

class Target:
    def __init__(self,host,user,key,known,tmp,sudo=False):
        self.host,self.user,self.sudo=host,user,sudo
        keyfile=tmp/(host+'.key');knownfile=tmp/(host+'.known_hosts')
        for p,value in [(keyfile,key),(knownfile,known)]:
            if not value.strip():raise RuntimeError('Missing required SSH secret')
            p.write_text(value+'\n');p.chmod(0o600)
        self.args=['ssh','-i',str(keyfile),'-o','IdentitiesOnly=yes','-o','BatchMode=yes',
                   '-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+str(knownfile),
                   '-o','ConnectTimeout=20','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=3',user+'@'+host]

    def call(self,source,payload,timeout=1100):
        command=('sudo -n ' if self.sudo else '')+'python3 -c '+shlex.quote(source)
        result=subprocess.run(self.args+[command],input=json.dumps(payload).encode(),capture_output=True,timeout=timeout)
        try:obj=json.loads(result.stdout)
        except Exception:raise RuntimeError('SSH operation failed before a structured result: '+self.host)
        if result.returncode:raise RuntimeError(str(payload.get('action','backup'))+' failed: '+obj.get('message','remote error'))
        return obj

    def stage(self,action,**payload):
        return self.call(REMOTE,{'action':action,**payload})

def public_check():
    for suffix in ['health','desk/health','desk/bull/health']:
        with urllib.request.urlopen('https://superbot-trading.duckdns.org/api/'+suffix,timeout=20) as r:
            obj=json.load(r)
            if suffix=='health':assert obj.get('mode')=='paper' and obj.get('desk_mode')=='paper'
            else:
                assert r.headers.get('x-superbot-desk-source')=='singapore'
                assert obj.get('bot_online') is True
    with urllib.request.urlopen('https://hitvprime.duckdns.org/api/',timeout=20) as r:
        assert r.status==200
    return {'public_https_paper':True,'hawk_online':True,'bull_online':True,'hitv_http_200':True}

def main():
    os.umask(0o077)
    tag='r'+os.environ['GITHUB_RUN_ID']+'a'+os.environ.get('GITHUB_RUN_ATTEMPT','1')
    token=secrets.token_hex(32)
    files={p.name:p.read_text() for p in (HERE/'app_link').glob('*.py') if not p.name.startswith('test_')}
    # Frozen original API modules are the source of truth for on-disk compatibility.
    expected={name:hashlib.sha256(files[name].encode()).hexdigest() for name in ['desk_api.py','desk_view.py','live_view.py']}
    expected['server.py']='0336008d99543d1739c2b3d38e8ef6da13a356c65569c87ed49a76bc242aabe3'
    common={'tag':tag,'token':token,'files':files}
    with tempfile.TemporaryDirectory(prefix='superbot-app-link-') as dirname:
        tmp=Path(dirname);tmp.chmod(0o700)
        sg_known=os.environ['SG_KNOWN_HOSTS']
        old=Target('51.91.109.45','root',os.environ['OLD_SSH_KEY'],PIN,tmp)
        sg=Target('51.79.205.82','ubuntu',os.environ['SG_SSH_KEY'],sg_known,tmp,sudo=True)
        activation_attempted=False
        try:
            print('PHASE fresh_verified_backups',flush=True)
            for target in [old,sg]:
                result=target.call(BACKUP,{})
                assert result['restore_regular_files_verified'] and result['database']['integrity_ok']
                print(json.dumps({'host':target.host,'backup_directory':result['backup_directory'],
                                  'restore_verified':True,'database_integrity_ok':True}),flush=True)
            print('PHASE prepare_original_backend_and_dedicated_key',flush=True)
            prepared=old.stage('prepare_old',**common,expected_sources=expected,known_hosts=sg_known)
            print('PHASE build_and_start_private_gateway_without_engines',flush=True)
            print(json.dumps(sg.stage('prepare_sg',**common,public_key=prepared['public_key'])),flush=True)
            print('PHASE private_tunnel_and_original_container_connectivity',flush=True)
            print(json.dumps(old.stage('prepare_tunnel',**common)),flush=True)
            print('PHASE activate_superbot_api_only',flush=True)
            activation_attempted=True
            print(json.dumps(old.stage('activate',**common)),flush=True)
            print('PHASE authenticated_read_checks_and_invariants',flush=True)
            print(json.dumps(old.stage('verify_old',**common)),flush=True)
            first=sg.stage('verify_sg',**common)
            print(json.dumps(first),flush=True)
            print(json.dumps(public_check()),flush=True)
            # Wait for further engine heartbeats, without invoking any bot command.
            time.sleep(35)
            second=sg.stage('verify_sg',**common)
            for b in ['hawk','bull']:
                assert second['portfolios'][b]['heartbeat_ts']>first['portfolios'][b]['heartbeat_ts']
            print(json.dumps({'second_observation':second,'heartbeats_advanced':True}),flush=True)
            print(json.dumps(public_check()),flush=True)
            print('MIGRATION_APP_LINK_VERIFIED',flush=True)
        except Exception as exc:
            print('MIGRATION_STOPPED: '+str(exc),flush=True)
            restored=not activation_attempted
            if activation_attempted:
                try:
                    result=old.stage('rollback',**common)
                    print(json.dumps(result),flush=True)
                    restored=result.get('rollback_completed') or result.get('rollback_needed') is False
                except Exception as rollback_exc:
                    print('ROLLBACK_REQUIRES_INSPECTION: '+str(rollback_exc),flush=True)
            if restored:
                for target in [old,sg]:
                    try:print(json.dumps(target.stage('cleanup',**common)),flush=True)
                    except Exception:print('Cleanup requires inspection on '+target.host,flush=True)
            raise SystemExit(1)

if __name__=='__main__':main()
