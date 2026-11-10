#!/bin/sh
# Controllo in SOLA LETTURA per il backup esterno con i bot fermi (prima e dopo la correzione di run.sh).
#
#   sh check-stopped-readonly.sh pre    prima di installare/lanciare: tutto e' pronto, fermo e quieto?
#   sh check-stopped-readonly.sh post [FIRMA]
#                                       dopo il backup: com'e' andata? Con la FIRMA stampata da "pre" verifica
#                                       anche che il cervello sia rimasto identico.
#
# Non scrive niente, non ferma e non avvia niente, non legge segreti. Stampa solo esiti, conteggi, orari, nomi di
# file e impronte: mai contenuti dei file, importi, token o chiavi. Esce con 0 se non ci sono BLOCCHI, 1 altrimenti.
#
# Che cosa NON puo' provare: che nessuno scriva mai. Raccoglie evidenze indipendenti tra loro (container, richieste
# in coda, worker exit-only vivo e coerente con systemd, nessun altro processo con file aperti in scrittura,
# cartelle dati invariate durante l'osservazione) e confronta l'impronta del cervello prima/dopo.
#
# ---- DIFFERENZE LEGITTIME DI VERSIONE degli strumenti Python installati (sezione 1) -------------------------------
#  1. Un'impronta diversa dal repository BLOCCA. Non si sostituisce nessun file "alla cieca".
#  2. Il controllo stampa l'impronta COMPLETA osservata e, se la conosce, la versione storica del repository a cui
#     corrisponde (informazione, non un permesso).
#  3. Confronto in sola lettura: scaricare la versione del repository in una cartella a parte, `diff -u` con quella
#     installata, inviare il diff alla revisione (sono programmi, non segreti).
#  4. Se la differenza e' APPROVATA, rilanciare indicando l'impronta COMPLETA approvata (64 caratteri, separate da
#     virgola, senza spazi; un'impronta abbreviata o diversa NON vale):
#         SUPERBOT_ACCEPT_TOOL_HASHES="backup_brain=<64 caratteri>" sh check-stopped-readonly.sh pre
#     Restano comunque bloccanti: la mancanza di --brain-arg / --bot-stopped e un file che non e' Python valido.
#  5. Aggiornare un programma installato e' un passo SEPARATO e approvato, mai parte di questa procedura.
#
# ---- POLITICA DI RIAVVIO DEI CONTAINER (sezione 3) ----------------------------------------------------------------
#  Ammessa: "no". "unless-stopped" solo se (a) il container risulta exited, non in riavvio e fermo da piu' di 1 ora
#  e (b) e' stato accettato ESPLICITAMENTE per nome: SUPERBOT_ACCEPT_RESTART_POLICY="superbot-desk-hawk=unless-stopped,
#  superbot-desk-bull=unless-stopped". "always", "on-failure" e qualunque altro valore non si accettano mai.
LC_ALL=C
export LC_ALL
MODE="${1:-pre}"
SIGPRE="${2:-}"
case "$MODE" in pre | post) ;; *) echo "uso: sh check-stopped-readonly.sh pre|post" >&2; exit 2 ;; esac
DATA="${SUPERBOT_DATA:-/opt/superbot-desk-data}"
EXTB="${SUPERBOT_EXTB:-/opt/superbot-extbackup}"
TOOLS="${SUPERBOT_TOOLS:-/opt/superbot-tools}"
SETTLE="${SUPERBOT_SETTLE:-15}"
BKEY="${SUPERBOT_BACKUP_KEY:-/root/.ssh/superbot_backup_ed25519}"
EXPECTED_RUN_SH=e6dc3efc37a2d151be470cfad73b31919b545334cbbe13e2dff18ecebc64e7c5
NOW="$(date +%s)"
DATAR="$(cd "$DATA" 2>/dev/null && pwd -P)"
DATAR="${DATAR:-$DATA}"
BLOCK=0
ok() { echo "OK         $*"; }
info() { echo "           $*"; }
warn() { echo "ATTENZIONE $*"; }
bad() { echo "BLOCCO     $*"; BLOCK=$((BLOCK + 1)); }
is_uint() { case "$1" in '' | *[!0-9]*) return 1 ;; *) return 0 ;; esac; }

# file del cervello: stessi nomi di backup_brain.py (CORE)
CORE="trade_history.jsonl lessons.md errors.md learning_log.jsonl capital-v1-journal.jsonl salvadanaio-journal.jsonl state_v2.json"
fp() {
  for P in hawk bull; do
    for F in $CORE; do
      [ -f "$DATA/$P/$F" ] && stat -c '%n %i %s %y' "$DATA/$P/$F"
    done
  done
}
signature() {
  for P in hawk bull; do
    for F in $CORE; do
      [ -f "$DATA/$P/$F" ] && sha256sum "$DATA/$P/$F"
    done
  done | sha256sum | cut -c1-16
}
# impronta di TUTTI i file della cartella dati, tranne quelli che il worker exit-only riscrive di continuo per sua natura
dirfp() {
  find "$DATA/$1" -type f ! -name exit_only_heartbeat.json ! -name '.exit-only-hb.*.tmp' ! -name .exit_only_writer.lock \
    -printf '%p %i %s %T@\n' 2>/dev/null | sort
}
pending_flags() {
  for F in reset.flag reset.flag.work close_position.flag close_position.flag.work; do
    [ -e "$DATA/$1/$F" ] && echo "$F"
  done
}
# processi con un file della cartella dati aperto IN SCRITTURA (escluso il blocco proprio del worker exit-only)
open_writers() {
  for FD in /proc/[0-9]*/fd/*; do
    T="$(readlink "$FD" 2>/dev/null)" || continue
    case "$T" in "$DATA"/hawk/* | "$DATA"/bull/* | "$DATAR"/hawk/* | "$DATAR"/bull/*) ;; *) continue ;; esac
    PID="${FD#/proc/}"
    PID="${PID%%/*}"
    N="${FD##*/}"
    FL="$(sed -n 's/^flags:[[:space:]]*//p' "/proc/$PID/fdinfo/$N" 2>/dev/null)"
    [ -n "$FL" ] || continue
    [ $((0$FL & 3)) -ne 0 ] || continue
    case "${T##*/}" in .exit_only_writer.lock) ;; *) echo "pid $PID ($(cat "/proc/$PID/comm" 2>/dev/null)) scrive ${T##*/}" ;; esac
  done
}
# battito del worker exit-only: "ready portfolio pid ts opt_in protection" ('?' se manca)
exit_hb() {
  python3 -I - "$DATA/$1/exit_only_heartbeat.json" <<'PY' 2>/dev/null || echo "illeggibile ? ? ? ? ?"
import json, sys
try:
    with open(sys.argv[1], encoding="utf8") as f:
        hb = json.load(f)
    def g(k):
        v = hb.get(k)
        return "?" if v is None else str(v).replace(" ", "_")
    print("%s %s %s %s %s %s" % (g("ready"), g("portfolio"), g("pid"), g("ts"), g("stop_monitor_opt_in"), g("stop_protection")))
except Exception:
    print("illeggibile ? ? ? ? ?")
PY
}
# versione storica del repository a cui corrisponde un'impronta (solo informazione)
hist_label() {
  case "$1:$2" in
    external_backup:7cad7d8fdc83b76f9cd28e93edcc75aafcca05955bf4214a0058b88e491fa5ab) echo "versione storica del repository: rule-pool@7447056 2026-10-19" ;;
    external_backup:eb58f45da9366b0effec978437a32b7c216708d806486cf32581849ec477265c) echo "versione storica del repository: rule-pool@7ce1386 2026-10-19" ;;
    backup_brain:4a92e7daa6cff9fbf339f471656df8ba44067b6927d15b411b50313de0cb5d2c) echo "versione storica del repository: rule-pool@3abf1f8 2026-10-27" ;;
    backup_brain:fbbaaa1700fb6a2c78e7b932ea9bb57fd06abc6084a49a5c257712ac628bc0c0) echo "versione storica del repository: rule-pool@725c309 2026-10-23" ;;
    backup_brain:d31aaeca9131070095adc8d1f14b0e261fb1c3f07dafdc30dfcb187a781bd626) echo "versione storica del repository: rule-pool@db5f08a 2026-10-20" ;;
    backup_brain:7234e1553ba738f1d0771dac69bee7e1d8c3f8d109fb80081ebecbef975be6de) echo "versione storica del repository: rule-pool@b99926c 2026-10-19" ;;
    backup_brain:c7675e30b3a0b35bfce7a6219f278cc5153b0eb52b04378f7d4197e81e5ff171) echo "versione storica del repository: rule-pool@7447056 2026-10-19; main@35fd345 2026-10-19" ;;
    backup_brain:914fc271a689e0eccb70b02b223b113215d14faa5854082e5d906be0232dad41) echo "versione storica del repository: rule-pool@8a023a2 2026-10-19; main@04f3472 2026-10-19" ;;
    backup_brain:94498501266243636ba92982a62916fdcb4f3459eb42462b964dc1829008bac8) echo "versione storica del repository: rule-pool@2a0dc9b 2026-10-19; main@c6f9c7c 2026-10-19" ;;
    backup_brain:c747a8ec21460c8ee9fb9b8bc3632c219763bd89609464866654d5e12b318626) echo "versione storica del repository: rule-pool@71b633f 2026-10-19; main@03996e0 2026-10-19" ;;
    backup_app_db:6bd6ebc209400c7a0b222c62690e2c2f11b6f0a927b83fa937a35dcaac0700c6) echo "versione storica del repository: rule-pool@2a0dc9b 2026-10-19; main@c6f9c7c 2026-10-19" ;;
    backup_app_db:5b32811d11f1b796c0a1ea482e286815b9a9e8fb51db246ddb38360d989462ed) echo "versione storica del repository: rule-pool@71b633f 2026-10-19; main@03996e0 2026-10-19" ;;
  esac
}
accepted_tool() { case ",${SUPERBOT_ACCEPT_TOOL_HASHES:-}," in *",$1=$2,"*) return 0 ;; esac; return 1; }
accepted_policy() { case ",${SUPERBOT_ACCEPT_RESTART_POLICY:-}," in *",$1=unless-stopped,"*) return 0 ;; esac; return 1; }

echo "== Controllo $MODE - $(date -u +%FT%TZ)"
if [ "$(id -u 2>/dev/null)" = 0 ]; then
  ok "eseguito come root (vede i file aperti da tutti i processi)"
else
  bad "non eseguito come root (uid $(id -u 2>/dev/null)): la prova sugli scrittori concorrenti non sarebbe affidabile"
fi

echo "== 1. Strumenti e wrapper installati"
if [ "$MODE" = pre ]; then
  if grep -q -- '--brain-arg' "$TOOLS/external_backup.py" 2>/dev/null; then ok "external_backup.py accetta --brain-arg"; else bad "external_backup.py non accetta --brain-arg (versione vecchia o assente)"; fi
  if grep -q -- '--bot-stopped' "$TOOLS/backup_brain.py" 2>/dev/null; then ok "backup_brain.py conosce --bot-stopped"; else bad "backup_brain.py non conosce --bot-stopped (versione vecchia o assente)"; fi
  chk() {
    H="$(sha256sum "$TOOLS/$1.py" 2>/dev/null | cut -d' ' -f1)"
    if [ -z "$H" ]; then
      bad "$1.py assente in $TOOLS"
      return
    fi
    if ! python3 -I -c 'import ast,sys; ast.parse(open(sys.argv[1], encoding="utf8").read())' "$TOOLS/$1.py" 2>/dev/null; then
      bad "$1.py non e' un programma Python valido"
    fi
    L="$(hist_label "$1" "$H")"
    if [ "$H" = "$2" ]; then
      ok "$1.py identico alla versione del repository (rule-pool fed2e3f)"
    elif accepted_tool "$1" "$H"; then
      ok "$1.py DIVERSO dal repository ma ACCETTATO ESPLICITAMENTE (SUPERBOT_ACCEPT_TOOL_HASHES) sha256 $H${L:+ - corrisponde a: $L}"
    else
      bad "$1.py DIVERSO dal repository: sha256 $H${L:+ - corrisponde a: $L}. Non sostituire: vedi 'differenze legittime di versione' in testa a questo script"
    fi
  }
  chk external_backup 7cad7d8fdc83b76f9cd28e93edcc75aafcca05955bf4214a0058b88e491fa5ab
  chk backup_brain 4a92e7daa6cff9fbf339f471656df8ba44067b6927d15b411b50313de0cb5d2c
  chk backup_app_db 6bd6ebc209400c7a0b222c62690e2c2f11b6f0a927b83fa937a35dcaac0700c6
fi
RH="$(sha256sum "$EXTB/run.sh" 2>/dev/null | cut -d' ' -f1)"
if [ -z "$RH" ]; then
  bad "run.sh assente in $EXTB"
elif [ "$RH" = "$EXPECTED_RUN_SH" ]; then
  ok "run.sh e' la versione corretta attesa (sha256 $(echo "$RH" | cut -c1-16))"
elif [ "$MODE" = pre ]; then
  info "run.sh attuale (da correggere o gia' diverso): sha256 $(echo "$RH" | cut -c1-16)"
else
  bad "run.sh installato NON e' la versione corretta attesa (sha256 $(echo "$RH" | cut -c1-16)): installazione mancata o sovrascritta"
fi

if [ "$MODE" = pre ]; then
  echo "== 2. Nessun backup in corso"
  S="$(systemctl is-active superbot-extbackup.service 2>/dev/null)"
  case "$S" in
    inactive | failed) ok "superbot-extbackup.service non e' in corso (stato: $S)" ;;
    active | activating) bad "superbot-extbackup.service e' in corso ($S)" ;;
    *) bad "superbot-extbackup.service: stato NON VERIFICABILE (${S:-risposta vuota}); non assumo che sia fermo" ;;
  esac
  # solo interpreti python che eseguono davvero questi script (non una shell che li nomina nel proprio testo)
  if pgrep -f '^[^ ]*python[0-9.]* (-I )?[^ ]*/(external_backup|backup_brain|backup_app_db)\.py' >/dev/null 2>&1; then bad "c'e' un processo di backup in esecuzione"; else ok "nessun processo di backup in esecuzione"; fi
fi

echo "== 3. Container dei bot e politica di riavvio"
for P in hawk bull; do
  C="superbot-desk-$P"
  OUT="$(timeout 30 docker inspect -f '{{.State.Running}}|{{.HostConfig.RestartPolicy.Name}}|{{.State.Status}}|{{.State.Restarting}}|{{.State.FinishedAt}}' "$C" 2>/dev/null)" || OUT=""
  OLDIFS="$IFS"
  IFS='|'
  set -f
  set -- $OUT
  set +f
  IFS="$OLDIFS"
  RUN="${1:-}"
  POL="${2:-}"
  STA="${3:-}"
  RST="${4:-}"
  FIN="${5:-}"
  if [ "$RUN" = false ] && [ "$RST" = false ] && { [ "$STA" = exited ] || [ "$STA" = created ]; }; then
    ok "$C fermo (docker inspect: stato $STA, non in riavvio)"
  else
    bad "$C NON risulta fermo (${OUT:-docker non risponde o container assente})"
  fi
  case "$POL" in
    no) ok "$C: politica di riavvio 'no'" ;;
    unless-stopped)
      FAGE=-1
      if FEPOCH="$(date -d "$FIN" +%s 2>/dev/null)" && is_uint "$FEPOCH"; then FAGE=$((NOW - FEPOCH)); fi
      if accepted_policy "$C" && [ "$STA" = exited ] && [ "$RST" = false ] && [ "$FAGE" -gt 3600 ]; then
        ok "$C: politica 'unless-stopped' ACCETTATA ESPLICITAMENTE (fermo da $FAGE s, exited, non in riavvio)"
      else
        bad "$C: politica di riavvio AUTOMATICA 'unless-stopped' non accettata (servono: accettazione esplicita per nome, stato exited, non in riavvio, fermo da piu' di 1 ora; fermo da: $FAGE s)"
      fi
      ;;
    '') bad "$C: politica di riavvio non leggibile: non la considero 'no'" ;;
    *) bad "$C: politica di riavvio AUTOMATICA '$POL' (atteso 'no'): il container potrebbe ripartire da solo; non accettabile" ;;
  esac
done

echo "== 4. Cartelle, file dei bot, posizioni e richieste in coda"
POS_hawk=sconosciuto
POS_bull=sconosciuto
for P in hawk bull; do
  D="$DATA/$P"
  if [ ! -d "$D" ]; then bad "$P: cartella dati assente"; continue; fi
  for F in state_v2.json trade_history.jsonl learning_log.jsonl lessons.md; do
    if [ -L "$D/$F" ] || [ ! -f "$D/$F" ]; then bad "$P: $F assente o collegamento simbolico"; fi
  done
  [ -s "$D/state_v2.json" ] || bad "$P: state_v2.json vuoto"
  # stessa regola di backup_brain.py: con capitale v1 serve anche il giornale.
  # Le posizioni sono un intero SOLO se main.positions e' un oggetto: altrimenti "sconosciuto" (mai 0).
  R="$(python3 -I - "$D" <<'PY' 2>/dev/null
import json, os, sys
d = sys.argv[1]
try:
    with open(os.path.join(d, "state_v2.json"), encoding="utf8") as f:
        s = json.load(f)
except Exception:
    print("stato_illeggibile - sconosciuto")
    raise SystemExit
cap = s.get("capital") if isinstance(s, dict) else None
v1 = isinstance(cap, dict) and cap.get("schema_version") == 1
vault = v1 and cap.get("policy") == "salvadanaio-only-v1"
j = "salvadanaio-journal.jsonl" if vault else "capital-v1-journal.jsonl"
main = s.get("main") if isinstance(s, dict) else None
pos = main.get("positions") if isinstance(main, dict) else None
n = str(len(pos)) if isinstance(pos, dict) else "sconosciuto"
print("%s %s %s" % ("v1" if v1 else "nessun_giornale_richiesto", j if v1 else "-", n))
PY
)"
  set -- $R
  KIND="${1:-?}"
  JNAME="${2:--}"
  POS="${3:-sconosciuto}"
  is_uint "$POS" || POS=sconosciuto
  case "$P" in hawk) POS_hawk="$POS" ;; bull) POS_bull="$POS" ;; esac
  case "$KIND" in
    stato_illeggibile) bad "$P: state_v2.json illeggibile come JSON" ;;
    v1)
      if [ -f "$D/$JNAME" ] && [ ! -L "$D/$JNAME" ]; then ok "$P: capitale v1, giornale $JNAME presente"; else bad "$P: capitale v1 ma manca $JNAME (backup_brain lo richiede)"; fi
      ;;
    nessun_giornale_richiesto) ok "$P: nessun giornale di capitale richiesto" ;;
    *) bad "$P: controllo dello stato non riuscito (python3?)" ;;
  esac
  if [ "$POS" = sconosciuto ]; then
    bad "$P: numero di posizioni aperte SCONOSCIUTO (struttura dello stato non riconosciuta): non lo considero zero"
  else
    info "$P: posizioni aperte nello stato = $POS"
  fi
  FLB=""
  for F in $(pending_flags "$P"); do
    bad "$P: richiesta di chiusura/reset in coda ($F): una scrittura sul cervello e' imminente"
    FLB="$FLB $F"
  done
  eval "FLAGS_$P=\"\$FLB \""
  if [ -f "$D/pause.flag" ]; then ok "$P: pause.flag presente"; else warn "$P: pause.flag assente"; fi
  if [ -f "$D/heartbeat.json" ]; then
    AGE=$((NOW - $(stat -c %Y "$D/heartbeat.json")))
    if [ "$AGE" -gt 600 ]; then ok "$P: heartbeat.json vecchio di $AGE s (il bot non scrive)"; else bad "$P: heartbeat.json vecchio di soli $AGE s: qualcuno lo sta scrivendo"; fi
  else
    ok "$P: nessun heartbeat.json"
  fi
done

echo "== 5. Servizi exit-only (restano attivi: servono per la chiusura manuale)"
EXIT_ACTIVE=""
for N in falco:hawk toro:bull; do
  U="superbot-v3-${N%%:*}-exit.service"
  P="${N##*:}"
  A="$(systemctl is-active "$U" 2>/dev/null)"
  info "$U = ${A:-sconosciuto}"
  case "$A" in
    inactive | failed) info "$P: worker exit-only non attivo: nessun worker che scriva sul cervello"; continue ;;
    active) ;;
    *) bad "$P: stato del servizio exit-only non determinabile ('${A:-vuoto}'): non assumo che sia innocuo"; continue ;;
  esac
  EXIT_ACTIVE="$EXIT_ACTIVE $P"
  eval "POS=\$POS_$P"
  MPID="$(systemctl show -p MainPID --value "$U" 2>/dev/null)"
  if is_uint "$MPID" && [ "$MPID" -gt 0 ] && [ -d "/proc/$MPID" ] && tr '\0' ' ' <"/proc/$MPID/cmdline" 2>/dev/null | grep -q 'desk\.exit_only'; then
    ok "$P: systemd indica il processo $MPID e il suo comando e' desk.exit_only"
  else
    bad "$P: il processo principale di systemd ('${MPID:-?}') non esiste o non e' desk.exit_only: evidenza non affidabile"
    MPID=0
  fi
  set -- $(exit_hb "$P")
  HREADY="$1"; HPORT="$2"; HPID="$3"; HTS="$4"; HOPT="$5"; HPROT="$6"
  info "$P: battito exit-only: ready=$HREADY portfolio=$HPORT pid=$HPID stop_monitor_opt_in=$HOPT stop_protection=$HPROT"
  [ "$HREADY" = True ] && ok "$P: il worker dichiara ready" || bad "$P: il worker exit-only NON dichiara ready (ready=$HREADY)"
  [ "$HPORT" = "$P" ] && ok "$P: il battito appartiene al portafoglio giusto" || bad "$P: il battito dichiara il portafoglio '$HPORT'"
  [ "$MPID" -gt 0 ] && [ "$HPID" = "$MPID" ] && ok "$P: il pid del battito coincide con quello di systemd" || bad "$P: il pid del battito ($HPID) non coincide con quello di systemd ($MPID)"
  HAGE="$(python3 -I -c 'import sys,time; print(int(time.time()-float(sys.argv[1])))' "$HTS" 2>/dev/null)"
  if is_uint "$HAGE" && [ "$HAGE" -le 15 ]; then ok "$P: battito exit-only fresco ($HAGE s)"; else bad "$P: battito exit-only non fresco o illeggibile (${HAGE:-?} s): il worker potrebbe non rispondere"; fi
  eval "HTS1_$P=\$HTS"
  if [ "$POS" = 0 ]; then
    ok "$P: posizioni aperte = 0: il worker non ha nulla da chiudere e riscrive solo il proprio battito"
  elif [ "$POS" = sconosciuto ]; then
    bad "$P: con il worker exit-only attivo il numero di posizioni deve essere NOTO e zero (qui e' sconosciuto)"
  else
    bad "$P: $POS posizioni aperte con il worker exit-only attivo: una chiusura manuale o il monitor stop scrivono sul cervello in qualsiasi momento; decidere prima con la revisione"
  fi
done

echo "== 6. Quiete e scrittori concorrenti"
F1="$(fp)"
NEWEST=0
for L in $(for P in hawk bull; do for F in $CORE; do [ -f "$DATA/$P/$F" ] && stat -c %Y "$DATA/$P/$F"; done; done); do
  [ "$L" -gt "$NEWEST" ] && NEWEST="$L"
done
if [ "$NEWEST" -eq 0 ]; then
  bad "nessun file del cervello trovato"
elif [ $((NOW - NEWEST)) -gt 300 ]; then
  ok "nessun file del cervello scritto negli ultimi 5 minuti (l'ultimo: $((NOW - NEWEST)) s fa)"
else
  bad "un file del cervello e' stato scritto $((NOW - NEWEST)) s fa"
fi
W="$(open_writers)"
if [ -z "$W" ]; then
  ok "nessun processo ha file delle cartelle dati aperti in scrittura (oltre al blocco del worker exit-only)"
else
  echo "$W" | while IFS= read -r LINE; do echo "BLOCCO     scrittore aperto: $LINE"; done
  BLOCK=$((BLOCK + $(echo "$W" | wc -l)))
fi
DH1="$(dirfp hawk)"
DB1="$(dirfp bull)"
if [ "$MODE" = pre ]; then
  sleep "$SETTLE"
  F2="$(fp)"
  if [ "$F1" = "$F2" ]; then
    ok "file del cervello invariati durante $SETTLE s di osservazione"
  else
    bad "i file del cervello sono cambiati durante l'osservazione (solo nomi): $( (echo "$F1"; echo "$F2") | sort | uniq -u | awk '{print $1}' | sort -u | tr '\n' ' ')"
  fi
  for P in hawk bull; do
    if [ "$P" = hawk ]; then D1="$DH1"; else D1="$DB1"; fi
    D2="$(dirfp "$P")"
    if [ "$D1" = "$D2" ]; then
      ok "$P: nessun altro file della cartella dati e' cambiato durante l'osservazione (esclusi i file propri del worker)"
    else
      bad "$P: file della cartella dati cambiati/creati/spariti durante l'osservazione (solo nomi): $( (echo "$D1"; echo "$D2") | sort | uniq -u | awk '{print $1}' | sort -u | tr '\n' ' ')"
    fi
    eval "FLB=\$FLAGS_$P"
    for F in $(pending_flags "$P"); do
      case " $FLB" in *" $F "*) continue ;; esac
      bad "$P: durante l'osservazione e' comparsa una richiesta ($F)"
    done
  done
  for P in $EXIT_ACTIVE; do
    set -- $(exit_hb "$P")
    eval "T1=\$HTS1_$P"
    T2="$4"
    if python3 -I -c 'import sys; sys.exit(0 if float(sys.argv[2]) > float(sys.argv[1]) else 1)' "$T1" "$T2" 2>/dev/null; then
      ok "$P: il battito exit-only e' AVANZATO durante l'osservazione: il worker e' vivo e in questo intervallo non ha toccato nient'altro"
    else
      bad "$P: il battito exit-only NON e' avanzato durante l'osservazione: il worker non risponde e l'osservazione non e' affidabile"
    fi
  done
fi
SIG="$(signature)"
echo "FIRMA_CERVELLO=$SIG   (impronta di tutti i file del cervello; deve essere IDENTICA prima e dopo il backup)"
if [ "$MODE" = post ]; then
  case "$SIGPRE" in
    "" | *[!0-9a-f]*) bad "firma PRE mancante o non valida: servono 16 caratteri esadecimali" ;;
    *)
      if [ "${#SIGPRE}" -ne 16 ]; then
        bad "firma PRE non valida: lunghezza diversa da 16"
      elif [ "$SIG" = "$SIGPRE" ]; then
        ok "il cervello e' identico a prima del backup (stessa firma)"
      else
        bad "il cervello e' DIVERSO da prima del backup (firma $SIGPRE -> $SIG): verificare cosa ha scritto"
      fi
      ;;
  esac
fi

if [ "$MODE" = pre ]; then
  echo "== 7. Spazio sul disco"
  NEED="$(du -sk "$DATA" 2>/dev/null | cut -f1)"
  NEED=$((${NEED:-0} * 3 + 1048576))
  AVAIL="$(df -Pk "$EXTB" 2>/dev/null | awk 'NR==2{print $4}')"
  if [ "${AVAIL:-0}" -gt "$NEED" ]; then
    ok "spazio libero sufficiente ($((AVAIL / 1024)) MB liberi, stima prudente del bisogno: $((NEED / 1024)) MB)"
  else
    bad "spazio libero insufficiente ($((${AVAIL:-0} / 1024)) MB liberi, stima del bisogno: $((NEED / 1024)) MB)"
  fi
fi

if [ "$MODE" = post ]; then
  echo "== 7. Esito del servizio"
  SHOWRAW="$(systemctl show superbot-extbackup.service -p ActiveState -p Result -p ExecMainStatus 2>/dev/null)"
  SHOWSVC="$(printf '%s\n' "$SHOWRAW" | tr '\n' ' ')"
  info "$SHOWSVC"
  # l'ordine delle righe di "systemctl show" non e' garantito: si controlla ogni proprieta' per conto suo
  if printf '%s\n' "$SHOWRAW" | grep -qx 'ActiveState=inactive' && printf '%s\n' "$SHOWRAW" | grep -qx 'Result=success' \
    && printf '%s\n' "$SHOWRAW" | grep -qx 'ExecMainStatus=0'; then
    ok "superbot-extbackup.service terminato con successo (inattivo, Result=success, uscita 0)"
  else
    bad "superbot-extbackup.service non risulta terminato con successo (${SHOWSVC:-risposta vuota}): il backup potrebbe essere ancora in corso o fallito"
  fi
  journalctl -u superbot-extbackup.service -n 25 --no-pager 2>/dev/null | cut -c1-220 | sed 's/^/           /'
  echo "== 8. Stato scritto dal backup (status.json)"
  ST="$(python3 -I - "$EXTB/status.json" "$NOW" <<'PY' 2>/dev/null
import json, sys, time
from datetime import datetime, timezone
try:
    with open(sys.argv[1], encoding="utf8") as f:
        s = json.load(f)
except Exception as e:
    print("ILLEGGIBILE %s" % type(e).__name__)
    raise SystemExit
err = s.get("ultimo_errore")
ok_ts = s.get("ultimo_successo")
age = "?"
same_attempt = "no"
try:
    now = datetime.fromtimestamp(float(sys.argv[2]), tz=timezone.utc)
    ok_dt = datetime.strptime(ok_ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    try_dt = datetime.strptime(s.get("ultimo_tentativo"), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    age = str(int((now - ok_dt).total_seconds()))
    if 0 <= (ok_dt - try_dt).total_seconds() <= 1800 and 0 <= (now - ok_dt).total_seconds() <= 1800:
        same_attempt = "si"
except (ValueError, TypeError, OverflowError):
    pass
print("STATO errore=%s successo_eta_s=%s archivio=%s sha=%s stesso_tentativo=%s" % ("si" if err else "no", age, s.get("archivio"), s.get("sha256"), same_attempt))
if err:
    print("ERRORE %s" % str(err).splitlines()[0][:200])
for k in ("ultimo_tentativo", "ultimo_successo", "dimensione", "archivi_visibili", "verifica"):
    print("DETTAGLIO %s = %s" % (k, s.get(k)))
PY
)"
  echo "$ST" | sed 's/^/           /'
  STL="$(echo "$ST" | sed -n 's/^STATO //p')"
  case "$STL" in
    *errore=no*) ok "status.json: nessun errore registrato" ;;
    *) bad "status.json: ultimo errore registrato o stato illeggibile" ;;
  esac
  case "$STL" in
    *stesso_tentativo=si*) ok "ultimo successo associato all'ultimo tentativo" ;;
    *) bad "status.json: ultimo successo non dimostrato per l'ultimo tentativo" ;;
  esac
  SAGE="$(echo "$STL" | sed -n 's/.*successo_eta_s=\([0-9]*\).*/\1/p')"
  if is_uint "$SAGE" && [ "$SAGE" -le 1800 ]; then ok "ultimo backup riuscito $SAGE s fa (entro 30 minuti)"; else bad "l'ultimo backup riuscito non e' recente (eta: ${SAGE:-sconosciuta} s): questo giro non risulta riuscito"; fi
  SSHA="$(echo "$STL" | sed -n 's/.*sha=\([0-9a-f]*\).*/\1/p')"
  echo "== 9. Manifesto pubblico e verifica remota"
  SARCH="$(echo "$STL" | sed -n 's/.*archivio=\([^ ]*\) sha=.*/\1/p')"
  M=""
  if printf '%s\n' "$SARCH" | grep -Eq '^superbot-backup-[0-9]{8}T[0-9]{6}Z\.tar\.gz\.age$'; then
    M="$(find "$EXTB/repo/archives" -type f -name "${SARCH%.tar.gz.age}.manifest.json" -print -quit 2>/dev/null)"
  else
    bad "status.json: nome archivio non valido"
  fi
  if [ -n "$M" ]; then
    MAN="$(python3 -I - "$M" <<'PY' 2>/dev/null
import json, sys
with open(sys.argv[1], encoding="utf8") as f:
    m = json.load(f)
print("SHA %s" % m.get("sha256"))
print("ARCHIVIO %s" % m.get("archivio"))
print("CREATO %s" % m.get("creato"))
print("archivio = %s" % m.get("archivio"))
print("creato = %s  dimensione = %s  file = %s" % (m.get("creato"), m.get("dimensione"), (m.get("contenuto") or {}).get("file")))
im = (m.get("versioni") or {}).get("immagini_in_esecuzione") or {}
for n in ("superbot-desk-hawk", "superbot-desk-bull"):
    v = im.get(n)
    print("%s in_esecuzione = %s" % (n, v.get("in_esecuzione") if isinstance(v, dict) else v))
PY
)"
    echo "$MAN" | grep -v '^SHA ' | sed 's/^/           /'
    MSHA="$(echo "$MAN" | sed -n 's/^SHA //p')"
    MARCH="$(echo "$MAN" | sed -n 's/^ARCHIVIO //p')"
    MCREATED="$(echo "$MAN" | sed -n 's/^CREATO //p')"
    STCREATED="$(echo "$ST" | sed -n 's/^DETTAGLIO ultimo_successo = //p')"
    if [ "$MARCH" = "$SARCH" ] && [ "$MCREATED" = "$STCREATED" ]; then
      ok "manifesto: archivio e data coincidono con l'ultimo successo"
    else
      bad "manifesto: archivio o data non coincidono con l'ultimo successo"
    fi
    if [ -n "$MSHA" ] && [ "$MSHA" = "$SSHA" ]; then ok "lo SHA-256 dell'archivio nel manifesto pubblico coincide con quello di status.json ($(echo "$MSHA" | cut -c1-16))"; else bad "lo SHA-256 del manifesto pubblico non coincide con status.json"; fi
    A="${M%.manifest.json}.tar.gz.age"
    if [ -f "$A" ] && [ ! -L "$A" ]; then
      ASHA="$(sha256sum "$A" 2>/dev/null | cut -d' ' -f1)"
      if [ -n "$ASHA" ] && [ "$ASHA" = "$SSHA" ]; then
        ok "archivio locale cifrato: SHA-256 verificato"
      else
        bad "archivio locale cifrato: SHA-256 non coincide con lo stato"
      fi
    else
      bad "archivio locale cifrato mancante o non regolare"
    fi
    NSTOP="$(echo "$MAN" | grep -c 'in_esecuzione = False')"
    NOTHER="$(echo "$MAN" | grep 'in_esecuzione = ' | grep -vc 'in_esecuzione = False')"
    if [ "$NSTOP" -eq 2 ] && [ "$NOTHER" -eq 0 ]; then ok "il manifesto registra hawk e bull NON in esecuzione"; else bad "il manifesto non registra entrambi i bot come non in esecuzione"; fi
  else
    bad "nessun manifesto nel repository locale dei backup"
  fi
  # verifica remota in sola lettura: la punta del repository privato su GitHub deve essere quella locale appena inviata
  if [ -d "$EXTB/repo/.git" ]; then
    LOCALHEAD="$(git -C "$EXTB/repo" rev-parse HEAD 2>/dev/null)"
    REMOTEHEAD="$(GIT_TERMINAL_PROMPT=0 GIT_SSH_COMMAND="ssh -i $BKEY -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=$EXTB/known_hosts -o ConnectTimeout=30" timeout 90 git -C "$EXTB/repo" ls-remote origin refs/heads/main 2>/dev/null | cut -f1)"
    if [ -n "$LOCALHEAD" ] && [ "$LOCALHEAD" = "$REMOTEHEAD" ]; then
      ok "verifica remota: la punta di main nel repository privato dei backup e' quella appena inviata ($(echo "$LOCALHEAD" | cut -c1-10))"
    else
      bad "verifica remota: punta locale ($(echo "${LOCALHEAD:-?}" | cut -c1-10)) diversa da quella remota ($(echo "${REMOTEHEAD:-?}" | cut -c1-10)) o remoto non raggiungibile"
    fi
  else
    bad "repository locale dei backup assente: nessuna verifica remota possibile"
  fi
fi

echo
if [ "$BLOCK" -eq 0 ]; then
  if [ "$MODE" = pre ]; then echo "ESITO: PRONTO - nessun blocco"; else echo "ESITO: CONTROLLO SUPERATO - nessun blocco"; fi
  exit 0
fi
echo "ESITO: NON PRONTO - $BLOCK blocchi. Non procedere: inviare questo testo a Claude/ChatGPT."
exit 1
