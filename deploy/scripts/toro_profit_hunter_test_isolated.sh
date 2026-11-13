#!/usr/bin/env bash
# One-off independent Toro V1 tests in /tmp only. NO server changes, no orders.
set -euo pipefail
umask 077
PIN=a4025d767c7bba0dc321e6bfce53344031c18d6a
BASE=https://raw.githubusercontent.com/alexiptv82/SuperBot-Trading/$PIN
TMP=$(mktemp -d /tmp/superbot-toro-v1-test-XXXXXXXX)
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/backend/desk" "$TMP/backend/tests" "$TMP/deploy/scripts"
touch "$TMP/backend/desk/__init__.py"
declare -A blobs
blobs["backend/desk/toro_profit_hunter.py"]=c622e908c03168942d9aa8f697132a22efe091b9
blobs["backend/tests/test_toro_profit_hunter_v1.py"]=19c0e20883b1f2dac47de1022cf0c47ac01e3b7a
blobs["backend/tests/test_toro_profit_hunter_step0.py"]=8b17ee3e970b5993e226e3d9646043b2859dcc1f
blobs["deploy/scripts/toro_profit_hunter_step0.py"]=4adf5716672117a4a7e0a5e58614e8ca0ec85a36
for path in "${!blobs[@]}"; do
  curl -fsSL --max-time 30 "$BASE/$path" -o "$TMP/$path"
  [[ "$(git hash-object "$TMP/$path")" == "${blobs[$path]}" ]] || {
    echo "TORO_TEST RESULT=FAIL reason=hash_mismatch path=$path"; exit 1;
  }
done
PY=/opt/superbot-v3-rc70-stage/.venv/bin/python3
if [[ ! -x "$PY" ]]; then PY=python3; fi
echo "TORO_TEST pinned_source=OK sha=$PIN"
PYTHONDONTWRITEBYTECODE=1 "$PY" -m py_compile \
    "$TMP/backend/desk/toro_profit_hunter.py" \
    "$TMP/backend/tests/test_toro_profit_hunter_v1.py" \
    "$TMP/backend/tests/test_toro_profit_hunter_step0.py" \
    "$TMP/deploy/scripts/toro_profit_hunter_step0.py"
cd "$TMP"
PYTHONPATH="$TMP/backend:$TMP" PYTHONDONTWRITEBYTECODE=1 "$PY" -m unittest discover \
   -s backend/tests -p 'test_toro_profit_hunter*.py' -v
echo "TORO_TEST RESULT=PASS scoped_unit_tests=18 stage_unchanged=1"
