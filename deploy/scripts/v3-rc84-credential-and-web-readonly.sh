#!/usr/bin/env bash
# One-shot read-only inspection of secret PRESENCE and RC84/web readiness.
# Never prints secrets, does not copy keys, launch orders, or change files/services.
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1
python3 -I - <<'PY'
import json, pathlib, re, stat, subprocess, time, urllib.request, urllib.error

root=pathlib.Path('/opt/superbot-v3-paper-runs')
runpaths={'hawk':root/'classic-hawk-paper20261111',
          'bull':root/'classic-bull-paper20261111',
          'brain':root/'brain-v3-paper20261111'}
def emit(name,val): print('RC84_READONLY_'+name+'='+str(val),flush=True)
def read_json(p):
    try:
        if p.is_symlink() or not p.is_file() or p.stat().st_size>131072:return None
        return json.loads(p.read_text(encoding='utf-8'))
    except (OSError,ValueError,UnicodeError):return None
def env_keys_from_lines(seq):
    result=set()
    for s in seq:
        if '=' not in s:continue
        k,v=s.split('=',1)
        if re.fullmatch(r'[A-Z_][A-Z0-9_]*',k) and v.strip():
            result.add(k)
    return result
def inspect_keys(container):
    try:
        p=subprocess.run(['docker','inspect',container],capture_output=True,text=True,timeout=8)
        if p.returncode:return None
        o=json.loads(p.stdout)[0]
        return env_keys_from_lines(o.get('Config',{}).get('Env') or [])
    except (OSError,ValueError,IndexError,subprocess.SubprocessError):
        return None
def envfile_keys(path):
    try:
        if path.is_symlink() or not path.is_file():return None
        mode=path.stat().st_mode
        if not stat.S_ISREG(mode) or mode & 0o077 or path.stat().st_size>65536:return None
        # parse key names only; NEVER echo secret values or file contents
        result=set()
        for ln in path.read_text(encoding='utf-8').splitlines():
            ln=ln.strip()
            if not ln or ln.startswith('#') or '=' not in ln: continue
            key,v=ln.split('=',1)
            key=key.removeprefix('export ').strip()
            if re.fullmatch(r'[A-Z_][A-Z0-9_]*',key) and v.strip():
                result.add(key)
        return result
    except (OSError,UnicodeError):return None
def active(service):
    try:
        r=subprocess.run(['systemctl','is-active','--quiet',service],timeout=8,
                        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        return r.returncode==0
    except (OSError,subprocess.SubprocessError):return False
for pf,service in [('hawk','superbot-v3-paper-falco.service'),
                   ('bull','superbot-v3-paper-toro.service'),
                   ('brain','superbot-v3-paper-brain-runner.service')]:
    emit(pf.upper()+'_NEW_SERVICE_ACTIVE',active(service))
    emit(pf.upper()+'_PAUSED', (runpaths[pf]/'pause.flag').is_file())
emit('BRAIN_EXIT_SERVICE_ACTIVE',active('superbot-v3-paper-brain-exit.service'))
mandate=read_json(runpaths['brain']/'mandate.json')
emit('BRAIN_MANDATE_UNAPPROVED',isinstance(mandate,dict) and mandate.get('approved') is False)
eb=read_json(runpaths['brain']/'exit_heartbeat.json')
emit('BRAIN_EXIT_HEARTBEAT_HEALTHY',isinstance(eb,dict) and eb.get('state')=='healthy' and eb.get('last_error') is None and type(eb.get('ts_ms')) is int and 0<=time.time()*1000-eb['ts_ms']<120000)
legacy={'hawk':inspect_keys('superbot-desk-hawk'),'bull':inspect_keys('superbot-desk-bull'),'brain':inspect_keys('superbot-brain-free')}
for pf in ('hawk','bull','brain'):
    label='ANTHROPIC_API_KEY' if pf in ('hawk','bull') else 'DEEPSEEK_API_KEY'
    emit(pf.upper()+'_LEGACY_PROVIDER_KEY_PRESENT',legacy[pf] is not None and label in legacy[pf])
envfolder=pathlib.Path('/etc/superbot-v3-paper')
for pf,filename,key in [('hawk','falco-ai.env','ANTHROPIC_API_KEY'),('bull','toro-ai.env','ANTHROPIC_API_KEY'),('brain','brain-ai.env','DEEPSEEK_API_KEY')]:
    keys=envfile_keys(envfolder/filename)
    emit(pf.upper()+'_NEW_KEY_FILE_SAFE',keys is not None)
    emit(pf.upper()+'_NEW_PROVIDER_KEY_PRESENT',keys is not None and key in keys)
# The running process may have obtained keys from systemd/environment; don't claim absence
# of credentials solely from a missing optional EnvironmentFile.
def code(url,method='GET'):
    try:
        req=urllib.request.Request(url,method=method,headers={'content-type':'application/json'})
        with urllib.request.urlopen(req,timeout=5) as x:return x.status
    except urllib.error.HTTPError as x:return x.code
    except Exception:return 0
emit('RC84_PREVIEW_AUTH_401',code('http://127.0.0.1:18081/api/v3/overview')==401)
emit('RC84_PREVIEW_MUTATION_423',code('http://127.0.0.1:18081/api/v3/brain/close','POST')==423)
emit('PUBLIC_RC73_API_HEALTH',code('http://127.0.0.1:8002/api/health')==200)
print('RC84_READONLY_NO_SECRET_VALUES_EXPOSED=True')
print('RC84_READONLY_NO_WRITES_OR_ORDERS=True')
PY
