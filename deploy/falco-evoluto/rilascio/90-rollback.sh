#!/bin/sh
# Rollback del rilascio: annulla SOLO i passi che il rilascio ha registrato come fatti, in ordine inverso.
# Interfaccia precedente, web e bridge precedenti, unita' nuove fermate (file spostati nel backup). Le due run, i loro
# journal e il codice installato restano (in pausa, mandato approved:false): nulla viene cancellato. RC1 non e' toccato.
set -u
D=$(cd "$(dirname "$0")" && pwd)
. "$D/comune.sh"
[ "$(id -u)" = 0 ] || nogo "serve root"
ST="$BACKUPS/rilascio.state"
[ -f "$ST" ] || { echo "nessun rilascio registrato: niente da annullare"; exit 0; }
done_step() { grep -qx "$1" "$ST"; }
RC=0
if done_step ui; then bash "$D/70-interfaccia.sh" --rollback || { RC=1; echo "ROLLBACK INTERFACCIA: VERIFICA MANUALE"; }; fi
if done_step web || done_step web_avviato; then
  python3 "$D/falco_scalp_web_cutover.py" --rollback || { RC=1; echo "ROLLBACK WEB/BRIDGE: VERIFICA MANUALE"; }; fi
if done_step unita || done_step unita_avviate; then
  KEEP="$BACKUPS/units-removed-$(date -u +%Y%m%dT%H%M%SZ)"; mkdir -p -m 700 "$KEEP"
  for u in "$U_F_RUN" "$U_S_RUN" "$U_F_EXIT" "$U_S_EXIT"; do
    systemctl stop "$u" 2>/dev/null || true
    [ -f "/etc/systemd/system/$u" ] && mv "/etc/systemd/system/$u" "$KEEP/"
  done
  systemctl daemon-reload
  echo "unita' nuove fermate; file conservati in $KEEP"
fi
mv "$ST" "$ST.rolled-back-$(date -u +%Y%m%dT%H%M%SZ)"
[ "$RC" = 0 ] && echo "ROLLBACK COMPLETATO: run e codice conservati (in pausa, mandato approved:false), RC1 invariato" \
  || echo "ROLLBACK CON PASSI DA VERIFICARE A MANO (vedi sopra)"
exit $RC
