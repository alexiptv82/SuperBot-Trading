#!/bin/sh
# PROVA (solo nuova run): ferma il servizio delle uscite, verifica che risulti NON sano (le aperture sono negate dal
# percorso serializzato, indipendentemente dal motivo mostrato dal runner), lo riavvia e verifica che torni sano.
set -eu
. "$(dirname "$0")/comune.sh"
[ "$(id -u)" = 0 ] || nogo "serve root"
OLD_BEFORE=$(systemctl show -p MainPID,ActiveState "$OLD_EXIT")
systemctl stop "$U_EXIT"
sleep 75
sh "$(dirname "$0")/30-controlli.sh" uscite && nogo "uscite ancora sane dopo l'arresto"
echo "PASS  uscite fermate: NON sane, nuove aperture negate"
systemctl start "$U_EXIT"
i=0; until sh "$(dirname "$0")/30-controlli.sh" uscite >/dev/null 2>&1; do i=$((i+1)); [ $i -lt 24 ] || nogo "uscite non tornate sane"; sleep 5; done
echo "PASS  uscite riavviate: di nuovo sane"
[ "$(systemctl show -p MainPID,ActiveState "$OLD_EXIT")" = "$OLD_BEFORE" ] || nogo "il servizio della vecchia run e' cambiato"
echo "PASS  servizio uscite della vecchia run invariato"
