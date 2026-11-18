#!/usr/bin/env bash
# One-time install of inert AI Arena systemd templates.
# No enable/start, no inference, no run creation or web/Brain changes.
set -Eeuo pipefail
IFS=$'\n\t'
SOURCE='/opt/superbot-arena-stage'
EXPECTED_SHA='48dc07494345fe9d973b900b67cd094cec56e7e5'
UNIT_SOURCE="$SOURCE/deploy/arena-paper-services"
TARGET='/etc/systemd/system'
say() { printf 'ARENA_UNITS_%s\n' "$*"; }
abort() { say "REFUSED=$1"; exit 2; }

[[ "$(id -u)" -eq 0 ]] || abort ROOT_REQUIRED
[[ -d /run/systemd/system ]] || abort SYSTEMD_NOT_RUNNING
[[ -d "$SOURCE/.git" && ! -L "$SOURCE" ]] || abort SOURCE_NOT_STAGED
[[ "$(git -C "$SOURCE" rev-parse HEAD)" == "$EXPECTED_SHA" ]] || abort SOURCE_SHA_CHANGED
[[ -d "$TARGET" && ! -L "$TARGET" ]] || abort SYSTEMD_TARGET_UNSAFE
for old in superbot-v3-paper-brain-runner.service superbot-v3-paper-brain-exit.service; do
  [[ "$(systemctl is-active "$old" 2>/dev/null || true)" == 'active' ]] \
    || abort BRAIN_HISTORICAL_NOT_ACTIVE
done

# Check all templates before writing any file.
for unit in superbot-arena-runner@.service superbot-arena-exit@.service superbot-arena-close-bridge.service; do
  src="$UNIT_SOURCE/$unit"
  dest="$TARGET/$unit"
  [[ -f "$src" && ! -L "$src" && ! -e "$dest" && ! -L "$dest" ]] \
    || abort "TEMPLATE_MISSING_OR_INSTALLED_$unit"
  grep -Fq 'Environment=DESK_MODE=paper' "$src" \
    || abort "NOT_PAPER_ONLY_$unit"
  if grep -Eq '^[[:space:]]*\[Install\]' "$src"; then
    abort "AUTO_ENABLE_SECTION_PRESENT_$unit"
  fi
done
for provider in deepseek qwen minimax; do
  for type in runner exit; do
    unit="superbot-arena-$type@$provider.service"
    [[ "$(systemctl show "$unit" -p LoadState --value 2>/dev/null || true)" == 'not-found' ]] \
      || abort "INSTANCE_ALREADY_PRESENT_$unit"
  done
done
[[ "$(systemctl show superbot-arena-close-bridge.service -p LoadState --value 2>/dev/null || true)" == 'not-found' ]] \
  || abort BRIDGE_ALREADY_PRESENT

say 'PRECHECK=PASS'
say 'SCOPE=SYSTEMD_TEMPLATE_FILES_ONLY'
say "PINNED_SOURCE_SHA=$EXPECTED_SHA"
for unit in superbot-arena-runner@.service superbot-arena-exit@.service superbot-arena-close-bridge.service; do
  install -o root -g root -m 0644 "$UNIT_SOURCE/$unit" "$TARGET/$unit" \
    || abort "COPY_FAILED_$unit"
  cmp -s "$UNIT_SOURCE/$unit" "$TARGET/$unit" || abort "VERIFY_FAILED_$unit"
  say "COPIED_AND_VERIFIED=$unit"
done
systemctl daemon-reload || abort SYSTEMD_RELOAD_FAILED

for provider in deepseek qwen minimax; do
  for type in runner exit; do
    unit="superbot-arena-$type@$provider.service"
    load="$(systemctl show "$unit" -p LoadState --value)"
    active="$(systemctl show "$unit" -p ActiveState --value)"
    enabled="$(systemctl is-enabled "$unit" 2>/dev/null || true)"
    say "UNIT=$unit|LOAD=$load|ACTIVE=$active|ENABLED=$enabled"
    [[ "$load" == 'loaded' && "$active" == 'inactive' ]] \
      || abort "INSTANCE_NOT_INERT_$unit"
    [[ "$enabled" != 'enabled' && "$enabled" != 'enabled-runtime' ]] \
      || abort "INSTANCE_ENABLED_UNEXPECTED_$unit"
  done
done
bridge='superbot-arena-close-bridge.service'
[[ "$(systemctl show "$bridge" -p LoadState --value)" == 'loaded' ]] \
  || abort BRIDGE_LOAD_FAILED
[[ "$(systemctl show "$bridge" -p ActiveState --value)" == 'inactive' ]] \
  || abort BRIDGE_STARTED_UNEXPECTED
say 'BRIDGE=INSTALLED_INACTIVE'
for old in superbot-v3-paper-brain-runner.service superbot-v3-paper-brain-exit.service; do
  [[ "$(systemctl is-active "$old" 2>/dev/null || true)" == 'active' ]] \
    || abort BRAIN_STATE_CHANGED_ALERT
done
say 'BRAIN_HISTORICAL=ACTIVE_UNCHANGED'
say 'RUNS_CREATED=FALSE'
say 'SERVICES_ENABLED_OR_STARTED=FALSE'
say 'PAID_INFERENCE=FALSE'
say 'TRIAL_14_DAYS_STARTED=FALSE'
say 'RESULT=SUCCESS_TEMPLATES_INSTALLED_INACTIVE'
