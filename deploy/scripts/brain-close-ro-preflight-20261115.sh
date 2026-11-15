#!/usr/bin/env bash
# SuperBot V3 PAPER: verifiche di sola lettura prima del fix web-only.
# Non modifica file, immagini, container, unit systemd o run.
set -euo pipefail
stage=/opt/superbot-v3-rc84-stage
say() { printf 'BRAIN_CLOSE_PREFLIGHT %s\n' "$*"; }

if [[ "$(id -u)" -ne 0 ]]; then say 'ERRORE=ESEGUIRE_CON_SUDO'; exit 2; fi
if ! git -C "$stage" rev-parse --is-inside-work-tree >/dev/null 2>&1; then say 'ERRORE=STAGE_GIT_ASSENTE'; exit 2; fi

say "utc=$(date -u +%FT%TZ)"
say "stage_sha=$(git -C "$stage" rev-parse HEAD)"
say 'STAGE_MODIFICHE_LOCALI_INIZIO'
git -C "$stage" status --porcelain=v1 --untracked-files=all | sed 's/^/BRAIN_CLOSE_PREFLIGHT changed: /'
say 'STAGE_MODIFICHE_LOCALI_FINE'
if git -C "$stage" diff --quiet -- backend/v3/runner/exit_service.py; then
  say 'stage_target_diff=nessuna_modifica_non_staged'
else
  say 'stage_target_diff=ATTENZIONE_FILE_MODIFICATO'
fi
if git -C "$stage" diff --cached --quiet -- backend/v3/runner/exit_service.py; then
  say 'stage_target_index=nessuna_modifica_staged'
else
  say 'stage_target_index=ATTENZIONE_FILE_MODIFICATO'
fi

for u in superbot-v3-paper-brain-runner superbot-v3-paper-brain-exit superbot-v3-paper-single-close-bridge; do
  say "unit=$u state=$(systemctl is-active "$u" 2>/dev/null || true) pid=$(systemctl show "$u" -p MainPID --value 2>/dev/null || true)"
done
if ! docker inspect superbot >/dev/null 2>&1; then say 'ERRORE=CONTAINER_WEB_ASSENTE'; exit 2; fi
say "web_image_tag=$(docker inspect superbot --format '{{.Config.Image}}')"
say "web_image_id=$(docker inspect superbot --format '{{.Image}}')"
say "web_running=$(docker inspect superbot --format '{{.State.Running}}')"
say "web_restart_policy=$(docker inspect superbot --format '{{.HostConfig.RestartPolicy.Name}}')"
say "web_code_mount=$(docker inspect superbot --format '{{range .Mounts}}{{if eq .Destination "/app/backend/v3/runner/exit_service.py"}}{{.Source}} rw={{.RW}}{{end}}{{end}}')"
say "web_brain_run_mount=$(docker inspect superbot --format '{{range .Mounts}}{{if eq .Source "/opt/superbot-v3-paper-runs/brain-v3-paper20261111"}}{{.Destination}} rw={{.RW}}{{end}}{{end}}')"
status=$(curl --silent --show-error --max-time 5 --output /dev/null --write-out '%{http_code}' http://127.0.0.1:8002/api/health || true)
say "web_http_health=$status"

docker exec -i -e PYTHONDONTWRITEBYTECODE=1 superbot python3 - <<'PY'
import os
from pathlib import Path
from backend.v3.runner import exit_service as es
from backend import v3_api as api

p = Path(es.__file__).resolve()
raw = p.read_text()
old = 'flags = os.O_RDWR | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)'
new = 'flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)'
print('BRAIN_CLOSE_PREFLIGHT web_module_path=' + str(p))
print('BRAIN_CLOSE_PREFLIGHT web_old_marker_count=' + str(raw.count(old)))
print('BRAIN_CLOSE_PREFLIGHT web_new_marker_count=' + str(raw.count(new)))
paths = api.V3Paths.from_env('/nonexistent', '/nonexistent')
print('BRAIN_CLOSE_PREFLIGHT web_close_allowed=' + str(api._brain_single_close_ready(paths, int(__import__('time').time() * 1000))))
print('BRAIN_CLOSE_PREFLIGHT web_paper=' + str(os.environ.get('DESK_MODE') == 'paper' and os.environ.get('TRADING_MODE') == 'paper'))
PY
say 'FINE_READ_ONLY_NO_DEPLOY'
