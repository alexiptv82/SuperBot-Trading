#!/usr/bin/env bash
# AI Arena AUTH HOTFIX preflight. Build and validate only; NEVER deploy.
# Use after the 2026-11-18 verified rollback of the Samsung PWA.
set -Eeuo pipefail
IFS=$'\n\t'

REPO='https://github.com/alexiptv82/SuperBot-Trading.git'
BRANCH='work/arena-vps-stage-paused-only-20261117'
PIN='e85321b5e2acfa7b6d47bf42f417600eafe64de3'
BASE='/opt/superbot-arena-ui-builds'
SEED="$BASE/preview.m9igvUqn"
LOCK_SHA='e22e24c21bb4d9c0d872356654c8cc98f330b1dce3774afb18738bf43a2fc48a'
IMAGE='node:20-bookworm-slim'
DOMAIN='superbot-trading.duckdns.org'
WEB='/opt/superbot-web/build'
EXPECTED_WORKING_SHA='1432effbd102fb50dfd47722fba46de4c5e91caf48f74c968194d681a4bd2d0c'
FAILED='/opt/superbot-web/.arena-failed-login-20261118T034527Z'

out(){ printf 'ARENA_AUTH_PREFLIGHT_%s\n' "$*"; }
refuse(){ out "REFUSED=$1"; exit 2; }

[[ "$(id -u)" -eq 0 ]] || refuse ROOT_REQUIRED
for bin in docker git curl python3.12 sha256sum; do
  command -v "$bin" >/dev/null 2>&1 || refuse "MISSING_TOOL_$bin"
done
[[ -d "$BASE" && ! -L "$BASE" ]] || refuse BASE_MISSING
[[ "$(stat -c '%u:%a' "$BASE")" == '0:700' ]] || refuse BASE_UNSAFE
[[ -f "$SEED/package-lock.json" && -d "$SEED/node_modules" ]] || refuse SEED_MISSING
[[ "$(sha256sum "$SEED/package-lock.json" | cut -d' ' -f1)" == "$LOCK_SHA" ]] || refuse LOCK_SHA_UNEXPECTED
[[ -f "$WEB/index.html" && ! -L "$WEB" ]] || refuse PUBLIC_BUILD_INVALID
[[ "$(sha256sum "$WEB/index.html" | cut -d' ' -f1)" == "$EXPECTED_WORKING_SHA" ]] || refuse PUBLIC_ROLLBACK_NOT_PRESERVED
[[ -s "$FAILED/index.html" ]] || refuse FAILED_BUNDLE_MISSING_FOR_AUDIT
docker image inspect "$IMAGE" >/dev/null 2>&1 || refuse NODE_IMAGE_NOT_LOCAL

out "PUBLIC_ROLLBACK=STILL_IN_PLACE"
# Do not print JS bundle content or credentials. Binary fingerprint only.
if grep -RlqF 'http://51.91.109.45:8002' "$FAILED/static/js" --include='*.js'; then
  out 'BROKEN_BUNDLE_HTTP_FALLBACK=DETECTED'
else
  out 'BROKEN_BUNDLE_HTTP_FALLBACK=NOT_FOUND'
fi

# Unauthenticated status endpoint should return JSON over same HTTPS host.
# Absolutely no password attempts and no WebAuthn credential prompts.
TMP="$(mktemp)" || refuse TEMP_FAILED
trap 'rm -f "$TMP"' EXIT
HTTP="$(curl -fsS --max-time 12 --resolve "$DOMAIN:443:127.0.0.1" \
  -H 'Accept: application/json' -o "$TMP" -w '%{http_code}' \
  "https://$DOMAIN/api/auth/webauthn/status" 2>/dev/null)" \
  || refuse AUTH_STATUS_UNREACHABLE
[[ "$HTTP" == '200' ]] || refuse AUTH_STATUS_NOT_HTTP_200
python3.12 - "$TMP" <<'PY'
import json, pathlib, sys
data=json.loads(pathlib.Path(sys.argv[1]).read_text())
assert isinstance(data,dict), 'AUTH_STATUS_NOT_OBJECT'
assert isinstance(data.get('available'),bool), 'AUTH_STATUS_AVAILABLE_INVALID'
assert isinstance(data.get('has_credentials'),bool), 'AUTH_STATUS_CREDS_INVALID'
print('ARENA_AUTH_PREFLIGHT_EXISTING_AUTH_STATUS=200_JSON_OK',flush=True)
PY

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DIR="$(mktemp -d "$BASE/auth-preflight.XXXXXXXX")" || refuse WORKSPACE_FAILED
chmod 0700 "$DIR"
out "WORKSPACE=$DIR"
GIT_TERMINAL_PROMPT=0 git clone --quiet --no-tags --single-branch \
  --depth 35 --branch "$BRANCH" "$REPO" "$DIR/source" || refuse CLONE_FAILED
git -C "$DIR/source" cat-file -e "$PIN^{commit}" 2>/dev/null || refuse PIN_NOT_FETCHED
git -C "$DIR/source" checkout --quiet --detach "$PIN" || refuse CHECKOUT_FAILED
[[ "$(git -C "$DIR/source" rev-parse HEAD)" == "$PIN" ]] || refuse SOURCE_COMMIT_MISMATCH

python3.12 - "$DIR/source/frontend/package.json" "$SEED/package.json" <<'PY'
import json,pathlib,sys
source=json.loads(pathlib.Path(sys.argv[1]).read_text())
installed=json.loads(pathlib.Path(sys.argv[2]).read_text())
assert source['dependencies']==installed['dependencies'], 'DEPENDENCIES_CHANGED'
assert source['scripts']==installed['scripts'], 'SCRIPTS_CHANGED'
assert installed.get('devDependencies')=={'ajv':'8.17.1'}, 'AJV_SEED_CHANGED'
print('ARENA_AUTH_PREFLIGHT_DEPENDENCIES_MATCH=TRUE',flush=True)
PY

WORK="$DIR/workspace"
mkdir -m 0700 "$WORK"
cp -a "$DIR/source/frontend/src" "$DIR/source/frontend/public" "$WORK/"
cp -a "$SEED/package.json" "$SEED/package-lock.json" "$SEED/node_modules" "$WORK/"
[[ -x "$WORK/node_modules/.bin/react-scripts" ]] || refuse REACT_SCRIPTS_UNAVAILABLE
out 'AUTH_TESTS_START=TRUE'
# IMPORTANT: explicitly use same-origin API for both legacy and Arena screens.
# Tests and compilation are offline inside a disposable Node container.
docker run --rm --network none --security-opt no-new-privileges --cap-drop ALL \
  --pids-limit 400 --memory 3g --cpus 2 \
  --mount "type=bind,src=$WORK,dst=/workspace" \
  --workdir /workspace \
  -e CI=true -e NODE_OPTIONS=--max-old-space-size=2048 \
  -e REACT_APP_BACKEND_URL='' -e REACT_APP_API_URL='' \
  -e REACT_APP_BRAIN_ARENA_PREVIEW=1 -e REACT_APP_PREVIEW_READONLY=0 \
  -e REACT_APP_BRAIN_ARENA_SHADOW_API=0 \
  -e REACT_APP_ARENA_MANUAL_CLOSE=0 \
  -e REACT_APP_ARENA_EXISTING_CLOSE=0 \
  "$IMAGE" sh -ec './node_modules/.bin/react-scripts test --watchAll=false --runInBand && npm run build' \
  || refuse TEST_OR_BUILD_FAILED_NO_DEPLOY

[[ -s "$WORK/build/index.html" && -d "$WORK/build/static/js" ]] || refuse BUILD_MISSING
if grep -RlqF 'http://51.91.109.45:8002' "$WORK/build/static/js" --include='*.js'; then
  refuse NEW_BUNDLE_CONTAINS_OLD_HTTP_IP
fi
grep -RlqF '/api/auth/login' "$WORK/build/static/js" --include='*.js' || refuse AUTH_LOGIN_PATH_MISSING
grep -RlqF '/api/auth/webauthn/status' "$WORK/build/static/js" --include='*.js' || refuse WEBAUTHN_PATH_MISSING
[[ "$(sha256sum "$WEB/index.html" | cut -d' ' -f1)" == "$EXPECTED_WORKING_SHA" ]] || refuse PUBLIC_CHANGED_DURING_PREFLIGHT

out "CANDIDATE_BUILD=$WORK/build"
out "SOURCE_PIN=$PIN"
out "INDEX_SHA256=$(sha256sum "$WORK/build/index.html" | cut -d' ' -f1)"
out 'AUTH_TESTS_AND_BUILD=PASS'
out 'NO_OLD_HTTP_FALLBACK=TRUE'
out 'PUBLIC_APP_UPDATED=FALSE'
out 'BRAIN_SERVICES_CHANGED=FALSE'
out 'ARENA_TRIAL_STARTED=FALSE'
out 'RESULT=SUCCESS_AUTH_PREFLIGHT_ONLY'
