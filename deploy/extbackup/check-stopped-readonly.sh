#!/bin/sh
# Controllo in SOLA LETTURA per il backup esterno con i bot fermi (prima e dopo la correzione di run.sh).
#
#   sh check-stopped-readonly.sh pre    prima di installare/lanciare: tutto e' pronto e fermo?
#   sh check-stopped-readonly.sh post [FIRMA]
#                                       dopo il backup: com'e' andata? Con la FIRMA stampata da "pre" verifica
#                                       anche che il cervello sia rimasto identico.
#
# Non scrive niente, non ferma e non avvia niente, non legge segreti. Stampa solo esiti, conteggi, orari e
# impronte brevi: mai contenuti dei file, importi, token o chiavi. Esce con 0 se non ci sono BLOCCHI, 1 altrimenti.
#
# Che cosa NON puo' provare: che nessuno scriva mai. Controlla i meccanismi noti (container dei bot, richieste
# di chiusura in coda, battito, worker exit-only, quiete dei file) e confronta l'impronta del cervello prima/dopo.
LC_ALL=C
export LC_ALL
MODE="${1:-pre}"
SIGPRE="${2:-}"
case "$MODE" in pre | post) ;; *) echo "uso: sh check-stopped-readonly.sh pre|post" >&2; exit 2 ;; esac
DATA="${SUPERBOT_DATA:-/opt/superbot-desk-data}"
EXTB="${SUPERBOT_EXTB:-/opt/superbot-extbackup}"
TOOLS="${SUPERBOT_TOOLS:-/opt/superbot-tools}"
SETTLE="${SUPERBOT_SETTLE:-15}"
NOW="$(date +%s)"
BLOCK=0
ok() { echo "OK         $*"; }
info() { echo "           $*"; }
warn() { echo "ATTENZIONE $*"; }
bad() { echo "BLOCCO     $*"; BLOCK=$((BLOCK + 1)); }

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

echo "== Controllo $MODE - $(date -u +%FT%TZ)"

if [ "$MODE" = pre ]; then
  echo "== 1. Strumenti e wrapper installati"
  if grep -q -- '--brain-arg' "$TOOLS/external_backup.py" 2>/dev/null; then ok "external_backup.py accetta --brain-arg"; else bad "external_backup.py non accetta --brain-arg (versione vecchia o assente)"; fi
  if grep -q -- '--bot-stopped' "$TOOLS/backup_brain.py" 2>/dev/null; then ok "backup_brain.py conosce --bot-stopped"; else bad "backup_brain.py non conosce --bot-stopped (versione vecchia o assente)"; fi
  # impronte attese = versioni del repository (ramo rule-pool, commit fed2e3f); una differenza non blocca da sola
  chk() {
    H="$(sha256sum "$TOOLS/$1.py" 2>/dev/null | cut -d' ' -f1)"
    if [ -z "$H" ]; then bad "$1.py assente in $TOOLS"
    elif [ "$H" = "$2" ]; then ok "$1.py identico alla versione del repository"
    else warn "$1.py DIVERSO dal repository (sha256 $(echo "$H" | cut -c1-16)): riferire prima di proseguire"; fi
  }
  chk external_backup 7cad7d8fdc83b76f9cd28e93edcc75aafcca05955bf4214a0058b88e491fa5ab
  chk backup_brain 4a92e7daa6cff9fbf339f471656df8ba44067b6927d15b411b50313de0cb5d2c
  chk backup_app_db 6bd6ebc209400c7a0b222c62690e2c2f11b6f0a927b83fa937a35dcaac0700c6
  if grep -q -- '--bot-stopped' "$EXTB/run.sh" 2>/dev/null; then ok "run.sh contiene gia' --bot-stopped"; else warn "run.sh attuale NON passa --bot-stopped (e' il difetto da correggere)"; fi
  info "sha256(run.sh) = $(sha256sum "$EXTB/run.sh" 2>/dev/null | cut -c1-16)"

  echo "== 2. Nessun backup in corso"
  S="$(systemctl is-active superbot-extbackup.service 2>/dev/null)"
  case "$S" in
    active | activating) bad "superbot-extbackup.service e' in corso ($S)" ;;
    *) ok "superbot-extbackup.service non e' in corso (stato: ${S:-sconosciuto})" ;;
  esac
  # solo interpreti python che eseguono davvero questi script (non una shell che li nomina nel proprio testo)
  if pgrep -f '^[^ ]*python[0-9.]* (-I )?[^ ]*/(external_backup|backup_brain|backup_app_db)\.py' >/dev/null 2>&1; then bad "c'e' un processo di backup in esecuzione"; else ok "nessun processo di backup in esecuzione"; fi
fi

echo "== 3. Container dei bot"
for P in hawk bull; do
  C="superbot-desk-$P"
  OUT="$(timeout 30 docker inspect -f '{{.State.Running}} {{.HostConfig.RestartPolicy.Name}}' "$C" 2>/dev/null)" || OUT=""
  RUN="${OUT%% *}"
  POL="${OUT#* }"
  if [ "$RUN" = false ]; then ok "$C fermo (docker inspect)"; else bad "$C NON risulta fermo (${OUT:-docker non risponde o container assente})"; fi
  if [ "$POL" = no ]; then ok "$C: politica di riavvio 'no'"; else warn "$C: politica di riavvio '${POL:-?}' (atteso 'no')"; fi
done

echo "== 4. Cartelle e file dei bot"
POS_hawk=-1
POS_bull=-1
for P in hawk bull; do
  D="$DATA/$P"
  if [ ! -d "$D" ]; then bad "$P: cartella dati assente"; continue; fi
  for F in state_v2.json trade_history.jsonl learning_log.jsonl lessons.md; do
    if [ -L "$D/$F" ] || [ ! -f "$D/$F" ]; then bad "$P: $F assente o collegamento simbolico"; fi
  done
  [ -s "$D/state_v2.json" ] || bad "$P: state_v2.json vuoto"
  # stessa regola di backup_brain.py: con capitale v1 serve anche il giornale
  R="$(python3 -I - "$D" <<'PY' 2>/dev/null
import json, os, sys
d = sys.argv[1]
try:
    with open(os.path.join(d, "state_v2.json"), encoding="utf8") as f:
        s = json.load(f)
except Exception:
    print("stato_illeggibile - -1")
    raise SystemExit
cap = s.get("capital") if isinstance(s, dict) else None
v1 = isinstance(cap, dict) and cap.get("schema_version") == 1
vault = v1 and cap.get("policy") == "salvadanaio-only-v1"
j = "salvadanaio-journal.jsonl" if vault else "capital-v1-journal.jsonl"
n = len(((s.get("main") or {}).get("positions") or {})) if isinstance(s, dict) else -1
print("%s %s %d" % ("v1" if v1 else "nessun_giornale_richiesto", j if v1 else "-", n))
PY
)"
  set -- $R
  KIND="${1:-?}"
  JNAME="${2:--}"
  POS="${3:--1}"
  case "$P" in hawk) POS_hawk="$POS" ;; bull) POS_bull="$POS" ;; esac
  case "$KIND" in
    stato_illeggibile) bad "$P: state_v2.json illeggibile come JSON" ;;
    v1)
      if [ -f "$D/$JNAME" ] && [ ! -L "$D/$JNAME" ]; then ok "$P: capitale v1, giornale $JNAME presente"; else bad "$P: capitale v1 ma manca $JNAME (backup_brain lo richiede)"; fi
      ;;
    nessun_giornale_richiesto) ok "$P: nessun giornale di capitale richiesto" ;;
    *) warn "$P: controllo del giornale non riuscito (python3?)" ;;
  esac
  info "$P: posizioni aperte nello stato = $POS"
  for F in reset.flag reset.flag.work close_position.flag close_position.flag.work; do
    if [ -e "$D/$F" ]; then bad "$P: richiesta in coda ($F): una scrittura sul cervello e' imminente"; fi
  done
  if [ -f "$D/pause.flag" ]; then ok "$P: pause.flag presente"; else warn "$P: pause.flag assente"; fi
  if [ -f "$D/heartbeat.json" ]; then
    AGE=$((NOW - $(stat -c %Y "$D/heartbeat.json")))
    if [ "$AGE" -gt 600 ]; then ok "$P: heartbeat.json vecchio di $AGE s (il bot non scrive)"; else bad "$P: heartbeat.json vecchio di soli $AGE s: qualcuno lo sta scrivendo"; fi
  else
    ok "$P: nessun heartbeat.json"
  fi
done

echo "== 5. Servizi exit-only (restano attivi: servono per la chiusura manuale)"
for N in falco:hawk toro:bull; do
  U="superbot-v3-${N%%:*}-exit.service"
  P="${N##*:}"
  A="$(systemctl is-active "$U" 2>/dev/null)"
  info "$U = ${A:-sconosciuto}"
  [ "$A" = active ] || continue
  eval "POS=\$POS_$P"
  HB="$DATA/$P/exit_only_heartbeat.json"
  H="$(python3 -I - "$HB" "$NOW" <<'PY' 2>/dev/null
import json, sys
try:
    with open(sys.argv[1], encoding="utf8") as f:
        hb = json.load(f)
    age = int(float(sys.argv[2]) - float(hb.get("ts", 0)))
    print("%s %d %s %s" % (hb.get("ready"), age, hb.get("stop_monitor_opt_in"), hb.get("stop_protection")))
except Exception:
    print("illeggibile 0 ? ?")
PY
)"
  set -- $H
  info "$P: battito exit-only: ready=${1:-?} eta=${2:-?}s stop_monitor_opt_in=${3:-?} stop_protection=${4:-?}"
  if [ "${POS:--1}" = 0 ]; then
    ok "$P: nessuna posizione aperta: il worker exit-only non ha nulla da chiudere, riscrive solo il proprio battito"
  elif [ "${3:-?}" = True ]; then
    bad "$P: ${POS} posizioni aperte con monitor stop attivo: il cervello puo' cambiare in qualsiasi momento"
  else
    warn "$P: ${POS} posizioni aperte: una chiusura manuale scriverebbe sul cervello (il backup scarta la copia se cambia)"
  fi
done

echo "== 6. Quiete dei file del cervello"
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
if [ "$MODE" = pre ]; then
  sleep "$SETTLE"
  F2="$(fp)"
  if [ "$F1" = "$F2" ]; then ok "file del cervello invariati durante $SETTLE s di osservazione"; else bad "i file del cervello sono cambiati durante l'osservazione: qualcuno scrive"; fi
fi
SIG="$(signature)"
echo "FIRMA_CERVELLO=$SIG   (impronta di tutti i file del cervello; deve essere IDENTICA prima e dopo il backup)"
if [ "$MODE" = post ] && [ -n "$SIGPRE" ]; then
  if [ "$SIG" = "$SIGPRE" ]; then ok "il cervello e' identico a prima del backup (stessa firma)"; else bad "il cervello e' DIVERSO da prima del backup (firma $SIGPRE -> $SIG): verificare cosa ha scritto"; fi
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
  info "$(systemctl show superbot-extbackup.service -p ActiveState -p Result -p ExecMainStatus 2>/dev/null | tr '\n' ' ')"
  journalctl -u superbot-extbackup.service -n 25 --no-pager 2>/dev/null | cut -c1-220 | sed 's/^/           /'
  echo "== 8. Stato scritto dal backup (status.json)"
  python3 -I - "$EXTB/status.json" <<'PY' 2>/dev/null | sed 's/^/           /'
import json, sys
try:
    with open(sys.argv[1], encoding="utf8") as f:
        s = json.load(f)
except Exception as e:
    print("status.json illeggibile: %s" % type(e).__name__)
    raise SystemExit
for k in ("ultimo_tentativo", "ultimo_successo", "archivio", "dimensione", "archivi_visibili", "verifica"):
    print("%s = %s" % (k, s.get(k)))
print("sha256 = %s" % str(s.get("sha256"))[:16])
e = s.get("ultimo_errore")
print("ultimo_errore = %s" % (str(e).splitlines()[0][:200] if e else None))
PY
  echo "== 9. Manifesto pubblico dell'ultimo archivio (nel repository locale dei backup)"
  M="$(ls -1 "$EXTB"/repo/archives/*/*/*.manifest.json 2>/dev/null | sort | tail -1)"
  if [ -n "$M" ]; then
    python3 -I - "$M" <<'PY' 2>/dev/null | sed 's/^/           /'
import json, os, sys
with open(sys.argv[1], encoding="utf8") as f:
    m = json.load(f)
print("archivio = %s" % m.get("archivio"))
print("creato = %s  dimensione = %s  file = %s" % (m.get("creato"), m.get("dimensione"), (m.get("contenuto") or {}).get("file")))
print("sha256(archivio cifrato) = %s" % str(m.get("sha256"))[:16])
im = (m.get("versioni") or {}).get("immagini_in_esecuzione") or {}
for n in ("superbot-desk-hawk", "superbot-desk-bull"):
    v = im.get(n)
    print("%s in_esecuzione = %s" % (n, v.get("in_esecuzione") if isinstance(v, dict) else v))
PY
    ARC="${M%.manifest.json}.tar.gz.age"
    if [ -f "$ARC" ]; then
      info "sha256 ricalcolato dell'archivio cifrato locale = $(sha256sum "$ARC" | cut -c1-16)"
    else
      info "(archivio cifrato locale non conservato sul server: e' normale, resta nel repository privato)"
    fi
  else
    warn "nessun manifesto nel repository locale dei backup"
  fi
fi

echo
if [ "$BLOCK" -eq 0 ]; then
  if [ "$MODE" = pre ]; then echo "ESITO: PRONTO - nessun blocco"; else echo "ESITO: CONTROLLO SUPERATO - nessun blocco (leggere comunque le sezioni 7-9)"; fi
  exit 0
fi
echo "ESITO: NON PRONTO - $BLOCK blocchi. Non procedere: inviare questo testo a Claude/ChatGPT."
exit 1
