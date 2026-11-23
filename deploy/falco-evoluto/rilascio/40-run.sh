#!/bin/sh
# Crea le DUE run nuove in pausa, mandato approved:false, journal verificato (prepare_paper_run). Uso: sh 40-run.sh <sha>
set -eu
. "$(dirname "$0")/comune.sh"
STAGE=$(stage_of "${1:-}")
[ "$(id -u)" = 0 ] || nogo "serve root"
prep() {  # cartella run_id configurazione capitale
  (cd "$STAGE" && DESK_MODE=paper PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 "$PY" -m backend.v3.runner.prepare_paper_run \
    --parent "$PARENT" --run-name "$1" --run-id "$2" --config "$STAGE/backend/v3/runner/$3" \
    --prepare-paper-paused --expected-initial-equity "$4") || nogo "preparazione di $1"
  R="$PARENT/$1"
  [ -f "$R/pause.flag" ] && [ -f "$R/PREPARED_PAUSED_ONLY.json" ] || nogo "$1 non in pausa"
  "$PY" -c "import json,sys; m=json.load(open('$R/mandate.json')); sys.exit(0 if m.get('approved') is False and m.get('run_id')=='$2' else 1)" \
    || nogo "$1: mandato non approved:false"
  cmp -s "$R/runner_config.json" "$STAGE/backend/v3/runner/$3" || nogo "$1: configurazione diversa dal commit"
  echo "PASS  run $1 ($2): in pausa, mandato approved:false, capitale $4"
}
prep "$F_DIR" "$F_ID" "$F_CFG" "$F_EQ"
prep "$S_DIR" "$S_ID" "$S_CFG" "$S_EQ"
