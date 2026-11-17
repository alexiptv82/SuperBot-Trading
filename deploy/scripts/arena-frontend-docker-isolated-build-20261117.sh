#!/usr/bin/env bash
# Offline-by-default UI flags; only npm dependency download uses network.
# Builds a fresh React AI Arena preview in an isolated directory.
# NEVER modifies /opt/superbot-web/build, Nginx, Docker services or bot state.
set -Eeuo pipefail
IFS=$'\n\t'

SOURCE='/opt/superbot-arena-stage'
EXPECTED_SHA='48dc07494345fe9d973b900b67cd094cec56e7e5'
RESULTS='/opt/superbot-arena-ui-builds'
IMAGE='node:20-bookworm-slim'

msg() { printf 'ARENA_UI_BUILD_%s\n' "$*"; }
fail() { msg "REFUSED=$1"; exit 2; }

[[ "$(id -u)" -eq 0 ]] || fail 'ROOT_REQUIRED_TO_USE_DOCKER'
[[ -d "$SOURCE/.git" && ! -L "$SOURCE" ]] || fail 'SOURCE_NOT_FOUND'
[[ "$(git -C "$SOURCE" rev-parse HEAD)" == "$EXPECTED_SHA" ]] || fail 'SOURCE_SHA_MISMATCH'
[[ ! -L "$SOURCE/frontend" ]] || fail 'FRONTEND_SYMLINK'
for name in package.json package-lock.json; do
  [[ -f "$SOURCE/frontend/$name" && ! -L "$SOURCE/frontend/$name" ]] || fail "MISSING_$name"
done
for name in src public; do
  [[ -d "$SOURCE/frontend/$name" && ! -L "$SOURCE/frontend/$name" ]] || fail "MISSING_$name"
done
[[ ! -L "$RESULTS" ]] || fail 'RESULTS_SYMLINK'
if [[ ! -d "$RESULTS" ]]; then install -d -o root -g root -m 0700 "$RESULTS"; fi
[[ "$(stat -c '%u:%a' "$RESULTS")" == '0:700' ]] || fail 'RESULTS_OWNERSHIP_UNSAFE'
command -v docker >/dev/null 2>&1 || fail 'DOCKER_MISSING'
command -v python3.12 >/dev/null 2>&1 || fail 'PYTHON_MISSING'

# The lockfile is a local file in the staged checkout; it is absent on the
# inspected GitHub commit. Check it belongs to this package before using it.
python3.12 - "$SOURCE/frontend" <<'PY'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1])
pkg = json.loads((p/'package.json').read_text())
lock = json.loads((p/'package-lock.json').read_text())
root = (lock.get('packages') or {}).get('')
assert root and root.get('dependencies') == pkg.get('dependencies'), 'LOCKFILE_ROOT_MISMATCH'
assert lock.get('lockfileVersion') in (2, 3), 'LOCKFILE_VERSION_UNSUPPORTED'
print('ARENA_UI_BUILD_LOCKFILE_MATCH=TRUE', flush=True)
PY

# Do not stop any running container, do not modify Nginx/web/brain.
if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  msg 'NODE_IMAGE_PULL=STARTING'
  docker pull "$IMAGE" >/dev/null || fail 'NODE_IMAGE_PULL_FAILED'
fi
msg 'NODE_IMAGE=READY'

JOB="$(mktemp -d "$RESULTS/preview.XXXXXXXX")" || fail 'NEW_BUILD_FOLDER_FAILED'
chmod 0700 "$JOB"
cp -a "$SOURCE/frontend/src" "$SOURCE/frontend/public" \
  "$SOURCE/frontend/package.json" "$SOURCE/frontend/package-lock.json" "$JOB/"
msg "BUILD_WORKDIR=$JOB"
msg "SOURCE_SHA=$EXPECTED_SHA"
msg 'APP_PUBLIC_BUILD=UNTOUCHED'
msg 'API_PROVIDERS=DISABLED_FOR_PREVIEW'
msg 'CLOSE_AND_INFERENCE=DISABLED'

# Container gets only its isolated bind mount; no daemon socket or host secrets.
# npm downloads dependencies from npmjs; model providers are never contacted.
if ! docker run --rm \
  --name "arena-ui-build-$(basename "$JOB")" \
  --network bridge \
  --security-opt no-new-privileges --cap-drop ALL \
  --pids-limit 400 --memory 3g --cpus 2 \
  --mount "type=bind,src=$JOB,dst=/workspace" \
  --workdir /workspace \
  -e CI=true \
  -e NODE_OPTIONS=--max-old-space-size=2048 \
  -e REACT_APP_PREVIEW_READONLY=1 \
  -e REACT_APP_BRAIN_ARENA_PREVIEW=1 \
  -e REACT_APP_BRAIN_ARENA_SHADOW_API=0 \
  -e REACT_APP_ARENA_MANUAL_CLOSE=0 \
  -e REACT_APP_ARENA_EXISTING_CLOSE=0 \
  "$IMAGE" sh -ec 'npm ci --no-audit --no-fund --prefer-offline && npm run build'; then
    fail 'BUILD_FAILED_NO_DEPLOY'
fi
[[ -s "$JOB/build/index.html" ]] || fail 'BUILD_OUTPUT_MISSING'
[[ -d "$JOB/build/static" ]] || fail 'BUILD_STATIC_MISSING'
msg "BUILD_READY_DIR=$JOB/build"
msg "BUILD_INDEX_SHA256=$(sha256sum "$JOB/build/index.html" | cut -d' ' -f1)"
msg 'PUBLIC_APP_UPDATED=FALSE'
msg 'NGINX_RELOADED=FALSE'
msg 'BRAIN_SERVICES_CHANGED=FALSE'
msg 'ARENA_TRIAL_STARTED=FALSE'
msg 'RESULT=SUCCESS_ISOLATED_BUILD_ONLY'
