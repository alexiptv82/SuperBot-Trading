#!/usr/bin/env bash
# AI Arena UI-only rollout after same-origin auth fix. Never starts trading.
# --activate / --rollback. Does not restart Nginx, Brain or containers.
set -Eeuo pipefail
IFS=$'\n\t'
DOMAIN=superbot-trading.duckdns.org
WEB=/opt/superbot-web
LIVE=$WEB/build
PREV=$WEB/.arena-authfix-previous
SOURCE=/opt/superbot-arena-ui-builds/auth-preflight.q8fwHIEV/workspace/build
OLD_SHA=1432effbd102fb50dfd47722fba46de4c5e91caf48f74c968194d681a4bd2d0c
NEW_SHA=4553bdabbd96c5be59505f878e7078f5d10aff89b00865b642b2a80256ced9bb
VERIFIED=/opt/superbot-v3-backups/arena-samsung-web-before-20261118T034527Z/build
BACKUPS=/opt/superbot-v3-backups
say(){ printf 'ARENA_AUTH_RELEASE_%s\n' "$*"; }
fail(){ say "REFUSED=$1"; exit 2; }
digest(){ sha256sum "$1/index.html" | cut -d' ' -f1; }
[[ "$(id -u)" == 0 ]] || fail ROOT_REQUIRED
for c in curl python3.12 nginx sha256sum systemctl; do command -v "$c" >/dev/null || fail "TOOL_MISSING_$c"; done
[[ -d "$WEB" && ! -L "$WEB" && -s "$LIVE/index.html" && ! -L "$LIVE" ]] || fail LIVE_NOT_VERIFIED
[[ -d "$BACKUPS" && -s "$VERIFIED/index.html" && ! -L "$VERIFIED" ]] || fail BACKUP_NOT_PRESENT
[[ "$(digest "$VERIFIED")" == "$OLD_SHA" ]] || fail BACKUP_SHA_BAD

brain_ok(){
  for u in superbot-v3-paper-brain-runner.service superbot-v3-paper-brain-exit.service; do
    [[ "$(systemctl is-active "$u" 2>/dev/null || true)" == active ]] || fail "BRAIN_NOT_ACTIVE_$u"
  done
}
api_ok(){
  local temp code
  temp="$(mktemp)" || fail TEMP_FAILED
  code="$(curl -sS --max-time 12 --resolve "$DOMAIN:443:127.0.0.1" \
    -o "$temp" -w '%{http_code}' "https://$DOMAIN/api/auth/webauthn/status" 2>/dev/null)" || {
      rm -f "$temp"; fail AUTH_ENDPOINT_UNREACHABLE;
    }
  [[ "$code" == 200 ]] || { rm -f "$temp"; fail "AUTH_HTTP_$code"; }
  python3.12 - "$temp" <<'PY' || { rm -f "$temp"; fail AUTH_JSON_BAD; }
import json,pathlib,sys
d=json.loads(pathlib.Path(sys.argv[1]).read_text())
assert isinstance(d,dict)
assert type(d.get('available')) is bool
assert type(d.get('has_credentials')) is bool
PY
  rm -f "$temp"
  say AUTH_ENDPOINT=200_VALID_JSON
}
web_ok(){
  local temp code actual
  temp="$(mktemp)" || fail TEMP_FAILED
  code="$(curl -sS --max-time 12 --resolve "$DOMAIN:443:127.0.0.1" \
    -o "$temp" -w '%{http_code}' "https://$DOMAIN/" 2>/dev/null)" || {
      rm -f "$temp"; fail WEB_UNREACHABLE;
    }
  actual="$(sha256sum "$temp" | cut -d' ' -f1)"
  rm -f "$temp"
  [[ "$code" == 200 ]] || fail "WEB_HTTP_$code"
  [[ "$actual" == "$(digest "$LIVE")" ]] || fail WEB_INDEX_CONTENT_MISMATCH
  say WEB=200_MATCHED_INDEX
}
case "$*" in
  --rollback)
    [[ -d "$PREV" && -s "$PREV/index.html" && ! -L "$PREV" ]] || fail PREVIOUS_MISSING
    [[ "$(digest "$PREV")" == "$OLD_SHA" ]] || fail PREVIOUS_SHA_BAD
    [[ "$(digest "$LIVE")" == "$NEW_SHA" ]] || fail LIVE_NOT_CANDIDATE
    BAD="$WEB/.arena-authfix-rejected-$(date -u +%Y%m%dT%H%M%SZ)"
    [[ ! -e "$BAD" ]] || fail REJECTED_PATH_EXISTS
    mv -T "$LIVE" "$BAD" || fail MOVE_CANDIDATE_FAILED
    mv -T "$PREV" "$LIVE" || { mv -T "$BAD" "$LIVE" || true; fail RESTORE_FAILED; }
    say ROLLBACK=OLD_APP_RESTORED
    say "BAD_BUILD_PRESERVED=$BAD"
    say "OLD_INDEX_SHA256=$(digest "$LIVE")"
    web_ok
    # Rollback never depends on Brain availability, no bot mutation.
    say RESULT=RESTORED_ORIGINAL_APP
    ;;
  --activate)
    [[ "$(digest "$LIVE")" == "$OLD_SHA" ]] || fail ORIGINAL_APP_CHANGED
    [[ ! -e "$PREV" && ! -L "$PREV" ]] || fail PREVIOUS_BACKUP_ALREADY_EXISTS
    [[ -d "$SOURCE" && ! -L "$SOURCE" && -s "$SOURCE/index.html" ]] || fail CANDIDATE_MISSING
    [[ "$(digest "$SOURCE")" == "$NEW_SHA" ]] || fail CANDIDATE_SHA_CHANGED
    [[ -d "$SOURCE/static/js" ]] || fail CANDIDATE_JS_MISSING
    if grep -RlqF 'http://51.91.109.45:8002' "$SOURCE/static/js" --include='*.js'; then fail HTTP_FALLBACK_NOT_FIXED; fi
    for f in manifest.json service-worker.js; do
      [[ -s "$LIVE/$f" && -s "$SOURCE/$f" ]] || fail "PWA_FILE_MISSING_$f"
    done
    nginx -t >/dev/null 2>&1 || fail NGINX_INVALID
    brain_ok
    web_ok
    api_ok
    STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
    SAVED="$BACKUPS/arena-authfix-before-$STAMP"
    STAGED="$WEB/.arena-authfix-candidate-$STAMP"
    [[ ! -e "$SAVED" && ! -e "$STAGED" ]] || fail ALREADY_EXISTS
    mkdir -m 0700 "$SAVED"
    cp -a "$LIVE" "$SAVED/build"
    diff -qr "$LIVE" "$SAVED/build" >/dev/null || fail NEW_BACKUP_COMPARE_FAILED
    say "BACKUP_VERIFIED=$SAVED/build"
    cp -a "$SOURCE" "$STAGED"
    # Preserve the working PWA identity and its service worker policy.
    cp -a "$LIVE/manifest.json" "$LIVE/service-worker.js" "$STAGED/"
    if [[ -d "$LIVE/icons" ]]; then
      mkdir -p "$STAGED/icons"
      cp -a "$LIVE/icons/." "$STAGED/icons/"
    fi
    find "$STAGED" -type d -exec chmod 0755 {} +
    find "$STAGED" -type f -exec chmod 0644 {} +
    [[ "$(digest "$STAGED")" == "$NEW_SHA" ]] || fail STAGED_BUILD_SHA_BAD
    cmp -s "$LIVE/manifest.json" "$STAGED/manifest.json" || fail PWA_MANIFEST_CHANGED
    cmp -s "$LIVE/service-worker.js" "$STAGED/service-worker.js" || fail SERVICE_WORKER_CHANGED
    say PWA_IDENTITY_FILES=PRESERVED
    mv -T "$LIVE" "$PREV" || fail LIVE_MOVE_FAILED
    if ! mv -T "$STAGED" "$LIVE"; then
      mv -T "$PREV" "$LIVE" || true
      fail NEW_BUILD_MOVE_FAILED
    fi
    # Static and auth checks must both pass; auto-rollback otherwise.
    if ! ( web_ok && api_ok && brain_ok ); then
      REJECT="$WEB/.arena-authfix-auto-rejected-$STAMP"
      mv -T "$LIVE" "$REJECT" || true
      mv -T "$PREV" "$LIVE" || fail AUTO_ROLLBACK_FAILED
      say AUTO_ROLLBACK=TRUE
      exit 2
    fi
    say "NEW_INDEX_SHA256=$(digest "$LIVE")"
    say "ROLLBACK_READY=$PREV"
    say BRAIN_SERVICES_CHANGED=FALSE
    say ARENA_AI_STARTED=FALSE
    say TRIAL_14_DAYS_STARTED=FALSE
    say RESULT=SUCCESS_UI_ONLY
    ;;
  *) fail SPECIFY_ACTIVATE_OR_ROLLBACK ;;
esac
