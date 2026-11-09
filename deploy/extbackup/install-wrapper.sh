#!/bin/sh
# Installa (o ripristina) SOLO il wrapper del backup esterno: /opt/superbot-extbackup/run.sh.
#
#   sh install-wrapper.sh status                    fotografia in sola lettura (nessuna modifica)
#   sh install-wrapper.sh install   [--apply] [--src FILE]
#   sh install-wrapper.sh rollback  [--apply]
#
# Senza --apply e' una SIMULAZIONE: controlla tutto, stampa che cosa farebbe, non scrive niente (nemmeno cartelle).
#
# Che cosa tocca (con --apply), e nient'altro:
#   - crea (una volta) la cartella di salvataggio $SUPERBOT_FIXDIR (default /root/extbackup-fix-20261109, modo 700);
#   - ci copia UNA SOLA VOLTA il run.sh attuale (run.sh.original + .sha256); un originale gia' salvato non si sovrascrive mai;
#   - sostituisce $EXTB/run.sh in modo atomico (file temporaneo nella stessa cartella + rename), poi rilegge e verifica l'impronta;
#     se la verifica fallisce rimette da solo l'originale.
# Non tocca: unit e timer systemd, programmi Python in /opt/superbot-tools, chiavi, known_hosts, recipient, status.json,
# archivi, dati o cervello dei bot, workflow. Non avvia, non ferma e non ricarica servizi. Non cancella niente
# (l'unico file rimosso e' il proprio temporaneo, se il rename non e' avvenuto).
#
# Rifiuta di procedere se: non e' root; l'origine non ha l'impronta attesa o non e' una shell valida; il backup e'
# in corso; run.sh attuale non e' ne' la versione corretta ne' la versione precedente nota del repository (in quel
# caso: non sostituire alla cieca; far approvare l'impronta indicata e rilanciare con
# SUPERBOT_ACCEPT_ORIGINAL_SHA=<64 caratteri>).
LC_ALL=C
export LC_ALL
EXPECTED_NEW=e6dc3efc37a2d151be470cfad73b31919b545334cbbe13e2dff18ecebc64e7c5
# run.sh scritto dall'azione "setup" del workflow sg-extbackup.yml su rule-pool (fed2e3f), prima della correzione
KNOWN_OLD=bd7cced916c28b4ce75c14b3805338318072d0817578e9708943743787a6e083
EXTB="${SUPERBOT_EXTB:-/opt/superbot-extbackup}"
FIXDIR="${SUPERBOT_FIXDIR:-/root/extbackup-fix-20261109}"
TARGET="$EXTB/run.sh"
ORIG="$FIXDIR/run.sh.original"
ORIGSHA="$FIXDIR/run.sh.original.sha256"
CMD="${1:-}"
[ $# -gt 0 ] && shift
APPLY=0
SRC=""
while [ $# -gt 0 ]; do
  case "$1" in
    --apply) APPLY=1 ;;
    --src)
      shift
      SRC="${1:-}"
      ;;
    *) echo "opzione sconosciuta: $1" >&2; exit 2 ;;
  esac
  shift
done
case "$CMD" in status | install | rollback) ;; *) echo "uso: sh install-wrapper.sh status | install [--apply] [--src FILE] | rollback [--apply]" >&2; exit 2 ;; esac
if [ -z "$SRC" ]; then
  SRC="$(dirname "$0")/run.sh"
fi

ok() { echo "OK         $*"; }
info() { echo "           $*"; }
die() { echo "BLOCCO     $*"; echo "ESITO: NESSUNA MODIFICA - $*"; exit 1; }
hash_of() { sha256sum "$1" 2>/dev/null | cut -d' ' -f1; }
label_of() {
  case "$1" in
    "$EXPECTED_NEW") echo "versione CORRETTA (con --bot-stopped)" ;;
    "$KNOWN_OLD") echo "versione PRECEDENTE nota (rule-pool fed2e3f, senza --bot-stopped)" ;;
    *) echo "versione SCONOSCIUTA" ;;
  esac
}
is_hex64() { case "$1" in *[!0-9a-f]* | '') return 1 ;; esac; [ "${#1}" -eq 64 ]; }

common_checks() {
  [ "$(id -u 2>/dev/null)" = 0 ] || die "va eseguito come root (adesso: uid $(id -u 2>/dev/null))"
  [ -d "$EXTB" ] || die "cartella $EXTB assente"
  [ -f "$TARGET" ] && [ ! -L "$TARGET" ] || die "$TARGET non e' un file normale (assente o collegamento simbolico)"
  S="$(systemctl is-active superbot-extbackup.service 2>/dev/null)"
  case "$S" in
    inactive | failed) ok "superbot-extbackup.service non e' in corso (stato: $S)" ;;
    *) die "superbot-extbackup.service non e' fermo (stato: ${S:-sconosciuto}): non modifico il wrapper durante un backup" ;;
  esac
  if pgrep -f '^[^ ]*python[0-9.]* (-I )?[^ ]*/(external_backup|backup_brain|backup_app_db)\.py' >/dev/null 2>&1; then
    die "c'e' un processo di backup in esecuzione"
  fi
  ok "nessun processo di backup in esecuzione"
}

# sostituzione atomica di $TARGET con il file $1; verifica che l'impronta finale sia $2
atomic_put() {
  T="$EXTB/.run.sh.new.$$"
  trap 'rm -f "$T"' EXIT
  cat "$1" >"$T" || return 1
  chmod 700 "$T" || return 1
  chown --reference="$TARGET" "$T" 2>/dev/null || return 1
  [ "$(hash_of "$T")" = "$2" ] || return 1
  sh -n "$T" || return 1
  mv -f "$T" "$TARGET" || return 1
  trap - EXIT
  [ "$(hash_of "$TARGET")" = "$2" ]
}

case "$CMD" in
  status)
    CUR="$(hash_of "$TARGET")"
    echo "== Fotografia (sola lettura)"
    info "run.sh installato: ${CUR:-assente} - $(label_of "${CUR:-x}")"
    info "run.sh atteso (correzione): $EXPECTED_NEW"
    [ -f "$TARGET" ] && info "modo/proprietario: $(stat -c '%a %U:%G' "$TARGET")"
    if [ -f "$ORIG" ]; then info "originale salvato: $(hash_of "$ORIG") in $ORIG"; else info "nessun originale salvato in $FIXDIR"; fi
    info "superbot-extbackup.service: $(systemctl is-active superbot-extbackup.service 2>/dev/null)"
    exit 0
    ;;
  install)
    echo "== Installazione del solo wrapper run.sh ($([ "$APPLY" = 1 ] && echo APPLICA || echo SIMULAZIONE))"
    common_checks
    [ -f "$SRC" ] && [ ! -L "$SRC" ] || die "origine $SRC non e' un file normale"
    SH="$(hash_of "$SRC")"
    [ "$SH" = "$EXPECTED_NEW" ] || die "l'origine ha sha256 $SH, atteso $EXPECTED_NEW: file diverso da quello approvato"
    sh -n "$SRC" || die "l'origine non e' una shell valida"
    ok "origine verificata: sha256 $SH"
    CUR="$(hash_of "$TARGET")"
    info "run.sh installato ora: $CUR - $(label_of "$CUR")"
    if [ "$CUR" = "$EXPECTED_NEW" ]; then
      ok "run.sh e' gia' la versione corretta: niente da fare"
      echo "ESITO: GIA' INSTALLATO - nessuna modifica"
      exit 0
    fi
    if [ "$CUR" != "$KNOWN_OLD" ]; then
      if [ "${SUPERBOT_ACCEPT_ORIGINAL_SHA:-}" = "$CUR" ] && is_hex64 "$CUR"; then
        ok "run.sh attuale e' una versione sconosciuta ma ACCETTATA ESPLICITAMENTE (SUPERBOT_ACCEPT_ORIGINAL_SHA)"
      else
        die "run.sh attuale ha sha256 $CUR: non e' ne' la versione corretta ne' quella precedente nota. Non sostituisco alla cieca: inviare questo testo alla revisione; se approvato, rilanciare con SUPERBOT_ACCEPT_ORIGINAL_SHA=$CUR"
      fi
    fi
    if [ -e "$ORIG" ]; then
      [ "$(hash_of "$ORIG")" = "$CUR" ] || die "in $FIXDIR c'e' gia' un originale salvato DIVERSO dal run.sh attuale: non lo sovrascrivo. Decidere con la revisione"
      ok "originale gia' salvato e uguale al run.sh attuale (non lo riscrivo)"
    else
      info "salverei una copia dell'originale in $ORIG"
    fi
    if [ "$APPLY" != 1 ]; then
      info "scriverei $TARGET (modo 700, stesso proprietario dell'attuale) in modo atomico e rileggerei l'impronta"
      echo "ESITO: SIMULAZIONE RIUSCITA - nessuna modifica. Per applicare: sh install-wrapper.sh install --apply"
      exit 0
    fi
    mkdir -p "$FIXDIR" && chmod 700 "$FIXDIR" || die "impossibile creare $FIXDIR"
    if [ ! -e "$ORIG" ]; then
      cp -p "$TARGET" "$ORIG.tmp" || die "copia dell'originale non riuscita"
      [ "$(hash_of "$ORIG.tmp")" = "$CUR" ] || { rm -f "$ORIG.tmp"; die "la copia dell'originale non coincide"; }
      mv "$ORIG.tmp" "$ORIG" || die "salvataggio dell'originale non riuscito"
      echo "$CUR  run.sh" >"$ORIGSHA"
      ok "originale salvato in $ORIG (sha256 $CUR)"
    fi
    if atomic_put "$SRC" "$EXPECTED_NEW"; then
      ok "run.sh installato e riletto: sha256 $(hash_of "$TARGET") ($(stat -c '%a %U:%G' "$TARGET"))"
      echo "ESITO: INSTALLATO - solo run.sh modificato. Prossimo passo: avviare il backup e verificare. Rollback: sh install-wrapper.sh rollback --apply"
      exit 0
    fi
    echo "BLOCCO     scrittura o verifica non riuscita"
    if [ "$(hash_of "$TARGET")" = "$CUR" ]; then
      echo "ESITO: FALLITO - run.sh NON e' stato modificato (sha256 $CUR)"
      exit 1
    fi
    info "run.sh e' cambiato: rimetto l'originale"
    if atomic_put "$ORIG" "$CUR"; then
      echo "ESITO: FALLITO - originale rimesso a posto (sha256 $CUR)"
    else
      echo "ESITO: FALLITO E ROLLBACK NON RIUSCITO - copia dell'originale in $ORIG: avvisare subito la revisione"
    fi
    exit 1
    ;;
  rollback)
    echo "== Ripristino del run.sh originale ($([ "$APPLY" = 1 ] && echo APPLICA || echo SIMULAZIONE))"
    common_checks
    [ -f "$ORIG" ] && [ -f "$ORIGSHA" ] || die "nessun originale salvato in $FIXDIR: niente da ripristinare"
    REC="$(cut -d' ' -f1 "$ORIGSHA")"
    is_hex64 "$REC" || die "$ORIGSHA illeggibile"
    [ "$(hash_of "$ORIG")" = "$REC" ] || die "la copia salvata dell'originale non coincide piu' con la sua impronta registrata: non la uso"
    ok "originale salvato integro: sha256 $REC"
    CUR="$(hash_of "$TARGET")"
    info "run.sh installato ora: $CUR - $(label_of "$CUR")"
    if [ "$CUR" = "$REC" ]; then
      ok "run.sh e' gia' l'originale: niente da fare"
      echo "ESITO: GIA' RIPRISTINATO - nessuna modifica"
      exit 0
    fi
    if [ "$CUR" != "$EXPECTED_NEW" ] && [ "${SUPERBOT_ACCEPT_ORIGINAL_SHA:-}" != "$CUR" ]; then
      die "run.sh attuale ($CUR) non e' quello installato da questa procedura: non lo sovrascrivo alla cieca"
    fi
    if [ "$APPLY" != 1 ]; then
      echo "ESITO: SIMULAZIONE RIUSCITA - nessuna modifica. Per applicare: sh install-wrapper.sh rollback --apply"
      exit 0
    fi
    if atomic_put "$ORIG" "$REC"; then
      chmod --reference="$ORIG" "$TARGET" 2>/dev/null
      ok "run.sh originale ripristinato e riletto: sha256 $(hash_of "$TARGET")"
      echo "ESITO: RIPRISTINATO - solo run.sh modificato"
      exit 0
    fi
    if [ "$(hash_of "$TARGET")" = "$CUR" ]; then
      echo "ESITO: RIPRISTINO NON RIUSCITO - run.sh NON e' stato modificato (sha256 $CUR)"
      exit 1
    fi
    echo "ESITO: RIPRISTINO NON RIUSCITO - la copia dell'originale resta in $ORIG: avvisare la revisione"
    exit 1
    ;;
esac
