#!/usr/bin/env bash
# NON-DEPLOYING React smoke/build for a fresh isolated checkout. No /opt writes.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
REQUIRED_BRANCH="work/arena-ui-smoke-build-20261117"
fail() { echo "ARENA_UI_BUILD RESULT=NOT_BUILT_$1"; exit 2; }
[[ -f "$ROOT/frontend/yarn.lock" && -f "$ROOT/frontend/package.json" ]] || fail MISSING_MANIFEST
[[ "$(git -C "$ROOT" branch --show-current)" == "$REQUIRED_BRANCH" ]] || fail WRONG_BRANCH
[[ -z "$(git -C "$ROOT" status --porcelain)" ]] || fail DIRTY_CHECKOUT
case "$ROOT" in /tmp/arena-ui-smoke.*/repo) ;; *) fail NOT_ISOLATED_TMP_REPO ;; esac
command -v node >/dev/null 2>&1 || fail NODE_NOT_INSTALLED
node -e 'process.exit(Number(process.versions.node.split(".")[0]) >= 16 ? 0 : 1)' || fail NODE_TOO_OLD
if command -v yarn >/dev/null 2>&1; then
  YARN=(yarn)
elif command -v corepack >/dev/null 2>&1; then
  YARN=(corepack yarn)
else
  fail YARN_UNAVAILABLE
fi
YARN_VERSION="$("${YARN[@]}" --version 2>/dev/null)" || fail YARN_NOT_WORKING
[[ "$YARN_VERSION" == 1.* ]] || fail YARN_V1_REQUIRED
AVAIL_KB="$(awk '$1=="MemAvailable:"{print $2}' /proc/meminfo)"
SWAP_KB="$(awk '$1=="SwapFree:"{print $2}' /proc/meminfo)"
DISK_KB="$(df -Pk "$ROOT" | awk 'NR==2 {print $4}')"
[[ "$AVAIL_KB" =~ ^[0-9]+$ && "$SWAP_KB" =~ ^[0-9]+$ && "$DISK_KB" =~ ^[0-9]+$ ]] || fail VPS_RESOURCE_UNKNOWN
if (( AVAIL_KB + SWAP_KB < 1400000 || DISK_KB < 1600000 )); then
  echo "ARENA_UI_BUILD memory_available_plus_swap_kib=$((AVAIL_KB+SWAP_KB))"
  echo "ARENA_UI_BUILD disk_available_kib=$DISK_KB"
  fail VPS_RESOURCES_BELOW_BUILD_THRESHOLD
fi
echo "ARENA_UI_BUILD mode=ISOLATED_REACT_TEST_AND_BUILD"
echo "ARENA_UI_BUILD source_sha=$(git -C "$ROOT" rev-parse HEAD)"
echo "ARENA_UI_BUILD node=$(node --version) yarn=$YARN_VERSION"
echo "ARENA_UI_BUILD service_changes=0 orders=0 paid_AI_calls=0"
cd "$ROOT/frontend"
nice -n 10 "${YARN[@]}" install --frozen-lockfile --ignore-scripts --non-interactive --no-progress
# The install may write node_modules, but must NOT rewrite tracked app configuration.
git -C "$ROOT" diff --quiet -- frontend/package.json || fail PACKAGE_JSON_MUTATED_BY_YARN
echo "ARENA_UI_BUILD step=THREE_TARGETED_JEST_FILES"
# package.json defines "start" and "build", but NO "test" script.
# Invoke locally installed react-scripts directly; do not change package.json.
[[ -x node_modules/.bin/react-scripts ]] || fail REACT_SCRIPTS_MISSING
CI=true nice -n 10 ./node_modules/.bin/react-scripts test --watchAll=false --runInBand --runTestsByPath \
  src/brainArenaModel.test.js \
  src/pages/BrainArena.test.js \
  src/pages/Overview.test.js
echo "ARENA_UI_BUILD step=FRONTEND_COMPILE"
CI=false REACT_APP_BACKEND_URL='' REACT_APP_PREVIEW_READONLY=0 \
REACT_APP_BRAIN_ARENA_PREVIEW=0 REACT_APP_BRAIN_ARENA_SHADOW_API=0 \
nice -n 10 "${YARN[@]}" build
[[ -f build/index.html ]] || fail NO_BUILD_HTML
BUNDLE="$(find build/static/js -maxdepth 1 -type f -name 'main.*.js' | head -n 1)"
[[ -n "$BUNDLE" && -f "$BUNDLE" ]] || fail NO_BUILD_BUNDLE
echo "ARENA_UI_BUILD artifact_SHA256=$(sha256sum "$BUNDLE" | awk '{print $1}')"
echo "ARENA_UI_BUILD build_files=$(find build -type f | wc -l)"
echo "ARENA_UI_BUILD published=NO deployment=NO services_changed=0"
echo "ARENA_UI_BUILD RESULT=TESTS_AND_REACT_BUILD_VERIFIED_NO_DEPLOY"
