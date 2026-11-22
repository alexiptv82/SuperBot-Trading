#!/bin/sh
# CONTROLLI in sola lettura. Uso: sh 30-controlli.sh [tutti|uscite]
# Il battito del runner riporta UN solo motivo (prima il mandato): la salute delle uscite si legge QUI direttamente,
# separata dal motivo del runner (blocco per mandato assente != blocco per uscite non sane).
set -eu
. "$(dirname "$0")/comune.sh"
STAGE=$(systemctl show -p WorkingDirectory --value "$U_EXIT" 2>/dev/null || true)
[ -n "$STAGE" ] && [ -d "$STAGE" ] || nogo "cartella del codice non trovata (unita' $U_EXIT)"
cd "$STAGE"
DESK_MODE=paper PYTHONPATH=. "$PY" "$(cd "$(dirname "$0")" && pwd)/controlli.py" "$RUN" "$RUN_ID" "${1:-tutti}"
