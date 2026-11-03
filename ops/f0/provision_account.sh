#!/usr/bin/env bash
# One-time local provisioner on Singapore VPS. REVIEW BEFORE RUNNING.
# Executed by human via Termius as root; never called by GitHub Actions.
# Only creates a restricted diagnostics account and installs a root-owned probe.
# It deliberately does NOT create or print SSH private keys.
set -euo pipefail

readonly ACCOUNT="superbot-f0"
readonly SOURCE="${1:-}"
readonly DEST="/usr/local/libexec/superbot-f0-status"

if (( EUID != 0 )); then
  echo "REFUSED: local admin authorization required" >&2; exit 2
fi
if [[ -z "$SOURCE" || ! -f "$SOURCE" || -L "$SOURCE" ]]; then
  echo "REFUSED: supply the reviewed local probe file" >&2; exit 2
fi
if [[ -e "$DEST" ]]; then
  echo "REFUSED: diagnostic command already exists; manual review required" >&2; exit 2
fi
if id "$ACCOUNT" >/dev/null 2>&1; then
  echo "REFUSED: account already exists; manual review required" >&2; exit 2
fi
if ! command -v useradd >/dev/null 2>&1; then
  echo "REFUSED: useradd unavailable" >&2; exit 2
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "REFUSED: python3 unavailable" >&2; exit 2
fi
python3 -m py_compile "$SOURCE"

# No sudo privileges, Docker group or trading-application groups.
useradd --system --user-group --create-home --home-dir "/home/$ACCOUNT" \
  --shell /bin/sh "$ACCOUNT"
install -d -o root -g root -m 0755 /usr/local/libexec
install -o root -g root -m 0755 "$SOURCE" "$DEST"
install -d -o "$ACCOUNT" -g "$ACCOUNT" -m 0700 "/home/$ACCOUNT/.ssh"
touch "/home/$ACCOUNT/.ssh/authorized_keys"
chown "$ACCOUNT:$ACCOUNT" "/home/$ACCOUNT/.ssh/authorized_keys"
chmod 0600 "/home/$ACCOUNT/.ssh/authorized_keys"

echo "F0_ACCOUNT_PROVISIONED"
echo "ACCOUNT=$ACCOUNT"
echo "FORCED_COMMAND=$DEST"
echo "NO_SSH_KEY_INSTALLED"
echo "NEXT: add a new, dedicated ed25519 PUBLIC key, never share private keys in ChatGPT."
