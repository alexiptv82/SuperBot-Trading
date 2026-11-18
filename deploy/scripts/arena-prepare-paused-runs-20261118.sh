#!/usr/bin/env bash
# AI Arena — preparazione delle TRE run PAPER in pausa sulla VPS Singapore. Nessun servizio avviato, nessun T0,
# nessun mandato approvato, nessuna chiave, nessuna spesa AI, nessun tocco a Brain storico/Falco/Toro/HI-TV.
#
#   --inspect  --sha <40hex> --day AAAA-MM-GG            (predefinito, sola lettura)
#   --update-stage --sha <40hex>                          stage codice al commit revisionato + venv senza pacchetti
#   --prepare-paused --sha <40hex> --day AAAA-MM-GG       tre run in pausa (frase di conferma interna al comando)
#   --replace-prepared --sha <40hex>                      SOSTITUISCE le tre run preparate (mai avviate, 0 posizioni)
#        con tre nuove alla config del commit: archivio verificabile delle vecchie, stage aggiornato, uscite
#        fermate SOLO dopo can-stop-exit e riavviate. Brain storico, bridge e runner decisionali non toccati.
set -Eeuo pipefail
IFS=$'\n\t'
REPO='https://github.com/alexiptv82/SuperBot-Trading.git'
BRANCH='work/arena-72h-18usd-budget-20261118'
STAGE='/opt/superbot-arena-stage'
ROOT='/opt/superbot-ai-arena-paper'
ETC='/etc/superbot-arena'
PY_SYS='/usr/bin/python3'
# Solo per i test locali: prefisso dei percorsi, accettato unicamente sotto /tmp/.
if [[ -n "${ARENA_PREP_TEST_PREFIX:-}" ]]; then
  [[ "$ARENA_PREP_TEST_PREFIX" == /tmp/* ]] || { echo 'ARENA_PREP_REFUSED=TEST_PREFIX_OUTSIDE_TMP'; exit 2; }
  STAGE="$ARENA_PREP_TEST_PREFIX$STAGE"; ROOT="$ARENA_PREP_TEST_PREFIX$ROOT"; ETC="$ARENA_PREP_TEST_PREFIX$ETC"
fi
say(){ printf 'ARENA_PREP_%s\n' "$*"; }
die(){ say "REFUSED=$1"; exit 2; }

MODE='--inspect'; SHA=''; DAY=''
while [[ $# -gt 0 ]]; do
  case "$1" in
    --inspect|--update-stage|--prepare-paused|--replace-prepared) MODE="$1"; shift ;;
    --branch) BRANCH="${2:-}"; shift 2 ;;
    --sha) SHA="${2:-}"; shift 2 ;;
    --day) DAY="${2:-}"; shift 2 ;;
    *) die "UNKNOWN_ARGUMENT" ;;
  esac
done
[[ "$SHA" =~ ^[0-9a-f]{40}$ ]] || die 'SHA_REQUIRED_40_HEX'
[[ -z "$DAY" || "$DAY" =~ ^20[0-9]{2}-[01][0-9]-[0-3][0-9]$ ]] || die 'DAY_FORMAT'

brain_ok(){
  for u in superbot-v3-paper-brain-runner.service superbot-v3-paper-brain-exit.service; do
    [[ "$(systemctl is-active "$u" 2>/dev/null || true)" == 'active' ]] || return 1
  done
}
arena_units_inactive(){
  for p in deepseek qwen minimax; do for t in runner exit; do
    s="$(systemctl is-active "superbot-arena-$t@$p.service" 2>/dev/null || true)"
    [[ "$s" == 'inactive' || "$s" == 'unknown' || "$s" == 'failed' ]] || return 1
  done; done
  s="$(systemctl is-active superbot-arena-close-bridge.service 2>/dev/null || true)"
  [[ "$s" == 'inactive' || "$s" == 'unknown' || "$s" == 'failed' ]]
}
runners_inactive(){
  for p in deepseek qwen minimax; do
    s="$(systemctl is-active "superbot-arena-runner@$p.service" 2>/dev/null || true)"
    [[ "$s" == 'inactive' || "$s" == 'unknown' || "$s" == 'failed' ]] || return 1
  done
}
BACKUPS="${ARENA_PREP_TEST_PREFIX:-}/opt/superbot-v3-backups"
HEALTH_WAIT_S="${ARENA_PREP_HEALTH_WAIT_S:-150}"
stage_py(){ printf '%s' "$STAGE/.venv/bin/python3"; }
code_setup(){                                     # trial_setup da una cartella di codice qualunque (es. temporanea)
  local dir="$1"; shift
  env -u DEEPSEEK_API_KEY -u OPENROUTER_API_KEY -u V3_ARENA_ALLOW_INFERENCE \
    PYTHONPATH="$dir:$dir/backend" PYTHONDONTWRITEBYTECODE=1 DESK_MODE=paper TRADING_MODE=paper \
    "$dir/.venv/bin/python3" -s -m backend.v3.arena.trial_setup "$@"
}
fetch_code(){                                     # clone del commit revisionato in una cartella nuova + venv vuota
  local dest="$1"
  if [[ -n "${ARENA_PREP_TEST_SOURCE:-}" ]]; then git clone -q --no-hardlinks "$ARENA_PREP_TEST_SOURCE" "$dest" || return 1
  else GIT_TERMINAL_PROMPT=0 git clone --quiet --no-tags --single-branch --branch "$BRANCH" "$REPO" "$dest" || return 1; fi
  git -C "$dest" checkout --quiet --detach "$SHA" || return 1
  [[ "$(git -C "$dest" rev-parse HEAD)" == "$SHA" ]] || return 1
  "$PY_SYS" -m venv "$dest/.venv" || return 1
}
setup(){
  env -u DEEPSEEK_API_KEY -u OPENROUTER_API_KEY -u V3_ARENA_ALLOW_INFERENCE \
    PYTHONPATH="$STAGE:$STAGE/backend" PYTHONDONTWRITEBYTECODE=1 DESK_MODE=paper TRADING_MODE=paper \
    "$(stage_py)" -s -m backend.v3.arena.trial_setup "$@"
}

inspect(){
  say 'READ_ONLY=TRUE'
  say "EXPECTED_SHA=$SHA"
  if brain_ok; then say 'BRAIN_HISTORICAL=ACTIVE'; else say 'BRAIN_HISTORICAL=NOT_ACTIVE_ALERT'; fi
  if arena_units_inactive; then say 'ARENA_UNITS=ALL_INACTIVE'; else say 'ARENA_UNITS=SOMETHING_RUNNING_ALERT'; fi
  if [[ -d "$STAGE/.git" && ! -L "$STAGE" ]]; then
    say "STAGE_SHA=$(git -C "$STAGE" rev-parse HEAD 2>/dev/null || echo unknown)"
  else say 'STAGE=MISSING'; fi
  if [[ -x "$(stage_py)" ]]; then say "STAGE_VENV=$("$(stage_py)" -c 'import sys;print(sys.version.split()[0])')"
  else say 'STAGE_VENV=MISSING_SERVICES_WOULD_FAIL'; fi
  for u in superbot-arena-runner@.service superbot-arena-exit@.service superbot-arena-close-bridge.service; do
    if cmp -s "$STAGE/deploy/arena-paper-services/$u" "/etc/systemd/system/$u"; then say "UNIT_MATCHES_STAGE=$u"
    else say "UNIT_DIFFERS_OR_MISSING=$u"; fi
  done
  [[ -f "$ETC/trial.env" ]] && say "TRIAL_ENV=$(grep -E '^ARENA_DAY=' "$ETC/trial.env" || true)" || say 'TRIAL_ENV=MISSING'
  if [[ -n "$DAY" && -x "$(stage_py)" && -f "$STAGE/backend/v3/arena/trial_setup.py" ]]; then
    setup inspect --root "$ROOT" --day "$DAY" || true
  fi
}

update_stage(){
  [[ "$(id -u)" == 0 ]] || die 'ROOT_REQUIRED'
  brain_ok || die 'BRAIN_HISTORICAL_NOT_ACTIVE'
  arena_units_inactive || die 'ARENA_UNIT_RUNNING'
  if [[ -d "$STAGE/.git" && "$(git -C "$STAGE" rev-parse HEAD)" == "$SHA" ]]; then
    say 'STAGE_ALREADY_AT_SHA=TRUE'
  else
    scratch="$(mktemp -d "${ARENA_PREP_TEST_PREFIX:-}/opt/.arena-stage-new.XXXXXXXX")"
    GIT_TERMINAL_PROMPT=0 git clone --quiet --no-tags --single-branch --branch "$BRANCH" "$REPO" "$scratch/c" \
      || die 'CLONE_FAILED'
    git -C "$scratch/c" checkout --quiet --detach "$SHA" || die 'SHA_NOT_ON_BRANCH'
    [[ "$(git -C "$scratch/c" rev-parse HEAD)" == "$SHA" ]] || die 'SHA_MISMATCH'
    if [[ -e "$STAGE" ]]; then
      old="$STAGE.prev-$(git -C "$STAGE" rev-parse --short=8 HEAD 2>/dev/null || echo x)-$(date -u +%Y%m%dT%H%M%SZ)"
      mv -T -- "$STAGE" "$old"; say "PREVIOUS_STAGE_KEPT=$old"
    fi
    mv -T -- "$scratch/c" "$STAGE"; rmdir "$scratch" || true
    say "STAGE_SHA=$SHA"
  fi
  if [[ ! -x "$(stage_py)" ]]; then
    "$PY_SYS" -m venv "$STAGE/.venv" || die 'VENV_CREATE_FAILED'      # solo libreria standard: nessun pip
    say 'STAGE_VENV_CREATED_NO_PACKAGES=TRUE'
  fi
  env -u DEEPSEEK_API_KEY -u OPENROUTER_API_KEY PYTHONPATH="$STAGE:$STAGE/backend" PYTHONDONTWRITEBYTECODE=1 \
    "$(stage_py)" -s -c 'import backend.v3.arena.runner, backend.v3.runner.exit_worker, backend.v3.arena.close_bridge_server, backend.v3.arena.trial_setup; print("ARENA_PREP_IMPORTS=OK")' \
    || die 'IMPORTS_FAILED'
  for u in superbot-arena-runner@.service superbot-arena-exit@.service superbot-arena-close-bridge.service; do
    cmp -s "$STAGE/deploy/arena-paper-services/$u" "/etc/systemd/system/$u" || say "UNIT_NEEDS_REINSTALL_REVIEW=$u"
  done
  say 'NO_SERVICE_STARTED=TRUE'
}

prepare(){
  [[ "$(id -u)" == 0 ]] || die 'ROOT_REQUIRED'
  [[ -n "$DAY" ]] || die 'DAY_REQUIRED'
  brain_ok || die 'BRAIN_HISTORICAL_NOT_ACTIVE'
  arena_units_inactive || die 'ARENA_UNIT_RUNNING'
  [[ "$(git -C "$STAGE" rev-parse HEAD 2>/dev/null)" == "$SHA" ]] || die 'STAGE_NOT_AT_SHA_RUN_UPDATE_STAGE'
  [[ -x "$(stage_py)" ]] || die 'STAGE_VENV_MISSING'
  [[ -d "$ROOT" && ! -L "$ROOT" && "$(stat -c '%u:%a' "$ROOT")" == '0:700' ]] || die 'ARENA_ROOT_UNSAFE'
  compact="${DAY//-/}"
  if [[ -e "$ETC/trial.env" ]]; then                       # controllo PRIMA di preparare, scrittura solo DOPO
    grep -qx "ARENA_DAY=$DAY" "$ETC/trial.env" || die 'TRIAL_ENV_DIFFERENT_DAY'
  fi
  setup prepare-paused --root "$ROOT" --day "$DAY" --confirm 'PREPARA-TRE-RUN-PAPER-IN-PAUSA' || die 'PREPARE_REFUSED'
  if [[ ! -e "$ETC/trial.env" ]]; then
    install -d -o root -g root -m 0700 "$ETC"
    tmp="$(mktemp "$ETC/.trial.env.XXXXXX")"
    printf 'ARENA_DAY=%s\nARENA_DAY_COMPACT=%s\nV3_ARENA_TRIAL_DAY=%s\n' "$DAY" "$compact" "$DAY" > "$tmp"
    chmod 0600 "$tmp"; mv -T -- "$tmp" "$ETC/trial.env"
    say 'TRIAL_ENV_WRITTEN=TRUE'
  fi
  arena_units_inactive || die 'ARENA_UNIT_STATE_CHANGED_ALERT'
  brain_ok || die 'BRAIN_STATE_CHANGED_ALERT'
  say 'RESULT=THREE_RUNS_PREPARED_PAUSED_NO_T0'
  say 'T0_ASSIGNED=FALSE MANDATES_APPROVED=FALSE SERVICES_STARTED=FALSE PAID_INFERENCE=FALSE'
}

# Recupero fail-closed di --replace-prepared. Non tocca mai Brain storico o runner decisionali.
# Stato globale: i trap EXIT/HUP/INT/TERM devono poterlo leggere anche dopo l'uscita dalla funzione.
REPLACE_TX_ACTIVE=0
REPLACE_TX_DAY=''
REPLACE_TX_ARCHIVE=''
REPLACE_TX_OLD_STAGE=''
REPLACE_TX_SCRATCH=''
replace_rollback(){
  local rc="${1:-1}" p run oldrun newrun failed now ok=1 compact
  trap - EXIT HUP INT TERM
  [[ "$REPLACE_TX_ACTIVE" == 1 ]] || return 0
  set +e
  say "ROLLBACK_STARTED=TRUE CODE=$rc"
  compact="${REPLACE_TX_DAY//-/}"
  now="$(date -u +%Y%m%dT%H%M%SZ)"
  failed="$BACKUPS/arena-replace-failed-$REPLACE_TX_DAY-$now-$RANDOM"
  # Gli exit sulle run nuove (ancora in pausa) devono rilasciare il journal prima del ripristino.
  for p in deepseek qwen minimax; do
    systemctl stop "superbot-arena-exit@$p.service" >/dev/null 2>&1 || ok=0
  done
  if [[ -n "$REPLACE_TX_ARCHIVE" && -d "$REPLACE_TX_ARCHIVE" ]]; then
    mkdir -p "$failed" || ok=0
    for p in deepseek qwen minimax; do
      run="brain-$p-paper$compact"
      newrun="$ROOT/$p/$run"
      oldrun="$REPLACE_TX_ARCHIVE/$p/$run"
      if [[ -e "$newrun" ]]; then
        mkdir -p "$failed/$p" && mv -T -- "$newrun" "$failed/$p/$run" || ok=0
      fi
      if [[ -d "$oldrun" ]]; then
        mkdir -p "$ROOT/$p" && mv -T -- "$oldrun" "$newrun" || ok=0
      elif [[ ! -d "$newrun" ]]; then
        ok=0
      fi
    done
    if [[ -f "$REPLACE_TX_ARCHIVE/SUPERSEDED.json" ]]; then
      mv -T -- "$REPLACE_TX_ARCHIVE/SUPERSEDED.json" "$REPLACE_TX_ARCHIVE/SUPERSEDED-ROLLED-BACK.json" || ok=0
    fi
  fi
  # Lo stage precedente deve tornare al percorso originale PRIMA dei tre start.
  if [[ -n "$REPLACE_TX_OLD_STAGE" && -d "$REPLACE_TX_OLD_STAGE" ]]; then
    if [[ -e "$STAGE" ]]; then
      mv -T -- "$STAGE" "$STAGE.failed-$now-$RANDOM" || ok=0
    fi
    if [[ -d "$REPLACE_TX_OLD_STAGE" && ! -e "$STAGE" ]]; then
      mv -T -- "$REPLACE_TX_OLD_STAGE" "$STAGE" || ok=0
    else
      ok=0
    fi
  fi
  for p in deepseek qwen minimax; do
    systemctl start "superbot-arena-exit@$p.service" >/dev/null 2>&1 || ok=0
  done
  if [[ "$ok" == 1 ]] && brain_ok; then
    say 'ROLLBACK_RESTORED=TRUE OLD_RUNS_BACK=TRUE EXIT_START_REQUESTED=TRUE'
  else
    say "ROLLBACK_INCOMPLETE=TRUE FAILED_NEW_SAVED=$failed"
    say 'MANUAL_RECOVERY_REQUIRED=TRUE DO_NOT_START_RUNNERS'
  fi
}

replace_prepared(){
  [[ "$(id -u)" == 0 ]] || die 'ROOT_REQUIRED'
  [[ -f "$ETC/trial.env" ]] || die 'TRIAL_ENV_MISSING'
  DAY="$(sed -n 's/^ARENA_DAY=//p' "$ETC/trial.env")"
  [[ "$DAY" =~ ^20[0-9]{2}-[01][0-9]-[0-3][0-9]$ ]] || die 'TRIAL_ENV_DAY_INVALID'
  brain_ok || die 'BRAIN_HISTORICAL_NOT_ACTIVE'
  runners_inactive || die 'ARENA_RUNNER_ACTIVE'
  new="$(mktemp -d "${ARENA_PREP_TEST_PREFIX:-}/opt/.arena-stage-new.XXXXXXXX")"; code="$new/c"
  fetch_code "$code" || die 'FETCH_OR_SHA_FAILED'
  say "NEW_CODE_SHA=$SHA DAY=$DAY"
  # 1) sola lettura con il codice nuovo: tre run preparate, 0 posizioni ciascuna
  code_setup "$code" inspect --root "$ROOT" --day "$DAY" > "$new/inspect-before.json" || true
  grep -q '"stage": "PREPARED_PAUSED_NO_T0"' "$new/inspect-before.json" || die 'RUNS_NOT_PREPARED_PAUSED_NO_T0'
  for p in deepseek qwen minimax; do
    code_setup "$code" can-stop-exit --provider "$p" --root "$ROOT" --day "$DAY" >/dev/null || die "CAN_STOP_EXIT_DENIED_$p"
  done
  say 'ZERO_POSITIONS_VERIFIED=TRUE'
  # 2) da qui i trap ripristinano stage, vecchie run e uscite in caso di errore/HUP.
  [[ -d "$STAGE/.git" && ! -L "$STAGE" ]] || die 'STAGE_INVALID'
  REPLACE_TX_ACTIVE=1; REPLACE_TX_DAY="$DAY"; REPLACE_TX_ARCHIVE=''; REPLACE_TX_OLD_STAGE=''
  REPLACE_TX_SCRATCH="$new"
  # Il percorso di archivio e' noto PRIMA di qualunque move, anche se Termius si disconnette.
  REPLACE_TX_ARCHIVE="$BACKUPS/arena-superseded-$DAY-$(date -u +%s%3N)-$(head -c 4 /dev/urandom | od -An -tx1 | tr -d ' \\n')"
  [[ "$REPLACE_TX_ARCHIVE" == "$BACKUPS"/arena-superseded-* && ! -e "$REPLACE_TX_ARCHIVE" ]] \
    || die 'ARCHIVE_NAME_COLLISION'
  trap 'replace_rollback "$?"' EXIT
  trap 'exit 129' HUP
  trap 'exit 130' INT
  trap 'exit 143' TERM
  for p in deepseek qwen minimax; do systemctl stop "superbot-arena-exit@$p.service"; done
  restart_exits(){ for p in deepseek qwen minimax; do systemctl start "superbot-arena-exit@$p.service"; done; }
  # 3) archivio delle vecchie run (mai cancellate)
  if ! code_setup "$code" supersede-prepared --root "$ROOT" --day "$DAY" --archive-parent "$BACKUPS" \
        --confirm "ARCHIVIA-TRE-RUN-PREPARATE-$DAY" \
        --archive-basename "${REPLACE_TX_ARCHIVE##*/}" > "$new/supersede.json"; then
    restart_exits; cat "$new/supersede.json"; die 'SUPERSEDE_REFUSED_OLD_RUNS_KEPT_EXITS_RESTARTED'
  fi
  archived_actual="$("$PY_SYS" - "$new/supersede.json" <<'PY'
import json,sys
o=json.load(open(sys.argv[1],encoding="utf-8"))
print(o["archive"])
PY
)"
  [[ "$archived_actual" == "$REPLACE_TX_ARCHIVE" && -d "$REPLACE_TX_ARCHIVE" ]] \
    || die 'ARCHIVE_PATH_INVALID'
  say "OLD_RUNS_ARCHIVED=$REPLACE_TX_ARCHIVE"
  if [[ -n "${ARENA_PREP_TEST_PREFIX:-}" && "${ARENA_PREP_TEST_FAILPOINT:-}" == after_archive ]]; then
    die 'INJECTED_FAILURE_AFTER_ARCHIVE'
  fi
  # 4) stage nuovo (il precedente resta accanto) e 5) tre run nuove in pausa
  old="$STAGE.prev-$(git -C "$STAGE" rev-parse --short=8 HEAD 2>/dev/null || echo x)-$(date -u +%Y%m%dT%H%M%SZ)"
  [[ -e "$STAGE" ]] || die 'STAGE_MISSING_AFTER_ARCHIVE'
  REPLACE_TX_OLD_STAGE="$old"
  mv -T -- "$STAGE" "$old"
  say "PREVIOUS_STAGE_KEPT=$old"
  if [[ -n "${ARENA_PREP_TEST_PREFIX:-}" && "${ARENA_PREP_TEST_FAILPOINT:-}" == after_stage_saved ]]; then
    die 'INJECTED_FAILURE_AFTER_STAGE_SAVED'
  fi
  mv -T -- "$code" "$STAGE"
  # Conservare lo scratch finche' il nuovo stage e le nuove uscite non siano sani.
  setup prepare-paused --root "$ROOT" --day "$DAY" --confirm 'PREPARA-TRE-RUN-PAPER-IN-PAUSA' >/dev/null \
    || die 'NEW_PREPARE_FAILED_NO_RUNS_EXITS_STOPPED_OLD_RUNS_IN_ARCHIVE'
  say 'NEW_RUNS_PREPARED_PAUSED_NO_T0=TRUE'
  if [[ -n "${ARENA_PREP_TEST_PREFIX:-}" && "${ARENA_PREP_TEST_FAILPOINT:-}" == after_new_prepared ]]; then
    die 'INJECTED_FAILURE_AFTER_NEW_PREPARED'
  fi
  # 6) uscite di nuovo attive e sane sulle run nuove
  restart_exits
  for i in $(seq 1 "$HEALTH_WAIT_S"); do
    setup inspect --root "$ROOT" --day "$DAY" > /tmp/.arena-inspect.$$ 2>/dev/null || true
    [[ "$(grep -c '"exit_service_healthy": true' /tmp/.arena-inspect.$$)" == 3 ]] && break
    sleep 1
  done
  n="$(grep -c '"exit_service_healthy": true' /tmp/.arena-inspect.$$ || true)"; rm -f /tmp/.arena-inspect.$$
  brain_ok || say 'BRAIN_STATE_CHANGED_ALERT'
  [[ "$n" == 3 ]] || die "EXITS_NOT_HEALTHY_COUNT_$n"
  # Commit della sostituzione: da qui in poi nessun trap deve ripristinare le vecchie run.
  REPLACE_TX_ACTIVE=0
  trap - EXIT HUP INT TERM
  rmdir "$new" 2>/dev/null || true
  say 'RESULT=PREPARED_RUNS_REPLACED_EXITS_HEALTHY'
  say 'T0_ASSIGNED=FALSE RUNNERS_STARTED=FALSE PAID_INFERENCE=FALSE BRIDGE_UNTOUCHED=TRUE'
}

case "$MODE" in
  --inspect) inspect ;;
  --update-stage) inspect; update_stage ;;
  --prepare-paused) prepare; inspect ;;
  --replace-prepared) replace_prepared ;;
esac
