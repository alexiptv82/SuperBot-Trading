#!/usr/bin/env bash
# Ripartenza PAPER con il Brain unico da 2.000 USDT (24/11/2026): un solo comando root, con archivio e rollback.
#   1. impronte del pacchetto (SHA256SUMS, ancorato dal comando che lo lancia);
#   2. codice del commit in una cartella NUOVA (30-codice.sh: identico al commit, moduli importabili) e regole dei
#      contratti Bitget per i 27 mercati della configurazione;
#   3. ripartenza_brain.py: pausa, chiusura contabile delle posizioni aperte di Falco Evoluto e Brain Scalp, arresto,
#      archivio integrale, unita' sul codice nuovo (Falco Evoluto disattivato), run nuova da 2.000 con journal nuovo,
#      avvio, verifica, attivazione PAPER -> RUNNING. Brain RC1 non viene toccato;
#   4. web con la dashboard nuova (solo il Brain; Falco Evoluto e Scalp in Archivio) e interfaccia (70-interfaccia.sh);
#   5. controllo finale dal dominio.
# Uso (root): ripartenza.sh                    -> esegue
#             ripartenza.sh --rollback TIMBRO  -> interfaccia, web, unita' e run precedenti (in pausa); nulla si cancella
# Esito (ultima riga RIPARTENZA_RESULT=...): 0 Brain unico RUNNING e dashboard verificata; 2 rifiutata prima di cambiare
# (bot precedenti invariati); 3 ripartenza non eseguita, run precedenti ripristinate in pausa; 4 run nuova pronta ma in
# pausa (attivazione fallita, rollback disponibile); 5 Brain RUNNING ma dashboard non aggiornata o da verificare.
set -Eeuo pipefail
IFS=$'\n\t'
D="$(cd "$(dirname "$0")" && pwd)"
DOMAIN="superbot-trading.duckdns.org"
say(){ printf 'RIPARTENZA_%s\n' "$*"; }
end(){ say "RESULT=$2"; exit "$1"; }
[[ "$(id -u)" == 0 ]] || end 2 RIFIUTATA_SERVE_ROOT
cd "$D"
sha256sum --strict --quiet -c SHA256SUMS || end 2 RIFIUTATA_IMPRONTE_DEL_PACCHETTO
(cd ui && sha256sum --strict --quiet -c SHA256SUMS) || end 2 RIFIUTATA_IMPRONTE_INTERFACCIA
SHA="$(cat COMMIT)"; [[ "$SHA" =~ ^[0-9a-f]{40}$ ]] || end 2 RIFIUTATA_COMMIT
TAR="backend-${SHA:0:12}.tar"; TAR_SHA="$(sha256sum "$TAR" | cut -d' ' -f1)"
UI_SHA="$(sha256sum ui/SHA256SUMS | cut -d' ' -f1)"
# shellcheck disable=SC1091
. "$D/comune.sh"
NEW="$(stage_of "$SHA")"
STATE=/opt/superbot-v3-backups/paper-app-web
MARK="$STATE/interfaccia-attivata"

ui_web_rollback(){
  local rc=0
  if [[ -f "$MARK" ]]; then
    if bash "$D/70-interfaccia.sh" --rollback; then mv "$MARK" "$MARK.annullata-$(date -u +%Y%m%dT%H%M%SZ)"; else rc=1; fi
  fi
  python3 "$D/web_app_update.py" --rollback || rc=1
  return $rc
}

if [[ "${1:-}" == "--rollback" ]]; then
  [[ "${2:-}" =~ ^[0-9]{8}T[0-9]{6}Z$ ]] || end 2 RIFIUTATA_SERVE_IL_TIMBRO
  rc=0
  ui_web_rollback || rc=1
  (cd "$NEW" && DESK_MODE=paper PYTHONPATH="$NEW" PYTHONDONTWRITEBYTECODE=1 "$PY" "$D/ripartenza_brain.py" --rollback "$2") || rc=1
  [[ $rc == 0 ]] && end 0 ROLLBACK_COMPLETATO_RUN_PRECEDENTI_IN_PAUSA || end 5 ROLLBACK_DA_VERIFICARE
fi
[[ $# -eq 0 ]] || end 2 RIFIUTATA_ARGOMENTO

say "COMMIT=$SHA"
say "== 1/5 codice nuovo in $NEW"
if [[ -e "$NEW" ]]; then        # tentativo precedente: si riusa solo se identico al commit
  T="$(mktemp -d)"; export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=safe.directory GIT_CONFIG_VALUE_0='*'
  git -C "$LAB" archive "$SHA" | tar -x -C "$T"
  diff -r "$T" "$NEW" >/dev/null || { rm -rf "$T"; end 2 RIFIUTATA_CARTELLA_DEL_CODICE_ESISTENTE_E_DIVERSA; }
  rm -rf "$T"; say "codice gia' installato e identico al commit"
else
  sh "$D/30-codice.sh" "$SHA" || end 2 RIFIUTATA_INSTALLAZIONE_DEL_CODICE
fi
say "== 2/5 regole dei contratti Bitget per i mercati del Brain"
(cd "$NEW" && DESK_MODE=paper PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 "$PY" "$D/contratti_check.py" \
  "$D/runner_config_brain_unico_2000_paper.json") || end 2 RIFIUTATA_REGOLE_DEI_CONTRATTI

say "== 3/5 ripartenza: archivio delle run attuali e Brain unico PAPER 2000"
LOG="$(mktemp)"; rc=0
(cd "$NEW" && DESK_MODE=paper PYTHONPATH="$NEW" PYTHONDONTWRITEBYTECODE=1 "$PY" "$D/ripartenza_brain.py" --esegui \
  --stage "$NEW") 2>&1 | tee "$LOG" || rc=$?
TIMBRO="$(sed -n 's/^RIPARTENZA TIMBRO=//p' "$LOG" | tail -1)"; rm -f "$LOG"
case "$rc" in
  0|6) ;;
  3) end 2 RIFIUTATA_BOT_PRECEDENTI_INVARIATI_IN_PAUSA ;;
  4) end 3 RIPARTENZA_NON_ESEGUITA_RUN_PRECEDENTI_RIPRISTINATE_IN_PAUSA ;;
  *) end 4 "RUN_NUOVA_PRONTA_MA_IN_PAUSA_rollback:${TIMBRO:-vedi_registro}" ;;
esac
say "TIMBRO=$TIMBRO (rollback: bash $D/ripartenza.sh --rollback $TIMBRO)"

say "== 4/5 web e interfaccia: dashboard del Brain unico"
python3 "$D/web_app_update.py" --deploy --brain-unico --backend-tar "$D/$TAR" --tar-sha256 "$TAR_SHA" --sha "$SHA" \
  || end 5 BRAIN_RUNNING_MA_WEB_NON_AGGIORNATA
if ! bash "$D/70-interfaccia.sh" --activate --candidate "$D/ui" --manifest-sha "$UI_SHA"; then
  python3 "$D/web_app_update.py" --rollback || true
  end 5 BRAIN_RUNNING_MA_INTERFACCIA_NON_AGGIORNATA
fi
mkdir -p -m 700 "$STATE"
printf '%s %s\n' "$(date -u +%Y%m%dT%H%M%SZ)" "$UI_SHA" > "$MARK"

say "== 5/5 controllo finale dal dominio"
code(){ curl -sS --max-time 12 --resolve "$DOMAIN:443:127.0.0.1" -o /dev/null -w '%{http_code}' "https://$DOMAIN$1" 2>/dev/null || echo 000; }
T="$(mktemp)"
C="$(curl -sS --max-time 12 --resolve "$DOMAIN:443:127.0.0.1" -o "$T" -w '%{http_code}' "https://$DOMAIN/" 2>/dev/null || echo 000)"
IDX="$(sha256sum "$T" | cut -d' ' -f1)"; rm -f "$T"
WANT="$(sha256sum ui/index.html | cut -d' ' -f1)"
if [[ "$C" == 200 && "$IDX" == "$WANT" && "$(code /api/v3/compare)" == 401 && "$(code /api/v3/paper-archive)" == 401 \
      && "$(code /api/v3/compare/brain_scalp/trades)" == 401 && "$(code /api/health)" == 200 ]]; then
  say "INDEX_SHA256=$IDX"
  end 0 BRAIN_UNICO_PAPER_RUNNING_DASHBOARD_VERIFICATA
fi
say "controllo dal dominio fallito (index $C): ripristino interfaccia e web precedenti; il Brain resta RUNNING"
ui_web_rollback || true
end 5 BRAIN_RUNNING_DASHBOARD_DA_VERIFICARE
