#!/usr/bin/env bash
# Initialize ONLY the two NEW classic PAPER state files with canonical RC84 data schema.
# No service start, no market data, no AI call, no historical overwrite, no LIVE orders.
set -euo pipefail
umask 077
export PYTHONDONTWRITEBYTECODE=1 DESK_MODE=paper

STAGE=/opt/superbot-v3-rc84-stage
ROOT=/opt/superbot-v3-paper-runs
HAWK="$ROOT/classic-hawk-paper20261111"
BULL="$ROOT/classic-bull-paper20261111"
BRAIN="$ROOT/brain-v3-paper20261111"
PYTHON=/opt/superbot-v3-rc70-stage/.venv/bin/python3
PIN=0e29a73a36f668643da4088178bacb8616a45ac0
MODE=--dry-run
if (( $# > 0 )); then MODE="$1"; fi
if (( $# > 1 )) || [[ "$MODE" != --dry-run && "$MODE" != --initialize-paused-accounts ]]; then
  echo RC84_ACCOUNT_REFUSED_MODE; exit 2
fi
die(){ echo "RC84_ACCOUNT_REFUSED_$1"; exit 2; }
[[ -x "$PYTHON" ]] || die "VENV_UNAVAILABLE"
[[ -d "$STAGE" && ! -L "$STAGE" ]] || die "STAGE_UNAVAILABLE"
[[ "$(git -C "$STAGE" rev-parse HEAD 2>/dev/null)" == "$PIN" ]] || die "PIN_MISMATCH"
for p in "$HAWK" "$BULL" "$BRAIN"; do
  [[ -d "$p" && ! -L "$p" && -f "$p/pause.flag" && ! -L "$p/pause.flag" ]] || die "RUN_NOT_PAUSED"
done
for p in "$HAWK" "$BULL"; do
  [[ -f "$p/PREPARED_PAUSED_ONLY.json" && ! -e "$p/state_v2.json" && ! -L "$p/state_v2.json" ]] \
     || die "CLASSIC_STATE_NOT_FRESH"
done
[[ -f "$BRAIN/mandate.json" && -f "$BRAIN/journal.db" ]] || die "BRAIN_MISSING"

# Independent Brain exit sidecar validation, no worker launched, no market or AI call.
DESK_MODE=paper PYTHONPATH="$STAGE" "$PYTHON" -m backend.v3.runner.exit_worker \
  --data-dir "$BRAIN" --run-id brain-v3-paper20261111 \
  --config "$BRAIN/runner_config.json" --validate-only \
  || die "BRAIN_VALIDATE_ONLY_FAILED"

# Verify both portfolio limits and markers BEFORE any write.
DESK_MODE=paper PYTHONPATH="$STAGE/backend" "$PYTHON" - "$HAWK" "$BULL" --check-only <<'PY' \
  || die "CLASSIC_SCHEMA_VERIFY_FAILED"
import json, pathlib, sys
from desk.cli import _make_hawk_config,_make_bull_config
for path, ident, config in zip(map(pathlib.Path,sys.argv[1:3]),
                               ("hawk","bull"),(_make_hawk_config(),_make_bull_config())):
    m=json.loads((path/"PREPARED_PAUSED_ONLY.json").read_text())
    assert m["portfolio_id"]==ident and m["paper_only"] is True and m["paused"] is True
    assert m["initial_equity"]=="1000"
    assert config.limits.start_equity==1000
    assert config.limits.kill_equity==450
print("RC84_CLASSICS_1000_SCHEMA_MATCH=True")
PY

if [[ "$MODE" == --dry-run ]]; then
  echo RC84_ACCOUNT_DRY_RUN=PASS
  echo RC84_ACCOUNT_CLASSICS_STILL_UNINITIALIZED=True
  echo RC84_ACCOUNT_BRAIN_EXIT_VALIDATE_ONLY=PASS
  echo RC84_ACCOUNT_NO_DATA_WRITES=True
  exit 0
fi

# This process is not a trading engine; its only writes are brand-new
# state_v2.json files in the NEW, paused directories.
DESK_MODE=paper PYTHONPATH="$STAGE/backend" "$PYTHON" - "$HAWK" "$BULL" <<'PY' \
  || die "CLASSIC_BOOTSTRAP_FAILED"
import json, os, pathlib, sys, time
from desk.cli import _make_hawk_config, _make_bull_config
from desk.engine import PaperAccount
paths=tuple(map(pathlib.Path,sys.argv[1:3]))
configs=(_make_hawk_config(),_make_bull_config())
now_ms=int(time.time()*1000)
for path, ident, config in zip(paths,("hawk","bull"),configs):
    assert (path/"pause.flag").is_file()
    account=PaperAccount(config.limits,"main")
    assert account.cash==1000 and len(account.positions)==0
    data={
       "main":account.to_dict(), "run_no":1,
       "run_started_ms":now_ms,"paused":True,"mode":"paused"
    }
    output=path/"state_v2.json"
    flags=os.O_CREAT | os.O_EXCL | os.O_WRONLY
    if hasattr(os,"O_NOFOLLOW"): flags |= os.O_NOFOLLOW
    fd=os.open(str(output),flags,0o600)
    with os.fdopen(fd,"w",encoding="utf-8") as fh:
        json.dump(data,fh,sort_keys=True,separators=(",",":"))
        fh.write("\n")
        fh.flush()
        os.fsync(fh.fileno())
    check=json.loads(output.read_text())
    assert check["main"]["cash"]==1000
    assert not check["main"]["positions"] and check["paused"] is True
    print("RC84_"+ident.upper()+"_INITIAL_EQUITY_PAPER=1000")
    print("RC84_"+ident.upper()+"_OPEN_POSITIONS=0")
print("RC84_CLASSIC_ACCOUNTS_INITIALIZED_PAUSED=True")
PY

echo RC84_BRAIN_EXIT_VALIDATE_ONLY=PASS
echo RC84_LEGACY_DATA_UNTOUCHED=True
echo RC84_NO_SERVICES_STARTED=True
echo RC84_NO_PAPER_ORDERS=True
