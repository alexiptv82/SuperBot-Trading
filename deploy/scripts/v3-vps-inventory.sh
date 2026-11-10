#!/usr/bin/env bash
# SuperBot V3: diagnostica esclusivamente in lettura. Non ferma, non avvia e non modifica servizi o dati.
set -euo pipefail
printf 'V3_AUDIT=READ_ONLY\n'
printf 'UTC=%s\n' "$(date -u +%FT%TZ)"
printf 'HOST=%s\n' "$(hostname)"
command -v docker >/dev/null || { echo 'DOCKER=UNAVAILABLE'; exit 2; }
printf '\n=== CONTAINER CORRELATI ===\n'
docker ps -a --format '{{.Names}} | {{.Status}}' | grep -Ei 'superbot|brain|shadow|hawk|bull|pool|deepseek' || true
printf '\n=== CONTAINER CLASSICI (MODALITA) ===\n'
for c in superbot-desk-hawk superbot-desk-bull; do
  if docker inspect "$c" >/dev/null 2>&1; then
    status="$(docker inspect -f '{{.State.Status}}' "$c")"
    mode="$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$c" | awk -F= '$1=="DESK_MODE" {print $2; exit}')"
    printf '%s status=%s desk_mode=%s\n' "$c" "$status" "${mode:-UNSET}"
  else
    printf '%s NOT_FOUND\n' "$c"
  fi
done
printf '\n=== STORICI E POSIZIONI (SOLO CONTEGGI) ===\n'
python3 - <<'PY'
import json, sqlite3
from pathlib import Path
for name in ('hawk','bull'):
    root=Path('/opt/superbot-desk-data')/name
    print(name.upper(), 'dir=', root.is_dir(), 'pause=',(root/'pause.flag').is_file())
    p=root/'state_v2.json'
    if p.is_file():
        try:
            state=json.loads(p.read_text())
            positions=(state.get('main') or {}).get('positions') or {}
            print(name.upper(),'open_count=',len(positions),'run_no=',state.get('run_no','unknown'))
        except Exception as ex: print(name.upper(),'state_read_error=',type(ex).__name__)
    hist=root/'trade_history.jsonl'
    print(name.upper(),'trade_history_present=',hist.is_file(),'learning_log_present=',(root/'learning_log.jsonl').is_file(),'lessons_present=',(root/'lessons.md').is_file())
for name,root in [('BRAIN_FREE',Path('/opt/superbot-brain-free')),('BRAIN_LEGACY',Path('/opt/superbot-desk-data/brain')),('BRAIN_ADAPTIVE',Path('/opt/superbot-brain-adaptive')),('POOL',Path('/opt/superbot-pool-data'))]:
    print(name,'dir=',root.is_dir(),'pause=',(root/'pause.flag').is_file())
    db=root/'brain.sqlite3'
    if db.is_file():
        # SQLite immutable=1 evita creazione/modifica di file -shm/-wal durante la diagnostica.
        # Se esiste un WAL non checkpointato, lo stato letto puo' essere vecchio: non e' certificazione runtime.
        try:
            with sqlite3.connect(f'file:{db}?mode=ro&immutable=1',uri=True,timeout=2) as cn:
                cn.execute('PRAGMA query_only=ON')
                row=cn.execute('SELECT body FROM state WHERE id=1').fetchone()
                state=json.loads(row[0]) if row else {}
                print(name,'mode=',state.get('mode'),'paused=',state.get('paused'),'open_count=',len(state.get('positions') or {}))
        except Exception as ex: print(name,'sqlite_read_error=',type(ex).__name__)
PY
printf '\n=== SERVIZI SYSTEMD CORRELATI (NOMI E STATI) ===\n'
if command -v systemctl >/dev/null; then
  systemctl list-units --type=service --all --no-pager --no-legend 2>/dev/null | grep -Ei 'superbot|brain|shadow|deepseek' | cut -c1-175 || true
fi
printf '\nV3_AUDIT_COMPLETED=YES\n'

printf '\n=== RUOLO DEI WORKER ATTIVI (METADATI, SENZA SEGRETI) ===\n'
python3 - <<'PY'
import json,subprocess
names=['superbot','superbot-desk-hawk','superbot-desk-bull','superbot-brain-free','superbot-turbo','superbot-ai','superbot-sidecar','superbot-pool']
for name in names:
    r=subprocess.run(['docker','inspect',name],capture_output=True,text=True)
    if r.returncode:continue
    d=json.loads(r.stdout)[0]
    cfg=d.get('Config') or {}
    mode=next((v.split('=',1)[1] for v in cfg.get('Env') or [] if v.startswith('DESK_MODE=')), 'UNSET')
    mounts=[]
    for m in d.get('Mounts') or []:
        s=m.get('Source','')
        if s.startswith('/opt/superbot'): mounts.append(s)
    cmd=cfg.get('Cmd') or []
    entry=cfg.get('Entrypoint') or []
    # Non stampare argomenti di comando: potrebbero contenere segreti.
    print(name, 'state=',d.get('State',{}).get('Status'),
          'image=',str(cfg.get('Image',''))[:90],
          'entry_exe=',str(entry[0] if entry else '')[:60],
          'cmd_exe=',str(cmd[0] if cmd else '')[:60],
          'mode=',mode,
          'restart=',(d.get('HostConfig') or {}).get('RestartPolicy',{}).get('Name','?'),
          'data_mounts=',','.join(mounts)[:300])
PY
printf '\n=== BACKUP_PREFLIGHT (SOLTANTO DIMENSIONI) ===\n'
for d in /opt/superbot-desk-data /opt/superbot-brain-free /opt/superbot-brain-adaptive /opt/superbot-pool-data; do
  if [ -d "$d" ]; then du -sh "$d" 2>/dev/null || true; fi
done
df -h /opt | tail -1


printf '\n=== PREFLIGHT PAPER V3 MINIMO ===\n'
# Esclusivamente letture di metadati/JSON allowlisted e checksum; mai chiavi, comandi di trading o scritture.
python3 -I - <<'PY'
import hashlib, json, os, re, subprocess, time
from pathlib import Path
ROOT=Path('/opt/superbot-v3-paper-runs/brain-v3-rc20261106')
BACK=Path('/opt/superbot-backups')
DATA=Path('/opt/superbot-desk-data')
NOW=time.time()

def out(k,v):
    print('PAPER_PREFLIGHT_'+k+'='+str(v).replace('\n','_')[:100],flush=True)

def allowed_json(path, limit=131072):
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size>limit:
            return None
        with path.open('rb') as f: obj=json.load(f)
        return obj if isinstance(obj,dict) else None
    except (OSError,ValueError,UnicodeError,TypeError):
        return None

def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda:f.read(1<<20),b''):
            h.update(block)
    return h.hexdigest()

def inspect(name):
    try:
        p=subprocess.run(['docker','inspect',name],capture_output=True,text=True,timeout=10)
        if p.returncode: return None
        return json.loads(p.stdout)[0]
    except (OSError,ValueError,IndexError,subprocess.SubprocessError):
        return None

out('RUN_DIR_PRESENT',ROOT.is_dir() and not ROOT.is_symlink())
for n in ('runner_config.json','mandate.json','PREPARED_PAUSED_ONLY.json',
          'journal.db','budget.db','pause.flag','heartbeat.json','exit_heartbeat.json'):
    p=ROOT/n
    out('RUN_FILE_'+n.upper().replace('.','_'), p.is_file() and not p.is_symlink())
conf=allowed_json(ROOT/'runner_config.json')
man=allowed_json(ROOT/'mandate.json')
marker=allowed_json(ROOT/'PREPARED_PAUSED_ONLY.json')
out('RUN_EQUITY_2000',bool(conf and str(conf.get('initial_equity'))=='2000'))
risk=conf.get('risk_policy') if conf else None
out('RUN_FLOOR_450',bool(isinstance(risk,dict) and str(risk.get('minimum_equity'))=='450'))
out('RUN_LEVERAGE_20_50',bool(isinstance(risk,dict) and risk.get('min_leverage')==20 and risk.get('max_leverage')==50))
out('RUN_LEVERAGE_MIN_VALUE',risk.get('min_leverage') if isinstance(risk,dict) and type(risk.get('min_leverage')) is int else 'UNSET')
out('RUN_LEVERAGE_MAX_VALUE',risk.get('max_leverage') if isinstance(risk,dict) and type(risk.get('max_leverage')) is int else 'UNSET')
out('MARKER_PAPER_PAUSED',bool(marker and marker.get('paper_only') is True and marker.get('paused') is True))
out('MANDATE_APPROVED',man.get('approved') if isinstance(man,dict) and type(man.get('approved')) is bool else 'UNKNOWN')
out('MARKER_MANDATE_UNAPPROVED',bool(marker and marker.get('mandate_approved') is False))
out('MARKER_CONFIG_SHA_MATCH',bool(marker and conf and isinstance(marker.get('config_sha256'),str) and
                               marker['config_sha256']==digest(ROOT/'runner_config.json')))
out('RUN_IDS_CONSISTENT',bool(man and marker and man.get('run_id')==marker.get('run_id') and marker.get('portfolio_id')=='brain'))
for db in ('journal.db','budget.db'):
    p=ROOT/db
    try:
        with p.open('rb') as f: sqlite_header=f.read(16)==b'SQLite format 3\x00'
        out(db.upper().replace('.','_')+'_SQLITE_HEADER',sqlite_header)
    except OSError:
        out(db.upper().replace('.','_')+'_SQLITE_HEADER','UNAVAILABLE')
for n in ('heartbeat.json','exit_heartbeat.json'):
    h=allowed_json(ROOT/n,16384)
    ts=h.get('ts_ms') if h else None
    if type(ts) in (int,float):
        age=(NOW*1000-ts)/1000
        out(n.upper().replace('.','_')+'_FRESH',0<=age<=120)
    else:
        out(n.upper().replace('.','_')+'_FRESH','NO_HEARTBEAT')
    if n=='heartbeat.json':
        out('RUNNER_BEAT_STATE', h.get('state') if h and h.get('state') in ('running','paused','halted') else 'UNKNOWN')
        out('RUNNER_BEAT_EXIT_MODE',h.get('exit_mode') if h and h.get('exit_mode') in ('sidecar','legacy','off') else 'UNKNOWN')

app=inspect('superbot')
if app:
    config=app.get('Config') or {}
    env=dict(e.split('=',1) for e in config.get('Env') or [] if '=' in e)
    out('APP_TRADING_MODE_PAPER',env.get('TRADING_MODE')=='paper')
    out('APP_DESK_MODE_PAPER',env.get('DESK_MODE')=='paper')
    out('APP_READONLY_CUTOVER',env.get('V3_CUTOVER_READONLY')=='1')
    out('APP_BRAIN_RUN_CONFIGURED',bool(env.get('V3_RUN_ID') and env.get('V3_JOURNAL_PATH') and env.get('V3_RUNNER_CONFIG_PATH')))
    out('APP_BRAIN_CLOSE_OPT_IN',env.get('V3_ALLOW_BRAIN_SINGLE_CLOSE')=='1')
    mounts=[m.get('Source','') for m in app.get('Mounts') or []]
    out('APP_MOUNTS_BRAIN_RUN',str(ROOT) in mounts)
else:
    out('APP_INSPECT','UNAVAILABLE')

try:
    units=subprocess.run(['systemctl','list-units','--all','--type=service','--no-legend','--plain','--no-pager'],
                         capture_output=True,text=True,timeout=10)
    if units.returncode:
        out('BRAIN_UNITS','UNKNOWN')
    else:
        matches=[]
        for line in units.stdout.splitlines():
            col=line.split()
            if col and ('brain' in col[0].lower() or 'superbot-v3' in col[0].lower()):
                matches.append(col[0]+'='+('/'.join(col[2:4]) if len(col)>3 else 'unknown'))
        out('RELATED_UNITS_COUNT',len(matches))
        for i,v in enumerate(matches[:16]): out('UNIT_'+str(i+1),v)
except (OSError,subprocess.SubprocessError):
    out('BRAIN_UNITS','UNKNOWN')

# Verifica archivio RC77 senza scrivere: tutti gli hash dei file elencati devono
# coincidere sia con i file originali sia con la copia, su entrambe le cartelle.
def verify_snapshot(folder):
    if folder.is_symlink() or not folder.is_dir():
        return False
    manifest=allowed_json(folder/'MANIFEST.json',4000000)
    if not manifest or manifest.get('schema')!='rc77-paper-local-snapshot-v1' or manifest.get('restore_rehearsal')!='PASS':
        return False
    if manifest.get('source_data_unchanged') is not True:
        return False
    portfolios=manifest.get('portfolios')
    if not isinstance(portfolios,dict) or set(portfolios)!= {'hawk','bull'}:
        return False
    essentials={'state_v2.json','trade_history.jsonl','learning_log.jsonl','lessons.md'}
    for name in ('hawk','bull'):
        entry=portfolios[name]
        if not isinstance(entry,dict) or entry.get('open_positions')!=0:
            return False
        hashes=entry.get('hashes')
        if not isinstance(hashes,dict) or len(hashes)>100000 or not essentials.issubset(hashes):
            return False
        if entry.get('files') != len(hashes):
            return False
        for rel,expect in hashes.items():
            if type(rel) is not str or len(rel)>400 or not re.fullmatch(r'[0-9a-f]{64}',str(expect)):
                return False
            parts=Path(rel)
            if parts.is_absolute() or '..' in parts.parts or not parts.parts:
                return False
            original=DATA/name/parts
            duplicate=folder/name/parts
            if any(x.is_symlink() or not x.is_file() for x in (original,duplicate)):
                return False
            if digest(original)!=expect or digest(duplicate)!=expect:
                return False
    return True

try:
    latest=sorted(BACK.glob('rc77-paper-legacy-*'),reverse=True)[:5] if BACK.is_dir() and not BACK.is_symlink() else []
    checks=[verify_snapshot(s) for s in latest]
    out('CLASSIC_RC77_SNAPSHOT_EXACT_MATCH',any(checks))
    out('CLASSIC_RC77_TESTED_CANDIDATES',len(latest))
    out('CLASSIC_RC77_PAST_RESTORE_RECORDED',any(checks))
except (OSError,TypeError,ValueError):
    out('CLASSIC_RC77_SNAPSHOT_EXACT_MATCH','UNKNOWN')
out('NO_FILES_WRITTEN_BY_PREFLIGHT',True)
print('PAPER_PREFLIGHT_READ_ONLY_COMPLETE=YES')
PY
