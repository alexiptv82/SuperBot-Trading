#!/bin/sh
# SuperBot - backup esterno cifrato di FALCO/TORO verso il destinatario age V2 e il repository V2 (migrazione da V1).
#
# Gli archivi V1 (repository superbot-backups, destinatario V1) restano dove sono, separati e intatti: questo wrapper NON li
# tocca, NON scrive su quel repository e NON usa la sua chiave di deploy ne' il suo file dei destinatari. Il codice di backup e'
# quello classico invariato (external_backup.py), eseguito tramite external_backup_multi.py che aggiunge soltanto i destinatari
# multipli e il RIFIUTO se l'impronta dei destinatari non e' quella approvata qui sotto (se il file sul server cambia, nessun
# archivio che nessuno sappia aprire).
#
# Stessa scelta della modalita' del cervello di /opt/superbot-extbackup/run.sh: --bot-stopped solo se docker DIMOSTRA che
# superbot-desk-hawk e superbot-desk-bull sono ENTRAMBI fermi; altrimenti percorso normale. Questa scelta e' solo comodita':
# l'autorita' resta backup_brain.py. Non scrive nulla, non ferma e non avvia nessun servizio.
#
# Esecuzione pianificata (SUPERBOT_V2_SCHEDULED=1, impostata dall'unita' systemd): rifiutata se manca
# /opt/superbot-extbackup-v2/timer-gate.json, scritto dall'installatore solo dopo la prova di un backup V2 reale e di un
# ripristino indipendente.
#
# Unica opzione ammessa: --print-mode (stampa "bot-stopped" oppure "normale" ed esce, senza fare il backup).
case "${1:-}" in
  "" | --print-mode) ;;
  *) echo "uso: run-classic.sh [--print-mode]" >&2; exit 2 ;;
esac
if [ "${SUPERBOT_V2_SCHEDULED:-}" = 1 ] && [ ! -f /opt/superbot-extbackup-v2/timer-gate.json ]; then
  echo "RIFIUTATO (timer_gate_missing): esecuzione pianificata senza la prova di un backup V2 reale e di un ripristino indipendente" >&2
  exit 1
fi
MODE=bot-stopped
for C in superbot-desk-hawk superbot-desk-bull; do
  R="$(timeout 30 docker inspect -f '{{.State.Running}}' "$C" 2>/dev/null)" || R=
  [ "$R" = false ] || MODE=normale
done
if [ "${1:-}" = "--print-mode" ]; then
  echo "$MODE"
  exit 0
fi
if [ "$MODE" = bot-stopped ]; then
  # con argparse serve la forma con "=" (--brain-arg --bot-stopped verrebbe letta come un'opzione)
  set -- --brain-arg=--bot-stopped --brain-retries 0
else
  set --
fi
exec /usr/bin/python3 -I /opt/superbot-tools/external_backup_multi.py \
  --expect-recipients-sha256 e3088c3f778d669a9c6751c1c20a7fbd6313a9a1d8a96910bc773152c108ef1b \
  --root /opt/superbot-desk-data --app-db /opt/superbot/data/superbot.db \
  --pool-db /opt/superbot-pool-data/pool.db --tools /opt/superbot-tools --work /opt/superbot-extbackup-v2/work \
  --remote git@github.com:alexiptv82/superbot-backups-v2.git --recipient-file /opt/superbot-extbackup-v2/recipients.txt \
  --ssh-key /root/.ssh/superbot_backup_v2_ed25519 --known-hosts /opt/superbot-extbackup/known_hosts "$@"
