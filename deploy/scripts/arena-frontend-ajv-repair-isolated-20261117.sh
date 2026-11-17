#!/usr/bin/env bash
# Repair ONLY a previously failed, isolated Arena frontend build.
# AJV mismatch (ajv-keywords 5 requires Ajv 8) is checked before any install.
# Never modifies the public PWA, nginx, bot containers, or Arena/Brain data.
set -Eeuo pipefail
IFS=$'\n\t'

SOURCE=/opt/superbot-arena-stage
ROOT=/opt/superbot-arena-ui-builds
IMAGE=node:20-bookworm-slim
PIN=48dc07494345fe9d973b900b67cd094cec56e7e5
say() { printf 'ARENA_AJV_FIX_%s\n' "$*"; }
die() { say "REFUSED=$1"; exit 2; }

[[ "$(id -u)" -eq 0 ]] || die ROOT_REQUIRED
[[ -d "$SOURCE/.git" && ! -L "$SOURCE" ]] || die SOURCE_MISSING
[[ "$(git -C "$SOURCE" rev-parse HEAD)" == "$PIN" ]] || die WRONG_SOURCE_COMMIT
[[ -d "$ROOT" && ! -L "$ROOT" ]] || die NO_ISOLATED_PREVIEWS
[[ "$(stat -c '%u:%a' "$ROOT")" == "0:700" ]] || die UNSAFE_ROOT_PERMISSIONS
docker image inspect "$IMAGE" >/dev/null 2>&1 || die NODE_IMAGE_NOT_LOCAL

# Pick most recently created, actual directory; never accept arbitrary input.
JOB="$(find "$ROOT" -mindepth 1 -maxdepth 1 -type d -name 'preview.*' -printf '%T@ %p\n' | sort -nr | head -1 | cut -d' ' -f2-)"
[[ -n "$JOB" && -d "$JOB" && ! -L "$JOB" ]] || die PREVIOUS_BUILD_NOT_FOUND
[[ "$(stat -c '%u:%a' "$JOB")" == "0:700" ]] || die UNSAFE_WORKSPACE
[[ -f "$JOB/package.json" && -f "$JOB/package-lock.json" && -d "$JOB/node_modules" ]] || die INCOMPLETE_PREVIOUS_INSTALL
cmp -s "$SOURCE/frontend/package.json" "$JOB/package.json" || die WORKSPACE_PACKAGE_DIFFERENT
[[ -f "$JOB/node_modules/ajv-keywords/package.json" ]] || die AJV_KEYWORDS_NOT_FOUND
say "ISOLATED_WORKSPACE=$JOB"
say 'PUBLIC_APP=UNTOUCHED'
say 'NO_MODEL_INFERENCE=TRUE'

# Diagnostic scripts are written as actual JS files in the isolated workspace.
# Avoid nested Bash/JS heredoc quoting inside 'sh -ec' (previous syntax bug).
cat > "$JOB/.arena-ajv-before.cjs" <<'ARENA_NODE_BEFORE'
const path = require("path");
const kwPath = require.resolve("ajv-keywords/package.json");
const kw = require(kwPath);
let ajv = null;
try {
  const ajvPath = require.resolve("ajv/package.json", { paths: [path.dirname(kwPath)] });
  ajv = require(ajvPath).version;
} catch (_) {}
console.log("ARENA_AJV_FIX_BEFORE_AJV_KEYWORDS=" + kw.version);
console.log("ARENA_AJV_FIX_BEFORE_AJV=" + (ajv || "missing"));
if (Number(kw.version.split(".")[0]) !== 5 ||
    (ajv && Number(ajv.split(".")[0]) >= 8)) {
  console.log("ARENA_AJV_FIX_REFUSED=UNEXPECTED_DEPENDENCY_TREE");
  process.exit(12);
}
console.log("ARENA_AJV_FIX_MISMATCH_CONFIRMED=TRUE");
ARENA_NODE_BEFORE

cat > "$JOB/.arena-ajv-after.cjs" <<'ARENA_NODE_AFTER'
const path = require("path");
const kwPath = require.resolve("ajv-keywords/package.json");
const p = require.resolve("ajv/package.json", { paths: [path.dirname(kwPath)] });
const v = require(p).version;
console.log("ARENA_AJV_FIX_AFTER_AJV=" + v);
if (Number(v.split(".")[0]) !== 8) process.exit(14);
require("ajv-keywords/dist/definitions/typeof");
console.log("ARENA_AJV_FIX_MODULE_RESOLUTION=OK");
ARENA_NODE_AFTER

docker run --rm --network bridge \
  --name "arena-ajv-repair-$(basename "$JOB")" \
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
  "$IMAGE" sh -ec '
    node .arena-ajv-before.cjs
    # Workspace-only dependency change, never touch pinned source.
    npm pkg set devDependencies.ajv=8.17.1
    npm install --no-audit --no-fund --legacy-peer-deps --ignore-scripts
    node .arena-ajv-after.cjs
    npm run build
  ' || die FIX_OR_BUILD_FAILED_NO_DEPLOY

[[ -s "$JOB/build/index.html" && -d "$JOB/build/static" ]] || die OUTPUT_MISSING
say "BUILD_READY_DIR=$JOB/build"
say "LOCKFILE_SHA256=$(sha256sum "$JOB/package-lock.json" | cut -d' ' -f1)"
say "INDEX_SHA256=$(sha256sum "$JOB/build/index.html" | cut -d' ' -f1)"
say 'PUBLIC_APP_UPDATED=FALSE'
say 'BRAIN_SERVICES_CHANGED=FALSE'
say 'RESULT=SUCCESS_ISOLATED_BUILD_ONLY'
