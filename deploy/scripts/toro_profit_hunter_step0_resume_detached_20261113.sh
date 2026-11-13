#!/usr/bin/env bash
# Isolated Bitget Step0 resume. Do not touch running bot services, journal or LIVE.
# User approved PAPER strategy research; frozen 2026-11-13 15:34:37Z history.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" == "0" ]] || { echo "TORO_RESUME RESULT=BLOCK root_required"; exit 2; }
OUT=/opt/superbot-toro-research/step0-20261113T153437Z
ROOT="$OUT/.resume_source"
LOG="$OUT/resume_run.log"
UNIT=toro-step0-resume-20261113
BASE=https://raw.githubusercontent.com/alexiptv82/SuperBot-Trading
PIN_RESUME=f89487c2f66993c3a4619042e44882182ad72ea3
PIN_CORE=18ac3971c76269341c61b041394fbdb10f8bdb97
PIN_FETCH=ab7e0b7d991b8f4bd714fccfec23b09a936e6717
[[ -d "$OUT" && ! -L "$OUT" && ! -e "$OUT/report_step0.json" ]] || {
  echo "TORO_RESUME RESULT=BLOCK original_dir_missing_or_final_report_exists"; exit 2;
}
if systemctl is-active --quiet "$UNIT.service"; then
  echo "TORO_RESUME RESULT=ALREADY_RUNNING unit=$UNIT.service"; exit 0
fi
[[ -f "$OUT/BTCUSDT_60m.csv" && -f "$OUT/ETHUSDT_240m.csv" &&
   -f "$OUT/SOLUSDT_60m.csv" && -f "$OUT/BNBUSDT_240m.csv" ]] || {
  echo "TORO_RESUME RESULT=BLOCK original_cached_files_missing"; exit 2;
}
mkdir -p "$ROOT/backend/desk" "$ROOT/backend/v3/lab_tools" "$ROOT/deploy/scripts"
touch "$ROOT/backend/desk/__init__.py"
download(){
  local ref=$1 path=$2 sha=$3 tmp="$ROOT/$2.partial"
  curl -fLsS --retry 2 --max-time 60 "$BASE/$ref/$path" -o "$tmp"
  if [[ "$(git hash-object "$tmp")" != "$sha" ]]; then
    echo "TORO_RESUME RESULT=BLOCK source_sha_invalid path=$path"
    rm -f -- "$tmp"; exit 2
  fi
  mv -f -- "$tmp" "$ROOT/$path"
}
download "$PIN_CORE" backend/desk/toro_profit_hunter.py 9367edec67a0d40d9019629eda906752ea6c3a65
download "$PIN_CORE" deploy/scripts/toro_profit_hunter_step0.py 4adf5716672117a4a7e0a5e58614e8ca0ec85a36
download "$PIN_FETCH" backend/v3/lab_tools/fetch_candles.py 150aec1d3427af926bd02a074bac4212615c4cdb
download "$PIN_RESUME" deploy/scripts/toro_profit_hunter_step0_resume_20261113.py 96d39208a1f3f857a6d5e05291213051927cf58a
PY=/opt/superbot-v3-rc70-stage/.venv/bin/python3
[[ -x "$PY" ]] || PY=/usr/bin/python3
[[ -x "$PY" ]] || { echo "TORO_RESUME RESULT=BLOCK python_missing"; exit 2; }
# Syntax check only, no imports, no contact with any bot.
"$PY" - "$ROOT" <<'PYC'
import ast, pathlib, sys
root=pathlib.Path(sys.argv[1])
paths=("backend/desk/toro_profit_hunter.py",
       "deploy/scripts/toro_profit_hunter_step0.py",
       "backend/v3/lab_tools/fetch_candles.py",
       "deploy/scripts/toro_profit_hunter_step0_resume_20261113.py")
for path in paths:
    ast.parse((root/path).read_text(),filename=path)
print("TORO_RESUME PINNED_SOURCE=OK PYTHON_SYNTAX=OK",flush=True)
PYC
command -v systemd-run >/dev/null || {
  echo "TORO_RESUME RESULT=BLOCK systemd_run_missing"; exit 2;
}
# systemd-run keeps working when Termius/SSH disconnects; CPU is capped to
# prioritize Brain. Logs and per-symbol reports persist in original OUT.
systemd-run --unit="$UNIT" --collect \
  --property=Type=exec \
  --property=Nice=15 \
  --property=CPUQuota=70% \
  --property=MemoryMax=700M \
  --property="StandardOutput=append:$LOG" \
  --property="StandardError=append:$LOG" \
  --property="WorkingDirectory=$ROOT" \
  --setenv="PYTHONPATH=$ROOT/backend:$ROOT" \
  --setenv=PYTHONDONTWRITEBYTECODE=1 \
  "$PY" -u "$ROOT/deploy/scripts/toro_profit_hunter_step0_resume_20261113.py"
echo "TORO_RESUME RESULT=LAUNCHED_DETACHED only_missing_XRP_fetch=1 saved_8_files_reused=1"
echo "TORO_RESUME LOG=$LOG"
echo "TORO_RESUME REPORT=$OUT/report_step0.json"
echo "TORO_RESUME STATUS=systemctl status $UNIT.service --no-pager"
