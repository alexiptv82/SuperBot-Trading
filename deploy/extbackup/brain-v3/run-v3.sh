#!/bin/sh
# SuperBot - avvio del backup esterno cifrato di Brain V3. AFFIANCA run.sh di Falco/Toro (non lo sostituisce, non lo chiama).
#
#   run-v3.sh [--mode v3|brain-free] [--plan | --preflight | altre opzioni di external_backup_brain_v3.py]
#
# --mode v3 (predefinito): certifica e copia le cartelle /opt/superbot-v3-paper-runs/brain-v3-* (sola lettura) e le invia cifrate.
# --mode brain-free      : copia certificata del solo database storico Brain Free, famiglia separata, da lanciare a mano.
# --plan                 : prova locale completa senza rete e senza invio.   --preflight : controlli di sola lettura.
#
# Usa SOLO in lettura il destinatario, la chiave di deploy e il known_hosts gia' presenti per il backup di Falco/Toro;
# scrive solo in /opt/superbot-extbackup-v3. Non ferma, non avvia e non riavvia nessun servizio o container.
MODE=v3
if [ "${1:-}" = "--mode" ]; then
  MODE="${2:-}"
  [ $# -ge 2 ] && shift 2 || shift
fi
case "$MODE" in
  v3 | brain-free) ;;
  *) echo "uso: run-v3.sh [--mode v3|brain-free] [--plan | --preflight]" >&2; exit 2 ;;
esac
exec /usr/bin/python3 -I /opt/superbot-tools/external_backup_brain_v3.py --mode "$MODE" \
  --runs-root /opt/superbot-v3-paper-runs --legacy-db /opt/superbot-brain-free/brain.sqlite3 \
  --work /opt/superbot-extbackup-v3 --tools /opt/superbot-tools \
  --remote git@github.com:alexiptv82/superbot-backups.git --recipient-file /opt/superbot-extbackup/recipient.txt \
  --ssh-key /root/.ssh/superbot_backup_ed25519 --known-hosts /opt/superbot-extbackup/known_hosts "$@"
