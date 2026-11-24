#!/usr/bin/env bash
# App PAPER (Brain, Trade, Performance, Archivio): installazione unica con backup, verifiche e rollback automatico.
#   1. impronte del pacchetto (SHA256SUMS, ancorato dal comando root che lo lancia);
#   2. web: backend con le rotte GET nuove + archivio del reset in sola lettura (web_app_update.py: immagine candidata,
#      sonda sulle run VERE senza rete, scambio con il vecchio container conservato fermo, sonda dal vivo);
#   3. interfaccia: 70-interfaccia.sh (backup verificato, PWA preservata, controllo dal dominio, ritorno automatico);
#   4. controllo finale dal dominio. Se 3 o 4 falliscono: interfaccia e web tornano entrambe alla versione precedente.
# NON tocca: runner, uscite, bridge, journal, mandati, pause, strategie, Brain RC1, nginx, .env (verificato: le unita'
# del Brain e il bridge non vengono riavviati). 25/11: web del SOLO Brain unico; sonda dal vivo con la chiusura manuale.
# Uso (root): aggiorna_app.sh            -> installa
#             aggiorna_app.sh --rollback -> interfaccia e web precedenti (idempotente, nulla viene cancellato)
# Esito: ultima riga "APP_RESULT=..."; codice 0 = installata e verificata; 2 = rifiutata prima di cambiare qualcosa;
#        3 = web non aggiornata (gia' tornata alla precedente); 4 = interfaccia o controllo finale falliti, tutto
#        riportato alla versione precedente; 5 = rollback da verificare a mano.
set -Eeuo pipefail
IFS=$'\n\t'
D="$(cd "$(dirname "$0")" && pwd)"
DOMAIN="superbot-trading.duckdns.org"
say(){ printf 'APP_%s\n' "$*"; }
end(){ say "RESULT=$2"; exit "$1"; }
[[ "${PAPER_APP_TEST_MODE:-0}" == 1 || "$(id -u)" == 0 ]] || end 2 RIFIUTATA_SERVE_ROOT
cd "$D"
sha256sum --strict --quiet -c SHA256SUMS || end 2 RIFIUTATA_IMPRONTE_DEL_PACCHETTO
SHA="$(cat COMMIT)"; [[ "$SHA" =~ ^[0-9a-f]{40}$ ]] || end 2 RIFIUTATA_COMMIT
TAR="backend-${SHA:0:12}.tar"; TAR_SHA="$(sha256sum "$TAR" | cut -d' ' -f1)"
UI_SHA="$(sha256sum ui/SHA256SUMS | cut -d' ' -f1)"
(cd ui && sha256sum --strict --quiet -c SHA256SUMS) || end 2 RIFIUTATA_IMPRONTE_INTERFACCIA

STATE="${PAPER_APP_STATE:-/opt/superbot-v3-backups/paper-app-web}"
MARK="$STATE/interfaccia-attivata"
# L'interfaccia torna indietro SOLO se l'ha attivata questo pacchetto (marcatore): altrimenti --rollback di
# 70-interfaccia.sh riporterebbe indietro la versione servita ora.
rollback(){
  local rc=0
  if [[ -f "$MARK" ]]; then
    if bash "$D/70-interfaccia.sh" --rollback; then mv "$MARK" "$MARK.annullata-$(date -u +%Y%m%dT%H%M%SZ)"; else rc=1; fi
  else
    say "interfaccia: nessuna attivazione registrata da annullare"
  fi
  python3 "$D/web_app_update.py" --rollback || rc=1
  return $rc
}

if [[ "${1:-}" == "--rollback" ]]; then
  rollback && end 0 ROLLBACK_COMPLETATO || end 5 ROLLBACK_DA_VERIFICARE
fi
[[ $# -eq 0 ]] || end 2 RIFIUTATA_ARGOMENTO

UNITS=(superbot-brain-scalp-p1-exit.service superbot-brain-scalp-p1-runner.service superbot-v3-paper-single-close-bridge.service)
units_state(){ [[ "${PAPER_APP_TEST_MODE:-0}" == 1 ]] && { echo test; return; }
  for u in "${UNITS[@]}"; do systemctl show -p ActiveState,ActiveEnterTimestampMonotonic,MainPID --value "$u" | tr '\n' ' '; done; }
BEFORE="$(units_state)"
say "COMMIT=$SHA"
say "== 1/3 web: backend con le rotte dell'app e archivio in sola lettura (Brain unico)"
python3 "$D/web_app_update.py" --deploy --brain-unico --backend-tar "$D/$TAR" --tar-sha256 "$TAR_SHA" --sha "$SHA" \
  || end 3 WEB_NON_AGGIORNATA_TORNATA_ALLA_PRECEDENTE

say "== 2/3 interfaccia"
if ! bash "$D/70-interfaccia.sh" --activate --candidate "$D/ui" --manifest-sha "$UI_SHA"; then
  say "interfaccia non attivata: rimetto anche la web precedente"
  python3 "$D/web_app_update.py" --rollback && end 4 INTERFACCIA_FALLITA_TUTTO_RIPRISTINATO || end 5 ROLLBACK_DA_VERIFICARE
fi
mkdir -p -m 700 "$STATE"
printf '%s %s\n' "$(date -u +%Y%m%dT%H%M%SZ)" "$UI_SHA" > "$MARK"

say "== 3/3 controllo finale dal dominio"
code(){ curl -sS --max-time 12 --resolve "$DOMAIN:443:127.0.0.1" -o /dev/null -w '%{http_code}' "https://$DOMAIN$1" 2>/dev/null || echo 000; }
T="$(mktemp)"
C="$(curl -sS --max-time 12 --resolve "$DOMAIN:443:127.0.0.1" -o "$T" -w '%{http_code}' "https://$DOMAIN/" 2>/dev/null || echo 000)"
IDX="$(sha256sum "$T" | cut -d' ' -f1)"; rm -f "$T"
WANT="$(sha256sum ui/index.html | cut -d' ' -f1)"
if [[ "$C" == 200 && "$IDX" == "$WANT" && "$(code /api/v3/compare)" == 401 && "$(code /api/v3/paper-archive)" == 401 \
      && "$(code /api/v3/compare/brain_scalp/trades)" == 401 && "$(code /api/health)" == 200 ]]; then
  say "INDEX_SHA256=$IDX"
  if [[ "$(units_state)" != "$BEFORE" ]]; then
    say "ATTENZIONE: stato delle unita' del Brain o del bridge cambiato durante l'aggiornamento: verificare"
    end 5 WEB_AGGIORNATA_UNITA_DA_VERIFICARE
  fi
  say "BRAIN=runner, uscite e bridge di chiusura non riavviati"
  end 0 APP_PAPER_INSTALLATA_E_VERIFICATA
fi
say "controllo finale fallito (index $C, atteso $WANT): ripristino interfaccia e web precedenti"
rollback && end 4 CONTROLLO_FINALE_FALLITO_TUTTO_RIPRISTINATO || end 5 ROLLBACK_DA_VERIFICARE
