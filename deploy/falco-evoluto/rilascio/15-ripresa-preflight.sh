#!/bin/sh
# Preflight della RIPRESA, in sola lettura: le due run del primo tentativo devono ESISTERE ed essere intatte (le si
# riusa, mai ricreate); tutto il resto come il preflight del rilascio. Uso: sh 15-ripresa-preflight.sh <sha> <UI> <sha UI>
set -eu
. "$(dirname "$0")/comune.sh"
SHA=${1:-}; UI=${2:-}; UISHA=${3:-}
[ "$(id -u)" = 0 ] || nogo "serve root"
printf '%s' "$SHA" | grep -Eq '^[0-9a-f]{40}$' || nogo "commit non valido"
export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=safe.directory GIT_CONFIG_VALUE_0='*'
git -C "$LAB" cat-file -e "$SHA^{commit}" 2>/dev/null || nogo "commit $SHA assente in $LAB"
STAGE=$(stage_of "$SHA")
[ ! -e "$STAGE" ] || nogo "$STAGE esiste gia'"
run_ok() {  # cartella run_id configurazione
  R="$PARENT/$1"
  [ -d "$R" ] && [ ! -L "$R" ] || nogo "run $1 assente: la ripresa non la ricrea"
  for f in journal.db budget.db runner_config.json mandate.json PREPARED_PAUSED_ONLY.json pause.flag; do
    [ -f "$R/$f" ] && [ ! -L "$R/$f" ] || nogo "$1: $f assente"; done
  "$PY" -c "
import json, sys
m = json.load(open('$R/mandate.json')); k = json.load(open('$R/PREPARED_PAUSED_ONLY.json'))
sys.exit(0 if m.get('approved') is False and m.get('run_id') == '$2' and k.get('run_id') == '$2'
         and k.get('paper_only') is True and k.get('mandate_approved') is False else 1)" \
    || nogo "$1: mandato o marcatore non coerenti (approved:false, run $2)"
  WANT=$("$PY" -c "import json; print(json.load(open('$R/PREPARED_PAUSED_ONLY.json'))['config_sha256'])")
  [ "$(sha256sum "$R/runner_config.json" | cut -d' ' -f1)" = "$WANT" ] || nogo "$1: configurazione cambiata dopo la preparazione"
  [ "$(git -C "$LAB" show "$SHA:backend/v3/runner/$3" | sha256sum | cut -d' ' -f1)" = "$WANT" ] \
    || nogo "$1: la configurazione del commit $SHA non e' quella della run"
  [ ! -e "$R/close_request.json" ] || nogo "$1: richiesta di chiusura pendente"
  echo "PASS  run $1 ($2) intatta: in pausa, mandato approved:false, configurazione = commit"
}
run_ok "$F_DIR" "$F_ID" "$F_CFG"
run_ok "$S_DIR" "$S_ID" "$S_CFG"
for u in "$U_F_EXIT" "$U_F_RUN" "$U_S_EXIT" "$U_S_RUN"; do [ ! -e "/etc/systemd/system/$u" ] || nogo "$u esiste gia'"; done
[ -x "$PY" ] || nogo "interprete $PY assente"
for u in "$RC1_EXIT" superbot-v3-paper-single-close-bridge.service; do
  [ "$(systemctl is-active "$u")" = active ] || nogo "$u non attiva"; done
grep -q V3_BRIDGE_EXTRA_RUNS /etc/systemd/system/superbot-v3-paper-single-close-bridge.service \
  && nogo "il bridge ha gia' le run aggiuntive: eseguire prima il rollback"
docker inspect superbot --format '{{.State.Running}}' 2>/dev/null | grep -qx true || nogo "web superbot non in esecuzione"
[ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 8 http://127.0.0.1:8002/api/health)" = 200 ] || nogo "web non sana"
docker inspect superbot-before-falco-scalp-web >/dev/null 2>&1 && nogo "container di backup di un tentativo precedente presente"
[ -f "$UI/SHA256SUMS" ] && [ "$(sha256sum "$UI/SHA256SUMS" | cut -d' ' -f1)" = "$UISHA" ] || nogo "build UI assente o diversa"
(cd "$UI" && sha256sum --strict --quiet -c SHA256SUMS) || nogo "file della build UI alterati"
[ -f "$AIENV" ] && grep -q '^DEEPSEEK_API_KEY=.' "$AIENV" || nogo "chiave DeepSeek assente in $AIENV"
FREE=$(df -Pk /opt | awk 'NR==2{print $4}'); [ "$FREE" -gt 2000000 ] || nogo "spazio su /opt sotto 2 GB"
echo "PASS  preflight della ripresa: run intatte, unita' nuove assenti, RC1 uscite attive, bridge e web come prima"
