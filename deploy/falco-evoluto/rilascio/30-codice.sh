#!/bin/sh
# Installa il codice del commit in una cartella NUOVA (git archive), verificata file per file. Uso: sh 30-codice.sh <sha>
set -eu
. "$(dirname "$0")/comune.sh"
SHA=${1:-}
[ "$(id -u)" = 0 ] || nogo "serve root"
export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=safe.directory GIT_CONFIG_VALUE_0='*'
STAGE=$(stage_of "$SHA")
[ ! -e "$STAGE" ] || nogo "$STAGE esiste gia'"
umask 022
mkdir "$STAGE"
git -C "$LAB" archive "$SHA" | tar -x -C "$STAGE"
T=$(mktemp -d); git -C "$LAB" archive "$SHA" | tar -x -C "$T"
diff -r "$T" "$STAGE" >/dev/null || { rm -rf "$T"; nogo "codice installato diverso dal commit"; }
rm -rf "$T"
chown -R root:root "$STAGE"
(cd "$STAGE" && PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 DESK_MODE=paper "$PY" -c \
  "import backend.v3.runner.wiring, backend.v3.runner.exit_worker, backend.v3.falco_evoluto, backend.v3.guardian, backend.v3.compare_view") \
  || nogo "il codice non si importa con $PY"
echo "PASS  codice $SHA in $STAGE (identico al commit, moduli importabili)"
