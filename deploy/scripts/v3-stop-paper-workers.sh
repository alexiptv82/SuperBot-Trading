#!/usr/bin/env bash
# Solo PAPER. Stop worker V3 e backup consistente sul VPS. Non tocca container app.
set -Eeuo pipefail
umask 077
fail() { echo "V3_STOP_FAILED linea=$1; controllare stato e backup; nessun riavvio automatico"; }
trap 'fail $LINENO' ERR
[ "$(hostname)" = 'vps-a06df2a7' ] || { echo 'BLOCK_WRONG_HOST'; exit 1; }
command -v docker >/dev/null
[ "$(docker inspect -f '{{.State.Running}}' superbot)" = 'true' ] || { echo 'BLOCK_DASHBOARD_OFFLINE'; exit 1; }
appmode=$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' superbot | awk -F= '$1=="DESK_MODE" {print $2; exit}')
[ "$appmode" = paper ] || { echo 'BLOCK_APP_NOT_PAPER'; exit 1; }
declare -A expected=(
  [superbot-desk-hawk]='superbot-desk'
  [superbot-desk-bull]='superbot-desk'
  [superbot-brain-free]='superbot-brain-free:sha-e0021488b47e'
  [superbot-turbo]='superbot-sidecar:sha-ed60e0705ed0'
  [superbot-ai]='superbot-aishadow:sha-53111b30b633'
  [superbot-sidecar]='superbot-sidecar:sha-ad8d0bddbbda'
  [superbot-pool]='superbot-pool'
)
workers=(superbot-desk-hawk superbot-desk-bull superbot-brain-free superbot-turbo superbot-ai superbot-sidecar superbot-pool)
for c in "${workers[@]}"; do
  image=$(docker inspect -f '{{.Config.Image}}' "$c") || { echo "BLOCK_MISSING_WORKER=$c"; exit 1; }
  [ "$image" = "${expected[$c]}" ] || { echo "BLOCK_CHANGED_WORKER=$c"; exit 1; }
done
for c in superbot-desk-hawk superbot-desk-bull superbot-brain-free; do
  mode=$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$c" | awk -F= '$1=="DESK_MODE" {print $2; exit}')
  [ "$mode" = paper ] || { echo "BLOCK_NOT_PAPER=$c"; exit 1; }
done
dirs=(superbot-desk-data superbot-brain-free superbot-brain-adaptive superbot-ai-data superbot-turbo-data superbot-sidecar-data superbot-pool-data)
for d in "${dirs[@]}"; do
  [ -d "/opt/$d" ] && [ ! -L "/opt/$d" ] || { echo "BLOCK_VOLUME_MISSING=$d"; exit 1; }
done
free_kib=$(df -Pk /opt | awk 'NR==2 {print $4}')
[ "$free_kib" -gt 4194304 ] || { echo 'BLOCK_LOW_DISK_SPACE'; exit 1; }
now=$(date -u +%Y%m%dT%H%M%SZ)
backup="/opt/superbot-v3-backups/$now"
mkdir -p -m 700 "$backup"
echo "BACKUP_TARGET=$backup"
{
  printf 'V3_VERSION=1\nSTOP_STARTED_UTC=%s\n' "$(date -u +%FT%TZ)"
  for c in "${workers[@]}"; do
    docker inspect -f '{{.Name}}|{{.Config.Image}}|{{.State.Status}}|{{.HostConfig.RestartPolicy.Name}}' "$c"
  done
} > "$backup/manifest-before.txt"
touch /opt/superbot-desk-data/hawk/pause.flag /opt/superbot-desk-data/bull/pause.flag /opt/superbot-brain-free/pause.flag
echo 'PAUSE_FLAGS=SET'
for c in "${workers[@]}"; do
  state=$(docker inspect -f '{{.State.Status}}' "$c")
  if [ "$state" = running ]; then
    docker stop --time 60 "$c" >/dev/null
  fi
  docker update --restart=no "$c" >/dev/null
  state=$(docker inspect -f '{{.State.Status}}' "$c")
  [ "$state" != running ] || { echo "BLOCK_WORKER_STILL_RUNNING=$c"; exit 1; }
  echo "WORKER_STOPPED=$c"
done
legacy=(
  superbot-brain-free-v1-20261028T124146Z
  superbot-brain-bull superbot-brain-hawk
  superbot-brain-bull-previous-20261027T133014Z
  superbot-brain-hawk-previous-20261027T133014Z
  superbot-brain-pilot
  superbot-brain-pilot-rollback-2c977c46ec78-1793026406434484798
)
for c in "${legacy[@]}"; do
  if docker inspect "$c" >/dev/null 2>&1; then
    state=$(docker inspect -f '{{.State.Status}}' "$c")
    [ "$state" != running ] || { echo "BLOCK_LEGACY_BRAIN_RUNNING=$c"; exit 1; }
    docker update --restart=no "$c" >/dev/null
  fi
done
tar -C /opt -czf "$backup/worker-data.tar.gz" "${dirs[@]}"
(cd "$backup" && sha256sum worker-data.tar.gz > SHA256SUMS && sha256sum -c SHA256SUMS)
tar -tzf "$backup/worker-data.tar.gz" >/dev/null
mkdir -p -m 700 "$backup/restore-test"
tar -xzf "$backup/worker-data.tar.gz" -C "$backup/restore-test"
for d in "${dirs[@]}"; do
  if ! diff -qr "/opt/$d" "$backup/restore-test/$d" > "$backup/diff-$d.txt" 2>&1; then
    echo "RESTORE_DIFF_FAILED=$d"; exit 1
  fi
done
echo 'BACKUP_RESTORE_DIFF=PASS'
python3 - "$backup/restore-test" <<'PY'
import sqlite3,sys
from pathlib import Path
root=Path(sys.argv[1])
for rel in ('superbot-brain-free/brain.sqlite3','superbot-pool-data/pool.db'):
    p=root/rel
    if not p.is_file():raise RuntimeError('BACKUP_DB_MISSING_'+rel)
    with sqlite3.connect('file:'+str(p)+'?mode=ro',uri=True,timeout=15) as db:
        db.execute('PRAGMA query_only=ON')
        check=db.execute('PRAGMA integrity_check').fetchone()[0]
    if check!='ok':raise RuntimeError('BACKUP_DB_BAD_'+rel)
    print('SQLITE_RESTORED_OK='+rel)
PY
[ "$(docker inspect -f '{{.State.Running}}' superbot)" = true ] || { echo 'APP_NOT_RUNNING'; exit 1; }
for c in "${workers[@]}"; do
  [ "$(docker inspect -f '{{.State.Running}}' "$c")" = false ] || { echo "WORKER_RESTARTED=$c"; exit 1; }
done
printf 'STOP_COMPLETED_UTC=%s\n' "$(date -u +%FT%TZ)" >> "$backup/manifest-before.txt"
echo 'DASHBOARD=RUNNING'
echo 'V3_ALL_WORKERS_STOPPED=YES'
echo 'V3_BACKUP_VERIFIED=YES'
echo "V3_BACKUP_PATH=$backup"
