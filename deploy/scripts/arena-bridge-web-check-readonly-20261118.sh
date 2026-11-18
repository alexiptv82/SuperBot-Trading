#!/usr/bin/env bash
# Verifica in SOLA LETTURA del collegamento app Samsung -> web -> socket del bridge di chiusura Arena.
# Non modifica nulla, non avvia ne' ferma servizi, non chiude posizioni. Una sola richiesta "status" (404 atteso).
#   sudo bash arena-bridge-web-check-readonly-20261118.sh [nome-container-web]   (predefinito: superbot)
set -uo pipefail
WEB="${1:-superbot}"
SOCK="${ARENA_BRIDGE_SOCKET:-/run/superbot-arena-close/arena.sock}"
HERE="$(cd "$(dirname "$0")" && pwd)"
say(){ echo "ARENA_BRIDGE_CHECK $*"; }
say "bridge_unit=$(systemctl is-active superbot-arena-close-bridge 2>/dev/null || echo unknown)"
if [[ -e "$SOCK" ]]; then say "host_socket=$(stat -c 'mode=%a owner=%U:%G' "$SOCK") dir=$(stat -c 'mode=%a owner=%U:%G' "$(dirname "$SOCK")")"
else say 'host_socket=MISSING'; fi
say "bridge_gid_env=$(systemctl show superbot-arena-close-bridge -p Environment -p EnvironmentFiles 2>/dev/null | grep -o 'V3_ARENA_CLOSE_GROUP_GID=[0-9]*' | head -1)"
if ! docker inspect "$WEB" >/dev/null 2>&1; then say "web_container=NOT_FOUND:$WEB"; exit 2; fi
say "web_user=$(docker inspect "$WEB" --format '{{.Config.User}}' | sed 's/^$/(root)/') group_add=$(docker inspect "$WEB" --format '{{.HostConfig.GroupAdd}}')"
say "web_mounts=$(docker inspect "$WEB" --format '{{range .Mounts}}{{.Source}}->{{.Destination}}(rw={{.RW}}) {{end}}' | tr ' ' '\n' | grep -E 'arena|superbot-paper-close' | xargs)"
say "userns=$(docker info --format '{{.SecurityOptions}}' 2>/dev/null | grep -o 'userns' | head -1 || true)"
docker exec -i "$WEB" python3 - "$SOCK" < "$HERE/arena_bridge_probe.py"
rc=$?
case $rc in
  0) say 'RESULT=WEB_TO_BRIDGE_CHANNEL_OK (la chiusura manuale resta da provare con UNA posizione PAPER reale e il tuo OK)';;
  *) say 'RESULT=CHANNEL_NOT_OK -> NON dichiarare la chiusura manuale funzionante dal Samsung (vedi codice sopra)';;
esac
exit $rc
