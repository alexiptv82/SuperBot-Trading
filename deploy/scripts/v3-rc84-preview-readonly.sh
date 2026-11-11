#!/usr/bin/env bash
# RC84: separate loopback-only, authenticated UI preview for THREE prepared PAPER runs.
# Explicitly NO orders, AI/strategies, exit workers, existing service changes or production web cutover.
set -euo pipefail
umask 077

PIN="0e29a73a36f668643da4088178bacb8616a45ac0"
STAGE=/opt/superbot-v3-rc84-stage
ROOT=/opt/superbot-v3-paper-runs
UI=/opt/superbot-v3-rc84-ui-preview
HAWK="$ROOT/classic-hawk-paper20261111"
BULL="$ROOT/classic-bull-paper20261111"
BRAIN="$ROOT/brain-v3-paper20261111"
NAME=superbot-v3-rc84-paper-preview
IMAGE=superbot-v3-rc84-preview:0e29a73a
PORT=18004
MODE="--dry-run"
if (( $# > 0 )); then MODE="$1"; fi
if (( $# > 1 )) || [[ "$MODE" != --dry-run && "$MODE" != --start-readonly-preview ]]; then
  echo RC84_PREVIEW_REFUSED_MODE; exit 2
fi
die(){ echo "RC84_PREVIEW_REFUSED_$1"; exit 2; }

for cmd in docker git curl python3; do command -v "$cmd" >/dev/null || die "MISSING_TOOL"; done
[[ -d "$STAGE" && ! -L "$STAGE" ]] || die "PINNED_STAGE_MISSING"
[[ "$(git -C "$STAGE" rev-parse HEAD 2>/dev/null)" == "$PIN" ]] || die "STAGE_SHA_MISMATCH"
[[ -d "$UI" && ! -L "$UI" && -d "$UI/frontend" && -f "$UI/frontend/index.html" ]] || die "FRONTEND_MISSING"
[[ ! -e "$UI/preview-ready.json" ]] || die "PREVIEW_ALREADY_PREPARED"
[[ ! -e "$UI/data/superbot.db" ]] || die "PREVIEW_DB_ALREADY_EXISTS"
[[ ! -L "$ROOT" && -d "$ROOT" ]] || die "RUN_PARENT_INVALID"

# Verify all three new run identities and pause flags. No old data volumes allowed.
for path in "$HAWK" "$BULL" "$BRAIN"; do
  [[ -d "$path" && ! -L "$path" && -f "$path/pause.flag" && ! -L "$path/pause.flag" ]] \
    || die "MISSING_PAUSED_RUN"
done
for classic in "$HAWK" "$BULL"; do
  [[ ! -e "$classic/close_position.flag" && ! -e "$classic/reset.flag" ]] || die "PENDING_CLASSIC_COMMAND"
done
python3 - "$HAWK" "$BULL" "$BRAIN" <<'PY' || die "RUN_IDENTITY_INVALID"
import json, pathlib, sys, hashlib
a,b,c=map(pathlib.Path,sys.argv[1:])
for name,path in (("hawk",a),("bull",b)):
    m=json.loads((path/"PREPARED_PAUSED_ONLY.json").read_text())
    assert m.get("portfolio_id")==name and m.get("paper_only") is True
    assert m.get("paused") is True and m.get("initial_equity")=="1000"
marker=json.loads((c/"PREPARED_PAUSED_ONLY.json").read_text())
mandate=json.loads((c/"mandate.json").read_text())
assert marker["paper_only"] is True and marker["paused"] is True
assert mandate["approved"] is False and marker["mandate_approved"] is False
assert marker["run_id"]==mandate["run_id"]=="brain-v3-paper20261111"
assert marker["initial_equity"]=="2000"
assert hashlib.sha256((c/"runner_config.json").read_bytes()).hexdigest()==marker["config_sha256"]
PY
if docker container inspect "$NAME" >/dev/null 2>&1; then die "PREVIEW_CONTAINER_ALREADY_EXISTS"; fi
if command -v ss >/dev/null 2>&1; then
  [[ -z "$(ss -H -ltn "( sport = :$PORT )")" ]] || die "PREVIEW_PORT_ALREADY_USED"
fi
[[ -f "$STAGE/Dockerfile" && -f "$STAGE/backend/v3_api.py" ]] || die "SOURCE_INCOMPLETE"
if [[ "$MODE" == --dry-run ]]; then
  echo RC84_PREVIEW_DRY_RUN=PASS
  echo RC84_PREVIEW_ALL_THREE_PAUSED=True
  echo RC84_PREVIEW_BRAIN_MANDATE_UNAPPROVED=True
  echo RC84_PREVIEW_NO_CHANGES=True
  exit 0
fi

mkdir -m 0700 "$UI/data" 
# Build an isolated image from pinned code; never retag production superbot.
docker build --pull=false --quiet --tag "$IMAGE" --file "$STAGE/Dockerfile" "$STAGE" >/dev/null \
  || die "DOCKER_IMAGE_BUILD_FAILED"
echo RC84_PREVIEW_ISOLATED_IMAGE_BUILT=True

# The app can write only to its NEW DB and /tmp; strategy DATA volumes are READ ONLY.
# No Anthropic, DeepSeek, or Bitget private keys are supplied.
docker run --detach \
  --name "$NAME" --restart no \
  --security-opt no-new-privileges:true --cap-drop ALL \
  --read-only --tmpfs /tmp:rw,nosuid,noexec,size=64m \
  --pids-limit 128 --memory 768m \
  -p 127.0.0.1:18004:8001 \
  -v "$UI/data:/app/data" \
  -v "$UI/frontend:/app/frontend/build:ro" \
  -v "$HAWK:$HAWK:ro" \
  -v "$BULL:$BULL:ro" \
  -v "$BRAIN:$BRAIN:ro" \
  -e TRADING_MODE=paper -e DESK_MODE=paper \
  -e V3_CUTOVER_READONLY=1 \
  -e V3_ALLOW_CLASSIC_SINGLE_CLOSE=0 \
  -e V3_ALLOW_BRAIN_SINGLE_CLOSE=0 \
  -e TELEGRAM_COMMANDS_ENABLED=false \
  -e PYTHONDONTWRITEBYTECODE=1 \
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
  "$IMAGE" >/dev/null || die "CONTAINER_CREATE_FAILED"

# Never expose preview to public network; do not assume success if health fails.
healthy=0
for i in 1 2 3 4 5 6 7 8 9 10; do
  if curl --fail --silent --max-time 3 http://127.0.0.1:18004/api/health >/dev/null; then
    healthy=1; break
  fi
  sleep 3
done
[[ "$healthy" == 1 ]] || die "PREVIEW_HEALTH_FAILED"
[[ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 4 http://127.0.0.1:18004/)" == 200 ]] \
  || die "PREVIEW_UI_FAILED"
[[ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 4 http://127.0.0.1:18004/api/v3/overview)" == 401 ]] \
  || die "PREVIEW_AUTH_FAILED"
[[ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 4 -X POST -H 'content-type: application/json' -d '{}' http://127.0.0.1:18004/api/v3/brain/close)" == 423 ]] \
  || die "PREVIEW_MUTATIONS_NOT_BLOCKED"
[[ "$(docker inspect -f '{{.HostConfig.RestartPolicy.Name}}' "$NAME")" == no ]] || die "PREVIEW_RESTART_POLICY_INVALID"

python3 - "$UI/preview-ready.json" <<'PY'
import json,sys,time
from pathlib import Path
Path(sys.argv[1]).write_text(json.dumps({
  "pinned_sha":"0e29a73a36f668643da4088178bacb8616a45ac0",
  "mode":"paper","cutover_readonly":True,"api":"loopback-only:18004",
  "frontend":True,"classic_runs_paused":True,"brain_mandate_approved":False,
  "worker_started":False,"checked_utc":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
},sort_keys=True)+"\n")
PY
echo RC84_PREVIEW_AUTH_UI_API_HEALTH=PASS
echo RC84_PREVIEW_MUTATIONS_BLOCKED=True
echo RC84_PREVIEW_NEW_WALLET_MOUNTS_READ_ONLY=True
echo RC84_PREVIEW_PRODUCTION_UNCHANGED=True
echo RC84_PREVIEW_STRATEGY_WORKERS_STARTED=False
echo RC84_PREVIEW_LOOPBACK_ONLY=True
