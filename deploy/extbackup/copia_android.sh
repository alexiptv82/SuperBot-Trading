#!/bin/sh
# Copia AGGIUNTIVA cifrata degli INDISPENSABILI per la chiave age dello SMARTPHONE del proprietario (una tantum,
# su autorizzazione). Stessi archivi obbligatori della prova certificata: Brain V3 attivo, 3 run Arena (journal V3
# obbligatori), database dell'app e del pool. Cifrata SOLO per la chiave Android; inviata in copie/android/ del
# repository privato superbot-backups, con la deploy key di root gia' esistente, e riverificata da un clone NUOVO.
# NON usa per cifrare e NON modifica il recipient.txt di produzione (solo controllo in lettura, impronta
# uguale prima e dopo); NON applica retention; NON tocca archives/, servizi, Brain o mandato; NON decifra nulla.
# Uso (root): sh copia_android.sh /root/extbackup-strumenti
set -eu
TOOLS="$1"
WORK=/root/extbackup-android
REMOTE=git@github.com:alexiptv82/superbot-backups.git
SSH_KEY=/root/.ssh/superbot_backup_ed25519
KNOWN=/opt/superbot-extbackup/known_hosts
PROD_RECIPIENT=/opt/superbot-extbackup/recipient.txt
APPROVED_KEY=age142uj5c8xx4d9csj2dsy2uvda6e0kt9y8xln3xpetemzhts6ljaqq40qy6u
ANDROID_KEY=age1kpdfwmlpjmmwre34kg5zpdjlrc3kjw7syymzax8tg2jm892wa5sqnzc9nm
[ "$(id -u)" = 0 ] || { echo "NO-GO: serve root"; exit 2; }
for f in "$SSH_KEY" "$KNOWN" "$PROD_RECIPIENT" "$TOOLS/copia_aggiuntiva.py" "$TOOLS/external_backup.py" "$TOOLS/backup_app_db.py"; do
  [ -f "$f" ] && [ ! -L "$f" ] || { echo "NO-GO: manca $f"; exit 2; }
done
# il recipient.txt di produzione si controlla SOLO in lettura: deve restare la sola chiave approvata, invariato
PROD_SHA=$(sha256sum "$PROD_RECIPIENT" | cut -d' ' -f1)
KEYS=$(grep -E '^age1[0-9a-z]{58}$' "$PROD_RECIPIENT" || true)
[ "$KEYS" = "$APPROVED_KEY" ] || { echo "NO-GO: il recipient.txt di produzione non e' la sola chiave approvata"; exit 2; }
case "$(systemctl is-active superbot-extbackup.service 2>/dev/null || true)" in
  active|activating) echo "NO-GO: il backup periodico e' in esecuzione: riprovare dopo"; exit 2 ;;
esac

REQUIRED_V3="/opt/superbot-v3-paper-runs/brain-v3-paper20261111
/opt/superbot-ai-arena-paper/deepseek/brain-deepseek-paper20261118
/opt/superbot-ai-arena-paper/qwen/brain-qwen-paper20261118
/opt/superbot-ai-arena-paper/minimax/brain-minimax-paper20261118"
APP_DB=/opt/superbot/data/superbot.db
POOL_DB=/opt/superbot-pool-data/pool.db
for d in $REQUIRED_V3; do
  [ -d "$d" ] && [ ! -L "$d" ] && [ -f "$d/journal.db" ] || { echo "NO-GO: run V3 obbligatoria mancante o senza journal.db: $d"; exit 1; }
done
for f in "$APP_DB" "$POOL_DB"; do [ -f "$f" ] || { echo "NO-GO: database mancante: $f"; exit 1; }; done

echo "== inventario degli indispensabili"
SRC_BYTES=0
for d in $REQUIRED_V3 "$APP_DB" "$POOL_DB"; do
  b=$(du -sb "$d" | cut -f1); SRC_BYTES=$((SRC_BYTES + b))
  echo "$(du -sh "$d" | cut -f1)  $d"
done
NEED=$((SRC_BYTES * 6 + 1073741824))
AVAIL=$(df --output=avail -B1 /root | tail -1 | tr -d ' ')
echo "== spazio VPS: sorgenti $((SRC_BYTES / 1048576)) MiB, necessari $((NEED / 1048576)) MiB, disponibili $((AVAIL / 1048576)) MiB"
[ "$AVAIL" -gt "$NEED" ] || { echo "NO-GO: spazio insufficiente"; exit 1; }

umask 077
mkdir -p -m 700 "$WORK"
LOG="$WORK/copia-android-$(date -u +%Y%m%dT%H%M%SZ).log"
ARGS=""
for d in $REQUIRED_V3; do ARGS="$ARGS --required-v3-run-dir $d"; done
echo "== copia aggiuntiva cifrata SOLO per la chiave Android"
RC=0
# shellcheck disable=SC2086
python3 -I "$TOOLS/copia_aggiuntiva.py" --tools "$TOOLS" --label android --recipient "$ANDROID_KEY" \
  --forbidden-recipient "$APPROVED_KEY" --root /opt/superbot-desk-data --app-db "$APP_DB" --pool-db "$POOL_DB" \
  --work "$WORK/lavoro" --remote "$REMOTE" --ssh-key "$SSH_KEY" --known-hosts "$KNOWN" $ARGS > "$LOG" 2>&1 || RC=$?
grep -E "storico run|RISULTATO|archivi originali|ERRORE" "$LOG" || true
[ "$(sha256sum "$PROD_RECIPIENT" | cut -d' ' -f1)" = "$PROD_SHA" ] || { echo "ALLARME: recipient.txt di produzione cambiato durante l'operazione"; exit 1; }
echo "recipient.txt di produzione invariato: $PROD_SHA"
[ "$RC" = 0 ] || { echo "NO-GO: copia aggiuntiva non riuscita (registro $LOG)"; exit 1; }
echo "ESITO: COPIA ANDROID DEGLI INDISPENSABILI INVIATA E VERIFICATA DA UN CLONE NUOVO (ripristino da fare su Termux)"
