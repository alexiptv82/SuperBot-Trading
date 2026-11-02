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
        try:
            with sqlite3.connect(f'file:{db}?mode=ro',uri=True,timeout=2) as cn:
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
