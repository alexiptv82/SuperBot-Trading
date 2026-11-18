#!/usr/bin/env bash
# AI Arena web UI (3 giorni, lettura /api/v3/arena) — BUILD + TEST only. NEVER deploys.
# Uso: arena-web-ui-readonly-preflight-20261118.sh --sha <40hex> [--branch <ramo>]
set -Eeuo pipefail
IFS=$'\n\t'

REPO='https://github.com/alexiptv82/SuperBot-Trading.git'
BRANCH='work/arena-web-readonly-cutover-20261118'
PIN=''
while [[ $# -gt 0 ]]; do
  case "$1" in
    --sha) PIN="${2:-}"; shift 2 ;;
    --branch) BRANCH="${2:-}"; shift 2 ;;
    *) printf 'ARENA_WEBUI_PREFLIGHT_REFUSED=UNKNOWN_ARGUMENT\n'; exit 2 ;;
  esac
done
BASE="${ARENA_WEBUI_BUILDS:-/opt/superbot-arena-ui-builds}"
SEED="$BASE/preview.m9igvUqn"
LOCK_SHA='e22e24c21bb4d9c0d872356654c8cc98f330b1dce3774afb18738bf43a2fc48a'
IMAGE='node:20-bookworm-slim'
PUBLIC="${ARENA_WEBUI_PUBLIC:-/opt/superbot-web/build}"

out(){ printf 'ARENA_WEBUI_PREFLIGHT_%s\n' "$*"; }
refuse(){ out "REFUSED=$1"; exit 2; }

[[ "$PIN" =~ ^[0-9a-f]{40}$ ]] || refuse SHA_PIN_REQUIRED_40_HEX
[[ "$BRANCH" =~ ^[A-Za-z0-9._/-]+$ && "$BRANCH" != *..* ]] || refuse BRANCH_INVALID
[[ "${ARENA_WEBUI_TEST_MODE:-0}" == 1 || "$(id -u)" -eq 0 ]] || refuse ROOT_REQUIRED
for bin in docker git sha256sum grep; do
  command -v "$bin" >/dev/null 2>&1 || refuse "MISSING_TOOL_$bin"
done
[[ -d "$BASE" && ! -L "$BASE" ]] || refuse BASE_MISSING
[[ "${ARENA_WEBUI_TEST_MODE:-0}" == 1 || "$(stat -c '%u:%a' "$BASE")" == '0:700' ]] || refuse BASE_UNSAFE
[[ -f "$SEED/package-lock.json" && -d "$SEED/node_modules" ]] || refuse SEED_MISSING
[[ "$(sha256sum "$SEED/package-lock.json" | cut -d' ' -f1)" == "$LOCK_SHA" ]] || refuse LOCK_SHA_UNEXPECTED
[[ -f "$PUBLIC/index.html" && ! -L "$PUBLIC" ]] || refuse PUBLIC_BUILD_INVALID
docker image inspect "$IMAGE" >/dev/null 2>&1 || refuse NODE_IMAGE_NOT_LOCAL

PUBLIC_BEFORE="$(sha256sum "$PUBLIC/index.html" | cut -d' ' -f1)"
out "PUBLIC_INDEX_SHA256_BEFORE=$PUBLIC_BEFORE"

DIR="$(mktemp -d "$BASE/webui-preflight.XXXXXXXX")" || refuse WORKSPACE_FAILED
chmod 0700 "$DIR"
out "WORKSPACE=$DIR"
GIT_TERMINAL_PROMPT=0 git clone --quiet --no-tags --single-branch \
  --depth 60 --branch "$BRANCH" "$REPO" "$DIR/source" || refuse CLONE_FAILED
git -C "$DIR/source" cat-file -e "$PIN^{commit}" 2>/dev/null || refuse PIN_NOT_FETCHED
git -C "$DIR/source" checkout --quiet --detach "$PIN" || refuse CHECKOUT_FAILED
[[ "$(git -C "$DIR/source" rev-parse HEAD)" == "$PIN" ]] || refuse SOURCE_COMMIT_MISMATCH

python3 - "$DIR/source/frontend/package.json" "$SEED/package.json" <<'PY' || refuse DEPENDENCIES_OR_SCRIPTS_CHANGED
import json, pathlib, sys
source = json.loads(pathlib.Path(sys.argv[1]).read_text())
installed = json.loads(pathlib.Path(sys.argv[2]).read_text())
assert source['dependencies'] == installed['dependencies']
assert source['scripts'] == installed['scripts']
assert installed.get('devDependencies') == {'ajv': '8.17.1'}
PY
out 'DEPENDENCIES_MATCH=TRUE'

WORK="$DIR/workspace"
mkdir -m 0700 "$WORK"
cp -a "$DIR/source/frontend/src" "$DIR/source/frontend/public" "$WORK/"
cp -a "$SEED/package.json" "$SEED/package-lock.json" "$SEED/node_modules" "$WORK/"
[[ -x "$WORK/node_modules/.bin/react-scripts" ]] || refuse REACT_SCRIPTS_UNAVAILABLE

out 'TESTS_AND_BUILD_START=TRUE'
# Same-origin API; Arena read API ON; every close control OFF; Arena tab reachable (PREVIEW=1).
docker run --rm --network none --security-opt no-new-privileges --cap-drop ALL \
  --pids-limit 400 --memory 3g --cpus 2 \
  --mount "type=bind,src=$WORK,dst=/workspace" --workdir /workspace \
  -e CI=true -e NODE_OPTIONS=--max-old-space-size=2048 \
  -e REACT_APP_BACKEND_URL='' -e REACT_APP_API_URL='' \
  -e REACT_APP_BRAIN_ARENA_PREVIEW=1 -e REACT_APP_PREVIEW_READONLY=0 \
  -e REACT_APP_BRAIN_ARENA_SHADOW_API=1 \
  -e REACT_APP_ARENA_MANUAL_CLOSE=0 -e REACT_APP_ARENA_EXISTING_CLOSE=0 \
  "$IMAGE" sh -ec './node_modules/.bin/react-scripts test --watchAll=false --runInBand && npm run build' \
  || refuse TEST_OR_BUILD_FAILED_NO_DEPLOY

JS="$WORK/build/static/js"
[[ -s "$WORK/build/index.html" && -d "$JS" ]] || refuse BUILD_MISSING
has(){ grep -RlqF -- "$1" "$JS" --include='*.js'; }
if has 'http://51.91.109.45:8002'; then refuse BUNDLE_HAS_OLD_HTTP_FALLBACK; fi
has '/api/v3/arena' || refuse BUNDLE_WITHOUT_ARENA_READ_API
has '3 giorni' || refuse BUNDLE_WITHOUT_3_DAYS_TEXT
if has '14 giorni'; then refuse BUNDLE_STILL_SAYS_14_DAYS; fi
has '/api/auth/login' || refuse AUTH_LOGIN_PATH_MISSING
has '/api/auth/webauthn/status' || refuse WEBAUTHN_PATH_MISSING

PUBLIC_AFTER="$(sha256sum "$PUBLIC/index.html" | cut -d' ' -f1)"
[[ "$PUBLIC_AFTER" == "$PUBLIC_BEFORE" ]] || refuse PUBLIC_CHANGED_DURING_PREFLIGHT

out "CANDIDATE_BUILD=$WORK/build"
out "SOURCE_PIN=$PIN"
out "INDEX_SHA256=$(sha256sum "$WORK/build/index.html" | cut -d' ' -f1)"
out "CURRENT_PUBLIC_INDEX_SHA256=$PUBLIC_AFTER"
out 'ARENA_READ_API_IN_BUNDLE=TRUE'
out 'MANUAL_CLOSE_UI_FLAG=0'
out 'NO_OLD_HTTP_FALLBACK=TRUE'
out 'PUBLIC_APP_UPDATED=FALSE'
out 'BRAIN_SERVICES_CHANGED=FALSE'
out 'RESULT=SUCCESS_WEBUI_PREFLIGHT_ONLY'
