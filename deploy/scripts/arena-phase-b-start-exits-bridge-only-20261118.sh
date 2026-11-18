#!/usr/bin/env bash
# AI Arena Fase B: PAPER exits and root-only bridge ONLY, authorization 18/11/2026.
set -Eeuo pipefail
IFS=$'\n\t'
S=/opt/superbot-arena-stage
P="$S/.venv/bin/python3"
D=20261118
export PYTHONPATH="$S:$S/backend" PYTHONDONTWRITEBYTECODE=1 DESK_MODE=paper TRADING_MODE=paper
echo 'ARENA_B=PRECHECK'
[ "$(git -C "$S" rev-parse HEAD)" = 731b836c5e74f3709187370ef4e59ed4d71ef583 ]
[ -x "$P" ]
grep -qx 'ARENA_DAY=2026-11-18' /etc/superbot-arena/trial.env
grep -qx 'ARENA_DAY_COMPACT=20261118' /etc/superbot-arena/trial.env
grep -qx 'V3_ARENA_TRIAL_DAY=2026-11-18' /etc/superbot-arena/trial.env
for u in superbot-arena-runner@.service superbot-arena-exit@.service superbot-arena-close-bridge.service; do
  cmp "/etc/systemd/system/$u" "$S/deploy/arena-paper-services/$u"
done
for u in superbot-v3-paper-brain-runner.service superbot-v3-paper-brain-exit.service; do
  [ "$(systemctl is-active "$u")" = active ]
done
for ai in deepseek qwen minimax; do
  [ "$(systemctl is-active "superbot-arena-runner@$ai.service")" = inactive ]
  [ "$(systemctl is-active "superbot-arena-exit@$ai.service")" = inactive ]
  DIR="/opt/superbot-ai-arena-paper/$ai/brain-$ai-paper$D"
  "$P" -s -m backend.v3.runner.exit_worker \
    --data-dir "$DIR" --run-id "brain-$ai-paper$D" \
    --config "$DIR/runner_config.json" --validate-only
  echo "PREFLIGHT_$ai=OK"
done
[ "$(systemctl is-active superbot-arena-close-bridge.service)" = inactive ]
"$P" -s - <<'PY'
from datetime import date
from pathlib import Path
from time import time
from backend.v3.arena.trial_setup import inspect
r=inspect(Path('/opt/superbot-ai-arena-paper'),date(2026,11,18),int(time()*1000))
assert r['stage']=='PREPARED_PAUSED_NO_T0' and not r['blockers']
for name in ('deepseek','qwen','minimax'):
    p=r['providers'][name]
    assert p['paused'] and not p['mandate_approved'] and p['t0_file'] is None and p['t0_in_manifest'] is None
    assert p['journal_chain_ok'] and p['open_positions']==0
print('ARENA_B_THREE_RUNS=PAUSED_NO_T0_ZERO_OPEN')
PY
if [ -e /run/superbot-arena-close ] || [ -L /run/superbot-arena-close ]; then
  [ "$(stat -c '%u:%g:%a' /run/superbot-arena-close)" = 0:0:700 ]
else
  install -d -o root -g root -m 0700 /run/superbot-arena-close
fi
[ ! -e /run/superbot-arena-close/arena.sock ]
[ ! -L /run/superbot-arena-close/arena.sock ]
if [ -f /etc/superbot-arena/bridge.env ]; then
  if grep -q '^V3_ARENA_CLOSE_GROUP_GID=' /etc/superbot-arena/bridge.env; then
    echo 'ARENA_B_REFUSED=BRIDGE_GROUP_REQUIRES_REVIEW'
    exit 2
  fi
fi
echo 'ARENA_B=START_EXITS'
for ai in deepseek qwen minimax; do
  systemctl start "superbot-arena-exit@$ai.service"
  echo "EXIT_$ai=$(systemctl is-active "superbot-arena-exit@$ai.service")"
done
systemctl start superbot-arena-close-bridge.service
[ -S /run/superbot-arena-close/arena.sock ]
[ "$(stat -c '%u:%g:%a' /run/superbot-arena-close/arena.sock)" = 0:0:600 ]
echo "BRIDGE=$(systemctl is-active superbot-arena-close-bridge.service)"
"$P" -s - <<'PY'
from datetime import date
from pathlib import Path
from time import time
from backend.v3.arena.trial_setup import inspect
r=inspect(Path('/opt/superbot-ai-arena-paper'),date(2026,11,18),int(time()*1000))
assert r['stage']=='PREPARED_PAUSED_NO_T0' and not r['blockers']
for name in ('deepseek','qwen','minimax'):
    healthy=r['providers'][name]['exit_service_healthy']
    print('ARENA_B_EXIT_HEALTH_'+name.upper()+'='+str(healthy),flush=True)
    assert healthy, 'exit_heartbeat_not_healthy_'+name
PY
for ai in deepseek qwen minimax; do
  [ "$(systemctl is-active "superbot-arena-runner@$ai.service")" = inactive ]
done
for u in superbot-v3-paper-brain-runner.service superbot-v3-paper-brain-exit.service; do
  [ "$(systemctl is-active "$u")" = active ]
done
echo 'ARENA_B_BRAIN=ACTIVE; RUNNERS=INACTIVE; T0=NOT_ASSIGNED'
echo 'ARENA_B_CLOSE_SOCKET=ROOT_ONLY_NOT_YET_CONNECTED_TO_SAMSUNG'
echo 'ARENA_B_AI_INFERENCE=NOT_STARTED'
echo 'ARENA_B_RESULT=SUCCESS_EXITS_AND_BRIDGE_ONLY'
