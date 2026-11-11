#!/usr/bin/env bash
# One-time repair of ONLY the isolated RC84 preview. Production web and strategies untouched.
# Serve the frontend from an independent loopback Nginx instance so FastAPI's
# catch-all static route cannot swallow /api/v3/overview (RC84 registration order).
set -euo pipefail
umask 077
UI=/opt/superbot-v3-rc84-ui-preview
ROOT=/opt/superbot-v3-paper-runs
HAWK="$ROOT/classic-hawk-paper20261111"
BULL="$ROOT/classic-bull-paper20261111"
BRAIN="$ROOT/brain-v3-paper20261111"
NAME=superbot-v3-rc84-paper-preview
IMAGE=superbot-v3-rc84-preview:0e29a73a
STAGE=/opt/superbot-v3-rc84-stage
PIN=0e29a73a36f668643da4088178bacb8616a45ac0

MODE=--dry-run
if (( $# > 0 )); then MODE="$1"; fi
if (( $# > 1 )) || [[ "$MODE" != --dry-run && "$MODE" != --repair-preview-only ]]; then
  echo RC84_ROUTING_REFUSED_MODE; exit 2
fi
die() { echo "RC84_ROUTING_REFUSED_$1"; exit 2; }

for cmd in docker nginx curl git python3; do command -v "$cmd" >/dev/null || die "MISSING_TOOL"; done
[[ -d "$UI/frontend" && -s "$UI/frontend/index.html" ]] || die "FRONTEND_MISSING"
[[ -d "$UI/data" && -d "$BRAIN" ]] || die "PREVIEW_DATA_MISSING"
[[ ! -e "$UI/preview-ready.json" ]] || die "ALREADY_VERIFIED_PREVIEW"
[[ "$(git -C "$STAGE" rev-parse HEAD 2>/dev/null)" == "$PIN" ]] || die "SOURCE_SHA_MISMATCH"
docker image inspect "$IMAGE" >/dev/null 2>&1 || die "PREVIEW_IMAGE_MISSING"
docker container inspect "$NAME" >/dev/null 2>&1 || die "ORIGINAL_PREVIEW_MISSING"
[[ "$(docker inspect -f '{{.HostConfig.RestartPolicy.Name}}' "$NAME")" == no ]] || die "ORIGINAL_PREVIEW_RESTART_NOT_DISABLED"

for d in "$HAWK" "$BULL" "$BRAIN"; do
  [[ -d "$d" && -f "$d/pause.flag" ]] || die "RUN_NOT_PAUSED"
done
python3 - "$BRAIN" <<'PY' || die "MANDATE_NOT_PAUSED"
import json,sys
from pathlib import Path
p=Path(sys.argv[1])
m=json.loads((p/"mandate.json").read_text())
marker=json.loads((p/"PREPARED_PAUSED_ONLY.json").read_text())
assert m["approved"] is False and marker["paused"] is True
assert marker["run_id"]=="brain-v3-paper20261111"
PY
if command -v ss >/dev/null 2>&1; then
  [[ -z "$(ss -H -ltn "( sport = :18081 )")" ]] || die "STATIC_PORT_ALREADY_IN_USE"
fi

if [[ "$MODE" == --dry-run ]]; then
  echo RC84_ROUTING_DRY_RUN=PASS
  echo RC84_ROUTING_TOUCHES_PRODUCTION=False
  exit 0
fi

# Only OUR newly introduced, unverified preview container is recreated.
# No old containers, Nginx configuration, strategies or systemd units are touched.
docker rm -f "$NAME" >/dev/null || die "PREVIEW_REMOVE_FAILED"
docker run --detach \
  --name "$NAME" --restart no \
  --security-opt no-new-privileges:true --cap-drop ALL \
  --read-only --tmpfs /tmp:rw,nosuid,noexec,size=64m \
  --pids-limit 128 --memory 768m \
  -p 127.0.0.1:18004:8001 \
  -v "$UI/data:/app/data" \
  -v "$HAWK:$HAWK:ro" -v "$BULL:$BULL:ro" -v "$BRAIN:$BRAIN:ro" \
  -e TRADING_MODE=paper -e DESK_MODE=paper -e V3_CUTOVER_READONLY=1 \
  -e V3_ALLOW_CLASSIC_SINGLE_CLOSE=0 -e V3_ALLOW_BRAIN_SINGLE_CLOSE=0 \
  -e TELEGRAM_COMMANDS_ENABLED=false -e PYTHONDONTWRITEBYTECODE=1 \
  -e DB_PATH=/app/data/superbot.db \
  -e DESK_DATA_DIR="$HAWK" -e DESK_DATA_DIR_BULL="$BULL" \
  -e V3_RUN_ID=brain-v3-paper20261111 \
  -e V3_JOURNAL_PATH="$BRAIN/journal.db" \
  -e V3_BUDGET_DB_PATH="$BRAIN/budget.db" \
  -e V3_HEARTBEAT_PATH="$BRAIN/heartbeat.json" \
  -e V3_PAUSE_FLAG_PATH="$BRAIN/pause.flag" \
  -e V3_RUNNER_CONFIG_PATH="$BRAIN/runner_config.json" \
  -e V3_CLOSE_REQUEST_PATH="$BRAIN/close_request.json" \
  -e V3_CLOSE_RESULT_PATH="$BRAIN/close_result.json" \
  "$IMAGE" >/dev/null || die "BACKEND_START_FAILED"

# Public STATIC assets only: give Nginx read/execute permissions.
# The preview database remains inaccessible (UI/data is mode 0700).
chmod 0755 "$UI" "$UI/frontend"
cat > "$UI/nginx-preview.conf" <<'NGINX'
pid /opt/superbot-v3-rc84-ui-preview/nginx.pid;
error_log /opt/superbot-v3-rc84-ui-preview/nginx-error.log warn;
worker_processes 1;
events { worker_connections 128; }
http {
  access_log off;
  include /etc/nginx/mime.types;
  server {
    listen 127.0.0.1:18081;
    server_name localhost;
    root /opt/superbot-v3-rc84-ui-preview/frontend;
    index index.html;
    add_header Cache-Control "no-store";
    location /api {
      proxy_pass http://127.0.0.1:18004;
      proxy_set_header Host $host;
      proxy_set_header X-Forwarded-Proto http;
    }
    location / {
      try_files $uri $uri/ /index.html;
    }
  }
}
NGINX
chmod 0600 "$UI/nginx-preview.conf"
nginx -t -c "$UI/nginx-preview.conf" >/dev/null 2>&1 || die "NGINX_PREVIEW_INVALID"
nginx -c "$UI/nginx-preview.conf" || die "NGINX_PREVIEW_START_FAILED"

healthy=0
for i in 1 2 3 4 5 6 7 8 9 10; do
  if curl -fsS --max-time 3 http://127.0.0.1:18081/api/health >/dev/null; then
    healthy=1
    break
  fi
  sleep 3
done
[[ "$healthy" == 1 ]] || die "PREVIEW_API_HEALTH_FAILED"
[[ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:18081/)" == 200 ]] \
  || die "PREVIEW_FRONTEND_NOT_200"
[[ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:18081/api/v3/overview)" == 401 ]] \
  || die "PREVIEW_AUTH_NOT_401"
[[ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 -X POST -H 'content-type: application/json' -d '{}' http://127.0.0.1:18081/api/v3/brain/close)" == 423 ]] \
  || die "PREVIEW_MUTATION_NOT_BLOCKED"

# Confirm isolated API container mounts only expected new data volumes, all read-only.
python3 - "$NAME" "$HAWK" "$BULL" "$BRAIN" <<'PY' || die "CONTAINER_MOUNTS_INVALID"
import json,subprocess,sys
name,*sources=sys.argv[1:]
r=subprocess.run(["docker","inspect",name],capture_output=True,text=True,check=True)
cfg=json.loads(r.stdout)[0]
assert cfg["State"]["Running"] is True
assert cfg["HostConfig"]["RestartPolicy"]["Name"]=="no"
assert cfg["HostConfig"]["ReadonlyRootfs"] is True
mounts={m["Source"]:m for m in cfg["Mounts"]}
for src in sources:
    assert src in mounts and mounts[src]["RW"] is False
env=dict(e.split("=",1) for e in cfg["Config"]["Env"] if "=" in e)
assert env["TRADING_MODE"]==env["DESK_MODE"]=="paper"
assert env["V3_CUTOVER_READONLY"]=="1"
assert env["V3_ALLOW_BRAIN_SINGLE_CLOSE"]=="0"
assert not any(k.startswith(("BITGET_API_", "BITGET_SECRET_", "DEEPSEEK_API_", "ANTHROPIC_API_"))
               for k in env)
PY

python3 - "$UI/preview-ready.json" <<'PY'
import json,sys,time
from pathlib import Path
Path(sys.argv[1]).write_text(json.dumps({
 "pinned_sha":"0e29a73a36f668643da4088178bacb8616a45ac0",
 "mode":"paper", "backend_port":"127.0.0.1:18004",
 "frontend_port":"127.0.0.1:18081", "isolated":True,
 "authentication_checked":True, "trading_mutations_blocked":True,
 "wallet_mounts_readonly":True,"strategy_workers_started":False,
 "checked_utc":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
},sort_keys=True)+"\n")
PY
echo RC84_PREVIEW_AUTH_UI_API_HEALTH=PASS
echo RC84_PREVIEW_THREE_NEW_PAPER_RUNS_READONLY=True
echo RC84_PREVIEW_MUTATIONS_BLOCKED=True
echo RC84_PREVIEW_LOOPBACK_ONLY=True
echo RC84_PREVIEW_PRODUCTION_UNCHANGED=True
echo RC84_PREVIEW_STRATEGY_WORKERS_STARTED=False
