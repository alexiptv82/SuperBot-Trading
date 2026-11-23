#!/bin/sh
# Comandi del proprietario per la run PAPER Brain Unico (root). NON viene eseguito dall'installazione.
#   sh 80-paper.sh stato                 sola lettura: uscite, runner, mandato, pausa, spesa, aperture
#   sh 80-paper.sh attiva "<Nome>"       verifica le condizioni d'avvio, approva il mandato, toglie la pausa
#   sh 80-paper.sh pausa                 nessun nuovo giro del Brain; le uscite e il tasto Chiudi continuano
#   sh 80-paper.sh riprendi              toglie la pausa (solo con mandato valido e uscite sane)
#   sh 80-paper.sh revoca                pausa + mandato approved:false (rollback dell'avvio; uscite attive)
# Non tocca configurazione, rischio, modello, simboli o budget (impronta verificata), ne' altre run.
set -eu
. "$(dirname "$0")/comune.sh"
D=$(cd "$(dirname "$0")" && pwd)
STAGE=/opt/superbot-brain-unico-3440340289fd
AIENV=/etc/superbot-v3-paper/brain-ai.env
TEMPLATE="$STAGE/backend/v3/runner/mandate_brain_unico_paper_b.TEMPLATE.json"
ACT="${1:-stato}"
[ "$(id -u)" = 0 ] || nogo "serve root"
[ -d "$RUN" ] && [ -f "$RUN/journal.db" ] || nogo "run assente"
pycheck() {  # mandato valido con la policy VERA della configurazione (stesso controllo del runner)
  (cd "$STAGE" && DESK_MODE=paper PYTHONPATH="$STAGE" PYTHONDONTWRITEBYTECODE=1 "$PY" -c "
import sys
from pathlib import Path
from backend.v3.runner.config import load_runner_config
from backend.v3.runner.wiring import MandateFile
run = Path('$RUN'); conf = load_runner_config((run / 'runner_config.json').read_bytes())
p = MandateFile(run / 'mandate.json', conf.risk_policy, '$RUN_ID').problem()
print('mandato:', 'VALIDO' if p is None else p); sys.exit(0 if p is None else 1)")
}
write_mandate() {  # $1 = true|false, $2 = approvato da ; scrittura atomica partendo dal modello del commit
  "$PY" - "$TEMPLATE" "$RUN/mandate.json" "$1" "$2" <<'PY'
import json, os, sys, tempfile
tpl, dst, ok, who = sys.argv[1], sys.argv[2], sys.argv[3] == "true", sys.argv[4]
m = json.load(open(tpl))
m["approved"], m["approved_by"] = ok, (who if ok else "")
fd, tmp = tempfile.mkstemp(dir=os.path.dirname(dst), prefix=".mandate.")
with os.fdopen(fd, "w") as f:
    json.dump(m, f, indent=2, ensure_ascii=False); f.flush(); os.fsync(f.fileno())
os.chmod(tmp, 0o600); os.replace(tmp, dst)
PY
}
pause_on() { [ -f "$RUN/pause.flag" ] || { printf 'pausa del proprietario %s\n' "$(date -u +%FT%TZ)" > "$RUN/pause.flag.tmp" && mv "$RUN/pause.flag.tmp" "$RUN/pause.flag"; }; }
preflight() {
  for u in "$U_EXIT" "$U_RUN"; do [ "$(systemctl is-active "$u")" = active ] || nogo "$u non attiva"; done
  sh "$D/30-controlli.sh" uscite >/dev/null || nogo "servizio delle uscite NON sano (feed o monitor)"
  echo "PASS  PAPER isolato: DESK_MODE=paper nelle unita', run con marcatore paper_only"
  printf '%s  %s\n' "$CFG_SHA" "$RUN/runner_config.json" | sha256sum --strict -c - >/dev/null || nogo "configurazione cambiata"
  echo "PASS  limiti di rischio = profilo B (impronta $CFG_SHA; policy legata dal mandato)"
  echo "PASS  servizio delle uscite sano (lease, battito, monitor con prezzi di mercato recenti)"
  [ -f "$AIENV" ] && grep -q '^DEEPSEEK_API_KEY=.' "$AIENV" || nogo "chiave DeepSeek assente in $AIENV"
  echo "PASS  chiave DeepSeek presente (valore non letto)"
  [ "$(systemctl show -p Environment --value "$U_RUN" | tr ' ' '\n' | grep -c '^DESK_MODE=paper$')" = 1 ] || nogo "runner non in PAPER"
}
case "$ACT" in
  stato)
    sh "$D/30-controlli.sh" tutti || true
    [ -f "$RUN/pause.flag" ] && echo "pausa: ATTIVA" || echo "pausa: no"
    pycheck || true ;;
  attiva)
    WHO="${2:-}"
    printf '%s' "$WHO" | grep -Eq '^[A-Za-z][A-Za-z .-]{1,40}$' || nogo "serve il nome di chi approva"
    preflight
    pause_on
    write_mandate true "$WHO"
    pycheck || { write_mandate false ""; nogo "mandato non valido: ripristinato approved:false"; }
    rm -f "$RUN/pause.flag"
    echo "PAPER ATTIVO: mandato approvato da $WHO, pausa tolta. Il Brain decide al prossimo giro (ciclo 60 min)."
    echo "Pausa immediata: sh $D/80-paper.sh pausa   |   Revoca: sh $D/80-paper.sh revoca" ;;
  pausa)
    pause_on; echo "PAUSA ATTIVA: nessun nuovo giro; uscite e chiusure manuali proseguono" ;;
  riprendi)
    preflight; pycheck || nogo "mandato non valido"; rm -f "$RUN/pause.flag"; echo "PAUSA TOLTA" ;;
  revoca)
    pause_on; write_mandate false ""; pycheck || true
    echo "REVOCATO: pausa attiva e mandato approved:false; le posizioni aperte restano gestite dalle uscite" ;;
  *) nogo "comando sconosciuto: $ACT" ;;
esac
