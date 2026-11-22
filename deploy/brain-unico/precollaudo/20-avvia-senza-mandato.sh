#!/bin/sh
# AVVIA senza mandato: prima il servizio delle uscite, poi il runner solo se le uscite sono sane. Il mandato resta
# approved:false, quindi il runner resta fermo (halted) e non chiama il modello. Uso (root): sh 20-avvia-senza-mandato.sh
set -eu
. "$(dirname "$0")/comune.sh"
[ "$(id -u)" = 0 ] || nogo "serve root"
"$PY" -c "import json,sys; m=json.load(open('$RUN/mandate.json')); sys.exit(0 if m.get('approved') is False else 1)" \
  || nogo "il mandato NON e' approved:false"
systemctl start "$U_EXIT"
i=0; until sh "$(dirname "$0")/30-controlli.sh" uscite >/dev/null 2>&1; do i=$((i+1)); [ $i -lt 24 ] || nogo "uscite non sane dopo 2 minuti"; sleep 5; done
systemctl start "$U_RUN"
echo "AVVIATI SENZA MANDATO: $U_EXIT (sano) e $U_RUN"
