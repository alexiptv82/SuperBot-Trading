#!/bin/sh
# Prova COMPLETA dell'extbackup sugli storici reali, SENZA trasferimento: il "remoto" e' un repository git locale in
# /root e la cifratura usa una CHIAVE DI PROVA generata qui. Ripristino con restore_external_backup.py e la chiave di
# prova (impronte, integrita' SQLite, catena e conteggio dei journal V3 rispetto all'originale); alla fine TUTTO viene
# cancellato. Nessun servizio fermato, nessun permesso cambiato, sorgenti solo in lettura.
# Stampa solo nomi di cartelle, dimensioni, conteggi ed esiti: nessun contenuto.
# Uso (root): sh prova_storici.sh /cartella/con/gli/script/verificati
set -eu
TOOLS="$1"
BASE=/root/extbackup-prova-storici
[ "$(id -u)" = 0 ] || { echo "NO-GO: serve root"; exit 2; }
[ ! -e "$BASE" ] || { echo "NO-GO: $BASE esiste gia'"; exit 2; }

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
mkdir -m 700 "$BASE"
trap 'rm -rf "$BASE"' EXIT
age-keygen -o "$BASE/prova.key" 2>/dev/null
age-keygen -y "$BASE/prova.key" > "$BASE/recipient-prova.txt"
git init -q --bare -b main "$BASE/remote.git"
ARGS=""
for d in $REQUIRED_V3; do ARGS="$ARGS --required-v3-run-dir $d"; done
ARGS="$ARGS --required-run-dir $DESK/brain"
for d in $OPTIONAL; do ARGS="$ARGS --run-dir $d"; done

echo "== backup (verso il repository LOCALE di prova)"
# shellcheck disable=SC2086
python3 -I "$TOOLS/external_backup.py" --root "$DESK" --app-db /opt/superbot/data/superbot.db \
  --pool-db /opt/superbot-pool-data/pool.db --tools "$TOOLS" --work "$BASE/work" --remote "$BASE/remote.git" \
  --recipient-file "$BASE/recipient-prova.txt" --app-repo /opt/superbot --bots-repo /opt/superbot-desk $ARGS $BRAIN_MODE \
  > "$BASE/backup.log" 2>&1 || { grep -E "Fail|NO-GO|errore|ERRORE|mancante" "$BASE/backup.log" | tail -5; echo "NO-GO: backup"; exit 1; }
grep -E "storico run|RISULTATO" "$BASE/backup.log" || true

echo "== ripristino con lo script ufficiale"
git clone -q "$BASE/remote.git" "$BASE/clone"
ARC=$(find "$BASE/clone/archives" -name '*.tar.gz.age' | head -1)
[ -n "$ARC" ] || { echo "NO-GO: archivio non trovato nel repository di prova"; exit 1; }
python3 -I "$TOOLS/restore_external_backup.py" --archive "$ARC" --identity "$BASE/prova.key" --out "$BASE/restore" \
  > "$BASE/restore.log" 2>&1 || { grep -E "journal|diverso|mancante|FALLITO" "$BASE/restore.log" | tail -8; echo "NO-GO: ripristino"; exit 1; }
grep -E "journal V3|RISULTATO" "$BASE/restore.log"
for r in "$BASE"/restore/dati/runs/*/; do
  echo "ripristinata $(find "$r" -type f | wc -l) file  $(basename "$r")"
done
echo "ESITO PROVA: OK (archivio di prova, chiave e copie cancellati all'uscita; nessun trasferimento)"
