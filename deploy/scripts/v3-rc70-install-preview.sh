#!/usr/bin/env bash
# RC70: install an isolated loopback-only PAPER UI preview. No production service changes.
set -euo pipefail
umask 077
STAGE=/opt/superbot-v3-rc70-stage
SNAP=/opt/superbot-backups/rc69-paper-legacy-20261107T110255Z-142218
BRAIN=/opt/superbot-v3-paper-runs/brain-v3-rc20261106
NAME=superbot-v3-rc70-preview
if [[ "${1:-}" != --prepare-stage ]]; then echo RC70_REFUSED_NO_EXPLICIT_STAGE; exit 2; fi
test -d "$STAGE" && test ! -L "$STAGE" || { echo RC70_STAGE_DIR_INVALID; exit 2; }
test -d "$SNAP" && test -f "$SNAP/MANIFEST.json" || { echo RC70_SNAPSHOT_NOT_VALID; exit 2; }
test -f "$STAGE/Dockerfile" && test -f "$STAGE/frontend/build/index.html" || { echo RC70_SOURCE_BUILD_MISSING; exit 2; }
test ! -f "$STAGE/preview-installed.flag" || { echo RC70_ALREADY_STAGED; exit 2; }
test ! -e "$STAGE/nginx.pid" || { echo RC70_NGINX_PID_ALREADY_EXISTS; exit 2; }
test ! -e "$STAGE/data/superbot.db" || { echo RC70_STAGE_DB_ALREADY_EXISTS; exit 2; }
test -d "$BRAIN" && test -f "$BRAIN/runner_config.json" && test -f "$BRAIN/pause.flag" || { echo RC70_BRAIN_NOT_PREPARED_PAUSED; exit 2; }
for n in hawk bull; do
  d=/opt/superbot-desk-data/$n
  test -f "$d/pause.flag" || { echo RC70_LEGACY_NOT_PAUSED; exit 2; }
  test "$(docker inspect -f '{{.State.Running}}' superbot-desk-"$n")" = false || { echo RC70_LEGACY_RUNNING; exit 2; }
  test "$(docker inspect -f '{{.HostConfig.RestartPolicy.Name}}' superbot-desk-"$n")" = no || { echo RC70_LEGACY_RESTART_ENABLED; exit 2; }
  for f in state_v2.json trade_history.jsonl learning_log.jsonl lessons.md; do
    test "$(sha256sum "$d/$f" | cut -d' ' -f1)" = "$(sha256sum "$SNAP/$n/$f" | cut -d' ' -f1)" || { echo RC70_SNAPSHOT_STALE; exit 2; }
  done
done
test "$(docker ps --format '{{.Names}}' --filter name="^$NAME$" | wc -l)" = 0 || { echo RC70_PREVIEW_ALREADY_RUNNING; exit 2; }
mkdir -p "$STAGE/data" "$STAGE/brain"
chmod 700 "$STAGE/data" "$STAGE/brain"
cp -a "$BRAIN/." "$STAGE/brain/"
test -f "$STAGE/brain/pause.flag" || { echo RC70_BRAIN_PAUSE_MISSING; exit 2; }
# Build only a separate image; no changes to the existing superbot image or container.
TAG=superbot-v3-rc70-preview:local
if ! docker build --pull=false --quiet -t "$TAG" "$STAGE" > "$STAGE/docker-build.log" 2>&1; then
  echo RC70_IMAGE_BUILD_FAILED
  exit 2
fi
echo RC70_IMAGE_BUILT=True
docker run -d \
  --name "$NAME" --restart no \
  --security-opt no-new-privileges:true --cap-drop ALL \
  --pids-limit 128 --memory 900m \
  -p 127.0.0.1:18003:8001 \
  -v "$STAGE/data:/app/data" \
  -v "$SNAP/hawk:/opt/superbot-desk-data/hawk:ro" \
  -v "$SNAP/bull:/opt/superbot-desk-data/bull:ro" \
  -v "$STAGE/brain:/opt/superbot-v3-paper-runs/brain-v3-rc20261106" \
  -e DB_PATH=/app/data/superbot.db \
  -e TRADING_MODE=paper -e DESK_MODE=paper -e TELEGRAM_COMMANDS_ENABLED=false \
  -e PYTHONDONTWRITEBYTECODE=1 -e DESK_DATA_DIR=/opt/superbot-desk-data/hawk \
  -e DESK_DATA_DIR_BULL=/opt/superbot-desk-data/bull \
  -e V3_RUN_ID=brain-rc-2000-20261106 \
  -e V3_JOURNAL_PATH=/opt/superbot-v3-paper-runs/brain-v3-rc20261106/journal.db \
  -e V3_RUNNER_CONFIG_PATH=/opt/superbot-v3-paper-runs/brain-v3-rc20261106/runner_config.json \
  -e V3_PAUSE_FLAG_PATH=/opt/superbot-v3-paper-runs/brain-v3-rc20261106/pause.flag \
  -e V3_HEARTBEAT_PATH=/opt/superbot-v3-paper-runs/brain-v3-rc20261106/heartbeat.json \
  -e V3_CLOSE_REQUEST_PATH=/opt/superbot-v3-paper-runs/brain-v3-rc20261106/manual_close_request.json \
  -e V3_CLOSE_RESULT_PATH=/opt/superbot-v3-paper-runs/brain-v3-rc20261106/manual_close_result.json \
  "$TAG" >/dev/null
echo RC70_PREVIEW_BACKEND_CONTAINER_CREATED=True
# Independently hosted Nginx instance: listens ONLY on 127.0.0.1:18080.
cat > "$STAGE/nginx-preview.conf" <<'CONF'
pid /opt/superbot-v3-rc70-stage/nginx.pid;
error_log /opt/superbot-v3-rc70-stage/nginx-error.log warn;
worker_processes 1;
events { worker_connections 256; }
http {
  access_log off;
  include /etc/nginx/mime.types;
  server {
    listen 127.0.0.1:18080;
    server_name localhost;
    root /opt/superbot-v3-rc70-stage/frontend/build;
    index index.html;
    add_header Cache-Control "no-store";
    location / { try_files $uri $uri/ /index.html; }
    location /api {
      proxy_pass http://127.0.0.1:18003;
      proxy_set_header Host $host;
      proxy_set_header X-Forwarded-Proto http;
    }
  }
}
CONF
nginx -t -c "$STAGE/nginx-preview.conf" >/dev/null 2>&1 || { echo RC70_PREVIEW_NGINX_INVALID; exit 2; }
nginx -c "$STAGE/nginx-preview.conf"
echo RC70_PREVIEW_STATIC_NGINX_CREATED=True
ready=0
for i in 1 2 3 4 5 6 7 8 9 10; do
  if curl --fail --silent --max-time 2 http://127.0.0.1:18003/api/health >/dev/null; then ready=1; break; fi
  sleep 3
done
test "$ready" = 1 || { echo RC70_PREVIEW_HEALTH_FAILED; exit 2; }
HTTP=$(curl -s -o /dev/null -w '%{http_code}' --max-time 4 http://127.0.0.1:18080/api/v3/overview)
test "$HTTP" = 401 || { echo "RC70_UNAUTH_EXPECTED_401_GOT=$HTTP"; exit 2; }
test "$(curl -s -o /dev/null -w '%{http_code}' --max-time 4 http://127.0.0.1:18080/)" = 200 || { echo RC70_PREVIEW_UI_FAILED; exit 2; }
for n in hawk bull; do
  test "$(docker inspect -f '{{.State.Running}}' superbot-desk-"$n")" = false || { echo RC70_LEGACY_CHANGED_ABORT; exit 2; }
done
test "$(curl -s -o /dev/null -w '%{http_code}' --max-time 4 http://127.0.0.1:8002/api/health)" = 200 || { echo RC70_PRODUCTION_WEB_FAILED; exit 2; }
echo "RC70_STAGE_CREATED_UTC=$(date -u +%FT%TZ)" > "$STAGE/preview-installed.flag"
echo RC70_PREVIEW_LOOPBACK_ONLY=True
echo RC70_PREVIEW_AUTH_ENFORCED=True
echo RC70_PRODUCTION_APP_STILL_HEALTHY=True
echo RC70_HISTORIC_WORKERS_UNCHANGED=True
echo RC70_BRAIN_PAUSED_COPY_ONLY=True
echo RC70_NO_TRADES_CLOSED=True
echo RC70_NO_PRODUCTION_DEPLOY=True
