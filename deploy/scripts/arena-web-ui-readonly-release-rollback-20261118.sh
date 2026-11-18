#!/usr/bin/env bash
# AI Arena web UI release (static files only) with verified backup and automatic rollback.
# --activate | --rollback  --candidate <dir> --new-sha <sha256 index.html> --old-sha <sha256 index.html>
# Does not restart nginx, containers or services. Release AFTER the backend route is live.
set -Eeuo pipefail
IFS=$'\n\t'

MODE="${1:-}"; [[ $# -gt 0 ]] && shift
CAND=''; NEW_SHA=''; OLD_SHA=''
while [[ $# -gt 0 ]]; do
  case "$1" in
    --candidate) CAND="${2:-}"; shift 2 ;;
    --new-sha) NEW_SHA="${2:-}"; shift 2 ;;
    --old-sha) OLD_SHA="${2:-}"; shift 2 ;;
    *) printf 'ARENA_WEBUI_RELEASE_REFUSED=UNKNOWN_ARGUMENT\n'; exit 2 ;;
  esac
done
DOMAIN="${ARENA_WEBUI_DOMAIN:-superbot-trading.duckdns.org}"
WEB="${ARENA_WEBUI_ROOT:-/opt/superbot-web}"
LIVE="$WEB/build"
PREV="$WEB/.arena-webui-previous"
BACKUPS="${ARENA_WEBUI_BACKUPS:-/opt/superbot-v3-backups}"
PY="${ARENA_WEBUI_PYTHON:-python3}"

say(){ printf 'ARENA_WEBUI_RELEASE_%s\n' "$*"; }
fail(){ say "REFUSED=$1"; exit 2; }
digest(){ sha256sum "$1/index.html" | cut -d' ' -f1; }

[[ "$MODE" == --activate || "$MODE" == --rollback ]] || fail SPECIFY_ACTIVATE_OR_ROLLBACK
[[ "$NEW_SHA" =~ ^[0-9a-f]{64}$ && "$OLD_SHA" =~ ^[0-9a-f]{64}$ ]] || fail SHA256_ARGUMENTS_REQUIRED
[[ "$NEW_SHA" != "$OLD_SHA" ]] || fail OLD_AND_NEW_SHA_EQUAL
[[ "${ARENA_WEBUI_TEST_MODE:-0}" == 1 || "$(id -u)" == 0 ]] || fail ROOT_REQUIRED
for c in curl "$PY" nginx sha256sum systemctl; do command -v "$c" >/dev/null || fail "TOOL_MISSING_$c"; done
[[ -d "$WEB" && ! -L "$WEB" && -s "$LIVE/index.html" && ! -L "$LIVE" ]] || fail LIVE_NOT_VERIFIED

brain_ok(){
  for u in superbot-v3-paper-brain-runner.service superbot-v3-paper-brain-exit.service; do
    [[ "$(systemctl is-active "$u" 2>/dev/null || true)" == active ]] || fail "BRAIN_NOT_ACTIVE_$u"
  done
}
fetch(){ # url outfile -> prints http code; same host/TLS path as the public app
  curl -sS --max-time 12 --resolve "$DOMAIN:443:127.0.0.1" -o "$2" -w '%{http_code}' "$1" 2>/dev/null
}
auth_ok(){
  local temp code
  temp="$(mktemp)" || fail TEMP_FAILED
  code="$(fetch "https://$DOMAIN/api/auth/webauthn/status" "$temp")" || { rm -f "$temp"; return 1; }
  [[ "$code" == 200 ]] || { rm -f "$temp"; return 1; }
  "$PY" - "$temp" <<'PY' || { rm -f "$temp"; return 1; }
import json, pathlib, sys
d = json.loads(pathlib.Path(sys.argv[1]).read_text())
assert isinstance(d, dict)
assert type(d.get('available')) is bool
assert type(d.get('has_credentials')) is bool
PY
  rm -f "$temp"; say AUTH_ENDPOINT=200_VALID_JSON
}
web_ok(){
  local temp code actual
  temp="$(mktemp)" || fail TEMP_FAILED
  code="$(fetch "https://$DOMAIN/" "$temp")" || { rm -f "$temp"; return 1; }
  actual="$(sha256sum "$temp" | cut -d' ' -f1)"; rm -f "$temp"
  [[ "$code" == 200 && "$actual" == "$(digest "$LIVE")" ]] || return 1
  say WEB=200_MATCHED_INDEX
}
arena_route_code(){ local t c; t="$(mktemp)"; c="$(fetch "https://$DOMAIN/api/v3/arena" "$t" || echo 000)"; rm -f "$t"; printf '%s' "$c"; }
arena_route_ok(){ [[ "$(arena_route_code)" == 401 ]]; }

case "$MODE" in
  --rollback)
    [[ -d "$PREV" && -s "$PREV/index.html" && ! -L "$PREV" ]] || fail PREVIOUS_MISSING
    [[ "$(digest "$PREV")" == "$OLD_SHA" ]] || fail PREVIOUS_SHA_BAD
    [[ "$(digest "$LIVE")" == "$NEW_SHA" ]] || fail LIVE_NOT_CANDIDATE
    BAD="$WEB/.arena-webui-rejected-$(date -u +%Y%m%dT%H%M%SZ)"
    [[ ! -e "$BAD" ]] || fail REJECTED_PATH_EXISTS
    mv -T "$LIVE" "$BAD" || fail MOVE_CANDIDATE_FAILED
    mv -T "$PREV" "$LIVE" || { mv -T "$BAD" "$LIVE" || true; fail RESTORE_FAILED; }
    say ROLLBACK=PREVIOUS_UI_RESTORED
    say "REJECTED_BUILD_PRESERVED=$BAD"
    web_ok || fail ROLLBACK_WEB_CHECK_FAILED_MANUAL_CHECK
    say RESULT=RESTORED_PREVIOUS_UI
    ;;
  --activate)
    [[ -n "$CAND" && -d "$CAND" && ! -L "$CAND" && -s "$CAND/index.html" ]] || fail CANDIDATE_MISSING
    [[ "$(digest "$LIVE")" == "$OLD_SHA" ]] || fail LIVE_INDEX_NOT_OLD_SHA
    [[ "$(digest "$CAND")" == "$NEW_SHA" ]] || fail CANDIDATE_SHA_MISMATCH
    [[ ! -e "$PREV" && ! -L "$PREV" ]] || fail PREVIOUS_BACKUP_ALREADY_EXISTS
    [[ -d "$CAND/static/js" ]] || fail CANDIDATE_JS_MISSING
    if grep -RlqF --include='*.js' -- 'http://51.91.109.45:8002' "$CAND/static/js"; then fail HTTP_FALLBACK_PRESENT; fi
    grep -RlqF --include='*.js' -- '/api/v3/arena' "$CAND/static/js" || fail CANDIDATE_WITHOUT_ARENA_API
    grep -RlqF --include='*.js' -- '3 giorni' "$CAND/static/js" || fail CANDIDATE_WITHOUT_3_DAYS
    if grep -RlqF --include='*.js' -- '14 giorni' "$CAND/static/js"; then fail CANDIDATE_SAYS_14_DAYS; fi
    for f in manifest.json service-worker.js; do
      [[ -s "$LIVE/$f" ]] || fail "PWA_FILE_MISSING_$f"
    done
    nginx -t >/dev/null 2>&1 || fail NGINX_INVALID
    [[ -d "$BACKUPS" && ! -L "$BACKUPS" ]] || fail BACKUPS_DIR_MISSING
    brain_ok
    web_ok || fail WEB_NOT_HEALTHY_BEFORE
    auth_ok || fail AUTH_NOT_HEALTHY_BEFORE
    code="$(arena_route_code)"
    [[ "$code" != 404 ]] || fail BACKEND_ARENA_ROUTE_NOT_LIVE
    [[ "$code" == 401 ]] || fail "BACKEND_ARENA_UNEXPECTED_HTTP_$code"
    STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
    SAVED="$BACKUPS/arena-webui-before-$STAMP"
    STAGED="$WEB/.arena-webui-candidate-$STAMP"
    [[ ! -e "$SAVED" && ! -e "$STAGED" ]] || fail ALREADY_EXISTS
    mkdir -m 0700 "$SAVED"
    cp -a "$LIVE" "$SAVED/build"
    diff -qr "$LIVE" "$SAVED/build" >/dev/null || fail BACKUP_COMPARE_FAILED
    say "BACKUP_VERIFIED=$SAVED/build"
    cp -a "$CAND" "$STAGED"
    # Keep the working PWA identity (manifest, service worker, icons) of the live app.
    cp -a "$LIVE/manifest.json" "$LIVE/service-worker.js" "$STAGED/"
    if [[ -d "$LIVE/icons" ]]; then mkdir -p "$STAGED/icons"; cp -a "$LIVE/icons/." "$STAGED/icons/"; fi
    find "$STAGED" -type d -exec chmod 0755 {} +
    find "$STAGED" -type f -exec chmod 0644 {} +
    [[ "$(digest "$STAGED")" == "$NEW_SHA" ]] || fail STAGED_BUILD_SHA_BAD
    cmp -s "$LIVE/manifest.json" "$STAGED/manifest.json" || fail PWA_MANIFEST_CHANGED
    cmp -s "$LIVE/service-worker.js" "$STAGED/service-worker.js" || fail SERVICE_WORKER_CHANGED
    say PWA_IDENTITY_FILES=PRESERVED
    mv -T "$LIVE" "$PREV" || fail LIVE_MOVE_FAILED
    if ! mv -T "$STAGED" "$LIVE"; then mv -T "$PREV" "$LIVE" || true; fail NEW_BUILD_MOVE_FAILED; fi
    if ! ( web_ok && auth_ok && arena_route_ok && brain_ok ); then
      REJECT="$WEB/.arena-webui-auto-rejected-$STAMP"
      mv -T "$LIVE" "$REJECT" || true
      mv -T "$PREV" "$LIVE" || fail AUTO_ROLLBACK_FAILED
      say AUTO_ROLLBACK=TRUE
      say "REJECTED_BUILD_PRESERVED=$REJECT"
      exit 2
    fi
    say "NEW_INDEX_SHA256=$(digest "$LIVE")"
    say "ROLLBACK_READY=$PREV"
    say BRAIN_SERVICES_CHANGED=FALSE
    say CONTAINERS_OR_NGINX_RESTARTED=FALSE
    say RESULT=SUCCESS_UI_ONLY
    ;;
esac
