#!/usr/bin/env bash
# RC84: start only FOUR NEW PAPER units against THREE NEW, PAUSED wallets.
# No service enable, no legacy stop, no public web change, no orders or mandate approval.
set -Eeuo pipefail
umask 077
export PYTHONDONTWRITEBYTECODE=1
MODE="--dry-run"
(( $# == 0 )) || MODE="$1"
if (( $# > 1 )) || [[ "$MODE" != --dry-run && "$MODE" != --start-paused-only ]]; then
  echo RC84_WORKERS_REFUSED_MODE; exit 2
fi

STAGE=/opt/superbot-v3-rc84-stage
PIN=0e29a73a36f668643da4088178bacb8616a45ac0
FILES=/opt/superbot-v3-rc84-services-staged-v2
ROOT=/opt/superbot-v3-paper-runs
HAWK="$ROOT/classic-hawk-paper20261111"
BULL="$ROOT/classic-bull-paper20261111"
BRAIN="$ROOT/brain-v3-paper20261111"
PY=/opt/superbot-v3-rc70-stage/.venv/bin/python3
NAMES="superbot-v3-paper-falco superbot-v3-paper-toro superbot-v3-paper-brain-exit superbot-v3-paper-brain-runner"
INSTALLED=0
COMPLETE=0
die(){ echo "RC84_WORKERS_REFUSED_$1"; exit 2; }
rollback() {
  echo RC84_WORKERS_ROLLBACK_NEW_UNITS_ONLY=True
  for n in $NAMES; do systemctl stop "$n.service" >/dev/null 2>&1 || :; done
  for n in $NAMES; do rm -f "/etc/systemd/system/$n.service"; done
  systemctl daemon-reload >/dev/null 2>&1 || :
}
finish(){
  local rc=$?
  trap - EXIT
  if [[ "$INSTALLED" == 1 && "$COMPLETE" != 1 ]]; then rollback; fi
  exit "$rc"
}
trap finish EXIT

for cmd in git python3 systemctl docker; do command -v "$cmd" >/dev/null || die MISSING_TOOL; done
[[ -x "$PY" && -d "$STAGE" && ! -L "$STAGE" && -d "$FILES" && ! -L "$FILES" ]] \
  || die STAGE_OR_PYTHON_UNAVAILABLE
[[ "$(git -C "$STAGE" rev-parse HEAD 2>/dev/null)" == "$PIN" ]] || die SOURCE_SHA_MISMATCH
for p in "$HAWK" "$BULL" "$BRAIN"; do
  [[ -d "$p" && ! -L "$p" && -f "$p/pause.flag" && ! -L "$p/pause.flag" ]] \
    || die ANY_RUN_NOT_PAUSED
  [[ -s "$p/PREPARED_PAUSED_ONLY.json" ]] || die RUN_MARKER_MISSING
done
for n in $NAMES; do
  [[ -f "$FILES/$n.service" && ! -L "$FILES/$n.service" ]] || die UNIT_STAGE_MISSING
  [[ ! -e "/etc/systemd/system/$n.service" && ! -L "/etc/systemd/system/$n.service" ]] || die UNIT_ALREADY_INSTALLED
  if systemctl is-active --quiet "$n.service"; then die UNIT_ALREADY_ACTIVE; fi
  if systemctl is-enabled --quiet "$n.service" 2>/dev/null; then die UNIT_ALREADY_ENABLED; fi
done
for n in hawk bull; do
  [[ "$(docker inspect -f '{{.State.Running}}' "superbot-desk-$n" 2>/dev/null)" == false ]] \
    || die LEGACY_CLASSIC_RUNNING
done
for n in superbot-v3-falco-exit superbot-v3-toro-exit; do
  systemctl is-active --quiet "$n.service" || die LEGACY_EXIT_SERVICE_MISSING
done

python3 - "$HAWK" "$BULL" "$BRAIN" <<'PY' || die PAPER_ACCOUNT_OR_MANDATE_MISMATCH
import hashlib, json, pathlib, sys, stat
hawk,bull,brain=map(pathlib.Path,sys.argv[1:])
for dir_,ident in ((hawk,"hawk"),(bull,"bull")):
    marker=json.loads((dir_/"PREPARED_PAUSED_ONLY.json").read_text())
    state=json.loads((dir_/"state_v2.json").read_text())
    assert marker["portfolio_id"]==ident and marker["paper_only"] is True
    assert marker["initial_equity"]=="1000" and marker["paused"] is True
    assert state["main"]["cash"]==1000 and not state["main"]["positions"]
    assert state["paused"] is True and state["mode"]=="paused"
    assert (dir_/"pause.flag").is_file()
    assert not any((dir_/x).exists() for x in (
        "reset.flag","close_position.flag","close_position.flag.work","reset_portfolio.flag"))
m=json.loads((brain/"mandate.json").read_text())
marker=json.loads((brain/"PREPARED_PAUSED_ONLY.json").read_text())
cfg=(brain/"runner_config.json").read_bytes()
risk=json.loads(cfg)["risk_policy"]
assert m["approved"] is False and marker["mandate_approved"] is False
assert marker["paper_only"] is True and marker["paused"] is True
assert marker["run_id"]==m["run_id"]=="brain-v3-paper20261111"
assert hashlib.sha256(cfg).hexdigest()==marker["config_sha256"]
assert risk["min_leverage"]==20 and risk["max_leverage"]==50
assert not any((brain/x).exists() for x in ("close_request.json","close_request.work","reset.flag"))
for name in ("falco-ai.env","toro-ai.env","brain-ai.env"):
    path=pathlib.Path("/etc/superbot-v3-paper")/name
    if not path.exists() and not path.is_symlink(): continue
    st=path.lstat()
    assert stat.S_ISREG(st.st_mode) and st.st_mode & 0o077 == 0
    raw=path.read_bytes()
    assert len(raw)<65536
    for line in raw.splitlines():
        head=line.split(b"=",1)[0].strip().removeprefix(b"export ").strip()
        assert head not in (
            b"DESK_MODE",b"TRADING_MODE",b"DESK_DATA_DIR",b"DESK_PORTFOLIO",
            b"V3_RUN_ID",b"V3_JOURNAL_PATH",b"V3_RUNNER_CONFIG_PATH"
        )
        assert not head.startswith((b"BITGET_",b"BYBIT_",b"BINANCE_"))
print("RC84_PAPER_IDENTITIES_AND_UNAPPROVED_MANDATE=PASS")
PY

DESK_MODE=paper PYTHONPATH="$STAGE" "$PY" -m backend.v3.runner.exit_worker \
  --data-dir "$BRAIN" --run-id brain-v3-paper20261111 \
  --config "$BRAIN/runner_config.json" --validate-only >/dev/null \
  || die BRAIN_EXISTING_JOURNAL_UNVERIFIED
if [[ "$MODE" == --dry-run ]]; then
  echo RC84_WORKERS_DRY_RUN=PASS
  echo RC84_WORKERS_FOUR_UNITS_NOT_INSTALLED=True
  echo RC84_WORKERS_ALL_PAUSES_PRESENT=True
  echo RC84_WORKERS_BRAIN_MANDATE_APPROVED=False
  echo RC84_WORKERS_NO_FILES_WRITTEN=True
  exit 0
fi

INSTALLED=1
for n in $NAMES; do install -m 0644 -- "$FILES/$n.service" "/etc/systemd/system/$n.service"; done
systemctl daemon-reload
for n in $NAMES; do
  [[ "$(systemctl is-enabled "$n.service" 2>/dev/null || true)" != enabled ]] || die UNEXPECTED_ENABLE
done
systemctl start superbot-v3-paper-brain-exit.service
systemctl start superbot-v3-paper-falco.service
systemctl start superbot-v3-paper-toro.service
systemctl start superbot-v3-paper-brain-runner.service

sleep 10
for n in $NAMES; do systemctl is-active --quiet "$n.service" || die SERVICE_NOT_ACTIVE; done
python3 - "$HAWK" "$BULL" "$BRAIN" <<'PY' || die PAUSED_HEARTBEATS_NOT_VERIFIED
import json, pathlib, sys, time
hawk,bull,brain=map(pathlib.Path,sys.argv[1:])
now=time.time()
for dir_,portfolio in ((hawk,"hawk"),(bull,"bull")):
    beat=json.loads((dir_/"heartbeat.json").read_text())
    st=json.loads((dir_/"state_v2.json").read_text())
    assert beat["exec_mode"]=="paper" and beat["portfolio"]==portfolio
    assert beat["mode"]=="paused" and beat["open_positions"]==0
    assert 0 <= now-float(beat["ts"]) < 40
    assert st["main"]["cash"]==1000 and len(st["main"]["positions"])==0
    assert (dir_/"pause.flag").is_file()
b=json.loads((brain/"heartbeat.json").read_text())
e=json.loads((brain/"exit_heartbeat.json").read_text())
assert b["run_id"]==e["run_id"]=="brain-v3-paper20261111"
assert b["state"] in ("halted","paused") and b["cycle"]==0
assert e["state"]=="healthy" and e["last_error"] is None
assert 0 <= now*1000-int(b["ts_ms"]) < 45000
assert 0 <= now*1000-int(e["ts_ms"]) < 45000
assert (brain/"pause.flag").is_file()
assert json.loads((brain/"mandate.json").read_text())["approved"] is False
print("RC84_NEW_FALCO_TORO_BRAIN_PAUSED_HEARTBEATS=PASS")
print("RC84_BRAIN_EXIT_SINGLE_OWNER_HEALTHY=PASS")
PY
for n in superbot-v3-falco-exit superbot-v3-toro-exit; do
  systemctl is-active --quiet "$n.service" || die LEGACY_EXIT_CHANGED
done
COMPLETE=1
echo RC84_FOUR_NEW_PAPER_SERVICES_ACTIVE_PAUSED=True
echo RC84_FOUR_NEW_PAPER_SERVICES_NOT_ENABLED=True
echo RC84_BRAIN_MANDATE_STILL_UNAPPROVED=True
echo RC84_NO_STRATEGY_CYCLES_OR_PAPER_TRADES=True
echo RC84_NO_LEGACY_OR_PUBLIC_WEB_CHANGES=True
