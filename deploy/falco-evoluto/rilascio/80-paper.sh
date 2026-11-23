#!/bin/sh
# Comandi del proprietario per UNA delle due run (root). NON eseguito dal rilascio.
#   sh 80-paper.sh falco|scalp stato               sola lettura
#   sh 80-paper.sh falco|scalp attiva "<Nome>"     verifica, approva il mandato della run, toglie la pausa
#   sh 80-paper.sh falco|scalp pausa               nessuna nuova apertura; uscite e chiusure manuali proseguono
#   sh 80-paper.sh falco|scalp riprendi            toglie la pausa (mandato valido e uscite sane)
#   sh 80-paper.sh falco|scalp revoca              pausa + mandato approved:false (le posizioni restano gestite)
# Non tocca configurazione, rischio, modello, simboli, budget, Guardian ne' l'altra run.
set -eu
D=$(cd "$(dirname "$0")" && pwd)
. "$D/comune.sh"
case "${1:-}" in
  falco) RUN=$PARENT/$F_DIR; ID=$F_ID; UE=$U_F_EXIT; UR=$U_F_RUN ;;
  scalp) RUN=$PARENT/$S_DIR; ID=$S_ID; UE=$U_S_EXIT; UR=$U_S_RUN ;;
  *) nogo "indicare falco oppure scalp" ;;
esac
ACT="${2:-stato}"
[ "$(id -u)" = 0 ] || nogo "serve root"
[ -d "$RUN" ] && [ -f "$RUN/journal.db" ] || nogo "run assente"
STAGE=$(systemctl show -p WorkingDirectory --value "$UE")
[ -n "$STAGE" ] && [ -d "$STAGE/backend" ] || nogo "codice della run non trovato"
check() { (cd "$STAGE" && DESK_MODE=paper PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 "$PY" "$D/controlli.py" "$RUN" "$ID" "$1"); }
pycheck() {
  (cd "$STAGE" && DESK_MODE=paper PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 "$PY" -c "
import sys
from pathlib import Path
from backend.v3.runner.config import load_runner_config
from backend.v3.runner.wiring import MandateFile
run = Path('$RUN'); conf = load_runner_config((run / 'runner_config.json').read_bytes())
p = MandateFile(run / 'mandate.json', conf.risk_policy, '$ID').problem()
print('mandato:', 'VALIDO' if p is None else p); sys.exit(0 if p is None else 1)")
}
write_mandate() {  # true|false nome ; scrittura atomica a partire dal mandato creato dalla preparazione
  "$PY" - "$RUN/mandate.json" "$1" "$2" <<'PY'
import json, os, sys, tempfile
dst, ok, who = sys.argv[1], sys.argv[2] == "true", sys.argv[3]
m = json.load(open(dst))
m["approved"], m["approved_by"] = ok, (who if ok else "")
fd, tmp = tempfile.mkstemp(dir=os.path.dirname(dst), prefix=".mandate.")
with os.fdopen(fd, "w") as f:
    json.dump(m, f, sort_keys=True, separators=(",", ":")); f.flush(); os.fsync(f.fileno())
os.chmod(tmp, 0o600); os.replace(tmp, dst)
PY
}
pause_on() { [ -f "$RUN/pause.flag" ] || { printf 'pausa del proprietario %s\n' "$(date -u +%FT%TZ)" > "$RUN/pause.flag.tmp" && mv "$RUN/pause.flag.tmp" "$RUN/pause.flag"; }; }
preflight() {
  for u in "$UE" "$UR"; do [ "$(systemctl is-active "$u")" = active ] || nogo "$u non attiva"; done
  check uscite >/dev/null || nogo "servizio delle uscite NON sano"
  WANT=$("$PY" -c "import json; print(json.load(open('$RUN/PREPARED_PAUSED_ONLY.json'))['config_sha256'])")
  printf '%s  %s\n' "$WANT" "$RUN/runner_config.json" | sha256sum --strict -c - >/dev/null || nogo "configurazione cambiata"
  [ -f "$AIENV" ] && grep -q '^DEEPSEEK_API_KEY=.' "$AIENV" || nogo "chiave DeepSeek assente"
  [ "$(systemctl show -p Environment --value "$UR" | tr ' ' '\n' | grep -c '^DESK_MODE=paper$')" = 1 ] || nogo "runner non in PAPER"
  echo "PASS  uscite sane, configurazione invariata (impronta del marcatore), chiave presente, PAPER"
}
case "$ACT" in
  stato) check tutti || true; [ -f "$RUN/pause.flag" ] && echo "pausa: ATTIVA" || echo "pausa: no"; pycheck || true ;;
  attiva)
    WHO="${3:-}"
    printf '%s' "$WHO" | grep -Eq '^[A-Za-z][A-Za-z .-]{1,40}$' || nogo "serve il nome di chi approva"
    preflight; pause_on; write_mandate true "$WHO"
    pycheck || { write_mandate false ""; nogo "mandato non valido: ripristinato approved:false"; }
    rm -f "$RUN/pause.flag"
    echo "PAPER ATTIVO ($ID): mandato approvato da $WHO, pausa tolta. Pausa: sh $D/80-paper.sh $1 pausa" ;;
  pausa) pause_on; echo "PAUSA ATTIVA ($ID): nessuna nuova apertura; uscite e chiusure manuali proseguono" ;;
  riprendi) preflight; pycheck || nogo "mandato non valido"; rm -f "$RUN/pause.flag"; echo "PAUSA TOLTA ($ID)" ;;
  revoca) pause_on; write_mandate false ""; pycheck || true; echo "REVOCATO ($ID): pausa e mandato approved:false" ;;
  *) nogo "comando sconosciuto: $ACT" ;;
esac
