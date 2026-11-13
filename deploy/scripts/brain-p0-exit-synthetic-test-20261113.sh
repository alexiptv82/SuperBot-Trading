#!/usr/bin/env bash
# Synthetic-only Brain V3 P0 exit coverage test. No operational runtime changes.
set -Eeuo pipefail
umask 077
STAGE=/opt/superbot-v3-rc70-stage
RUN=/opt/superbot-v3-paper-runs/brain-v3-paper20261111
BASE=0e29a73a36f668643da4088178bacb8616a45ac0
SOURCE=a14a898e91286b054513c9ab545d02d233290a96
REPO=https://raw.githubusercontent.com/alexiptv82/SuperBot-Trading
test -f "$RUN/pause.flag" || { echo 'BRAIN_P0_TEST FAIL reason=brain_not_paused'; exit 2; }
systemctl is-active --quiet superbot-v3-paper-brain-exit.service || { echo 'BRAIN_P0_TEST FAIL reason=exit_sidecar_not_active'; exit 2; }
test -x "$STAGE/.venv/bin/python3" || { echo 'BRAIN_P0_TEST FAIL reason=missing_python_venv'; exit 2; }
test "$(git -C "$STAGE" rev-parse HEAD)" = "$BASE" || { echo 'BRAIN_P0_TEST FAIL reason=stage_base_changed'; exit 2; }
# Avoid accidentally testing different hotfixes from the currently pinned VPS.
test "$(git -C "$STAGE" hash-object backend/v3/runner/contracts.py)" = 8ffc7f6ec3fe832b30fc70fbc1f41ef319b6f452 || { echo 'BRAIN_P0_TEST FAIL reason=contracts_hotfix_mismatch'; exit 2; }
test "$(git -C "$STAGE" hash-object backend/v3/lab_tools/fetch_candles.py)" = 150aec1d3427af926bd02a074bac4212615c4cdb || { echo 'BRAIN_P0_TEST FAIL reason=candles_hotfix_mismatch'; exit 2; }
echo "BRAIN_P0_TEST PRECHECK=PASS paused=1 exit_sidecar_active=1 two_hotfixes_pinned=1"
WORK=$(mktemp -d /tmp/brain-p0-test.XXXXXXXX)
LOG=/tmp/brain-p0-test-20261113.log
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK"
git -C "$STAGE" archive "$BASE" | tar -xf - -C "$WORK"
# Overlay precisely the two hotfixes already installed locally.
cp "$STAGE/backend/v3/runner/contracts.py" "$WORK/backend/v3/runner/contracts.py"
cp "$STAGE/backend/v3/lab_tools/fetch_candles.py" "$WORK/backend/v3/lab_tools/fetch_candles.py"
# Download ONLY the four new/changed P0 lab artifacts; pin the Git blob of each.
get_one() {
  local path="$1" expected="$2" actual
  curl --fail --silent --show-error --location --retry 2 --max-time 45 \
    --output "$WORK/$path" "$REPO/$SOURCE/$path"
  actual=$(git -C "$STAGE" hash-object "$WORK/$path")
  test "$actual" = "$expected" || { echo "BRAIN_P0_TEST FAIL reason=bad_source_hash path=$path"; exit 3; }
}
get_one backend/v3/runner/monitor.py 8f3e75673e8bc46963f52c45c7d5415066cb0584
get_one backend/v3/runner/feed.py 4982360bcc2694b93c62f13733e31211dcf8d1d6
get_one backend/tests/test_v3_brain_exit_feed_observability_20261113.py 98a64f4fd57920531a49d3a1513329cbfdd1d23a
get_one backend/tests/test_v3_runner_feed_monitor.py 6fa6bedcc0edb63204e78909176bc7e260d9745
echo "BRAIN_P0_TEST SOURCE=PASS commit=$SOURCE files=4 temp_worktree=1"
"$STAGE/.venv/bin/python3" -m compileall -q \
  "$WORK/backend/v3/runner/monitor.py" "$WORK/backend/v3/runner/feed.py" \
  "$WORK/backend/tests/test_v3_brain_exit_feed_observability_20261113.py" \
  "$WORK/backend/tests/test_v3_runner_feed_monitor.py"
# Dependencies are read from the existing venv; code + test data only from scratch.
set +e
(cd "$WORK" && PYTHONPATH="$WORK" "$STAGE/.venv/bin/python3" -m pytest -q \
  backend/tests/test_v3_brain_exit_feed_observability_20261113.py \
  backend/tests/test_v3_runner_feed_monitor.py \
  backend/tests/test_v3_exit_service.py \
  backend/tests/test_v3_exit_worker.py) >"$LOG" 2>&1
rc=$?
set -e
tail -n 32 "$LOG"
if [[ $rc -ne 0 ]]; then
  echo "BRAIN_P0_TEST RESULT=FAIL exit_code=$rc log=$LOG stage_untouched=1 paused=1"
  exit "$rc"
fi
test -f "$RUN/pause.flag" || { echo "BRAIN_P0_TEST FAIL reason=pause_disappeared"; exit 3; }
systemctl is-active --quiet superbot-v3-paper-brain-exit.service || { echo "BRAIN_P0_TEST FAIL reason=exit_sidecar_stopped"; exit 3; }
echo "BRAIN_P0_TEST RESULT=PASS isolated_only=1 no_runtime_changes=1 pause=1 exit_active=1 log=$LOG"
