#!/usr/bin/env bash
# Register ONLY a dedicated SSH public key for superbot-f0.
# Run once as root via Termius. Never upload private key to this server via chat.
set -euo pipefail
readonly ACCOUNT="superbot-f0"
readonly PUBLIC_KEY="${1:-}"
readonly AUTH="/home/$ACCOUNT/.ssh/authorized_keys"
readonly FORCED="/usr/local/libexec/superbot-f0-status"

if (( EUID != 0 )) || [[ ! -f "$PUBLIC_KEY" || -L "$PUBLIC_KEY" ]]; then
  echo "REFUSED: root plus local regular public-key file required" >&2; exit 2
fi
if [[ ! -f "$FORCED" || -L "$FORCED" || ! -f "$AUTH" || -L "$AUTH" ]]; then
  echo "REFUSED: forced-command account not safely provisioned" >&2; exit 2
fi
if [[ "$(stat -c '%U:%G:%a' "$FORCED")" != "root:root:755" ]]; then
  echo "REFUSED: forced-command ownership/mode is not trusted" >&2; exit 2
fi

# Keep exactly the algorithm and base64 key material (drop untrusted comments).
# A single line, no option injection into authorized_keys.
if [[ "$(wc -l < "$PUBLIC_KEY")" -ne 1 ]]; then
  echo "REFUSED: public key must be one complete line" >&2; exit 2
fi
read -r kind key _ < "$PUBLIC_KEY" || true
if [[ "$kind" != "ssh-ed25519" || ! "$key" =~ ^[A-Za-z0-9+/=]+$ ]]; then
  echo "REFUSED: expected SSH ed25519 public key" >&2; exit 2
fi
if ! ssh-keygen -lf "$PUBLIC_KEY" -E sha256 >/dev/null 2>&1; then
  echo "REFUSED: invalid public key" >&2; exit 2
fi

readonly RESTRICTED="restrict,command=\"$FORCED\" $kind $key"
if grep -Fqx "$RESTRICTED" "$AUTH"; then
  echo "F0_PUBLIC_KEY_ALREADY_INSTALLED"
else
  printf '%s\n' "$RESTRICTED" >> "$AUTH"
  chown "$ACCOUNT:$ACCOUNT" "$AUTH"
  chmod 0600 "$AUTH"
  echo "F0_PUBLIC_KEY_REGISTERED"
fi
echo "F0_ACCOUNT_HAS_NO_SUDO_OR_DOCKER_GROUP_BY_DESIGN"
echo "Never paste your private key into a chat, commit, Actions log, or screenshot."
