#!/bin/sh
# Backup cifrato ESTERNO DEFINITIVO (una tantum, su autorizzazione del proprietario): due archivi indipendenti,
# "indispensabili" e "storici", cifrati con la chiave PUBBLICA approvata e inviati al repository privato
# superbot-backups con la deploy key di root gia' esistente. Ogni invio e' riverificato da un clone NUOVO da GitHub
# (SHA-256 dell'archivio e di ogni parte). Stessa selezione degli archivi della prova certificata (prova_storici.sh).
# NON installa ne' modifica l'extbackup periodico, NON tocca servizi, NON decifra nulla (la chiave privata e' solo
# sul PC del proprietario). Uso (root): sh backup_definitivo.sh /root/extbackup-strumenti
set -eu
TOOLS="$1"
WORK=/root/extbackup-definitivo
REMOTE=git@github.com:alexiptv82/superbot-backups.git
SSH_KEY=/root/.ssh/superbot_backup_ed25519
KNOWN=/opt/superbot-extbackup/known_hosts
RECIPIENT=/opt/superbot-extbackup/recipient.txt
APPROVED_KEY=age142uj5c8xx4d9csj2dsy2uvda6e0kt9y8xln3xpetemzhts6ljaqq40qy6u
[ "$(id -u)" = 0 ] || { echo "NO-GO: serve root"; exit 2; }
for f in "$SSH_KEY" "$KNOWN" "$RECIPIENT"; do [ -f "$f" ] && [ ! -L "$f" ] || { echo "NO-GO: manca $f"; exit 2; }; done
# il destinatario deve essere ESATTAMENTE la chiave pubblica approvata (deploy/extbackup/recipient.txt)
KEYS=$(grep -E '^age1[0-9a-z]{58}$' "$RECIPIENT" || true)
[ "$KEYS" = "$APPROVED_KEY" ] || { echo "NO-GO: il destinatario non e' la sola chiave pubblica approvata"; exit 2; }
case "$(systemctl is-active superbot-extbackup.service 2>/dev/null || true)" in
  active|activating) echo "NO-GO: il backup periodico e' in esecuzione: riprovare dopo"; exit 2 ;;
esac

# --- archivi OBBLIGATORI: se ne manca uno, NO-GO prima di qualunque copia
DESK=/opt/superbot-desk-data
REQUIRED_V3="/opt/superbot-v3-paper-runs/brain-v3-paper20261111
/opt/superbot-ai-arena-paper/deepseek/brain-deepseek-paper20261118
/opt/superbot-ai-arena-paper/qwen/brain-qwen-paper20261118
/opt/superbot-ai-arena-paper/minimax/brain-minimax-paper20261118"
REQUIRED="$REQUIRED_V3
$DESK/brain"
for d in $REQUIRED "$DESK/hawk" "$DESK/bull"; do
  [ -d "$d" ] && [ ! -L "$d" ] || { echo "NO-GO: archivio obbligatorio mancante: $d"; exit 1; }
done
# --- archivi FACOLTATIVI: inclusi se presenti
OPTIONAL=""
for d in /opt/superbot-v3-paper-runs/*/ /opt/superbot-brain-free/ /opt/superbot-brain-adaptive/ /opt/superbot-ai-data/; do
  [ -d "$d" ] || continue
  d="${d%/}"
  case "
$REQUIRED
" in *"
$d
"*) continue ;; esac
  OPTIONAL="$OPTIONAL $d"
done

echo "== inventario (nomi, dimensioni, file, sottocartelle)"
SRC_BYTES=0
for d in $REQUIRED $OPTIONAL "$DESK/hawk" "$DESK/bull" /opt/superbot/data/superbot.db /opt/superbot-pool-data/pool.db; do
  b=$(du -sb "$d" | cut -f1); SRC_BYTES=$((SRC_BYTES + b))
  if [ -d "$d" ]; then
    echo "$(du -sh "$d" | cut -f1) $(find "$d" -type f | wc -l) file $(find "$d" -mindepth 1 -type d | wc -l) sottocartelle  $d"
  else
    echo "$(du -sh "$d" | cut -f1) file  $d"
  fi
done

# --- spazio: copie temporanee + tar.gz in chiaro + cifrato + repository git + clone + ripristino (stima 6x) + 1 GiB
NEED=$((SRC_BYTES * 6 + 1073741824))
AVAIL=$(df --output=avail -B1 /root | tail -1 | tr -d ' ')
echo "== spazio: sorgenti $((SRC_BYTES / 1048576)) MiB, necessari $((NEED / 1048576)) MiB, disponibili $((AVAIL / 1048576)) MiB"
[ "$AVAIL" -gt "$NEED" ] || { echo "NO-GO: spazio insufficiente"; exit 1; }

# --- modalita' del cervello di Falco/Toro: la STESSA scelta di run.sh (docker, mai dedotta dai file).
# Entrambi i container fermi (docker inspect = false) -> --bot-stopped (backup_brain.py riverifica il fermo per
# ciascun portafoglio e il battito vecchio); entrambi attivi -> percorso normale (confine di ciclo).
# Stati diversi o non verificabili -> NO-GO: nessuna copia incoerente dichiarata valida.
BRAIN_MODE=""
STATES=""
for C in superbot-desk-hawk superbot-desk-bull; do
  R="$(timeout 30 docker inspect -f '{{.State.Running}}' "$C" 2>/dev/null)" || R=
  echo "classico $C: running=${R:-non verificabile}"
  STATES="$STATES ${R:-x}"
done
case "$STATES" in
  " false false") BRAIN_MODE="--brain-arg=--bot-stopped --brain-retries 0"; echo "== Falco/Toro: entrambi fermi -> --bot-stopped" ;;
  " true true") echo "== Falco/Toro: entrambi attivi -> backup normale (confine di ciclo)" ;;
  *) echo "NO-GO: stato di Falco/Toro misto o non verificabile:$STATES"; exit 1 ;;
esac


umask 077
mkdir -p -m 700 "$WORK"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
ESS_ARGS="--component indispensabili"
for d in $REQUIRED_V3; do ESS_ARGS="$ESS_ARGS --required-v3-run-dir $d"; done
STO_ARGS="--component storici --required-run-dir $DESK/brain"
for d in $OPTIONAL; do STO_ARGS="$STO_ARGS --run-dir $d"; done

send_one() {
  comp="$1"; shift
  log="$WORK/backup-$comp-$STAMP.log"
  echo "== backup cifrato ESTERNO del componente $comp"
  # shellcheck disable=SC2068,SC2086
  if python3 -I "$TOOLS/external_backup.py" --root "$DESK" --app-db /opt/superbot/data/superbot.db \
      --pool-db /opt/superbot-pool-data/pool.db --tools "$TOOLS" --work "$WORK/$comp" --remote "$REMOTE" \
      --ssh-key "$SSH_KEY" --known-hosts "$KNOWN" --recipient-file "$RECIPIENT" \
      --app-repo /opt/superbot --bots-repo /opt/superbot-desk $@ > "$log" 2>&1; then
    grep -E "storico run|RISULTATO|tolti dalla punta" "$log" || true
    return 0
  fi
  grep -E "ERRORE|Fail|NO-GO|errore|mancante|rifiut" "$log" | tail -40
  echo "NO-GO: backup esterno del componente $comp (registro $log)"
  return 1
}

# gli indispensabili per primi: se falliscono non si prosegue
# shellcheck disable=SC2086
send_one indispensabili $ESS_ARGS || exit 1
# shellcheck disable=SC2086
send_one storici $STO_ARGS $BRAIN_MODE || { echo "ESITO: INDISPENSABILI INVIATI E VERIFICATI, STORICI NO-GO"; exit 3; }
echo "ESITO: INDISPENSABILI E STORICI INVIATI E VERIFICATI DA UN CLONE NUOVO (ripristino da fare sul PC del proprietario)"
