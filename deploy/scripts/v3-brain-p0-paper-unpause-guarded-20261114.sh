#!/usr/bin/env bash
# Brain PAPER V3: remove pause only after verifying the exact P0 installation.
# Scope: only /opt/superbot-v3-paper-runs/brain-v3-paper20261111/pause.flag.
# NO merge, deployment, service restart, portfolio reset, orders or mode changes.
set -Eeuo pipefail
export PYTHONDONTWRITEBYTECODE=1
[[ "${EUID}" -eq 0 ]] || { echo "BRAIN_RESUME RESULT=ABORT reason=run_as_root"; exit 2; }
RUN=/opt/superbot-v3-paper-runs/brain-v3-paper20261111
LIVE=/opt/superbot-v3-rc84-repair-ab7e0b7
STAGE=/opt/superbot-v3-rc84-stage
PY=/opt/superbot-v3-rc70-stage/.venv/bin/python3
RUNNER=superbot-v3-paper-brain-runner.service
EXIT=superbot-v3-paper-brain-exit.service
MON=backend/v3/runner/monitor.py
FEED=backend/v3/runner/feed.py
CONTRACTS=backend/v3/runner/contracts.py
CANDLES=backend/v3/lab_tools/fetch_candles.py
MON_SHA=623dcc31b3e6c5c6c31827ba3d98f2fa018ca6d38bb2072ad4d7aefbe71627a8
FEED_SHA=4002b8a444bce3c10f93fbaca5c20a9f863bc31d4d8f008a1ec92f9bff752def
CONTRACTS_SHA=9f6eb36fc32a104760860b565a8b2ec985afe20ec9ac01eec99b0d8809e41cf7
CANDLES_SHA=9daffbf375a31bc835d96851311ade1c6029f3049befdb75504553c4719a4b8b
abort(){ echo "BRAIN_RESUME RESULT=ABORT reason=$1 pause_unchanged=1"; exit 3; }
[[ -x "$PY" && -f "$RUN/pause.flag" && ! -L "$RUN/pause.flag" ]] || abort interpreter_or_pause_missing
for S in "$RUNNER" "$EXIT"; do
    systemctl is-active --quiet "$S" || abort service_inactive
    [[ "$(systemctl show -p WorkingDirectory --value "$S")" == "$LIVE" ]] || abort unexpected_workdir
    systemctl show -p ExecStart --value "$S" | grep -Fq 'DESK_MODE=paper' || abort nonpaper_service
    systemctl show -p ExecStart --value "$S" | grep -Fq "$RUN" || abort wrong_run
done
for D in "$LIVE" "$STAGE"; do
    [[ -d "$D" && ! -L "$D" ]] || abort stage_missing
    echo "$MON_SHA  $D/$MON" | sha256sum -c --status || abort monitor_hash_mismatch
    echo "$FEED_SHA  $D/$FEED" | sha256sum -c --status || abort feed_hash_mismatch
    echo "$CONTRACTS_SHA  $D/$CONTRACTS" | sha256sum -c --status || abort bitget_contracts_hash_mismatch
    echo "$CANDLES_SHA  $D/$CANDLES" | sha256sum -c --status || abort bitget_candles_hash_mismatch
done
# Mandatory PAPER run health, signed mandate, risk policy, fresh runner and sidecar.
(cd "$LIVE" && "$PY" - <<'PY'
import json, time
from pathlib import Path
from backend.v3.runner.config import load_runner_config
from backend.v3.runner.wiring import MandateFile
from backend.v3.runner.exit_service import exit_service_healthy
run=Path("/opt/superbot-v3-paper-runs/brain-v3-paper20261111")
id="brain-v3-paper20261111"
conf=load_runner_config((run/"runner_config.json").read_bytes())
mandate=MandateFile(run/"mandate.json", conf.risk_policy, id)
problem=mandate.problem()
if problem:
    raise RuntimeError("mandate_"+problem)
now=int(time.time()*1000)
for name, state, maxage in (("heartbeat.json","paused",15000),("exit_heartbeat.json","healthy",15000)):
    h=json.loads((run/name).read_text())
    age=now-h.get("ts_ms",0)
    if h.get("run_id")!=id or h.get("state")!=state or h.get("last_error") is not None or not 0<=age<=maxage:
        raise RuntimeError("unhealthy_"+name)
if not exit_service_healthy(data_dir=run, run_id=id, now_ms=now):
    raise RuntimeError("exit_service_not_healthy")
print("BRAIN_RESUME PREFLIGHT=PASS mandate=approved policy=unchanged runner=paused exit=healthy mode=PAPER code_p0=verified")
PY
) || abort run_health_or_mandate_failed
# Single mutation: enable Brain PAPER cycles; leave all other service/config/data files untouched.
rm -- "$RUN/pause.flag"
echo "BRAIN_RESUME PAUSE_REMOVED=1 paper_only=1 no_restart=1"
# Verify that the runner notices the new state. A long AI call can delay heartbeat.
OK=0
for i in $(seq 1 12); do
    sleep 5
    if ! systemctl is-active --quiet "$RUNNER" || ! systemctl is-active --quiet "$EXIT"; then
        break
    fi
    if (cd "$LIVE" && "$PY" - <<'PY'
import json,time
from pathlib import Path
root=Path('/opt/superbot-v3-paper-runs/brain-v3-paper20261111')
runner=json.loads((root/'heartbeat.json').read_text())
exit=json.loads((root/'exit_heartbeat.json').read_text())
now=time.time()*1000
assert not (root/'pause.flag').exists()
assert runner.get('state')=='running', runner.get('state')
assert runner.get('last_error') is None,runner.get('last_error')
assert runner.get('run_id')=='brain-v3-paper20261111'
assert exit.get('state')=='healthy',exit.get('state')
assert exit.get('last_error') is None
assert 0 <= now-exit.get('ts_ms',0) <= 15000
assert 0 <= now-runner.get('ts_ms',0) <= 15000
PY
    ) >/dev/null 2>&1; then OK=1; break; fi
done
if [[ "$OK" == 1 ]]; then
    echo "BRAIN_RESUME RESULT=PASS mode=PAPER runner=running exit=healthy pause=absent no_forced_trade=1"
else
    touch "$RUN/pause.flag"
    echo "BRAIN_RESUME RESULT=REPAUSED reason=post_start_check_failed followup_required=1"
    exit 4
fi
