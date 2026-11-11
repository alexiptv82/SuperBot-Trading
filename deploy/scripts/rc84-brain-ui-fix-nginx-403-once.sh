#!/usr/bin/env bash
# One-time recovery of published frontend *public asset permissions only*.
# No Docker/systemd/restart/worker/mandate/auth DB/secret changes.
set -euo pipefail
umask 077
MODE="${1:---check}"
[[ $# -le 1 && ( "$MODE" == "--check" || "$MODE" == "--repair" ) ]] || { echo RC84_403_BAD_MODE; exit 2; }
ROOT=/opt/superbot-web/build
INDEX="$ROOT/index.html"
REPORT=/opt/superbot-v3-brain-ui-stage/brain-ui-public-cutover-report.json
BACKUP=/opt/superbot-web/build.rc84-before-brain-ui
PIN=d0c832620e9b237ce97305029bab5150d3f77489

# Invariant: repair must apply ONLY to the exact user-approved Brain UI release.
[[ -d "$ROOT" && ! -L "$ROOT" && -f "$INDEX" && ! -L "$INDEX" ]] \
  || { echo RC84_403_PUBLIC_FRONTEND_NOT_EXPECTED; exit 2; }
[[ -d "$BACKUP" && ! -L "$BACKUP" && -f "$BACKUP/index.html" ]] \
  || { echo RC84_403_ROLLBACK_MISSING; exit 2; }
[[ -f "$REPORT" && ! -L "$REPORT" ]] || { echo RC84_403_RELEASE_MARKER_MISSING; exit 2; }
[[ "$(docker inspect -f '{{.Config.Image}}' superbot 2>/dev/null)" == "superbot:brain-ui-20261111" ]] \
  || { echo RC84_403_DEPLOYED_BACKEND_CHANGED; exit 2; }
python3 -I - "$REPORT" "$PIN" <<'PY'
import json,sys
with open(sys.argv[1],encoding='utf-8') as f:
    p=json.load(f)
assert p.get('release_sha')==sys.argv[2]
assert p.get('paper_paused') is True
assert p.get('brain_mandate_approved') is False
print('RC84_403_RELEASE_IDENTITY_VERIFIED=True')
PY
[[ -z "$(find "$ROOT" -type l -print -quit)" ]] \
  || { echo RC84_403_SYMLINK_IN_PUBLIC_ASSETS; exit 2; }

# Trading safety: check only markers, no journal opening and NO model calls.
for p in /opt/superbot-v3-paper-runs/classic-hawk-paper20261111 \
         /opt/superbot-v3-paper-runs/classic-bull-paper20261111 \
         /opt/superbot-v3-paper-runs/brain-v3-paper20261111; do
  [[ -f "$p/pause.flag" ]] || { echo RC84_403_RUN_NOT_PAUSED; exit 2; }
done
python3 -I - <<'PY'
import json,pathlib
p=pathlib.Path('/opt/superbot-v3-paper-runs/brain-v3-paper20261111/mandate.json')
assert json.loads(p.read_text()).get('approved') is False
print('RC84_403_BRAIN_MANDATE_UNAPPROVED=True')
PY

command -v runuser >/dev/null || { echo RC84_403_NO_RUNUSER; exit 2; }
MODE_BEFORE="$(stat -c '%a' "$ROOT")"
echo "RC84_403_ASSET_DIR_MODE_BEFORE=$MODE_BEFORE"
if runuser -u www-data -- test -r "$INDEX"; then
  echo RC84_403_WWWDATA_INDEX_READABLE_ALREADY=True
  if [[ "$MODE" == "--repair" ]]; then
    echo RC84_403_NO_CHANGE_ALREADY_READABLE=True
  fi
  exit 0
fi
echo RC84_403_WWWDATA_INDEX_READABLE_BEFORE=False
if [[ "$MODE" == "--check" ]]; then
  echo RC84_403_DIAGNOSIS=PUBLIC_ASSETS_INACCESSIBLE
  exit 0
fi
[[ "$MODE_BEFORE" == 700 ]] || { echo RC84_403_REFUSED_UNEXPECTED_MODE; exit 2; }
# Public React build: requires standard read/traverse permission for Nginx.
find "$ROOT" -type d -exec chmod 0755 {} +
find "$ROOT" -type f -exec chmod 0644 {} +
runuser -u www-data -- test -r "$INDEX" \
  || { echo RC84_403_FIX_NOT_SUFFICIENT; exit 2; }
echo RC84_403_ASSET_DIR_MODE_AFTER="$(stat -c '%a' "$ROOT")"
echo RC84_403_WWWDATA_INDEX_READABLE_AFTER=True
echo RC84_403_NGINX_STATIC_FILE_PERMISSIONS_REPAIRED=True
echo RC84_403_NO_SERVICE_RESTART_OR_TRADING_CHANGES=True
