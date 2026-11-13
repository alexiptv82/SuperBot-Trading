#!/usr/bin/env bash
# Brain V3 PAPER — explicitly authorised 2026-11-13: remove ONLY Brain pause flag.
# Must not touch Falco/Toro, risk parameters, models, code, services, journal, budget or LIVE.
# Designed to be run directly by the operator via Termius on the Singapore VPS.
set -Eeuo pipefail
umask 077
STAGE=/opt/superbot-v3-rc84-stage
RUN=/opt/superbot-v3-paper-runs/brain-v3-paper20261111
RUN_ID=brain-v3-paper20261111
BASE=0e29a73a36f668643da4088178bacb8616a45ac0
RUN_UNIT=superbot-v3-paper-brain-runner.service
EXIT_UNIT=superbot-v3-paper-brain-exit.service
PY=/opt/superbot-v3-rc70-stage/.venv/bin/python3
STARTED=0
OK=0
say(){ printf 'BRAIN_START %s\n' "$*"; }
fail(){ say "RESULT=BLOCK reason=$1"; exit 2; }
rollback(){
    local ret="$?"
    trap - EXIT INT TERM
    if [[ "$STARTED" == 1 && "$OK" == 0 ]]; then
        if [[ ! -f "$RUN/pause.flag" ]]; then
            ( umask 077; : > "$RUN/pause.flag" ) || true
        fi
        say "ROLLBACK_PAUSE_RESTORED=$([[ -f "$RUN/pause.flag" ]] && echo 1 || echo 0)"
    fi
    exit "$ret"
}
trap rollback EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

[[ "$(id -u)" == 0 ]] || fail root_required
[[ -x "$PY" && -d "$RUN" && -d "$STAGE" && ! -L "$RUN" && ! -L "$STAGE" ]] || fail paths_invalid
[[ "$(git -C "$STAGE" rev-parse HEAD)" == "$BASE" ]] || fail wrong_installed_base
[[ "$(git -C "$STAGE" status --porcelain | grep -c '^ M ' || true)" == 2 ]] || fail unexpected_worktree_count
changed="$(git -C "$STAGE" diff --name-only)"
[[ "$changed" == $'backend/v3/lab_tools/fetch_candles.py\nbackend/v3/runner/contracts.py' ]] || fail unexpected_worktree_files
[[ "$(git -C "$STAGE" status --porcelain | wc -l)" == 2 ]] || fail unexpected_untracked_files
[[ "$(git hash-object "$STAGE/backend/v3/lab_tools/fetch_candles.py")" == 150aec1d3427af926bd02a074bac4212615c4cdb ]] || fail candles_fix_not_installed
[[ "$(git hash-object "$STAGE/backend/v3/runner/contracts.py")" == 8ffc7f6ec3fe832b30fc70fbc1f41ef319b6f452 ]] || fail contracts_fix_not_installed
[[ -f "$RUN/pause.flag" && ! -L "$RUN/pause.flag" ]] || fail brain_not_paused
[[ -f "$RUN/PREPARED_PAUSED_ONLY.json" && ! -L "$RUN/PREPARED_PAUSED_ONLY.json" ]] || fail preparation_missing
systemctl is-active --quiet "$EXIT_UNIT" || fail exit_unit_inactive
systemctl is-active --quiet "$RUN_UNIT" || fail runner_unit_inactive

for unit in "$RUN_UNIT" "$EXIT_UNIT"; do
    cmd="$(systemctl show -p ExecStart --value "$unit")"
    [[ "$cmd" == *"--data-dir $RUN "* && "$cmd" == *"--run-id $RUN_ID "* &&
       "$cmd" == *"--config $RUN/runner_config.json"* ]] || fail "unit_scope_invalid_$unit"
    pid="$(systemctl show -p MainPID --value "$unit")"
    [[ "$pid" =~ ^[0-9]+$ && "$pid" -gt 1 && -r "/proc/$pid/environ" ]] || fail "unit_pid_missing_$unit"
    tr '\0' '\n' < "/proc/$pid/environ" | grep -qx 'DESK_MODE=paper' || fail "unit_not_paper_$unit"
done
[[ "$(systemctl show -p ExecStart --value "$RUN_UNIT")" == *"--exit-mode sidecar"* ]] || fail runner_not_sidecar
[[ "$(systemctl show -p ExecStart --value "$EXIT_UNIT")" == *"--legacy-exits-disabled"* ]] || fail exit_not_single_owner

# Complete read-only check with exact installed code. No API order and no journal modification.
PYTHONPATH="$STAGE" PYTHONDONTWRITEBYTECODE=1 "$PY" - "$RUN" "$RUN_ID" "$STAGE" <<'PYCODE' || fail brain_operational_preflight
import json, sqlite3, sys, time
from pathlib import Path
from decimal import Decimal
from backend.v3.runner.config import load_runner_config
from backend.v3.runner.prepared_config_guard import verify_prepared_run_config
from backend.v3.runner.wiring import MandateFile
from backend.v3.runner.exit_service import exit_service_healthy
from backend.v3.events import EventJournal
from backend.v3.dashboard import build_summary

run, run_id, stage = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
c = load_runner_config((run / "runner_config.json").read_bytes())
reference = load_runner_config((stage/"backend/v3/runner/runner_config_brain2000_paper.json").read_bytes())
assert c == reference, "config_template_mismatch"
assert c.initial_equity == Decimal("2000") and c.risk_policy.minimum_equity == Decimal("450"), "equity_mismatch"
assert (c.risk_policy.min_leverage, c.risk_policy.max_leverage)==(20,50), "leverage_mismatch"
assert (c.daily_loss_warn, c.daily_loss_halt)==(Decimal("0.35"),Decimal("0.50")), "daily_loss_mismatch"
assert c.daily_cap_usd == Decimal("0.75") and c.cycle_minutes==60, "budget_or_interval_mismatch"
assert c.model=="deepseek-flash" and len(c.symbols)==8, "model_or_symbols_mismatch"
verify_prepared_run_config(data_dir=run, run_id=run_id, config=c)
mandate = MandateFile(run/"mandate.json", c.risk_policy, run_id)
assert mandate.problem() is None, "mandate_not_authorised"
assert (run/"pause.flag").is_file(), "pause_missing"
now = int(time.time()*1000)
assert exit_service_healthy(data_dir=run, run_id=run_id, now_ms=now), "exit_sidecar_unhealthy"
jpath = run/"journal.db"
with sqlite3.connect(jpath.as_uri()+"?mode=ro",uri=True,timeout=10) as db:
    db.execute("PRAGMA query_only=ON")
    assert db.execute("PRAGMA quick_check").fetchone()[0]=="ok", "journal_corrupt"
j=EventJournal(jpath)
j.verify_chain()
summ=build_summary(j, "brain", run_id)
assert len(summ.open_positions)==0, "brain_positions_already_open"
with sqlite3.connect((run/"budget.db").as_uri()+"?mode=ro",uri=True,timeout=10) as db:
    db.execute("PRAGMA query_only=ON")
    assert db.execute("PRAGMA quick_check").fetchone()[0]=="ok", "budget_corrupt"
hb=json.loads((run/"heartbeat.json").read_text())
assert hb.get("run_id")==run_id and hb.get("state")=="paused" and hb.get("last_error") is None, "runner_not_paused"
assert 0 <= now-int(hb.get("ts_ms",0)) < 30000, "runner_heartbeat_stale"
print("BRAIN_START PREFLIGHT=PASS policy=approved model=deepseek-flash exit_healthy=1 "
      "journal_chain=ok initial_equity=2000 risk_unchanged=1 open_positions=0",flush=True)
PYCODE

# No restart and no new settings. This is the ONLY operational mutation on success.
[[ -f "$RUN/pause.flag" && ! -L "$RUN/pause.flag" ]] || fail pause_changed_before_start
STARTED=1
rm -- "$RUN/pause.flag" || fail cannot_remove_brain_pause
say "BRAIN_PAUSE_REMOVED=1 ONLY_BRAIN=1"
# A first Brain cycle may synchronously spend minutes analysing 8 markets.
# Do NOT misclassify a temporarily old heartbeat as failure while an AI call is in flight.
for i in 1 2 3; do
    sleep 3
    [[ ! -e "$RUN/pause.flag" ]] || fail pause_reappeared
    systemctl is-active --quiet "$EXIT_UNIT" || fail exit_unit_failed_after_start
    systemctl is-active --quiet "$RUN_UNIT" || fail runner_unit_failed_after_start
    PYTHONPATH="$STAGE" PYTHONDONTWRITEBYTECODE=1 "$PY" - "$RUN" "$RUN_ID" <<'PYCODE' || fail exit_unhealthy_after_start
import sys,time
from pathlib import Path
from backend.v3.runner.exit_service import exit_service_healthy
assert exit_service_healthy(data_dir=Path(sys.argv[1]),run_id=sys.argv[2],now_ms=int(time.time()*1000)), "exit unhealthy"
PYCODE
done
OK=1
say "RESULT=PASS brain_paper_unpaused=1 runner_active=1 exit_healthy=1"
say "NEXT=first_full_cycle_pending_or_in_progress_no_order_forced"
say "ROLLBACK_COMMAND=sudo touch /opt/superbot-v3-paper-runs/brain-v3-paper20261111/pause.flag"
