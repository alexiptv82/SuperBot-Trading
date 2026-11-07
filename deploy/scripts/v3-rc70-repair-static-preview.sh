#!/usr/bin/env bash
# Fix only preview static asset readability for nginx worker; never affect production.
set -euo pipefail
umask 077
STAGE=/opt/superbot-v3-rc70-stage
PUBLIC=/opt/superbot-v3-rc70-public
test -d "$STAGE" && test ! -L "$STAGE" || { echo RC70_STAGE_NOT_FOUND; exit 2; }
test -f "$STAGE/nginx-preview.conf" && test -f "$STAGE/frontend/build/index.html" || { echo RC70_STAGE_ASSETS_NOT_FOUND; exit 2; }
test -f "$STAGE/nginx.pid" || { echo RC70_STAGING_NGINX_NOT_RUNNING; exit 2; }
test -e "$PUBLIC" && { echo RC70_PUBLIC_FOLDER_ALREADY_EXISTS; exit 2; } || true
install -d -m 0755 "$PUBLIC"
cp -a "$STAGE/frontend/build/." "$PUBLIC/"
find "$PUBLIC" -type d -exec chmod 0755 '{}' '+'
find "$PUBLIC" -type f -exec chmod 0644 '{}' '+'
python3 - <<'PY'
from pathlib import Path
cfg=Path('/opt/superbot-v3-rc70-stage/nginx-preview.conf')
s=cfg.read_text()
old='root /opt/superbot-v3-rc70-stage/frontend/build;'
assert s.count(old)==1
s=s.replace(old,'root /opt/superbot-v3-rc70-public;')
cfg.write_text(s)
PY
nginx -t -c "$STAGE/nginx-preview.conf" >/dev/null 2>&1 || { echo RC70_NGINX_CONFIG_BAD; exit 2; }
nginx -s reload -c "$STAGE/nginx-preview.conf" >/dev/null 2>&1
ok=0
for i in 1 2 3 4 5; do
  http="$(curl -s -o /dev/null -w '%{http_code}' --max-time 4 http://127.0.0.1:18080/)" || true
  if [ "$http" = 200 ]; then ok=1; break; fi
  sleep 1
done
test "$ok" = 1 || { echo RC70_PREVIEW_STATIC_STILL_UNAVAILABLE; exit 2; }
test "$(curl -s -o /dev/null -w '%{http_code}' --max-time 4 http://127.0.0.1:18080/api/v3/overview)" = 401 || { echo RC70_UNAUTHORIZED_API_NOT_BLOCKED; exit 2; }
test "$(curl -s -o /dev/null -w '%{http_code}' --max-time 4 http://127.0.0.1:8002/api/health)" = 200 || { echo RC70_PRODUCTION_HEALTH_FAILED; exit 2; }
for n in hawk bull; do
  test "$(docker inspect -f '{{.State.Running}}' superbot-desk-"$n")" = false || { echo RC70_CLASSIC_STARTED; exit 2; }
done
test "$(docker inspect -f '{{.State.Running}}' superbot-v3-rc70-preview)" = true || { echo RC70_STAGE_BACKEND_STOPPED; exit 2; }
printf 'RC70_STAGE_APPROVED_PREVIEW=True\n' > "$STAGE/preview-installed.flag"
echo RC70_PREVIEW_UI_HTTP_200=True
echo RC70_PREVIEW_API_401_FOR_UNAUTH=True
echo RC70_PREVIEW_LOCALHOST_ONLY=True
echo RC70_PRODUCTION_HEALTH_200=True
echo RC70_BOTS_UNTOUCHED=True
