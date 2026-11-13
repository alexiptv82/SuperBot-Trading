#!/usr/bin/env bash
# SuperBot RC84: approved hotfix of Brain Bitget feed ONLY, with backup/rollback.
# No classici restart. No mandate change. No unpause. No order. No merge.
# Authorisation: user explicitly approved two-module Brain-only install on 2026-11-13.
set -Eeuo pipefail
umask 077

STAGE=/opt/superbot-v3-rc84-stage
RUN_ID=brain-v3-paper20261111
RUN=/opt/superbot-v3-paper-runs/$RUN_ID
RUN_UNIT=superbot-v3-paper-brain-runner.service
EXIT_UNIT=superbot-v3-paper-brain-exit.service
BASE=0e29a73a36f668643da4088178bacb8616a45ac0
PIN=5113e10a57f7db2461f1259151af593569c34850
URL=https://raw.githubusercontent.com/alexiptv82/SuperBot-Trading/$PIN
FILE1=backend/v3/runner/contracts.py
FILE2=backend/v3/lab_tools/fetch_candles.py
OLD1=9abc0b728107cfa76f6c2d27d9c75acb700ebeaf
OLD2=4c0f91c56124da1615acbb43722f03f5afd31082
NEW1=8ffc7f6ec3fe832b30fc70fbc1f41ef319b6f452
NEW2=150aec1d3427af926bd02a074bac4212615c4cdb
PY=/opt/superbot-v3-rc70-stage/.venv/bin/python3
TEMP=
BACKUP=
MUTATED=0
DONE=0

log(){ echo "BRAIN_DEPLOY $*"; }
fail(){ log "FAIL reason=$1"; exit 1; }
assert_blob(){
    local file="$1" expected="$2" actual
    actual="$(git hash-object "$file")" || return 1
    [[ "$actual" == "$expected" ]]
}

check_paused(){
    [[ -f "$RUN/pause.flag" && ! -L "$RUN/pause.flag" ]]
}

check_data(){
    # No write to operational DB: count positions through its official read-only journal view.
    PYTHONPATH="$STAGE" PYTHONDONTWRITEBYTECODE=1 "$PY" - "$RUN" "$RUN_ID" <<'PYCODE'
import sys, sqlite3
from pathlib import Path
from backend.v3.dashboard import build_summary
from backend.v3.events import EventJournal
root, run = Path(sys.argv[1]), sys.argv[2]
journal = root / "journal.db"
with sqlite3.connect(journal.as_uri()+"?mode=ro", uri=True, timeout=10) as db:
    db.execute("PRAGMA query_only=ON")
    ok = db.execute("PRAGMA quick_check").fetchone()[0]
    if ok != "ok":
        raise SystemExit("journal_integrity_failed")
j = EventJournal(journal)
j.verify_chain()
s = build_summary(j, "brain", run)
print(f"BRAIN_DEPLOY journal_integrity=ok open_positions={len(s.open_positions)}", flush=True)
if s.open_positions:
    raise SystemExit("open_positions_exist")
PYCODE
}

backup_db(){
    local src="$1" dst="$2"
    PYTHONDONTWRITEBYTECODE=1 "$PY" - "$src" "$dst" <<'PYCODE'
import sqlite3, sys
from pathlib import Path
src, dst = (Path(p) for p in sys.argv[1:])
with sqlite3.connect(src.as_uri() + "?mode=ro", uri=True, timeout=10) as reader:
    reader.execute("PRAGMA query_only=ON")
    with sqlite3.connect(dst) as writer:
        reader.backup(writer, pages=256, sleep=0.2)
        if writer.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise SystemExit("backup_integrity_failed")
PYCODE
}

healthy_exit(){
    PYTHONPATH="$STAGE" PYTHONDONTWRITEBYTECODE=1 "$PY" - "$RUN" "$RUN_ID" <<'PYCODE'
from pathlib import Path
import sys,time
from backend.v3.runner.exit_service import exit_service_healthy
ok = exit_service_healthy(data_dir=Path(sys.argv[1]), run_id=sys.argv[2], now_ms=int(time.time()*1000))
raise SystemExit(0 if ok else 1)
PYCODE
}

pause_beat(){
    PYTHONDONTWRITEBYTECODE=1 "$PY" - "$RUN" "$RUN_ID" <<'PYCODE'
from pathlib import Path
import json,sys,time
d, run = Path(sys.argv[1]), sys.argv[2]
try:
    b = json.loads((d/"heartbeat.json").read_text())
    good = (b.get("run_id")==run and b.get("state")=="paused"
            and b.get("last_error") is None
            and 0 <= int(time.time()*1000)-b["ts_ms"] <= 30000)
except (ValueError,KeyError,TypeError,OSError):
    good = False
raise SystemExit(0 if good else 1)
PYCODE
}

wait_exit(){
    local i
    for i in {1..90}; do
        if systemctl is-active --quiet "$EXIT_UNIT" && healthy_exit >/dev/null 2>&1; then
            log "exit_healthy=1"
            return 0
        fi
        sleep 1
    done
    return 1
}

wait_runner(){
    local i
    for i in {1..45}; do
        if systemctl is-active --quiet "$RUN_UNIT" && pause_beat >/dev/null 2>&1; then
            log "runner_paused_heartbeat=1"
            return 0
        fi
        sleep 1
    done
    return 1
}

on_exit(){
    local code="$?"
    trap - EXIT ERR INT TERM
    if [[ "$code" -ne 0 && "$MUTATED" == 1 && "$DONE" == 0 ]]; then
        log "ROLLBACK_BEGIN"
        # Ensure absolutely no new Brain opens, even if another operator removed pause.
        [[ -f "$RUN/pause.flag" ]] || : > "$RUN/pause.flag"
        systemctl stop "$RUN_UNIT" >/dev/null 2>&1 || true
        systemctl stop "$EXIT_UNIT" >/dev/null 2>&1 || true
        if [[ -n "$BACKUP" && -f "$BACKUP/contracts.py" && -f "$BACKUP/fetch_candles.py" ]]; then
            cp -a "$BACKUP/contracts.py" "$STAGE/$FILE1" || true
            cp -a "$BACKUP/fetch_candles.py" "$STAGE/$FILE2" || true
            if assert_blob "$STAGE/$FILE1" "$OLD1" && assert_blob "$STAGE/$FILE2" "$OLD2"; then
                log "ROLLBACK_SOURCE_RESTORED=1"
            else
                log "ROLLBACK_SOURCE_RESTORED=0 MANUAL_CHECK_REQUIRED=1"
            fi
        fi
        systemctl start "$EXIT_UNIT" >/dev/null 2>&1 || true
        wait_exit >/dev/null 2>&1 || true
        systemctl start "$RUN_UNIT" >/dev/null 2>&1 || true
        if systemctl is-active --quiet "$EXIT_UNIT" && systemctl is-active --quiet "$RUN_UNIT"; then
            log "ROLLBACK_BRAIN_SERVICES_ACTIVE=1"
        else
            log "ROLLBACK_BRAIN_SERVICES_ACTIVE=0 MANUAL_CHECK_REQUIRED=1"
        fi
        log "ROLLBACK_COMPLETED_CHECK_STATUS=1"
    fi
    [[ -z "$TEMP" ]] || rm -rf "$TEMP"
    exit "$code"
}
trap on_exit EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

[[ "$(id -u)" == 0 ]] || fail "root_required"
[[ -x "$PY" ]] || fail "python_venv_missing"
[[ -d "$STAGE" && ! -L "$STAGE" && -d "$RUN" && ! -L "$RUN" ]] || fail "stage_or_run_missing"
[[ "$(git -C "$STAGE" rev-parse HEAD)" == "$BASE" ]] || fail "stage_sha_mismatch"
[[ -z "$(git -C "$STAGE" status --porcelain)" ]] || fail "stage_has_uncommitted_changes"
assert_blob "$STAGE/$FILE1" "$OLD1" || fail "old_contracts_hash_mismatch"
assert_blob "$STAGE/$FILE2" "$OLD2" || fail "old_candles_hash_mismatch"
check_paused || fail "brain_not_paused"
systemctl is-active --quiet "$EXIT_UNIT" || fail "exit_service_not_active"
systemctl is-active --quiet "$RUN_UNIT" || fail "runner_service_not_active"

# Verify exact scoped units without reading or printing the secret EnvironmentFile.
for unit in "$RUN_UNIT" "$EXIT_UNIT"; do
    execs="$(systemctl show -p ExecStart --value "$unit")"
    [[ "$execs" == *"--data-dir $RUN "* &&
       "$execs" == *"--run-id $RUN_ID "* &&
       "$execs" == *"--config $RUN/runner_config.json"* ]] || fail "unexpected_unit_scope_$unit"
done
[[ "$(systemctl show -p ExecStart --value "$RUN_UNIT")" == *"--exit-mode sidecar"* ]] || fail "runner_not_sidecar"
[[ "$(systemctl show -p ExecStart --value "$EXIT_UNIT")" == *"--start-paper"* ]] || fail "exit_unit_invalid"

check_data || fail "journal_or_open_position_gate"
healthy_exit || fail "exit_not_healthy_before"
log "PREFLIGHT=PASS stage_sha=$BASE brain_paused=1 open_positions=0 exit_healthy=1"

TEMP="$(mktemp -d /tmp/brain-rc84-install-XXXXXXXX)" || fail "temporary_dir_failed"
mkdir -p "$TEMP/backend/v3/runner" "$TEMP/backend/v3/lab_tools"
curl -fsSL --retry 2 --max-time 25 "$URL/$FILE1" -o "$TEMP/$FILE1" || fail "download_contracts_failed"
curl -fsSL --retry 2 --max-time 25 "$URL/$FILE2" -o "$TEMP/$FILE2" || fail "download_candles_failed"
assert_blob "$TEMP/$FILE1" "$NEW1" || fail "download_contracts_bad_hash"
assert_blob "$TEMP/$FILE2" "$NEW2" || fail "download_candles_bad_hash"
PYTHONDONTWRITEBYTECODE=1 "$PY" - "$TEMP" <<'PYCODE'
import sys,ast
from pathlib import Path
root=Path(sys.argv[1])
for name in ("backend/v3/runner/contracts.py","backend/v3/lab_tools/fetch_candles.py"):
    ast.parse((root/name).read_text(encoding="utf-8"),filename=name)
print("BRAIN_DEPLOY downloaded_code_syntax=ok",flush=True)
PYCODE

# Durable, private backup: original source + consistent SQLite online snapshots.
BACKUP_ROOT=/opt/superbot-v3-brain-hotfix-backups
[[ ! -L "$BACKUP_ROOT" ]] || fail "backup_symlink"
mkdir -p -m 0700 "$BACKUP_ROOT"
chmod 0700 "$BACKUP_ROOT"
BACKUP="$(mktemp -d "$BACKUP_ROOT/brain-20261113-XXXXXXXX")" || fail "backup_directory_failed"
cp -a "$STAGE/$FILE1" "$BACKUP/contracts.py"
cp -a "$STAGE/$FILE2" "$BACKUP/fetch_candles.py"
cp -a "$RUN/runner_config.json" "$BACKUP/runner_config.json"
cp -a "$RUN/mandate.json" "$BACKUP/mandate.json"
cp -a "$RUN/pause.flag" "$BACKUP/pause.flag"
backup_db "$RUN/journal.db" "$BACKUP/journal.db"
backup_db "$RUN/budget.db" "$BACKUP/budget.db"
(
 cd "$BACKUP"
 sha256sum contracts.py fetch_candles.py runner_config.json mandate.json pause.flag journal.db budget.db > SHA256SUMS
)
assert_blob "$BACKUP/contracts.py" "$OLD1" || fail "backup_contracts_hash_mismatch"
assert_blob "$BACKUP/fetch_candles.py" "$OLD2" || fail "backup_candles_hash_mismatch"
log "BACKUP_VERIFIED=1 path=$BACKUP"

# Paused + zero positions: stop only Brain's two workers before changing shared source.
systemctl stop "$RUN_UNIT" || fail "stop_brain_runner_failed"
systemctl stop "$EXIT_UNIT" || fail "stop_brain_exit_failed"
MUTATED=1
! systemctl is-active --quiet "$RUN_UNIT" || fail "runner_did_not_stop"
! systemctl is-active --quiet "$EXIT_UNIT" || fail "exit_did_not_stop"
check_paused || fail "pause_disappeared_during_restart"
# Recheck no new trade appeared between preflight and the controlled stop.
check_data || fail "journal_changed_or_open_position_during_stop"

# The two files are deliberately the only stage source files changed.
install -m 0644 "$TEMP/$FILE1" "$STAGE/$FILE1" || fail "install_contracts_failed"
install -m 0644 "$TEMP/$FILE2" "$STAGE/$FILE2" || fail "install_candles_failed"
assert_blob "$STAGE/$FILE1" "$NEW1" || fail "installed_contracts_bad_hash"
assert_blob "$STAGE/$FILE2" "$NEW2" || fail "installed_candles_bad_hash"
# Expected: Git HEAD remains 0e29a73; exactly two tracked files appear modified.
CHANGED="$(git -C "$STAGE" diff --name-only)"
[[ "$CHANGED" == $'backend/v3/lab_tools/fetch_candles.py\nbackend/v3/runner/contracts.py' ]] ||
    fail "unexpected_git_diff"
log "INSTALL=PASS changed_files=2 stage_sha_remains=$BASE"

# Start exit FIRST. Runner must remain paused and cannot open until a healthy exit owner exists.
systemctl start "$EXIT_UNIT" || fail "start_brain_exit_failed"
wait_exit || fail "exit_not_healthy_after"
check_paused || fail "pause_disappeared_after_exit"
systemctl start "$RUN_UNIT" || fail "start_brain_runner_failed"
wait_runner || fail "runner_not_paused_after"
healthy_exit || fail "exit_unhealthy_final"
check_paused || fail "pause_disappeared_final"
check_data || fail "journal_or_open_positions_final"
assert_blob "$STAGE/$FILE1" "$NEW1" || fail "source_changed_after"
assert_blob "$STAGE/$FILE2" "$NEW2" || fail "source_changed_after"

DONE=1
log "RESULT=PASS brain_only_hotfix_installed=1 pause=1 open_positions=0 exit_healthy=1"
log "BACKUP_KEEP=$BACKUP"
log "NEXT_STEP=separate_approval_required_to_unpause"
