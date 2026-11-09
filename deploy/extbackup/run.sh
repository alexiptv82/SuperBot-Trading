#!/bin/sh
# SuperBot - avvio del backup esterno cifrato.
# Chiamato da superbot-extbackup.service (ExecStart) e dall'azione "run" del workflow sg-extbackup.
#
# Ad ogni esecuzione sceglie la modalita' del backup del cervello:
#   - docker DIMOSTRA che superbot-desk-hawk e superbot-desk-bull esistono e sono ENTRAMBI fermi
#       -> si passa --bot-stopped a backup_brain.py (non c'e' piu' un confine di ciclo da aspettare);
#          niente nuovi tentativi da 5 minuti (--brain-retries 0): un container attivo non diventa fermo aspettando;
#   - in ogni altro caso (container attivo, assente, docker che non risponde) -> percorso NORMALE, come prima.
#
# Questa scelta e' solo comodita': l'autorita' resta backup_brain.py, che rifiuta da solo --bot-stopped se un
# container risulta attivo, se docker non e' utilizzabile o se il battito e' ancora fresco, e ricontrolla il fermo
# anche a copia finita. Questo file non scrive nulla, non ferma e non avvia nessun servizio.
#
# Unica opzione ammessa: --print-mode (stampa "bot-stopped" oppure "normale" ed esce, senza fare il backup).
case "${1:-}" in
  "" | --print-mode) ;;
  *) echo "uso: run.sh [--print-mode]" >&2; exit 2 ;;
esac
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
  # attenzione: con argparse serve la forma con "=" (--brain-arg --bot-stopped verrebbe letta come un'opzione)
  set -- --brain-arg=--bot-stopped --brain-retries 0
else
  set --
fi
exec /usr/bin/python3 -I /opt/superbot-tools/external_backup.py \
  --root /opt/superbot-desk-data --app-db /opt/superbot/data/superbot.db \
  --pool-db /opt/superbot-pool-data/pool.db --tools /opt/superbot-tools --work /opt/superbot-extbackup \
  --remote git@github.com:alexiptv82/superbot-backups.git --recipient-file /opt/superbot-extbackup/recipient.txt \
  --ssh-key /root/.ssh/superbot_backup_ed25519 --known-hosts /opt/superbot-extbackup/known_hosts "$@"
