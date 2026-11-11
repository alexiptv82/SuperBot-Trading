#!/usr/bin/env bash
# One-shot RC84 source staging. NO production deploy, worker, service or PAPER run is started.
# Default mode reports prerequisites only; explicit --stage-source clones a detached pinned commit.
set -euo pipefail
umask 077
PIN="0e29a73a36f668643da4088178bacb8616a45ac0"
REMOTE="https://github.com/alexiptv82/SuperBot-Trading.git"
DEST="/opt/superbot-v3-rc84-stage"

mode="--dry-run"
if (( $# > 0 )); then mode="$1"; fi
if (( $# > 1 )) || [[ "$mode" != "--dry-run" && "$mode" != "--stage-source" ]]; then
  echo RC84_STAGE_REFUSED_MODE; exit 2
fi
command -v git >/dev/null || { echo RC84_STAGE_REFUSED_NO_GIT; exit 2; }
[[ -d /opt && ! -L /opt ]] || { echo RC84_STAGE_REFUSED_NO_OPT; exit 2; }
[[ ! -e "$DEST" && ! -L "$DEST" ]] || { echo RC84_STAGE_REFUSED_DEST_EXISTS; exit 2; }
if [[ "$mode" == "--dry-run" ]]; then
  echo RC84_STAGE_SOURCE_DRY_RUN=PASS
  echo RC84_STAGE_NO_CHANGES=True
  exit 0
fi
# This writes only a brand-new, private source directory; no branch checkout into /opt/superbot.
git -c core.hooksPath=/dev/null clone --no-checkout "$REMOTE" "$DEST" >/dev/null 2>&1 \
  || { echo RC84_STAGE_CLONE_FAILED; exit 2; }
chmod 0700 "$DEST"
git -C "$DEST" -c core.hooksPath=/dev/null checkout --detach "$PIN" >/dev/null 2>&1 \
  || { echo RC84_STAGE_PIN_MISSING; exit 2; }
[[ "$(git -C "$DEST" rev-parse HEAD)" == "$PIN" ]] \
  || { echo RC84_STAGE_WRONG_COMMIT; exit 2; }
[[ -f "$DEST/backend/v3/runner/runner_config_brain2000_paper.json" ]] \
  || { echo RC84_STAGE_CONFIG_MISSING; exit 2; }
[[ -f "$DEST/backend/desk/cli.py" && -f "$DEST/backend/v3/runner/prepare_paper_run.py" ]] \
  || { echo RC84_STAGE_SOURCE_INCOMPLETE; exit 2; }
echo RC84_STAGE_SOURCE_PINNED="$PIN"
echo RC84_STAGE_ONLY_FILES_INSTALLED=True
echo RC84_PRODUCTION_UNCHANGED=True
