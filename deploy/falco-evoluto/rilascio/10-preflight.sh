#!/bin/sh
# Preflight in SOLA LETTURA: nessuna scrittura. Uso: sh 10-preflight.sh <commit 40 hex> <cartella UI> <sha256 SHA256SUMS>
set -eu
. "$(dirname "$0")/comune.sh"
SHA=${1:-}; UI=${2:-}; UISHA=${3:-}
[ "$(id -u)" = 0 ] || nogo "serve root"
printf '%s' "$SHA" | grep -Eq '^[0-9a-f]{40}$' || nogo "commit non valido"
export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=safe.directory GIT_CONFIG_VALUE_0='*'
git -C "$LAB" cat-file -e "$SHA^{commit}" 2>/dev/null || nogo "commit $SHA assente in $LAB"
STAGE=$(stage_of "$SHA")
[ ! -e "$STAGE" ] || nogo "$STAGE esiste gia'"
for d in "$F_DIR" "$S_DIR"; do [ ! -e "$PARENT/$d" ] || nogo "run $d esiste gia' (non la sovrascrivo)"; done
for u in "$U_F_EXIT" "$U_F_RUN" "$U_S_EXIT" "$U_S_RUN"; do [ ! -e "/etc/systemd/system/$u" ] || nogo "$u esiste gia'"; done
[ -x "$PY" ] || nogo "interprete $PY assente"
[ -d "$PARENT" ] && [ ! -L "$PARENT" ] || nogo "$PARENT assente"
for u in "$RC1_EXIT" superbot-v3-paper-single-close-bridge.service; do
  [ "$(systemctl is-active "$u")" = active ] || nogo "$u non attiva"; done
docker inspect superbot --format '{{.State.Running}}' 2>/dev/null | grep -qx true || nogo "web superbot non in esecuzione"
[ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 8 http://127.0.0.1:8002/api/health)" = 200 ] || nogo "web non sana"
docker inspect superbot-before-falco-scalp-web >/dev/null 2>&1 && nogo "container di backup di un rilascio precedente presente"
[ -f "$UI/SHA256SUMS" ] && [ "$(sha256sum "$UI/SHA256SUMS" | cut -d' ' -f1)" = "$UISHA" ] || nogo "build UI assente o diversa"
(cd "$UI" && sha256sum --strict --quiet -c SHA256SUMS) || nogo "file della build UI alterati"
if [ -f "$AIENV" ] && grep -q '^DEEPSEEK_API_KEY=.' "$AIENV"; then echo "PASS  chiave DeepSeek presente (valore non letto)"
else nogo "chiave DeepSeek assente in $AIENV"; fi
FREE=$(df -Pk /opt | awk 'NR==2{print $4}'); [ "$FREE" -gt 2000000 ] || nogo "spazio su /opt sotto 2 GB"
echo "PASS  preflight: commit $SHA, run e unita' nuove assenti, RC1 uscite attive, bridge e web sani, build UI verificata"
