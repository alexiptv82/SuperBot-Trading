#!/bin/sh
# ROLLBACK del backend: ferma e rimuove SOLO le due unita' nuove. Codice e run nuova restano (journal append-only,
# niente cancellazioni). La dashboard attiva NON viene toccata. Uso (root): sh 90-rollback.sh
set -eu
. "$(dirname "$0")/comune.sh"
[ "$(id -u)" = 0 ] || nogo "serve root"
OLD_BEFORE=$(systemctl show -p MainPID,ActiveState "$OLD_EXIT")
systemctl stop "$U_RUN" "$U_EXIT" 2>/dev/null || true
rm -f "/etc/systemd/system/$U_RUN" "/etc/systemd/system/$U_EXIT"
systemctl daemon-reload
[ "$(systemctl is-active "$U_RUN" 2>/dev/null || true)" != active ] || nogo "runner ancora attivo"
[ "$(systemctl is-active "$U_EXIT" 2>/dev/null || true)" != active ] || nogo "uscite nuove ancora attive"
[ "$(systemctl show -p MainPID,ActiveState "$OLD_EXIT")" = "$OLD_BEFORE" ] || nogo "il servizio della vecchia run e' cambiato"
[ -f "$RUN/journal.db" ] || nogo "journal della nuova run mancante"
echo "ROLLBACK OK: unita' nuove fermate e rimosse; vecchia run invariata; journal nuovo conservato; dashboard non toccata"
