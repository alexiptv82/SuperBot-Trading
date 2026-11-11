#!/usr/bin/env bash
# Provision only existing Claude/DeepSeek keys from STOPPED legacy PAPER containers
# to private EnvironmentFiles for the NEW PAUSED PAPER services. No key values in logs.
set -euo pipefail
umask 077
export PYTHONDONTWRITEBYTECODE=1
MODE="${1:---dry-run}"
[[ $# -le 1 && ( "$MODE" == --dry-run || "$MODE" == --provision-paused-only ) ]] || { echo RC84_AI_REFUSED_MODE; exit 2; }
python3 -I - "$MODE" <<'PY'
import json, os, pathlib, re, stat, subprocess, sys
mode=sys.argv[1]
root=pathlib.Path('/opt/superbot-v3-paper-runs')
paths=[root/'classic-hawk-paper20261111',root/'classic-bull-paper20261111',root/'brain-v3-paper20261111']
dest=pathlib.Path('/etc/superbot-v3-paper')
specs=[('superbot-desk-hawk','falco-ai.env','ANTHROPIC_API_KEY'),
       ('superbot-desk-bull','toro-ai.env','ANTHROPIC_API_KEY'),
       ('superbot-brain-free','brain-ai.env','DEEPSEEK_API_KEY')]
def refuse(code):
    print('RC84_AI_REFUSED_'+code,flush=True)
    raise SystemExit(2)
for p in paths:
    if p.is_symlink() or not p.is_dir() or (p/'pause.flag').is_symlink() or not (p/'pause.flag').is_file():
        refuse('RUN_NOT_PAUSED')
m=json.loads((paths[2]/'mandate.json').read_text())
if m.get('approved') is not False: refuse('BRAIN_MANDATE_APPROVED')
if dest.exists() or dest.is_symlink():
    if not dest.is_dir() or dest.is_symlink() or dest.stat().st_mode & 0o077:
        refuse('TARGET_DIR_UNSAFE')
for _,name,_ in specs:
    p=dest/name
    if p.exists() or p.is_symlink():
        refuse('TARGET_KEY_FILE_ALREADY_EXISTS')
result=[]
for container,name,key in specs:
    p=subprocess.run(['docker','inspect',container],capture_output=True,text=True,timeout=10)
    if p.returncode: refuse('SOURCE_CONTAINER_MISSING')
    o=json.loads(p.stdout)[0]
    if o['State']['Running'] is not False: refuse('SOURCE_CONTAINER_RUNNING')
    data=dict(s.split('=',1) for s in (o['Config']['Env'] or []) if '=' in s)
    if data.get('DESK_MODE')!='paper': refuse('SOURCE_NOT_PAPER')
    value=data.get(key,'')
    # EnvironmentFile safe unquoted value: letters, numbers, punctuation used by normal provider API tokens.
    # Do not echo a malformed or missing key.
    if not re.fullmatch(r'[A-Za-z0-9_.-]{20,512}',value): refuse('PROVIDER_KEY_NOT_SAFE_OR_MISSING')
    result.append((name,key,value))
if mode=='--dry-run':
    print('RC84_AI_ALL_THREE_EXISTING_KEYS_VALID_FORMAT=True')
    print('RC84_AI_THREE_TARGETS_UNOCCUPIED=True')
    print('RC84_AI_DRY_RUN_NO_WRITES=True')
    raise SystemExit(0)
created=[]
try:
    if not dest.exists():dest.mkdir(mode=0o700)
    os.chmod(dest,0o700)
    for name,key,value in result:
        p=dest/name
        flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0)
        fd=os.open(str(p),flags,0o600)
        created.append(p)
        with os.fdopen(fd,'w',encoding='utf-8') as f:
            f.write(key+'='+value+'\n')
            f.flush()
            os.fsync(f.fileno())
        os.chmod(p,0o600)
except (OSError,ValueError):
    for p in created:
        try:p.unlink()
        except OSError:pass
    refuse('PRIVATE_FILE_WRITE_FAILED')
print('RC84_AI_EXISTING_PROVIDER_KEYS_PROVISIONED=3')
print('RC84_AI_KEYS_ONLY_SERVER_LOCAL=True')
print('RC84_AI_BITGET_KEYS_NOT_COPIED=True')
print('RC84_AI_NO_SERVICES_RESTARTED=True')
print('RC84_AI_NO_PROVIDER_REQUESTS=True')
print('RC84_AI_RUNS_STILL_PAUSED=True')
PY
