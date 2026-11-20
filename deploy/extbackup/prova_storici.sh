#!/bin/sh
# Prova COMPLETA dell'extbackup sugli storici reali (Falco, Toro, app, pool + tutte le run Brain V3, Arena e Brain libero),
# SENZA trasferimento: il "remoto" e' un repository git locale in /root e la cifratura usa una CHIAVE DI PROVA generata qui.
# Il ripristino si verifica con restore_external_backup.py e la chiave di prova; alla fine TUTTO viene cancellato
# (archivio, chiave, repository, copie). Nessun servizio fermato, nessun permesso cambiato, sorgenti in sola lettura.
# Stampa solo nomi di cartelle, dimensioni, numero di file e l'esito: nessun contenuto.
# Uso (root): sh prova_storici.sh /percorso/della/cartella/con/gli/script/verificati
set -eu
TOOLS="$1"
BASE=/root/extbackup-prova-storici
[ "$(id -u)" = 0 ] || { echo "NO-GO: serve root"; exit 2; }
[ ! -e "$BASE" ] || { echo "NO-GO: $BASE esiste gia'"; exit 2; }
umask 077
mkdir -m 700 "$BASE"
trap 'rm -rf "$BASE"' EXIT
age-keygen -o "$BASE/prova.key" 2>/dev/null
age-keygen -y "$BASE/prova.key" > "$BASE/recipient-prova.txt"
git init -q --bare -b main "$BASE/remote.git"

echo "== inventario (nomi e dimensioni)"
RUNS=""
for d in /opt/superbot-v3-paper-runs/*/ /opt/superbot-ai-arena-paper/*/*/ /opt/superbot-brain-free/; do
  [ -d "$d" ] || continue
  d="${d%/}"
  echo "run $(du -sh "$d" | cut -f1) $(find "$d" -maxdepth 1 -type f | wc -l) file  $d"
  RUNS="$RUNS --run-dir $d"
done
for d in /opt/superbot-desk-data /opt/superbot-brain-adaptive /opt/superbot-ai-data; do
  [ -d "$d" ] && echo "altro $(du -sh "$d" | cut -f1)  $d"
done

echo "== backup (verso il repository LOCALE di prova)"
# shellcheck disable=SC2086
python3 -I "$TOOLS/external_backup.py" --root /opt/superbot-desk-data --app-db /opt/superbot/data/superbot.db \
  --pool-db /opt/superbot-pool-data/pool.db --tools "$TOOLS" --work "$BASE/work" --remote "$BASE/remote.git" \
  --recipient-file "$BASE/recipient-prova.txt" --app-repo /opt/superbot --bots-repo /opt/superbot-desk $RUNS \
  > "$BASE/backup.log" 2>&1 || { tail -5 "$BASE/backup.log"; echo "NO-GO: backup"; exit 1; }
grep -E "^storico run|RISULTATO|^OK" "$BASE/backup.log" || true

echo "== ripristino con lo script ufficiale"
git clone -q "$BASE/remote.git" "$BASE/clone"
ARC=$(find "$BASE/clone/archives" -name '*.tar.gz.age' | head -1)
[ -n "$ARC" ] || { echo "NO-GO: archivio non trovato nel repository di prova"; exit 1; }
python3 -I "$TOOLS/restore_external_backup.py" --archive "$ARC" --identity "$BASE/prova.key" --out "$BASE/restore" \
  > "$BASE/restore.log" 2>&1 || { tail -5 "$BASE/restore.log"; echo "NO-GO: ripristino"; exit 1; }
grep "RISULTATO" "$BASE/restore.log"
for r in "$BASE"/restore/dati/runs/*/; do
  echo "ripristinata $(find "$r" -maxdepth 1 -type f | wc -l) file  $(basename "$r")"
done
echo "ESITO PROVA: OK (archivio di prova, chiave e copie cancellati all'uscita; nessun trasferimento)"
