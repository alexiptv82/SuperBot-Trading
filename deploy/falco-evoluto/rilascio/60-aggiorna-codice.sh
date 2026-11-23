#!/bin/sh
# Aggiornamento MIRATO del codice di Falco Evoluto e Brain Scalp (es. correzione regole contratti BTC/ETH, 5539ee47).
# Cambia SOLO la cartella del codice nelle 4 unita' (uscite + runner) e le riavvia. NON tocca: run, journal, mandati,
# pause, configurazioni, Brain RC1, web, bridge, interfaccia. Durante tutto l'aggiornamento le run restano in pausa con
# mandato approved:false: il runner non puo' aprire (verificato prima, durante e dopo). Rollback automatico delle unita'.
# Uso (root): sh 60-aggiorna-codice.sh <commit 40 hex>
set -u
D=$(cd "$(dirname "$0")" && pwd)
. "$D/comune.sh"
SHA=${1:-}
[ "$(id -u)" = 0 ] || nogo "serve root"
printf '%s' "$SHA" | grep -Eq '^[0-9a-f]{40}$' || nogo "commit non valido"
export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=safe.directory GIT_CONFIG_VALUE_0='*'
git -C "$LAB" cat-file -e "$SHA^{commit}" 2>/dev/null || nogo "commit $SHA assente in $LAB"
NEW=$(stage_of "$SHA")
[ ! -e "$NEW" ] || nogo "$NEW esiste gia'"
UNITS="$U_F_EXIT $U_F_RUN $U_S_EXIT $U_S_RUN"
OLD=$(systemctl show -p WorkingDirectory --value "$U_F_EXIT")
for u in $UNITS; do
  [ -f "/etc/systemd/system/$u" ] || nogo "$u assente"
  [ "$(systemctl is-active "$u")" = active ] || nogo "$u non attiva"
  [ "$(systemctl show -p WorkingDirectory --value "$u")" = "$OLD" ] || nogo "$u: cartella del codice diversa dalle altre"
done
printf '%s' "$OLD" | grep -Eq '^/opt/superbot-falco-scalp-[0-9a-f]{12}$' && [ -d "$OLD/backend" ] || nogo "codice attuale non riconosciuto"
locked() {  # run run_id cfg: in pausa, mandato approved:false, configurazione = commit nuovo
  R="$PARENT/$1"
  [ -f "$R/pause.flag" ] || nogo "$1: pausa assente (l'aggiornamento richiede la pausa)"
  "$PY" -c "import json,sys; m=json.load(open('$R/mandate.json')); sys.exit(0 if m.get('approved') is False and m.get('run_id')=='$2' else 1)" \
    || nogo "$1: mandato non approved:false"
  WANT=$("$PY" -c "import json; print(json.load(open('$R/PREPARED_PAUSED_ONLY.json'))['config_sha256'])")
  [ "$(git -C "$LAB" show "$SHA:backend/v3/runner/$3" | sha256sum | cut -d' ' -f1)" = "$WANT" ] \
    || nogo "$1: la configurazione del commit $SHA non e' quella della run"
}
locked "$F_DIR" "$F_ID" "$F_CFG"; locked "$S_DIR" "$S_ID" "$S_CFG"
echo "PASS  preflight: 4 unita' attive su $OLD, run in pausa con mandato approved:false, configurazioni = commit"
B="$BACKUPS/aggiorna-$(date -u +%Y%m%dT%H%M%SZ)"; mkdir -p -m 700 "$B"
for u in $UNITS; do cp -a "/etc/systemd/system/$u" "$B/$u"; done
echo "PASS  backup delle unita' in $B"
sh "$D/30-codice.sh" "$SHA" || nogo "installazione del codice (unita' non toccate)"
(cd "$NEW" && DESK_MODE=paper PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 "$PY" "$D/contratti_check.py" \
  "$PARENT/$F_DIR/runner_config.json" "$PARENT/$S_DIR/runner_config.json") || nogo "regole dei contratti incomplete con il codice nuovo (unita' non toccate)"
restore() {
  echo "== ROLLBACK delle unita'"
  for u in $UNITS; do cp -a "$B/$u" "/etc/systemd/system/$u"; done
  systemctl daemon-reload
  for p in "$U_F_EXIT:$U_F_RUN" "$U_S_EXIT:$U_S_RUN"; do
    systemctl stop "${p#*:}" 2>/dev/null; systemctl restart "${p%%:*}"; systemctl start "${p#*:}"; done
  echo "ESITO AGGIORNAMENTO: NO-GO ($1). Unita' riportate al codice $OLD; run, mandati e pause invariati."
  exit 1
}
for u in $UNITS; do
  F="/etc/systemd/system/$u"
  sed "s#$OLD#$NEW#g" "$B/$u" > "$F.new"
  # l'unica differenza ammessa e' la cartella del codice
  [ "$(diff "$B/$u" "$F.new" | grep -c '^[<>]')" -ge 2 ] && [ "$(sed "s#$NEW#$OLD#g" "$F.new" | cmp -s - "$B/$u"; echo $?)" = 0 ] \
    || { rm -f "$F.new"; restore "unita' $u non trasformabile"; }
  chmod 644 "$F.new"; mv "$F.new" "$F"
done
systemctl daemon-reload
check() { (cd "$NEW" && DESK_MODE=paper PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 "$PY" "$D/controlli.py" "$1" "$2" "$3"); }
swap() {  # etichetta cartella run_id uscite runner
  R="$PARENT/$2"
  systemctl stop "$5" || restore "$1: stop runner"
  systemctl restart "$4" || restore "$1: riavvio uscite"
  i=0; until check "$R" "$3" uscite >/dev/null 2>&1; do i=$((i+1)); [ $i -lt 36 ] || restore "$1: uscite non sane"; sleep 5; done
  systemctl start "$5" || restore "$1: avvio runner"
  i=0; until check "$R" "$3" tutti >/dev/null 2>&1; do i=$((i+1)); [ $i -lt 60 ] || restore "$1: controlli non superati"; sleep 5; done
  [ "$(systemctl show -p WorkingDirectory --value "$4")" = "$NEW" ] && [ "$(systemctl show -p WorkingDirectory --value "$5")" = "$NEW" ] \
    || restore "$1: unita' non sul codice nuovo"
  check "$R" "$3" tutti
  echo "PASS  $1: uscite sane e runner fermo per il mandato sul codice $SHA (nessuna spesa, nessuna apertura)"
}
swap "Falco Evoluto" "$F_DIR" "$F_ID" "$U_F_EXIT" "$U_F_RUN"
swap "Brain Scalp" "$S_DIR" "$S_ID" "$U_S_EXIT" "$U_S_RUN"
[ "$(systemctl is-active "$RC1_EXIT")" = active ] && [ -f "$RC1_RUN/pause.flag" ] || echo "ATTENZIONE: verificare RC1"
echo "ESITO AGGIORNAMENTO: OK (codice $SHA; run, journal, mandati approved:false e pause invariati; codice precedente conservato in $OLD)"
