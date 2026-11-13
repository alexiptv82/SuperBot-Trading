#!/usr/bin/env bash
# Brain V3 PAPER-only exit-feed hotfix. Default: preflight only.
# --apply is explicitly opt-in and MUST have separate user authorization.
# No Git checkout, no merge, no Actions, no changes to Bitget hotfixes or trading policies.
set -Eeuo pipefail
export PYTHONDONTWRITEBYTECODE=1
MODE="${1:---check}"
case "$MODE" in --check|--apply) ;; *) echo 'Usage: script [--check|--apply]'; exit 2;; esac
[[ "${EUID}" -eq 0 ]] || { echo "BRAIN_P0_INSTALL ABORT=must_run_as_root"; exit 2; }
RUN=/opt/superbot-v3-paper-runs/brain-v3-paper20261111
LIVE=/opt/superbot-v3-rc84-repair-ab7e0b7
STAGE=/opt/superbot-v3-rc84-stage
PYTHON=/opt/superbot-v3-rc70-stage/.venv/bin/python3
RUNNER=superbot-v3-paper-brain-runner.service
EXIT=superbot-v3-paper-brain-exit.service
PIN=4efd1a31051dd023480d4d9a327016ae9a6f9a0e
BASE_MON=30e183c17be00ebade2e3355992feb54c76bdd4e84d6408df10f46944cb0d248
BASE_FEED=e40de9a4fa3f04084b0f687b68a9b88ff4a17aac48459e5439d6f4d43c10b547
HOTFIX_CONTRACTS=9f6eb36fc32a104760860b565a8b2ec985afe20ec9ac01eec99b0d8809e41cf7
HOTFIX_CANDLES=9daffbf375a31bc835d96851311ade1c6029f3049befdb75504553c4719a4b8b
NEW_MON=623dcc31b3e6c5c6c31827ba3d98f2fa018ca6d38bb2072ad4d7aefbe71627a8
NEW_FEED=4002b8a444bce3c10f93fbaca5c20a9f863bc31d4d8f008a1ec92f9bff752def
MON=backend/v3/runner/monitor.py
FEED=backend/v3/runner/feed.py
CONTRACTS=backend/v3/runner/contracts.py
CANDLES=backend/v3/lab_tools/fetch_candles.py
TMP=$(mktemp -d /tmp/brain-p0-install.XXXXXXXX)
BACKUP=''
CHANGED=0
COMPLETE=0
restore() {
  if [[ "$CHANGED" -eq 1 && "$COMPLETE" -ne 1 && -d "$BACKUP" ]]; then
    echo "BRAIN_P0_INSTALL ROLLBACK=BEGIN backup=$BACKUP"
    for D in "$LIVE" "$STAGE"; do
      NAME=live; [[ "$D" == "$STAGE" ]] && NAME=stage
      for F in "$MON" "$FEED"; do
        KEY=${F##*/}
        install -m 0644 "$BACKUP/$NAME.$KEY" "$D/$F"
      done
    done
    systemctl restart "$EXIT" || true
    systemctl restart "$RUNNER" || true
    echo "BRAIN_P0_INSTALL ROLLBACK=ATTEMPTED review_services_and_pause=1"
  fi
}
clean() {
  code=$?
  if [[ "$code" -ne 0 ]]; then restore; fi
  rm -rf -- "$TMP"
  exit "$code"
}
trap clean EXIT
abort() { echo "BRAIN_P0_INSTALL ABORT=$1"; exit 3; }
[[ -f "$RUN/pause.flag" && ! -L "$RUN/pause.flag" ]] || abort brain_not_paused
[[ -x "$PYTHON" && -f "$RUN/journal.db" ]] || abort python_or_journal_missing
for S in "$RUNNER" "$EXIT"; do systemctl is-active --quiet "$S" || abort service_not_active; done
for S in "$RUNNER" "$EXIT"; do
  [[ "$(systemctl show --value -p WorkingDirectory "$S")" == "$LIVE" ]] || abort working_directory_unexpected
done
for D in "$LIVE" "$STAGE"; do
  [[ -d "$D" && ! -L "$D" ]] || abort directory_unexpected
  for F in "$MON" "$FEED" "$CONTRACTS" "$CANDLES"; do
    [[ -f "$D/$F" && ! -L "$D/$F" ]] || abort source_not_regular
  done
  echo "$BASE_MON  $D/$MON" | sha256sum -c --status || abort monitor_baseline_changed
  echo "$BASE_FEED  $D/$FEED" | sha256sum -c --status || abort feed_baseline_changed
  echo "$HOTFIX_CONTRACTS  $D/$CONTRACTS" | sha256sum -c --status || abort contracts_hotfix_changed
  echo "$HOTFIX_CANDLES  $D/$CANDLES" | sha256sum -c --status || abort candles_hotfix_changed
done
# Journal and open-position check must be read-only; refuse patch with open positions.
(
  cd "$LIVE"
  "$PYTHON" - <<'PY'
from pathlib import Path
from backend.v3.events import EventJournal
from backend.v3.dashboard import build_summary
d=Path('/opt/superbot-v3-paper-runs/brain-v3-paper20261111')
j=EventJournal(d/'journal.db')
count, head=j.verify_chain()
s=build_summary(j,'brain','brain-v3-paper20261111')
n=len(s.open_positions)
print('BRAIN_P0_INSTALL JOURNAL=OK events=%d open_positions=%d' % (count,n))
if n: raise SystemExit(6)
PY
) || abort journal_or_open_positions
for ITEM in "$MON" "$FEED"; do
  NAME=${ITEM##*/}
  curl -fLsS --retry 2 --max-time 30 -o "$TMP/$NAME" \
    "https://raw.githubusercontent.com/alexiptv82/SuperBot-Trading/$PIN/$ITEM" || abort download_failed
done
echo "$NEW_MON  $TMP/monitor.py" | sha256sum -c --status || abort monitor_candidate_mismatch
echo "$NEW_FEED  $TMP/feed.py" | sha256sum -c --status || abort feed_candidate_mismatch
"$PYTHON" - <<'PY' "$TMP"
import ast, pathlib, sys
p=pathlib.Path(sys.argv[1])
for f in ('monitor.py','feed.py'): ast.parse((p/f).read_text())
print('BRAIN_P0_INSTALL CANDIDATE_SYNTAX=PASS')
PY
echo "BRAIN_P0_INSTALL PRECHECK=PASS pause=1 live_and_stage_baseline=match hotfixes=preserved"
if [[ "$MODE" == --check ]]; then
  echo "BRAIN_P0_INSTALL RESULT=CHECK_ONLY no_stage_changes=1 no_restart=1"
  exit 0
fi
# --apply requires operator authorization in the chat and zero open PAPER positions.
umask 077
mkdir -p -m 0700 /opt/superbot-v3-brain-p0-backups
BACKUP=$(mktemp -d /opt/superbot-v3-brain-p0-backups/brain-p0-20261114.XXXXXXXX)
for D in "$LIVE" "$STAGE"; do
  NAME=live; [[ "$D" == "$STAGE" ]] && NAME=stage
  for F in "$MON" "$FEED"; do
    cp -p -- "$D/$F" "$BACKUP/$NAME.${F##*/}"
  done
done
echo "BRAIN_P0_INSTALL BACKUP=CREATED path=$BACKUP"
CHANGED=1
for D in "$LIVE" "$STAGE"; do
  for F in "$MON" "$FEED"; do
    NAME=${F##*/}
    cp -p -- "$TMP/$NAME" "$D/$F.brain-p0-next"
    chmod --reference="$D/$F" "$D/$F.brain-p0-next"
    chown --reference="$D/$F" "$D/$F.brain-p0-next"
    mv -f -- "$D/$F.brain-p0-next" "$D/$F"
  done
done
for D in "$LIVE" "$STAGE"; do
  echo "$NEW_MON  $D/$MON" | sha256sum -c --status || abort installed_monitor_hash
  echo "$NEW_FEED  $D/$FEED" | sha256sum -c --status || abort installed_feed_hash
  echo "$HOTFIX_CONTRACTS  $D/$CONTRACTS" | sha256sum -c --status || abort contracts_hotfix_changed_postinstall
  echo "$HOTFIX_CANDLES  $D/$CANDLES" | sha256sum -c --status || abort candles_hotfix_changed_postinstall
done
systemctl restart "$EXIT" || abort restart_exit_failed
systemctl restart "$RUNNER" || abort restart_runner_failed
systemctl is-active --quiet "$EXIT" || abort exit_not_active_after
systemctl is-active --quiet "$RUNNER" || abort runner_not_active_after
[[ -f "$RUN/pause.flag" ]] || abort pause_removed_unexpectedly
# Refuse a claimed success unless heartbeats report a paused runner and working exit worker.
STATE_OK=0
for N in 1 2 3 4 5 6 7 8 9 10; do
  sleep 2
  if ( cd "$LIVE"; "$PYTHON" - <<'PY'
from pathlib import Path
import json,time
root=Path('/opt/superbot-v3-paper-runs/brain-v3-paper20261111')
runner=json.loads((root/'heartbeat.json').read_text())
exit=json.loads((root/'exit_heartbeat.json').read_text())
now=time.time()*1000
assert runner.get('state')=='paused', runner.get('state')
assert exit.get('state')=='healthy', exit.get('state')
assert exit.get('last_error') is None
assert 0 <= now-exit['ts_ms'] <= 15000
assert 0 <= now-runner['ts_ms'] <= 180000
assert (root/'pause.flag').exists()
PY
  ); then STATE_OK=1; break; fi
done
[[ "$STATE_OK" -eq 1 ]] || abort heartbeat_not_ready
COMPLETE=1
echo "BRAIN_P0_INSTALL RESULT=PASS applied_files=2 locations=2 pause=preserved hotfixes=preserved backup=$BACKUP"
