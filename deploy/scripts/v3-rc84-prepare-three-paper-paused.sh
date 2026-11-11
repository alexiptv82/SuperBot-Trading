#!/usr/bin/env bash
# RC84: prepare THREE NEW PAPER identities, PAUSED ONLY.
# Does not install/start services, change app, touch legacy state, send orders or approve mandates.
# The RC84 source checkout is provisioned separately, and MUST match the pinned SHA.
set -euo pipefail
umask 077
export PYTHONDONTWRITEBYTECODE=1

PIN="0e29a73a36f668643da4088178bacb8616a45ac0"
STAGE=/opt/superbot-v3-rc84-stage
ROOT=/opt/superbot-v3-paper-runs
TAG=paper20261111
HAWK="$ROOT/classic-hawk-$TAG"
BULL="$ROOT/classic-bull-$TAG"
BRAIN="$ROOT/brain-v3-$TAG"
CONFIG="$STAGE/backend/v3/runner/runner_config_brain2000_paper.json"

mode="--dry-run"
if (( $# > 0 )); then mode="$1"; fi
if (( $# > 1 )) || [[ "$mode" != "--dry-run" && "$mode" != "--prepare-paused-paper" ]]; then
  echo RC84_PREP_REFUSED_BAD_MODE; exit 2
fi

die() { echo "RC84_PREP_REFUSED_$1"; exit 2; }
for tool in python3 git; do command -v "$tool" >/dev/null || die "MISSING_TOOL"; done
[[ -d "$STAGE" && ! -L "$STAGE" && -d "$STAGE/.git" ]] || die "SOURCE_STAGE_NOT_PINNED"
[[ "$(git -C "$STAGE" rev-parse HEAD 2>/dev/null)" == "$PIN" ]] || die "SOURCE_SHA_MISMATCH"
[[ -d "$ROOT" && ! -L "$ROOT" ]] || die "PAPER_PARENT_UNAVAILABLE"
[[ -f "$CONFIG" && ! -L "$CONFIG" ]] || die "BRAIN_CONFIG_UNAVAILABLE"

# Inspect only the non-secret, committed Brain profile. No model call or exchange connection.
python3 - "$CONFIG" <<'PY' || die "BRAIN_PROFILE_MISMATCH"
import json, sys
from decimal import Decimal
with open(sys.argv[1], encoding="utf-8") as src:
    cfg=json.load(src)
r=cfg["risk_policy"]
assert Decimal(str(cfg["initial_equity"]))==2000
assert Decimal(str(r["minimum_equity"]))==450
assert type(r["min_leverage"]) is int and r["min_leverage"]==20
assert type(r["max_leverage"]) is int and r["max_leverage"]==50
assert Decimal(str(r["max_open_risk_fraction"]))==Decimal("0.12")
assert Decimal(str(r["max_position_margin_fraction"]))==Decimal("0.20")
assert Decimal(str(r["max_loss_margin_fraction"]))==Decimal("0.214285714285714285")
assert cfg["cycle_minutes"]==60
PY

for path in "$HAWK" "$BULL" "$BRAIN"; do
  [[ ! -e "$path" && ! -L "$path" ]] || die "NEW_RUN_ALREADY_EXISTS"
done
if [[ "$mode" == "--dry-run" ]]; then
  echo RC84_PREP_DRY_RUN=PASS
  echo RC84_PREP_PIN="$PIN"
  echo RC84_PREP_ALL_NEW_DIRS=AVAILABLE
  echo RC84_PREP_NO_FILES_WRITTEN=True
  exit 0
fi

# No docker/systemctl calls. Every new classic is PAUSED before any runtime is connected.
mkdir -m 0700 -- "$HAWK"
printf '%s\n' "prepared_and_paused" > "$HAWK/pause.flag"
chmod 0600 "$HAWK/pause.flag"
mkdir -m 0700 -- "$BULL"
printf '%s\n' "prepared_and_paused" > "$BULL/pause.flag"
chmod 0600 "$BULL/pause.flag"

# Initial state_v2.json is deliberately absent: the PAPER engine initializes
# a fresh 1,000 USDT account from PORTFOLIO.limits on its future approved first start.
# The metadata below is an operator marker, not an engine state/mandate.
for item in hawk bull; do
  dir="$HAWK"
  [[ "$item" != bull ]] || dir="$BULL"
  printf '{"portfolio_id":"%s","initial_equity":"1000","paper_only":true,"paused":true,"source_sha":"%s"}\n' \
    "$item" "$PIN" > "$dir/PREPARED_PAUSED_ONLY.json"
  chmod 0600 "$dir/PREPARED_PAUSED_ONLY.json"
done

# Reuse the V3 preparator; it creates its own append-only journal, ledger,
# pause.flag and an explicitly UNAPPROVED mandate. Never amend an old Brain run.
# Prefer the already provisioned application venv used by the existing RC70 preview.
# It is used only to execute the isolated preparator, never to start a service.
BRAIN_PYTHON=/opt/superbot-v3-rc70-stage/.venv/bin/python3
[[ -x "$BRAIN_PYTHON" ]] || die "BRAIN_PYTHON_VENV_UNAVAILABLE"
DESK_MODE=paper PYTHONPATH="$STAGE" "$BRAIN_PYTHON" -m backend.v3.runner.prepare_paper_run \
  --parent "$ROOT" --run-name "$(basename "$BRAIN")" \
  --run-id "brain-v3-$TAG" --config "$CONFIG" \
  --expected-initial-equity 2000 --prepare-paper-paused \
  || die "BRAIN_PREPARATION_FAILED_LEFT_PAUSED_DIRS_FOR_INSPECTION"

[[ -f "$BRAIN/pause.flag" && -f "$BRAIN/PREPARED_PAUSED_ONLY.json" && -f "$BRAIN/mandate.json" ]] \
  || die "BRAIN_PREPARATION_INCOMPLETE"
python3 - "$BRAIN" "$HAWK" "$BULL" <<'PY' || die "POST_PREP_MISMATCH"
import json, pathlib, sys
brain, hawk, bull=map(pathlib.Path, sys.argv[1:])
m=json.loads((brain/"mandate.json").read_text())
marker=json.loads((brain/"PREPARED_PAUSED_ONLY.json").read_text())
assert m["approved"] is False and marker["mandate_approved"] is False
assert marker["paper_only"] is True and marker["paused"] is True
assert marker["initial_equity"]=="2000"
assert all((p/"pause.flag").is_file() and not (p/"state_v2.json").exists()
           for p in (hawk,bull))
PY
echo RC84_THREE_PAPER_RUNS_PREPARED_PAUSED=True
echo RC84_BRAIN_MANDATE_APPROVED=False
echo RC84_NO_CONTAINER_STARTED=True
echo RC84_NO_LEGACY_FILES_TOUCHED=True
echo RC84_RELEASE_NOT_INSTALLED=True
