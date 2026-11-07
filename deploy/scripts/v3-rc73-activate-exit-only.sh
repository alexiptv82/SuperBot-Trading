#!/usr/bin/env bash
# RC73: explicit user-authorized PAPER-only exit worker activation.
# Does NOT issue any close, reset, resume, or trading command.
set -euo pipefail
umask 077
BASE=/opt/superbot-v3-rc70-stage
SCRIPT="$BASE/backend/desk/exit_only.py"
CANDIDATE="$SCRIPT.rc73-candidate"
PREVIOUS="$SCRIPT.rc73-previous"
SNAP=/opt/superbot-backups/rc69-paper-legacy-20261107T110255Z-142218
if [[ "${1:-}" != "--activate-paper-close-only" ]]; then
  echo RC73_REFUSED_NO_EXPLICIT_OPERATOR_ACTIVATION; exit 2
fi
test -f "$SCRIPT" && test -f "$CANDIDATE" && test ! -e "$PREVIOUS" || { echo RC73_CODE_STAGE_INVALID; exit 2; }
test -x "$BASE/.venv/bin/python3" && test -s "$SNAP/MANIFEST.json" || { echo RC73_STAGE_OR_BACKUP_MISSING; exit 2; }
test -r "$BASE/backend/desk/cli.py" || { echo RC73_LEGACY_CODE_MISSING; exit 2; }
for p in hawk bull; do
  u="superbot-v3-$([ "$p" = hawk ] && echo falco || echo toro)-exit.service"
  test "$(systemctl is-enabled "$u" 2>/dev/null || true)" = disabled || { echo RC73_EXIT_SERVICE_NOT_DISABLED; exit 2; }
  test "$(systemctl is-active "$u" 2>/dev/null || true)" != active || { echo RC73_EXIT_SERVICE_ALREADY_ACTIVE; exit 2; }
  test "$(docker inspect -f '{{.State.Running}}' "superbot-desk-$p")" = false || { echo RC73_LEGACY_BOT_RUNNING; exit 2; }
  test "$(docker inspect -f '{{.HostConfig.RestartPolicy.Name}}' "superbot-desk-$p")" = no || { echo RC73_LEGACY_BOT_AUTORESTART; exit 2; }
  d="/opt/superbot-desk-data/$p"
  test -f "$d/pause.flag" || { echo RC73_LEGACY_NOT_PAUSED; exit 2; }
  for flag in reset.flag reset.flag.work close_position.flag close_position.flag.work reset_portfolio.flag; do
    test ! -e "$d/$flag" || { echo RC73_UNRECONCILED_PENDING_FLAG; exit 2; }
  done
  for f in state_v2.json trade_history.jsonl learning_log.jsonl lessons.md; do
    cmp -s "$d/$f" "$SNAP/$p/$f" || { echo RC73_SNAPSHOT_NO_LONGER_MATCHES; exit 2; }
  done
done
python3 - <<'PY'
import json
from pathlib import Path
counts={'hawk':6,'bull':2}
for name,count in counts.items():
    root=Path('/opt/superbot-desk-data')/name
    data=json.loads((root/'state_v2.json').read_text())
    assert len(data['main']['positions'])==count, 'RC73_WRONG_POSITION_COUNT'
print('RC73_ORIGINAL_POSITIONS_6_2_VERIFIED=True')
PY
# Do not allow backend writes until both exit-only owners explicitly prove ready.
test "$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' superbot | grep -c '^V3_CUTOVER_READONLY=1$' || true)" = 1 || { echo RC73_WEB_NOT_READONLY; exit 2; }
test "$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' superbot | grep -c '^V3_ALLOW_CLASSIC_SINGLE_CLOSE=1$' || true)" = 0 || { echo RC73_WEB_ALREADY_UNLOCKED; exit 2; }
# Exact candidate compilation/import before replacing only the inactive service code.
"$BASE/.venv/bin/python3" -m py_compile "$CANDIDATE"
cp -p "$SCRIPT" "$PREVIOUS"
revert() {
  echo RC73_EXIT_ACTIVATION_ROLLBACK=True
  systemctl stop superbot-v3-falco-exit.service superbot-v3-toro-exit.service 2>/dev/null || true
  if [ -f "$PREVIOUS" ]; then cp -p "$PREVIOUS" "$SCRIPT"; fi
}
trap revert ERR
mv "$CANDIDATE" "$SCRIPT"
chmod 0600 "$SCRIPT"
# Import check; no network requests and no simulated close.
PYTHONPATH="$BASE/backend" DESK_MODE=paper DESK_PORTFOLIO=hawk DESK_DATA_DIR=/opt/superbot-desk-data/hawk \
 "$BASE/.venv/bin/python3" -c 'from desk.exit_only import ExitOnlyWorker; assert ExitOnlyWorker is not None'
systemctl start superbot-v3-falco-exit.service
systemctl start superbot-v3-toro-exit.service
sleep 7
python3 - <<'PY'
import json,subprocess,time
from pathlib import Path
for portfolio,name in (('hawk','falco'),('bull','toro')):
    unit='superbot-v3-'+name+'-exit.service'
    assert subprocess.run(['systemctl','is-active','--quiet',unit]).returncode==0, 'unit_not_running'
    assert subprocess.run(['systemctl','is-enabled',unit],capture_output=True,text=True).stdout.strip()=='disabled'
    d=Path('/opt/superbot-desk-data')/portfolio
    hb=json.loads((d/'exit_only_heartbeat.json').read_text())
    assert hb['mode']=='paper-exit-only' and hb['portfolio']==portfolio and hb['ready'] is True
    assert 0 <= time.time()-hb['ts'] <= 12, 'heartbeat_stale'
    state=json.loads((d/'state_v2.json').read_text())
    assert len(state['main']['positions'])=={'hawk':6,'bull':2}[portfolio]
    assert not any((d/n).exists() for n in ('reset.flag','reset.flag.work','close_position.flag','close_position.flag.work'))
    print('RC73_'+name.upper()+'_EXIT_ONLY_READY_NO_COMMANDS=True')
print('RC73_BOTH_EXIT_ONLY_SERVICES_ACTIVE_NO_TRADES_CLOSED=True')
PY
trap - ERR
echo RC73_NO_HISTORIC_BOT_RESTART=True
echo RC73_WEB_STILL_READONLY=True
echo RC73_CODE_PREVIOUS_AVAILABLE_FOR_ROLLBACK=True
