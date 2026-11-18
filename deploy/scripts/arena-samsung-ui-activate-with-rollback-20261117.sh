#!/usr/bin/env bash
# One-time activation of AI Arena UI only. Does NOT start AI trading.
set -Eeuo pipefail
IFS='https://github.com/alexiptv82/SuperBot-Trading.git'
BRANCH='work/arena-vps-stage-paused-only-20261117'
PIN='3d15a7a02cf00e7b544711e365af3cb27becca87'
BASE='/opt/superbot-arena-ui-builds'
SEED="$BASE/preview.m9igvUqn"
EXPECTED_LOCK='e22e24c21bb4d9c0d872356654c8cc98f330b1dce3774afb18738bf43a2fc48a'
PUBLIC='/opt/superbot-web/build'
WEB='/opt/superbot-web'
BACKUPS='/opt/superbot-v3-backups'
IMAGE='node:20-bookworm-slim'
DOMAIN='superbot-trading.duckdns.org'

say(){ printf 'ARENA_ACTIVATION_%s\n' "$*"; }
stop(){ say "REFUSED=$1"; exit 2; }

[[ "$(id -u)" == 0 ]] || stop ROOT_REQUIRED
for tool in git docker python3.12 nginx curl sha256sum; do
  command -v "$tool" >/dev/null || stop "TOOL_MISSING_$tool"
done
[[ -d "$BASE" && ! -L "$BASE" && -d "$SEED/node_modules" ]] || stop SEED_MISSING
[[ -f "$SEED/package-lock.json" && -f "$SEED/package.json" ]] || stop SEED_INCOMPLETE
[[ "$(sha256sum "$SEED/package-lock.json" | cut -d' ' -f1)" == "$EXPECTED_LOCK" ]] || stop SEED_LOCK_SHA_MISMATCH
[[ -f "$PUBLIC/index.html" && ! -L "$PUBLIC" && ! -L "$WEB" ]] || stop PUBLIC_PATH_UNEXPECTED
[[ -d "$BACKUPS" && ! -L "$BACKUPS" ]] || stop BACKUP_PATH_UNSAFE
docker image inspect "$IMAGE" >/dev/null 2>&1 || stop NODE_IMAGE_MISSING
nginx -t >/dev/null 2>&1 || stop NGINX_CONFIG_INVALID
for unit in superbot-v3-paper-brain-runner.service superbot-v3-paper-brain-exit.service; do
  [[ "$(systemctl is-active "$unit" 2>/dev/null || true)" == active ]] || stop BRAIN_UNHEALTHY
done

# Validate that lockfile is the fixed one from the successfully tested build.
python3.12 - "$SEED" <<'PY'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1]); pkg=json.loads((p/'package.json').read_text()); lock=json.loads((p/'package-lock.json').read_text()); root=lock['packages']['']
assert root['dependencies']==pkg['dependencies'], 'SEED_LOCK_DEPENDENCIES_MISMATCH'
assert pkg.get('devDependencies',{})=={'ajv':'8.17.1'}, 'SEED_AJV_DEPS_UNEXPECTED'
assert lock['lockfileVersion'] in (2,3), 'SEED_LOCK_UNSUPPORTED'
print('ARENA_ACTIVATION_DEPENDENCIES_PINNED=TRUE', flush=True)
PY

[[ $(df -Pk "$BASE" | tail -1 | awk '{print $4}') -gt 4194304 ]] || stop INSUFFICIENT_FREE_SPACE
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RELEASE="$(mktemp -d "$BASE/release.XXXXXXXX")" || stop RELEASE_DIR_FAILED
chmod 0700 "$RELEASE"
SOURCE="$RELEASE/source"
say "RELEASE_WORKDIR=$RELEASE"
# The branch contains later safety/runbook commits; build the reviewed code PIN,
# not the moving branch HEAD. Fetch a shallow but sufficient reachable history.
GIT_TERMINAL_PROMPT=0 git clone --quiet --no-tags --single-branch --depth 40 --branch "$BRANCH" "$REPO" "$SOURCE" || stop SOURCE_CLONE_FAILED
git -C "$SOURCE" cat-file -e "$PIN^{commit}" 2>/dev/null || stop PINNED_CODE_NOT_IN_CLONE
git -C "$SOURCE" checkout --quiet --detach "$PIN" || stop CODE_CHECKOUT_FAILED
[[ "$(git -C "$SOURCE" rev-parse HEAD)" == "$PIN" ]] || stop CODE_COMMIT_CHANGED

python3.12 - "$SOURCE/frontend/package.json" "$SEED/package.json" <<'PY'
import json, pathlib, sys
original=json.loads(pathlib.Path(sys.argv[1]).read_text()); seeded=json.loads(pathlib.Path(sys.argv[2]).read_text())
assert original.get('dependencies')==seeded.get('dependencies'), 'DEPS_CHANGED'
assert original.get('scripts')==seeded.get('scripts'), 'SCRIPTS_CHANGED'
print('ARENA_ACTIVATION_FRONTEND_MANIFEST_MATCH=TRUE',flush=True)
PY

JOB="$RELEASE/workspace"
mkdir -m 0700 "$JOB"
cp -a "$SOURCE/frontend/src" "$SOURCE/frontend/public" "$JOB/"
cp -a "$SEED/package.json" "$SEED/package-lock.json" "$SEED/node_modules" "$JOB/"
[[ -x "$JOB/node_modules/.bin/react-scripts" ]] || stop REACT_SCRIPTS_MISSING
say 'TESTS_START=TRUE'
# No model-provider or external API calls: all frontend tests mock requests.
docker run --rm --network none --security-opt no-new-privileges --cap-drop ALL \
  --pids-limit 400 --memory 3g --cpus 2 \
  --mount "type=bind,src=$JOB,dst=/workspace" --workdir /workspace \
  -e CI=true -e NODE_OPTIONS=--max-old-space-size=2048 \
  -e REACT_APP_BRAIN_ARENA_PREVIEW=1 -e REACT_APP_PREVIEW_READONLY=0 \
  -e REACT_APP_BRAIN_ARENA_SHADOW_API=0 -e REACT_APP_ARENA_MANUAL_CLOSE=0 \
  -e REACT_APP_ARENA_EXISTING_CLOSE=0 \
  "$IMAGE" sh -ec './node_modules/.bin/react-scripts test --watchAll=false --runInBand && npm run build' \
  || stop TESTS_OR_BUILD_FAILED_NO_DEPLOY
[[ -s "$JOB/build/index.html" && -d "$JOB/build/static" ]] || stop OUTPUT_NOT_READY
say 'TESTS_AND_BUILD=PASS'
say 'NEW_CODE_COMMIT='$PIN

# Before release, back up the full serving tree and verify its contents.
OLD_SHA="$(sha256sum "$PUBLIC/index.html" | cut -d' ' -f1)"
BACKUP="$BACKUPS/arena-samsung-web-before-$STAMP"
[[ ! -e "$BACKUP" && ! -L "$BACKUP" ]] || stop BACKUP_ALREADY_EXISTS
mkdir -m 0700 "$BACKUP"
cp -a "$PUBLIC" "$BACKUP/build"
[[ -s "$BACKUP/build/index.html" && "$(sha256sum "$BACKUP/build/index.html" | cut -d' ' -f1)" == "$OLD_SHA" ]] || stop BACKUP_VERIFY_FAILED
diff -qr "$PUBLIC" "$BACKUP/build" >/dev/null || stop BACKUP_FULL_COMPARE_FAILED
say 'PUBLIC_BACKUP=VERIFIED'
say "PUBLIC_BACKUP_DIR=$BACKUP"

CANDIDATE="$WEB/.arena-new-$STAMP"
PREVIOUS="$WEB/.arena-previous-$STAMP"
[[ ! -e "$CANDIDATE" && ! -e "$PREVIOUS" ]] || stop DEST_ALREADY_EXISTS
cp -a "$JOB/build" "$CANDIDATE"
find "$CANDIDATE" -type d -exec chmod 0755 {} +
find "$CANDIDATE" -type f -exec chmod 0644 {} +
[[ "$(sha256sum "$CANDIDATE/index.html" | cut -d' ' -f1)" == "$(sha256sum "$JOB/build/index.html" | cut -d' ' -f1)" ]] || stop CANDIDATE_HASH_INVALID
say 'ACTIVATION_SWAP=STARTED'
mv -T "$PUBLIC" "$PREVIOUS" || stop OLD_BUILD_MOVE_FAILED
if ! mv -T "$CANDIDATE" "$PUBLIC"; then
  mv -T "$PREVIOUS" "$PUBLIC" || true
  stop NEW_BUILD_MOVE_FAILED_ROLLBACK_ATTEMPTED
fi

CODE="$(curl -sS -o /dev/null --max-time 10 --resolve "$DOMAIN:443:127.0.0.1" \
  -w '%{http_code}' "https://$DOMAIN/" || true)"
if [[ "$CODE" != '200' ]]; then
  say "SMOKE_HTTP_CODE=$CODE"
  mv -T "$PUBLIC" "$WEB/.arena-failed-$STAMP" || true
  mv -T "$PREVIOUS" "$PUBLIC" || stop ROLLBACK_FAILED_BACKUP_AVAILABLE
  stop WEB_SMOKE_FAILED_ROLLED_BACK
fi

say "SMOKE_HTTP_CODE=$CODE"
say "LIVE_INDEX_SHA256=$(sha256sum "$PUBLIC/index.html" | cut -d' ' -f1)"
say "PUBLIC_BUILD_DIR=$PUBLIC"
say "PREVIOUS_INSTANT_ROLLBACK=$PREVIOUS"
say 'PWA_UI_ACTIVATED=TRUE'
say 'BRAIN_SERVICES_CHANGED=FALSE'
say 'AI_RUNNERS_STARTED_BY_SCRIPT=FALSE'
say 'NO_NEW_ARENA_AI_CALLS=TRUE'
say 'TEST_14D_STARTED=FALSE'
say 'RESULT=SUCCESS_UI_ONLY'
\n\t'

# DO NOT REUSE THIS RELEASE COMMAND after the Samsung login/biometric incident.
# The old build did not specify a same-origin API URL. A HTTP 200 on / did
# not catch that regression. The replacement procedure first builds/tests
# the auth-corrected candidate, compares the broken PWA, and does NOT deploy.
echo 'ARENA_ACTIVATION_REFUSED=SUPERSEDED_BY_AUTH_PREFLIGHT_20261118'
exit 2

REPO='https://github.com/alexiptv82/SuperBot-Trading.git'
BRANCH='work/arena-vps-stage-paused-only-20261117'
PIN='3d15a7a02cf00e7b544711e365af3cb27becca87'
BASE='/opt/superbot-arena-ui-builds'
SEED="$BASE/preview.m9igvUqn"
EXPECTED_LOCK='e22e24c21bb4d9c0d872356654c8cc98f330b1dce3774afb18738bf43a2fc48a'
PUBLIC='/opt/superbot-web/build'
WEB='/opt/superbot-web'
BACKUPS='/opt/superbot-v3-backups'
IMAGE='node:20-bookworm-slim'
DOMAIN='superbot-trading.duckdns.org'

say(){ printf 'ARENA_ACTIVATION_%s\n' "$*"; }
stop(){ say "REFUSED=$1"; exit 2; }

[[ "$(id -u)" == 0 ]] || stop ROOT_REQUIRED
for tool in git docker python3.12 nginx curl sha256sum; do
  command -v "$tool" >/dev/null || stop "TOOL_MISSING_$tool"
done
[[ -d "$BASE" && ! -L "$BASE" && -d "$SEED/node_modules" ]] || stop SEED_MISSING
[[ -f "$SEED/package-lock.json" && -f "$SEED/package.json" ]] || stop SEED_INCOMPLETE
[[ "$(sha256sum "$SEED/package-lock.json" | cut -d' ' -f1)" == "$EXPECTED_LOCK" ]] || stop SEED_LOCK_SHA_MISMATCH
[[ -f "$PUBLIC/index.html" && ! -L "$PUBLIC" && ! -L "$WEB" ]] || stop PUBLIC_PATH_UNEXPECTED
[[ -d "$BACKUPS" && ! -L "$BACKUPS" ]] || stop BACKUP_PATH_UNSAFE
docker image inspect "$IMAGE" >/dev/null 2>&1 || stop NODE_IMAGE_MISSING
nginx -t >/dev/null 2>&1 || stop NGINX_CONFIG_INVALID
for unit in superbot-v3-paper-brain-runner.service superbot-v3-paper-brain-exit.service; do
  [[ "$(systemctl is-active "$unit" 2>/dev/null || true)" == active ]] || stop BRAIN_UNHEALTHY
done

# Validate that lockfile is the fixed one from the successfully tested build.
python3.12 - "$SEED" <<'PY'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1]); pkg=json.loads((p/'package.json').read_text()); lock=json.loads((p/'package-lock.json').read_text()); root=lock['packages']['']
assert root['dependencies']==pkg['dependencies'], 'SEED_LOCK_DEPENDENCIES_MISMATCH'
assert pkg.get('devDependencies',{})=={'ajv':'8.17.1'}, 'SEED_AJV_DEPS_UNEXPECTED'
assert lock['lockfileVersion'] in (2,3), 'SEED_LOCK_UNSUPPORTED'
print('ARENA_ACTIVATION_DEPENDENCIES_PINNED=TRUE', flush=True)
PY

[[ $(df -Pk "$BASE" | tail -1 | awk '{print $4}') -gt 4194304 ]] || stop INSUFFICIENT_FREE_SPACE
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RELEASE="$(mktemp -d "$BASE/release.XXXXXXXX")" || stop RELEASE_DIR_FAILED
chmod 0700 "$RELEASE"
SOURCE="$RELEASE/source"
say "RELEASE_WORKDIR=$RELEASE"
# The branch contains later safety/runbook commits; build the reviewed code PIN,
# not the moving branch HEAD. Fetch a shallow but sufficient reachable history.
GIT_TERMINAL_PROMPT=0 git clone --quiet --no-tags --single-branch --depth 40 --branch "$BRANCH" "$REPO" "$SOURCE" || stop SOURCE_CLONE_FAILED
git -C "$SOURCE" cat-file -e "$PIN^{commit}" 2>/dev/null || stop PINNED_CODE_NOT_IN_CLONE
git -C "$SOURCE" checkout --quiet --detach "$PIN" || stop CODE_CHECKOUT_FAILED
[[ "$(git -C "$SOURCE" rev-parse HEAD)" == "$PIN" ]] || stop CODE_COMMIT_CHANGED

python3.12 - "$SOURCE/frontend/package.json" "$SEED/package.json" <<'PY'
import json, pathlib, sys
original=json.loads(pathlib.Path(sys.argv[1]).read_text()); seeded=json.loads(pathlib.Path(sys.argv[2]).read_text())
assert original.get('dependencies')==seeded.get('dependencies'), 'DEPS_CHANGED'
assert original.get('scripts')==seeded.get('scripts'), 'SCRIPTS_CHANGED'
print('ARENA_ACTIVATION_FRONTEND_MANIFEST_MATCH=TRUE',flush=True)
PY

JOB="$RELEASE/workspace"
mkdir -m 0700 "$JOB"
cp -a "$SOURCE/frontend/src" "$SOURCE/frontend/public" "$JOB/"
cp -a "$SEED/package.json" "$SEED/package-lock.json" "$SEED/node_modules" "$JOB/"
[[ -x "$JOB/node_modules/.bin/react-scripts" ]] || stop REACT_SCRIPTS_MISSING
say 'TESTS_START=TRUE'
# No model-provider or external API calls: all frontend tests mock requests.
docker run --rm --network none --security-opt no-new-privileges --cap-drop ALL \
  --pids-limit 400 --memory 3g --cpus 2 \
  --mount "type=bind,src=$JOB,dst=/workspace" --workdir /workspace \
  -e CI=true -e NODE_OPTIONS=--max-old-space-size=2048 \
  -e REACT_APP_BRAIN_ARENA_PREVIEW=1 -e REACT_APP_PREVIEW_READONLY=0 \
  -e REACT_APP_BRAIN_ARENA_SHADOW_API=0 -e REACT_APP_ARENA_MANUAL_CLOSE=0 \
  -e REACT_APP_ARENA_EXISTING_CLOSE=0 \
  "$IMAGE" sh -ec './node_modules/.bin/react-scripts test --watchAll=false --runInBand && npm run build' \
  || stop TESTS_OR_BUILD_FAILED_NO_DEPLOY
[[ -s "$JOB/build/index.html" && -d "$JOB/build/static" ]] || stop OUTPUT_NOT_READY
say 'TESTS_AND_BUILD=PASS'
say 'NEW_CODE_COMMIT='$PIN

# Before release, back up the full serving tree and verify its contents.
OLD_SHA="$(sha256sum "$PUBLIC/index.html" | cut -d' ' -f1)"
BACKUP="$BACKUPS/arena-samsung-web-before-$STAMP"
[[ ! -e "$BACKUP" && ! -L "$BACKUP" ]] || stop BACKUP_ALREADY_EXISTS
mkdir -m 0700 "$BACKUP"
cp -a "$PUBLIC" "$BACKUP/build"
[[ -s "$BACKUP/build/index.html" && "$(sha256sum "$BACKUP/build/index.html" | cut -d' ' -f1)" == "$OLD_SHA" ]] || stop BACKUP_VERIFY_FAILED
diff -qr "$PUBLIC" "$BACKUP/build" >/dev/null || stop BACKUP_FULL_COMPARE_FAILED
say 'PUBLIC_BACKUP=VERIFIED'
say "PUBLIC_BACKUP_DIR=$BACKUP"

CANDIDATE="$WEB/.arena-new-$STAMP"
PREVIOUS="$WEB/.arena-previous-$STAMP"
[[ ! -e "$CANDIDATE" && ! -e "$PREVIOUS" ]] || stop DEST_ALREADY_EXISTS
cp -a "$JOB/build" "$CANDIDATE"
find "$CANDIDATE" -type d -exec chmod 0755 {} +
find "$CANDIDATE" -type f -exec chmod 0644 {} +
[[ "$(sha256sum "$CANDIDATE/index.html" | cut -d' ' -f1)" == "$(sha256sum "$JOB/build/index.html" | cut -d' ' -f1)" ]] || stop CANDIDATE_HASH_INVALID
say 'ACTIVATION_SWAP=STARTED'
mv -T "$PUBLIC" "$PREVIOUS" || stop OLD_BUILD_MOVE_FAILED
if ! mv -T "$CANDIDATE" "$PUBLIC"; then
  mv -T "$PREVIOUS" "$PUBLIC" || true
  stop NEW_BUILD_MOVE_FAILED_ROLLBACK_ATTEMPTED
fi

CODE="$(curl -sS -o /dev/null --max-time 10 --resolve "$DOMAIN:443:127.0.0.1" \
  -w '%{http_code}' "https://$DOMAIN/" || true)"
if [[ "$CODE" != '200' ]]; then
  say "SMOKE_HTTP_CODE=$CODE"
  mv -T "$PUBLIC" "$WEB/.arena-failed-$STAMP" || true
  mv -T "$PREVIOUS" "$PUBLIC" || stop ROLLBACK_FAILED_BACKUP_AVAILABLE
  stop WEB_SMOKE_FAILED_ROLLED_BACK
fi

say "SMOKE_HTTP_CODE=$CODE"
say "LIVE_INDEX_SHA256=$(sha256sum "$PUBLIC/index.html" | cut -d' ' -f1)"
say "PUBLIC_BUILD_DIR=$PUBLIC"
say "PREVIOUS_INSTANT_ROLLBACK=$PREVIOUS"
say 'PWA_UI_ACTIVATED=TRUE'
say 'BRAIN_SERVICES_CHANGED=FALSE'
say 'AI_RUNNERS_STARTED_BY_SCRIPT=FALSE'
say 'NO_NEW_ARENA_AI_CALLS=TRUE'
say 'TEST_14D_STARTED=FALSE'
say 'RESULT=SUCCESS_UI_ONLY'
