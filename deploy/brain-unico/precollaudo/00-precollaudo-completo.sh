#!/bin/sh
# PRE-COLLAUDO COMPLETO in un solo comando (root), SENZA mandato: installa (10), avvia (20), controlla (30), prova il
# proprietario unico delle uscite, la pausa, l'arresto e il riavvio delle uscite (40), poi il rollback (90).
# Alla fine le due unita' nuove sono fermate e rimosse; codice e run nuova restano (journal append-only).
# Non tocca Falco, Toro, Arena, Brain storico, servizio uscite della vecchia run, dashboard: lo stato di tutte le
# unita' superbot* e di tutti i container e' fotografato prima e confrontato dopo.
# In caso di FAIL a meta': rollback automatico delle sole unita' nuove. Mandato sempre approved:false.
# Uso (root): sh 00-precollaudo-completo.sh <commit di 40 caratteri>
set -u
. "$(dirname "$0")/comune.sh"
D=$(cd "$(dirname "$0")" && pwd)
COMMIT="${1:-}"
[ "$(id -u)" = 0 ] || nogo "serve root"
printf '%s' "$COMMIT" | grep -Eq '^[0-9a-f]{40}$' || nogo "commit non valido"
# il laboratorio appartiene a superbot-agent: git (eseguito da root) lo legge solo con safe.directory esplicito,
# valido per questo processo e nessun altro
export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=safe.directory GIT_CONFIG_VALUE_0='*'
FAILS=0
res() { if [ "$1" = 0 ]; then echo "PASS  $2"; else echo "FAIL  $2"; FAILS=$((FAILS + 1)); fi; }
snapshot() {
  systemctl list-units 'superbot*' --all --no-legend --plain 2>/dev/null | cut -d' ' -f1 | sort | while read -r u; do
    case "$u" in "$U_EXIT"|"$U_RUN") continue ;; esac
    echo "$u $(systemctl show -p MainPID,ActiveState --value "$u" | tr '\n' ' ')"
  done
  ids=$(docker ps -aq 2>/dev/null || true)
  [ -z "$ids" ] || docker inspect -f '{{.Name}} {{.State.StartedAt}} {{.State.Running}}' $ids | sort
}
wait_all() {   # attende fino a 5 minuti che tutti i controlli di 30-controlli.sh passino (battito del runner)
  i=0
  until sh "$D/30-controlli.sh" tutti >/dev/null 2>&1; do
    i=$((i + 1)); [ $i -lt 60 ] || return 1; sleep 5
  done
}
abort() {
  echo "FAIL  $1: interruzione, rollback automatico delle sole unita' nuove"
  sh "$D/90-rollback.sh" || echo "FAIL  rollback automatico: verificare a mano"
  echo "ESITO PRE-COLLAUDO: NON SUPERATO ($1)"
  exit 1
}

echo "== pre-collaudo Brain Unico, commit $COMMIT, $(date -u +%Y-%m-%dT%H:%M:%SZ)"
git -C "$LAB" cat-file -e "$COMMIT^{commit}" || nogo "commit assente nel laboratorio"
snapshot > /root/precollaudo-prima.txt
echo "fotografia iniziale: $(wc -l < /root/precollaudo-prima.txt) unita'/container"
OLD_BEFORE=$(systemctl show -p MainPID,ActiveState "$OLD_EXIT" | tr '\n' ' ')

sh "$D/10-installa.sh" "$COMMIT" || nogo "installazione (nessuna unita' avviata)"
res 0 "1 codice al commit $COMMIT e impronta della configurazione $CFG_SHA (anche nella run)"
STAGE=/opt/superbot-brain-unico-$(printf '%s' "$COMMIT" | cut -c1-12)

sh "$D/20-avvia-senza-mandato.sh" || abort "avvio senza mandato"
res 0 "2 servizio delle uscite della nuova run avviato e SANO (lease, battito, monitor)"

wait_all; rc=$?
sh "$D/30-controlli.sh" tutti
res $rc "3 runner senza mandato: halted per il mandato, nessuna spesa AI, nessuna apertura"
[ $rc = 0 ] || abort "controllo 3"

# 5: un secondo processo delle uscite sulla stessa run NON parte (lease gia' detenuto)
ERR=$(cd "$STAGE" && timeout 60 env DESK_MODE=paper PYTHONPATH="$STAGE" PYTHONDONTWRITEBYTECODE=1 "$PY" -m \
  backend.v3.runner.exit_worker --data-dir "$RUN" --run-id "$RUN_ID" --config "$RUN/runner_config.json" \
  --start-paper --legacy-exits-disabled 2>&1 >/dev/null); rc=$?
echo "secondo processo delle uscite: uscita $rc, $ERR"
[ $rc = 3 ] && echo "$ERR" | grep -q exit_owner_busy && sh "$D/30-controlli.sh" uscite >/dev/null; res $? \
  "5 proprietario unico: secondo processo rifiutato (exit_owner_busy), il primo resta sano"

# 6: pausa attiva (run preparata in pausa): nessun giro del Brain, le uscite proseguono sane
[ -f "$RUN/pause.flag" ] && sh "$D/30-controlli.sh" uscite >/dev/null; res $? "6 pausa attiva: nessun nuovo giro, uscite sane"

sh "$D/40-prova-arresto-uscite.sh"; rc=$?
res $rc "4 arresto delle uscite: NON sane entro 75 s, riavvio sano, vecchia run invariata"
[ $rc = 0 ] || abort "controllo 4"
wait_all; rc=$?
sh "$D/30-controlli.sh" tutti
res $rc "3bis dopo il riavvio delle uscite: tutti i controlli ancora PASS"

sh "$D/90-rollback.sh"; rc=$?
[ ! -e "/etc/systemd/system/$U_EXIT" ] && [ ! -e "/etc/systemd/system/$U_RUN" ] && [ -f "$RUN/journal.db" ] || rc=1
res $rc "7a rollback del backend: unita' nuove fermate e rimosse, journal nuovo conservato"

"$PY" -c "import json,sys; sys.exit(0 if json.load(open('$RUN/mandate.json')).get('approved') is False else 1)"
res $? "mandato ancora approved:false"
[ "$(systemctl show -p MainPID,ActiveState "$OLD_EXIT" | tr '\n' ' ')" = "$OLD_BEFORE" ]
res $? "servizio delle uscite della vecchia run invariato (PID e stato)"
snapshot > /root/precollaudo-dopo.txt
diff /root/precollaudo-prima.txt /root/precollaudo-dopo.txt
res $? "nessun'altra unita' superbot* ne' container cambiato (Falco, Toro, Arena, Brain storico, dashboard)"
echo "7b rollback web: NON eseguito (dashboard attiva non toccata; prova isolata da autorizzare a parte)"
if [ "$FAILS" = 0 ]; then
  echo "ESITO PRE-COLLAUDO: TUTTI PASS (mandato non approvato; 72 ore non avviate; unita' nuove rimosse dal rollback)"
else
  echo "ESITO PRE-COLLAUDO: $FAILS FAIL"
  exit 1
fi
