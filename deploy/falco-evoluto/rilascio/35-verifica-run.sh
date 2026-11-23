#!/bin/sh
# Verifica dei journal delle due run riusate con il codice appena installato: catena di hash integra, nessuna
# apertura o chiusura registrata (solo la preparazione). Sola lettura. Uso: sh 35-verifica-run.sh <sha>
set -eu
. "$(dirname "$0")/comune.sh"
STAGE=$(stage_of "${1:-}")
[ "$(id -u)" = 0 ] || nogo "serve root"
for spec in "$F_DIR:$F_ID" "$S_DIR:$S_ID"; do
  d=${spec%%:*}; id=${spec#*:}
  (cd "$STAGE" && DESK_MODE=paper PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 "$PY" -c "
import sqlite3, sys
from backend.v3.events import EventJournal
path = '$PARENT/$d/journal.db'
j = EventJournal(path)
j.verify_chain()
kinds = [r.event.kind for r in j.list_run('brain', '$id')]
bad = [k for k in kinds if k in ('paper_open', 'paper_close')]
print('journal %s: %d eventi, catena integra, aperture/chiusure: %d' % ('$id', len(kinds), len(bad)))
sys.exit(0 if 'run_prepared' in kinds and not bad else 1)") || nogo "$d: journal non integro o con operazioni"
done
echo "PASS  journal delle due run integri e senza operazioni (conservati, non ricreati)"
