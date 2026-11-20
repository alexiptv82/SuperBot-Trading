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
# All'uscita i dati in chiaro, la chiave di prova e gli archivi si cancellano SEMPRE. Se la prova fallisce restano
# solo i due registri testuali (nomi di file, conteggi, esiti; nessun contenuto, nessuna chiave) in un file 600.
LOGKEEP="$BASE-$(date -u +%Y%m%dT%H%M%SZ).log"
finish() {
  rc=$?
  if [ "$rc" -ne 0 ] && [ -d "$BASE" ]; then
    cat "$BASE"/*.log > "$LOGKEEP" 2>/dev/null || true
    echo "registri della prova conservati in $LOGKEEP (solo root); cartella di prova e dati in chiaro cancellati"
  fi
  rm -rf "$BASE"
}
mkdir -m 700 "$BASE"
trap finish EXIT
age-keygen -o "$BASE/prova.key" 2>/dev/null
age-keygen -y "$BASE/prova.key" > "$BASE/recipient-prova.txt"
git init -q --bare -b main "$BASE/remote.git"
ESS_ARGS="--component indispensabili"
for d in $REQUIRED_V3; do ESS_ARGS="$ESS_ARGS --required-v3-run-dir $d"; done
STO_ARGS="--component storici --required-run-dir $DESK/brain"
for d in $OPTIONAL; do STO_ARGS="$STO_ARGS --run-dir $d"; done

# backup di un componente verso il repository LOCALE di prova; esito nel file $BASE/<componente>.rc
backup_one() {
  comp="$1"; shift
  echo "== backup del componente $comp (verso il repository LOCALE di prova)"
  # shellcheck disable=SC2068,SC2086
  if python3 -I "$TOOLS/external_backup.py" --root "$DESK" --app-db /opt/superbot/data/superbot.db \
      --pool-db /opt/superbot-pool-data/pool.db --tools "$TOOLS" --work "$BASE/work" --remote "$BASE/remote.git" \
      --recipient-file "$BASE/recipient-prova.txt" --app-repo /opt/superbot --bots-repo /opt/superbot-desk $@ \
      > "$BASE/backup-$comp.log" 2>&1; then
    grep -E "storico run|RISULTATO" "$BASE/backup-$comp.log" || true
    echo 0 > "$BASE/$comp.rc"
  else
    grep -E "ERRORE|Fail|NO-GO|errore|mancante|rifiut" "$BASE/backup-$comp.log" | tail -40
    echo "NO-GO: backup del componente $comp"
    echo 1 > "$BASE/$comp.rc"
  fi
}

# ripristino di un componente con lo script ufficiale: 0 certificato, 3 integro ma non certificato, 1 difetto tecnico
restore_one() {
  comp="$1"
  [ "$(cat "$BASE/$comp.rc")" = 0 ] || return 0
  echo "== ripristino del componente $comp con lo script ufficiale"
  ARC=$(find "$BASE/clone/archives" -name "superbot-backup-$comp-*.tar.gz.age*" | sed 's/\.part[0-9]*$//' | sort -u | head -1)
  if [ -z "$ARC" ]; then echo "NO-GO: archivio $comp non trovato nel repository di prova"; echo 1 > "$BASE/$comp.rc"; return 0; fi
  RC=0
  python3 -I "$TOOLS/restore_external_backup.py" --archive "$ARC" --identity "$BASE/prova.key" \
    --out "$BASE/restore-$comp" > "$BASE/restore-$comp.log" 2>&1 || RC=$?
  if [ "$RC" != 0 ] && [ "$RC" != 3 ]; then
    grep -E "ERRORE:|ANOMALIA SEMANTICA:|journal V3|coerenza|FALLITO" "$BASE/restore-$comp.log" | sed 's/ La cartella .* resta per l.esame\.//' | head -60
    echo "NO-GO: ripristino del componente $comp (difetto TECNICO)"; echo 1 > "$BASE/$comp.rc"; return 0
  fi
  grep -E "parti:|ANOMALIA SEMANTICA:|coerenza|journal V3|componente:|RISULTATO" "$BASE/restore-$comp.log" | sed 's/ Cartella .*//'
  for r in "$BASE/restore-$comp"/dati/runs/*/; do
    [ -d "$r" ] && echo "ripristinata $(find "$r" -type f | wc -l) file  $(basename "$r")"
  done
  echo "$RC" > "$BASE/$comp.rc"
}

# shellcheck disable=SC2086
backup_one indispensabili $ESS_ARGS
# shellcheck disable=SC2086
backup_one storici $STO_ARGS $BRAIN_MODE
git clone -q "$BASE/remote.git" "$BASE/clone"
restore_one indispensabili
restore_one storici

ESS=$(cat "$BASE/indispensabili.rc"); STO=$(cat "$BASE/storici.rc")
case "$ESS" in 0) E="CERTIFICATI" ;; *) E="NO-GO (difetto tecnico)" ;; esac
case "$STO" in 0) T="CERTIFICATI" ;; 3) T="INTEGRI MA NON CERTIFICATI (Falco/Toro conservati com'e')" ;; *) T="NO-GO (difetto tecnico)" ;; esac
echo "COMPONENTE indispensabili (database, Brain V3, Arena): $E"
echo "COMPONENTE storici (Falco/Toro, Brain storico e libero, adattivo, ai-data): $T"
if [ "$ESS" = 0 ] && [ "$STO" = 0 ]; then
  echo "ESITO PROVA: OK (archivi di prova, chiave e copie cancellati all'uscita; nessun trasferimento)"
  exit 0
fi
if [ "$ESS" = 0 ] && [ "$STO" = 3 ]; then
  echo "ESITO PROVA: INDISPENSABILI CERTIFICATI, STORICI NON CERTIFICATI SEMANTICAMENTE (nessun trasferimento)"
  exit 3
fi
echo "ESITO PROVA: NO-GO (vedi i componenti sopra)"
exit 1
