#!/bin/sh
# Brain Unico: preparazione COMPLETA dell'avvio PAPER in un solo comando (root), SENZA approvare il mandato.
#   1. 50-unita.sh           unita' definitive sulla run esistente, avviate senza mandato (halted, nessuna spesa)
#   2. web + bridge          web app e canale di chiusura collegati alla nuova run (rollback automatico)
#   3. 70-interfaccia.sh     schermata Brain Unico come pagina principale (rollback automatico)
#   4. controlli finali      uscite sane, runner fermo per il mandato, nessuna apertura/spesa, altri servizi invariati
# Dopo: l'avvio vero si fa SOLO con "sh 80-paper.sh attiva <Nome>" (consenso finale del proprietario).
# Uso (root): sh 00-avvio-completo.sh <commit integrazione 40 hex> <cartella build UI> <sha256 di SHA256SUMS>
set -u
. "$(dirname "$0")/comune.sh"
D=$(cd "$(dirname "$0")" && pwd)
SHA="${1:-}"; UI="${2:-}"; UISHA="${3:-}"
[ "$(id -u)" = 0 ] || nogo "serve root"
printf '%s' "$SHA" | grep -Eq '^[0-9a-f]{40}$' || nogo "commit non valido"
printf '%s' "$UISHA" | grep -Eq '^[0-9a-f]{64}$' || nogo "impronta della UI non valida"
FAILS=0
res() { if [ "$1" = 0 ]; then echo "PASS  $2"; else echo "FAIL  $2"; FAILS=$((FAILS + 1)); fi; }
snapshot() {
  systemctl list-units 'superbot*' --all --no-legend --plain 2>/dev/null | cut -d' ' -f1 | sort | while read -r u; do
    case "$u" in "$U_EXIT"|"$U_RUN"|superbot-v3-paper-single-close-bridge.service) continue ;; esac
    echo "$u $(systemctl show -p MainPID,ActiveState --value "$u" | tr '\n' ' ')"
  done
  for c in $(docker ps -a --format '{{.Names}}' | sort); do
    case "$c" in superbot|superbot-before-brain-unico-web|superbot-brain-unico-web-*|superbot-rc84-paper-close-bridge) continue ;; esac
    docker inspect -f '{{.Name}} {{.State.StartedAt}} {{.State.Running}}' "$c"
  done
}
echo "== avvio Brain Unico (senza mandato), integrazione $SHA, $(date -u +%Y-%m-%dT%H:%M:%SZ)"
snapshot > /root/avvio-brain-unico-prima.txt
OLD_BEFORE=$(systemctl show -p MainPID,ActiveState "$OLD_EXIT" | tr '\n' ' ')

sh "$D/50-unita.sh"; rc=$?
res $rc "1 unita' definitive sulla run esistente, uscite sane, runner fermo per il mandato"
[ $rc = 0 ] || { echo "ESITO AVVIO: NON PRONTO (unita')"; exit 1; }

python3 "$D/brain_unico_web_cutover.py" --deploy --source-root "$LAB" --sha "$SHA"; rc=$?
res $rc "2 web app e canale di chiusura sulla nuova run (sonde candidate e live, chiusura negativa via bridge = 404)"
[ $rc = 0 ] || { echo "ESITO AVVIO: NON PRONTO (web: ripristinata la precedente). Unita' Brain Unico attive senza mandato."; exit 1; }

bash "$D/70-interfaccia.sh" --activate --candidate "$UI" --manifest-sha "$UISHA"; rc=$?
res $rc "3 interfaccia Brain Unico pubblicata (PWA invariata, backup e rollback pronti)"
if [ $rc != 0 ]; then
  # nessuno stato parziale: backend e canale di chiusura tornano ai precedenti (l'interfaccia non e' cambiata o e'
  # gia' stata riportata indietro da 70-interfaccia.sh)
  if [ -e /opt/superbot-web/.brain-unico-webui-previous ]; then
    echo "RIPRISTINO MANUALE NECESSARIO (interfaccia): sudo bash $D/70-interfaccia.sh --rollback"
  fi
  if python3 "$D/brain_unico_web_cutover.py" --rollback; then
    echo "ESITO AVVIO: NON PRONTO (interfaccia). Web e bridge precedenti RIPRISTINATI; unita' Brain Unico attive senza mandato."
  else
    echo "ESITO AVVIO: NON PRONTO (interfaccia). RIPRISTINO MANUALE NECESSARIO: sudo python3 $D/brain_unico_web_cutover.py --rollback"
  fi
  exit 1
fi

sh "$D/30-controlli.sh" tutti; res $? "4 controlli: mandato approved:false, runner halted, nessuna spesa AI, nessuna apertura, uscite sane"
"$PY" -c "import json,sys; sys.exit(0 if json.load(open('$RUN/mandate.json')).get('approved') is False else 1)"
res $? "mandato ancora approved:false"
[ -f "$RUN/pause.flag" ]; res $? "pausa attiva (nessun giro fino all'attivazione)"
[ "$(systemctl show -p MainPID,ActiveState "$OLD_EXIT" | tr '\n' ' ')" = "$OLD_BEFORE" ]
res $? "servizio delle uscite della vecchia run invariato"
snapshot > /root/avvio-brain-unico-dopo.txt
diff /root/avvio-brain-unico-prima.txt /root/avvio-brain-unico-dopo.txt
res $? "Falco, Toro, Arena, Brain storico e altri container invariati"
if [ "$FAILS" = 0 ]; then
  echo "ESITO AVVIO: PRONTO PER L'ATTIVAZIONE PAPER (mandato NON approvato, nessun trade)"
  echo "Attivazione, solo con il consenso finale: sudo sh $D/80-paper.sh attiva \"<Nome>\""
else
  echo "ESITO AVVIO: $FAILS FAIL"; exit 1
fi
