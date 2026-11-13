#!/usr/bin/env bash
# Synthetic regression test for Brain P0 exit-feed patch.
# Strictly laboratory-only: clones to a new temporary directory, does not edit VPS stage,
# does not restart services, does not touch PAPER journals, never sends Bitget orders.
set -Eeuo pipefail
export GIT_TERMINAL_PROMPT=0
export PYTHONDONTWRITEBYTECODE=1
BRAIN_DIR=/opt/superbot-v3-paper-runs/brain-v3-paper20261111
STAGE=/opt/superbot-v3-rc70-stage
BRANCH=work/brain-exit-observability-20261113
URL=https://github.com/alexiptv82/SuperBot-Trading.git
if [[ ! -f "$BRAIN_DIR/pause.flag" ]]; then
    echo "BRAIN_P0_TEST RESULT=ABORT reason=brain_pause_missing"; exit 2
fi
if [[ "$(systemctl is-active superbot-v3-paper-brain-exit.service)" != active ]]; then
    echo "BRAIN_P0_TEST RESULT=ABORT reason=brain_exit_not_active"; exit 2
fi
PYTHON="$STAGE/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
    echo "BRAIN_P0_TEST RESULT=ABORT reason=python_venv_missing"; exit 2
fi
TMP="$(mktemp -d /tmp/brain-p0-feed-test.XXXXXXXX)"
cleanup() { case "$TMP" in /tmp/brain-p0-feed-test.*) rm -rf -- "$TMP";; esac; }
trap cleanup EXIT
git clone -q --depth 1 --single-branch --branch "$BRANCH" "$URL" "$TMP/repo"
cd "$TMP/repo"
# Pin exactly the four audited source/test blobs, ignoring future branch changes.
while read -r file expected; do
    actual="$(git hash-object "$file")"
    if [[ "$actual" != "$expected" ]]; then
        echo "BRAIN_P0_TEST RESULT=ABORT reason=source_blob_mismatch file=$file got=$actual"; exit 3
    fi
done <<'BLOBS'
backend/v3/runner/monitor.py 8f3e75673e8bc46963f52c45c7d5415066cb0584
backend/v3/runner/feed.py 4982360bcc2694b93c62f13733e31211dcf8d1d6
backend/tests/test_v3_brain_exit_feed_observability_20261113.py 98a64f4fd57920531a49d3a1513329cbfdd1d23a
backend/tests/test_v3_runner_feed_monitor.py 6fa6bedcc0edb63204e78909176bc7e260d9745c
BLOBS
"$PYTHON" -m py_compile backend/v3/runner/monitor.py backend/v3/runner/feed.py backend/tests/test_v3_brain_exit_feed_observability_20261113.py
echo "BRAIN_P0_TEST SOURCE_BLOBS=PASS SYNTAX=PASS run_mode=ISOLATED"
# No pytest cache, no live credentials or stage configuration imports, no network.
nice -n 10 "$PYTHON" -m pytest -q -p no:cacheprovider \
    backend/tests/test_v3_brain_exit_feed_observability_20261113.py \
    backend/tests/test_v3_runner_feed_monitor.py \
    backend/tests/test_v3_exit_service.py \
    backend/tests/test_v3_exit_worker.py \
    backend/tests/test_v3_post_ai_guard.py \
    backend/tests/test_v3_runner_manual_close.py
echo "BRAIN_P0_TEST RESULT=PASS synthetic_and_regression_only=1 stage_unchanged=1 pause_preserved=1 exit_service_untouched=1"
