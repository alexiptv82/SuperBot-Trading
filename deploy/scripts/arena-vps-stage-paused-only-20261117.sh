#!/usr/bin/env bash
# Stage-only SuperBot AI Arena PAPER. No service starts, mandates, keys, or trading.
set -Eeuo pipefail
REPO='https://github.com/alexiptv82/SuperBot-Trading.git'
BRANCH='work/arena-paper-runners-manual-close-20261117'
PIN='48dc07494345fe9d973b900b67cd094cec56e7e5'
STAGE='/opt/superbot-arena-stage'
ROOT='/opt/superbot-ai-arena-paper'
say(){ printf 'ARENA_STAGE %s\n' "$*"; }
die(){ say "REFUSED=$1"; exit 2; }

inspect(){
  say 'INSPECTION_READ_ONLY=TRUE'
  say "REQUIRED_GIT_SHA=$PIN"
  for unit in superbot-v3-paper-falco.service superbot-v3-paper-toro.service superbot-v3-paper-brain.service; do
    if command -v systemctl >/dev/null 2>&1; then
      result="$(systemctl is-active "$unit" 2>/dev/null || true)"
      say "SERVICE_$unit=${result:-unknown}"
    fi
  done
  for p in "$STAGE" "$ROOT"; do
    if [[ -L "$p" ]]; then say "UNSAFE_SYMLINK=$p"
    elif [[ -d "$p" ]]; then say "ALREADY_EXISTS=$p"
    else say "MISSING=$p"; fi
  done
  [[ ! -d "$STAGE/.git" ]] || say "EXISTING_STAGE_SHA=$(git -C "$STAGE" rev-parse HEAD 2>/dev/null || true)"
  say 'NO_LEGACY_SERVICE_CHANGED=TRUE'
}

safe_parent(){
  local p="$1"
  [[ ! -L "$p" ]] || die 'SYMLINK_TARGET'
  if [[ -e "$p" ]]; then
    [[ -d "$p" ]] || die 'NON_DIRECTORY_TARGET'
    [[ "$(stat -c '%u:%a' "$p")" == '0:700' ]] || die 'EXISTING_FOLDER_PERMISSIONS_UNEXPECTED'
  fi
}

stage(){
  [[ "$(id -u)" == 0 ]] || die 'ROOT_REQUIRED'
  [[ -d /opt && ! -L /opt ]] || die 'OPT_UNSAFE'
  command -v git >/dev/null 2>&1 || die 'GIT_MISSING'
  safe_parent "$ROOT"
  for provider in deepseek qwen minimax; do safe_parent "$ROOT/$provider"; done
  if [[ -e "$STAGE" || -L "$STAGE" ]]; then
    [[ ! -L "$STAGE" && -d "$STAGE/.git" ]] || die 'STAGE_EXISTS_UNEXPECTED'
    [[ "$(git -C "$STAGE" rev-parse HEAD)" == "$PIN" ]] || die 'STAGE_COMMIT_DIFFERENT'
    say 'SOURCE_ALREADY_STAGED=TRUE'
  else
    scratch="$(mktemp -d /opt/.arena-staging.XXXXXXXX)" || die 'TEMP_CREATION_FAILED'
    say "TEMP_STAGE=$scratch"
    GIT_TERMINAL_PROMPT=0 git clone --quiet --no-tags --single-branch --depth 1 \
      --branch "$BRANCH" "$REPO" "$scratch/checkout" || die 'CLONE_FAILED_TEMP_PRESERVED'
    [[ "$(git -C "$scratch/checkout" rev-parse HEAD)" == "$PIN" ]] || die 'SHA_MISMATCH_TEMP_PRESERVED'
    [[ ! -e "$STAGE" && ! -L "$STAGE" ]] || die 'DEST_APPEARED_TEMP_PRESERVED'
    mv -T -- "$scratch/checkout" "$STAGE"
    rmdir "$scratch" || true
    say "SOURCE_STAGED_COMMIT=$PIN"
  fi
  [[ -e "$ROOT" ]] || install -d -o root -g root -m 0700 "$ROOT"
  for provider in deepseek qwen minimax; do
    [[ -e "$ROOT/$provider" ]] || install -d -o root -g root -m 0700 "$ROOT/$provider"
  done
  say 'THREE_PROVIDER_PARENTS_PREPARED=TRUE'
  say 'NO_TRIAL_T0_OR_RUN_JOURNALS_CREATED=TRUE'
  say 'NO_AI_CREDITS_SPENT=TRUE'
  say 'NO_SYSTEMD_OR_WEB_CHANGES=TRUE'
  python_bin=''
  for candidate in /opt/superbot-v3-rc70-stage/.venv/bin/python3 \
                   /opt/superbot-v3-rc84-stage/.venv/bin/python3; do
    if [[ -x "$candidate" ]] && "$candidate" -I -c 'import fastapi, sqlalchemy' >/dev/null 2>&1; then
      python_bin="$candidate"; break
    fi
  done
  if [[ -n "$python_bin" ]]; then
    say "EXISTING_PYTHON_DEPENDENCIES=$python_bin"
    if env -u DEEPSEEK_API_KEY -u OPENROUTER_API_KEY \
      PYTHONPATH="$STAGE" PYTHONDONTWRITEBYTECODE=1 DESK_MODE=paper TRADING_MODE=paper \
      "$python_bin" -B -c 'from backend.v3.arena.readiness import audit_trial_configs; r=audit_trial_configs(); assert not r["trial_ready"]; assert r["configured_universe_identical"]; assert r["configured_risk_policy_identical"]; assert r["configured_capital_equal"]; print("ARENA_OFFLINE_CONFIG_OK_SYMBOLS="+str(r["providers"]["qwen"]["symbol_count"]))'; then
      say 'OFFLINE_CONFIG_CHECK=PASS'
    else
      say 'OFFLINE_CONFIG_CHECK=NEEDS_REVIEW'
    fi
  else
    say 'OFFLINE_CONFIG_CHECK=SKIPPED_NO_COMPATIBLE_EXISTING_VENV'
  fi
  say 'STAGE_COMPLETE_ALL_RUNNERS_NOT_STARTED=TRUE'
}

case "${1:---inspect}" in
  --inspect) inspect ;;
  --stage) inspect; stage ;;
  *) die 'USAGE_EXPECTED_--inspect_OR_--stage' ;;
esac
