#!/usr/bin/env bash
# AI Arena — preparazione delle TRE run PAPER in pausa sulla VPS Singapore. Nessun servizio avviato, nessun T0,
# nessun mandato approvato, nessuna chiave, nessuna spesa AI, nessun tocco a Brain storico/Falco/Toro/HI-TV.
#
#   --inspect  --sha <40hex> --day AAAA-MM-GG            (predefinito, sola lettura)
#   --update-stage --sha <40hex>                          stage codice al commit revisionato + venv senza pacchetti
#   --prepare-paused --sha <40hex> --day AAAA-MM-GG       tre run in pausa (frase di conferma interna al comando)
set -Eeuo pipefail
IFS=$'\n\t'
REPO='https://github.com/alexiptv82/SuperBot-Trading.git'
BRANCH='work/arena-prepare-paused-runs-20261118'
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
    --inspect|--update-stage|--prepare-paused) MODE="$1"; shift ;;
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
stage_py(){ printf '%s' "$STAGE/.venv/bin/python3"; }
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
    scratch="$(mktemp -d /opt/.arena-stage-new.XXXXXXXX)"
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
  if [[ -e "$ETC/trial.env" ]]; then
    grep -qx "ARENA_DAY=$DAY" "$ETC/trial.env" || die 'TRIAL_ENV_DIFFERENT_DAY'
  else
    install -d -o root -g root -m 0700 "$ETC"
    umask 077
    printf 'ARENA_DAY=%s\nARENA_DAY_COMPACT=%s\nV3_ARENA_TRIAL_DAY=%s\n' "$DAY" "$compact" "$DAY" > "$ETC/trial.env"
    say 'TRIAL_ENV_WRITTEN=TRUE'
  fi
  setup prepare-paused --root "$ROOT" --day "$DAY" --confirm 'PREPARA-TRE-RUN-PAPER-IN-PAUSA' || die 'PREPARE_REFUSED'
  arena_units_inactive || die 'ARENA_UNIT_STATE_CHANGED_ALERT'
  brain_ok || die 'BRAIN_STATE_CHANGED_ALERT'
  say 'RESULT=THREE_RUNS_PREPARED_PAUSED_NO_T0'
  say 'T0_ASSIGNED=FALSE MANDATES_APPROVED=FALSE SERVICES_STARTED=FALSE PAID_INFERENCE=FALSE'
}

case "$MODE" in
  --inspect) inspect ;;
  --update-stage) inspect; update_stage ;;
  --prepare-paused) prepare; inspect ;;
esac
