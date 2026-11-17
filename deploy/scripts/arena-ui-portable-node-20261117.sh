#!/usr/bin/env bash
# Portable Node + Yarn only in isolated /tmp Arena UI clone.
# No apt, global npm, daemon, service, bot process, production build or deploy.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WORK="$(dirname "$ROOT")"
fail() { echo "ARENA_NODE RESULT=STOPPED_$1"; exit 2; }
[[ "$ROOT" == /tmp/arena-ui-smoke.*/repo ]] || fail NOT_ISOLATED_REPO
[[ "$(git -C "$ROOT" branch --show-current)" == "work/arena-ui-smoke-build-20261117" ]] || fail WRONG_BRANCH
[[ -z "$(git -C "$ROOT" status --porcelain)" ]] || fail DIRTY_CHECKOUT
command -v curl >/dev/null 2>&1 || fail CURL_NOT_AVAILABLE
command -v tar >/dev/null 2>&1 || fail TAR_NOT_AVAILABLE
command -v xz >/dev/null 2>&1 || fail XZ_NOT_AVAILABLE
case "$(uname -s)/$(uname -m)" in
  Linux/x86_64)
    ARCH="linux-x64"
    EXPECTED="f4cb75bb036f0d0eddf6b79d9596df1aaab9ddccd6a20bf489be5abe9467e84e"
    ;;
  Linux/aarch64)
    ARCH="linux-arm64"
    EXPECTED="eab80cb88f8fda1e65f5e8d0420c9809bdb320b03fd34976ab7161b6e703b910"
    ;;
  *) fail UNSUPPORTED_ARCH ;;
esac
NODE_VERSION="22.16.0"
LABEL="node-v${NODE_VERSION}-${ARCH}"
ARCHIVE="${WORK}/${LABEL}.tar.xz"
NODE_HOME="${WORK}/${LABEL}"
if [[ ! -x "${NODE_HOME}/bin/node" ]]; then
  echo "ARENA_NODE action=DOWNLOAD_OFFICIAL_PORTABLE_BINARY"
  echo "ARENA_NODE url=https://nodejs.org/dist/v${NODE_VERSION}/${LABEL}.tar.xz"
  curl --proto '=https' --tlsv1.2 --fail --location --silent --show-error \
    --connect-timeout 12 --max-time 180 --retry 1 \
    --output "${ARCHIVE}.part" \
    "https://nodejs.org/dist/v${NODE_VERSION}/${LABEL}.tar.xz" ||
    fail NODE_OFFICIAL_DOWNLOAD_FAILED
  printf '%s  %s\n' "$EXPECTED" "${ARCHIVE}.part" | sha256sum -c - >/dev/null ||
    fail NODE_SHA256_MISMATCH
  mv "${ARCHIVE}.part" "$ARCHIVE"
  tar -xJf "$ARCHIVE" -C "$WORK" --no-same-owner ||
    fail NODE_EXTRACTION_FAILED
fi
[[ "$("${NODE_HOME}/bin/node" --version)" == "v${NODE_VERSION}" ]] ||
  fail NODE_BINARY_VERSION_MISMATCH
# Keep Corepack, Yarn, caches, dependency installs and build INSIDE /tmp.
mkdir -p "$WORK/localbin" "$WORK/corepack-cache" "$WORK/home"
printf '#!/bin/sh\nexec "%s/bin/corepack" yarn "$@"\n' "$NODE_HOME" \
  > "$WORK/localbin/yarn"
chmod 700 "$WORK/localbin/yarn"
export PATH="$WORK/localbin:$NODE_HOME/bin:$PATH"
export COREPACK_HOME="$WORK/corepack-cache"
export COREPACK_ENABLE_DOWNLOAD_PROMPT=0
export COREPACK_DEFAULT_TO_LATEST=0
# Do not let Corepack auto-pin a packageManager entry into frontend/package.json.
export COREPACK_ENABLE_AUTO_PIN=0
export HOME="$WORK/home"
echo "ARENA_NODE version=$(node --version)"
echo "ARENA_NODE mode=TEMPORARY_NO_APT_NO_GLOBAL_INSTALL"
echo "ARENA_NODE yarn_managed_by=COREPACK_ISOLATED"
echo "ARENA_NODE orders=0 services_changed=0 paid_AI_calls=0"
# Existing build enforces memory/disk gates and never deploys.
bash "$ROOT/deploy/scripts/arena-ui-isolated-build-20261117.sh"
