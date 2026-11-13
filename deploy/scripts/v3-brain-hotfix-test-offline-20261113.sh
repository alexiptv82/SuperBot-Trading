#!/usr/bin/env bash
# Brain RC84 - isolated offline smoke/regression suite for exact GitHub patch.
# Does NOT touch the installed service, runtime files, VPS production tree, data, or keys.
# GitHub downloads only. Everything is created under /tmp and deleted at exit.
set -euo pipefail
umask 077
STAGE="/opt/superbot-v3-rc84-stage"
PIN="4fd28ad7e4d00d3db9d15c510dbedf700ce24719"
EXPECTED_STAGE="0e29a73a36f668643da4088178bacb8616a45ac0"
ROOT_URL="https://raw.githubusercontent.com/alexiptv82/SuperBot-Trading/$PIN"
if ! git -C "$STAGE" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "BRAIN_HOTFIX_VERIFY=BLOCK reason=stage_git_missing"; exit 2
fi
ACTUAL="$(git -C "$STAGE" rev-parse HEAD)"
if [[ "$ACTUAL" != "$EXPECTED_STAGE" ]]; then
  echo "BRAIN_HOTFIX_VERIFY=BLOCK reason=installed_commit_changed stage_sha=$ACTUAL"; exit 2
fi
if [[ -n "$(git -C "$STAGE" status --porcelain)" ]]; then
  echo "BRAIN_HOTFIX_VERIFY=BLOCK reason=installed_stage_dirty"; exit 2
fi
TMP="$(mktemp -d /tmp/superbot-brain-test-XXXXXXXX)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/backend/v3/lab_tools" "$TMP/backend/v3/runner" "$TMP/backend/tests"
touch "$TMP/backend/__init__.py" "$TMP/backend/v3/__init__.py" "$TMP/backend/v3/lab_tools/__init__.py" "$TMP/backend/v3/runner/__init__.py"
for path in backend/v3/lab_tools/fetch_candles.py backend/v3/runner/contracts.py backend/tests/test_brain_market_hotfix_rc84.py; do
  curl -fsSL --max-time 25 "$ROOT_URL/$path" -o "$TMP/$path"
done
if [[ "$(git hash-object "$TMP/backend/v3/lab_tools/fetch_candles.py")" != "150aec1d3427af926bd02a074bac4212615c4cdb" ||
      "$(git hash-object "$TMP/backend/v3/runner/contracts.py")" != "8ffc7f6ec3fe832b30fc70fbc1f41ef319b6f452" ||
      "$(git hash-object "$TMP/backend/tests/test_brain_market_hotfix_rc84.py")" != "bd32e412533bd1c848da322fe6994a4d4d896808" ]]; then
  echo "BRAIN_HOTFIX_VERIFY=BLOCK reason=github_file_hash_mismatch"; exit 2
fi
echo "BRAIN_HOTFIX_VERIFY=PINNED_SOURCE_OK stage=$ACTUAL sha=$PIN"
PY="/opt/superbot-v3-rc70-stage/.venv/bin/python3"
[[ -x "$PY" ]] || PY="/usr/bin/python3"
# Exact committed tests, not hand-copied. No pytest dependency required.
cd "$TMP"
PYTHONPATH="$TMP" PYTHONDONTWRITEBYTECODE=1 "$PY" - <<'PY'
import re
import runpy
from backend.v3.lab_tools.fetch_candles import fetch_rows

def report(name):
    print("BRAIN_HOTFIX_VERIFY=" + name, flush=True)

suite = runpy.run_path("backend/tests/test_brain_market_hotfix_rc84.py")
tests = sorted((key, value) for key, value in suite.items() if key.startswith("test_") and callable(value))
assert len(tests) == 4, f"unexpected_number_of_pinned_tests:{len(tests)}"
for name, func in tests:
    func()
    report("PASS " + name)
report(f"PINNED_TESTS_PASS={len(tests)}/{len(tests)}")

count = 0
for step in (60_000, 900_000, 3_600_000, 14_400_000):
    end = (1_750_000_000_000 // step) * step
    for n in (3, 4, 5, 197, 198, 199, 200, 201, 202, 397, 398, 399, 400, 401, 600, 1000):
        start = end - n * step
        for inclusive in (False, True):
            for holes in (set(), {1, n // 2}):
                hist = {
                    t: [str(t), "100", "101", "99", "100", "1", "1"]
                    for j, t in enumerate(range(start, end + step, step))
                    if j not in holes
                }
                def get_json(url):
                    fields = dict(re.findall(r"(\w+)=([^&]+)", url.split("?", 1)[1]))
                    lo, hi, limit = (int(fields[x]) for x in ("startTime", "endTime", "limit"))
                    assert lo % step == hi % step == 0 and limit <= 200
                    rows = [hist[t] for t in sorted(hist) if lo <= t <= hi and (inclusive or t < hi)]
                    return {"code": "00000", "data": rows[-limit:]}
                output = fetch_rows("SOLUSDT", start, end, candle_ms=step, get_json=get_json)
                expected = {t for j, t in enumerate(range(start, end, step)) if j not in holes}
                assert set(output) == expected, (step, n, inclusive, holes)
                assert end not in output
                count += 1
report(f"TIMEFRAME_BOUNDARY_CASES_PASS={count}/{count}")
report("RESULT=PASS code_only_no_runtime_changes")
PY
