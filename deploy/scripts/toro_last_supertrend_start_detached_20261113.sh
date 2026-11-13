#!/usr/bin/env bash
# Research-only last Toro LONG Supertrend test, detached from SSH/Termius.
# Public OHLCV only; no orders, no API keys, no bot unit restarts.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" == "0" ]] || { echo "TORO_ST_BOOT BLOCK=root_required"; exit 2; }
OUT=/opt/superbot-toro-research/supertrend-last-20261113
SRC="$OUT/.src"
LOG="$OUT/replay_run.log"
UNIT=toro-supertrend-last-20261113
REPO=https://raw.githubusercontent.com/alexiptv82/SuperBot-Trading
PIN_TEST=8dfacbdb8da76e53bc0148ed928b2ef330ad2c10
PIN_FETCH=ab7e0b7d991b8f4bd714fccfec23b09a936e6717

if [[ -e "$OUT/report.json" ]]; then
  echo "TORO_ST_BOOT RESULT=REPORT_ALREADY_PRESENT"
  echo "TORO_ST_BOOT REPORT=$OUT/report.json"
  exit 0
fi
if systemctl is-active --quiet "$UNIT.service"; then
  echo "TORO_ST_BOOT RESULT=ALREADY_RUNNING unit=$UNIT.service"
  exit 0
fi
mkdir -p "$SRC/deploy/scripts" "$SRC/backend/v3/lab_tools"
touch "$SRC/backend/__init__.py" "$SRC/backend/v3/__init__.py" "$SRC/backend/v3/lab_tools/__init__.py"
fetch_pinned() {
  local ref="$1" path="$2" expected="$3"
  local tmp="$SRC/$path.tmp"
  curl -fsSL --retry 2 --max-time 60 "$REPO/$ref/$path" -o "$tmp"
  if [[ "$(git hash-object "$tmp")" != "$expected" ]]; then
    echo "TORO_ST_BOOT RESULT=BLOCK source_sha_mismatch=$path"
    rm -f "$tmp"
    exit 2
  fi
  mv -f "$tmp" "$SRC/$path"
}
fetch_pinned "$PIN_TEST" deploy/scripts/toro_last_supertrend_replay_20261113.py 652421126fa4dea1f03c962f6e1a23a4c16162ec
fetch_pinned "$PIN_FETCH" backend/v3/lab_tools/fetch_candles.py 150aec1d3427af926bd02a074bac4212615c4cdb

PY=/opt/superbot-v3-rc70-stage/.venv/bin/python3
[[ -x "$PY" ]] || PY=/usr/bin/python3
[[ -x "$PY" ]] || { echo "TORO_ST_BOOT RESULT=BLOCK python_missing"; exit 2; }
"$PY" -m py_compile "$SRC/deploy/scripts/toro_last_supertrend_replay_20261113.py" "$SRC/backend/v3/lab_tools/fetch_candles.py"
PYTHONPATH="$SRC" "$PY" "$SRC/deploy/scripts/toro_last_supertrend_replay_20261113.py" --self-test
echo "TORO_ST_BOOT SOURCE_SHA=PASS SYNTHETIC=PASS"

command -v systemd-run >/dev/null || { echo "TORO_ST_BOOT BLOCK=systemd_run_missing"; exit 2; }
systemd-run --unit="$UNIT" --collect \
  --property=Type=exec \
  --property=Nice=15 \
  --property=CPUQuota=65% \
  --property=MemoryMax=850M \
  --property="StandardOutput=append:$LOG" \
  --property="StandardError=append:$LOG" \
  --property="WorkingDirectory=$SRC" \
  --setenv="PYTHONPATH=$SRC" \
  --setenv=PYTHONDONTWRITEBYTECODE=1 \
  "$PY" -u "$SRC/deploy/scripts/toro_last_supertrend_replay_20261113.py"
echo "TORO_ST_BOOT RESULT=LAUNCHED_DETACHED paper_orders=0 production_units_unchanged=1"
echo "TORO_ST_BOOT LOG=$LOG"
echo "TORO_ST_BOOT REPORT=$OUT/report.json"
