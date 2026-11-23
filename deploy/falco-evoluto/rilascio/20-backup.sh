#!/bin/sh
# Fotografia di cio' che il rilascio cambia (unita' del bridge, web, interfaccia) piu' lo stato di RC1. Non cancella nulla.
set -eu
. "$(dirname "$0")/comune.sh"
[ "$(id -u)" = 0 ] || nogo "serve root"
B="$BACKUPS/before-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p -m 700 "$B"
cp -a /etc/systemd/system/superbot-v3-paper-single-close-bridge.service "$B/bridge.service"
docker inspect superbot > "$B/web-inspect.json"
systemctl list-units 'superbot*' --all --no-legend --plain > "$B/units.txt"
sha256sum /opt/superbot-web/build/index.html > "$B/ui-index.sha256"
ls -la "$RC1_RUN" > "$B/rc1-listing.txt"
chmod -R go-rwx "$B"
echo "PASS  backup in $B (unita' bridge, web, unita', interfaccia, elenco RC1)"
