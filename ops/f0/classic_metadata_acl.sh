#!/usr/bin/env bash
# F0: targeted filesystem METADATA traversal only for Hawk/Bull.
# No changes without --apply. Never grants file read, directory listing,
# sudo, Docker access, or access to Brain sources.
set -Eeuo pipefail
umask 077

MODE="${1:---check}"
if (( $# > 1 )) || [[ "$MODE" != "--check" && "$MODE" != "--apply" ]]; then
  echo "Usage: $0 [--check|--apply]" >&2
  exit 2
fi
if (( EUID != 0 )); then
  echo "F0_ACL_BLOCKED: run locally as root in Termius (not from GitHub)" >&2
  exit 2
fi

ACCOUNT="superbot-f0"
BASE="/opt/superbot-desk-data"
HAWK="$BASE/hawk"
BULL="$BASE/bull"
SAFE="/root/superbot-f0-setup"

for cmd in getfacl setfacl runuser stat id; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "F0_ACL_BLOCKED: missing $cmd (no packages installed)" >&2
    exit 2
  fi
done
if ! id "$ACCOUNT" >/dev/null 2>&1; then
  echo "F0_ACL_BLOCKED: diagnostics account not provisioned" >&2
  exit 2
fi
for group in $(id -nG "$ACCOUNT"); do
  if [[ "$group" == "sudo" || "$group" == "docker" || "$group" == "root" ]]; then
    echo "F0_ACL_BLOCKED: forbidden group membership" >&2
    exit 2
  fi
done

for directory in /opt "$BASE" "$HAWK" "$BULL"; do
  if [[ ! -d "$directory" || -L "$directory" ]]; then
    echo "F0_ACL_BLOCKED: directory absent or symlink: $directory" >&2
    exit 2
  fi
done
for portfolio in "$HAWK" "$BULL"; do
  for name in state_v2.json trade_history.jsonl learning_log.jsonl lessons.md; do
    file="$portfolio/$name"
    if [[ ! -f "$file" || -L "$file" ]]; then
      echo "F0_ACL_BLOCKED: required source file not regular: $file" >&2
      exit 2
    fi
  done
  if [[ ! -d "$portfolio/archive" || -L "$portfolio/archive" ]]; then
    echo "F0_ACL_BLOCKED: archive absent or symlink: $portfolio/archive" >&2
    exit 2
  fi
  # An existing ACL mask without 'x' can hide earlier restrictions on other
  # principals. Changing that mask could broaden their effective rights.
  mask="$(getfacl -cp "$portfolio" | awk -F: '$1 == "mask" { print $3 }')"
  if [[ -n "$mask" && "$mask" != *x* ]]; then
    echo "F0_ACL_BLOCKED: existing ACL mask would require widening: $portfolio" >&2
    exit 2
  fi
done

status_check() {
  local p name
  for p in "$HAWK" "$BULL"; do
    for name in state_v2.json trade_history.jsonl learning_log.jsonl lessons.md; do
      if ! runuser -u "$ACCOUNT" -- stat -c %F "$p/$name" >/dev/null 2>&1; then
        return 1
      fi
    done
    if ! runuser -u "$ACCOUNT" -- stat -c %F "$p/archive" >/dev/null 2>&1; then
      return 1
    fi
  done
  return 0
}

if status_check; then
  echo "F0_CLASSIC_METADATA_ALREADY_ACCESSIBLE"
  echo "F0_ACL_NO_CHANGE"
  exit 0
fi
if [[ "$MODE" == "--check" ]]; then
  echo "F0_CLASSIC_METADATA_NOT_ACCESSIBLE"
  echo "F0_ACL_DRY_RUN_ONLY"
  exit 0
fi

if [[ ! -d "$SAFE" || -L "$SAFE" ]] || [[ "$(stat -c '%U:%a' "$SAFE")" != "root:700" ]]; then
  echo "F0_ACL_BLOCKED: private root setup directory must be root:700" >&2
  exit 2
fi

# An exact BEFORE snapshot enables rollback. Do not overwrite earlier receipts.
backup="$(mktemp "$SAFE/acl-before-hawk-bull.XXXXXXXX")"
chmod 600 "$backup"
getfacl -p "$HAWK" "$BULL" > "$backup"
chmod 600 "$backup"
applied=1
rollback() {
  local rc=$?
  trap - ERR INT TERM
  if [[ "$applied" == 1 ]]; then
    if setfacl --restore="$backup" >/dev/null 2>&1; then
      echo "F0_ACL_ROLLED_BACK"
    else
      echo "F0_ACL_ROLLBACK_FAILED: review the root-only ACL witness" >&2
    fi
  fi
  exit "$rc"
}
trap rollback ERR INT TERM

for portfolio in "$HAWK" "$BULL"; do
  mask="$(getfacl -cp "$portfolio" | awk -F: '$1 == "mask" { print $3 }')"
  if [[ -n "$mask" ]]; then
    # Preserve the old mask exactly: no permission broadening for others.
    setfacl -n -m "u:$ACCOUNT:--x" "$portfolio"
  else
    # First named ACL creates a mask from unchanged group permissions + x.
    setfacl -m "u:$ACCOUNT:--x" "$portfolio"
  fi
done
if ! status_check; then
  echo "F0_ACL_BLOCKED: post-change metadata check failed" >&2
  false
fi
applied=0
trap - ERR INT TERM
echo "F0_CLASSIC_METADATA_PASS"
echo "F0_ACL_CHANGED_ONLY_HAWK_BULL_SEARCH"
echo "F0_ACL_ORIGINAL_STATE_RETAINED_ROOT_ONLY"
echo "NO_FILE_READ_PERMISSIONS_GRANTED"
