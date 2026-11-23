#!/usr/bin/env bash
# Interfaccia Brain Unico (solo file statici) con backup verificato e rollback automatico. Stesso meccanismo del
# rilascio UI Arena del 18/11: non riavvia nginx ne' container; conserva manifest, service worker e icone della PWA
# (stessa app installata sul telefono). Da eseguire DOPO il cutover del backend (rotta /api/v3/brain/config attiva).
# Uso (root): 70-interfaccia.sh --activate --candidate <cartella build> --manifest-sha <sha256 di SHA256SUMS>
#             70-interfaccia.sh --rollback
set -Eeuo pipefail
IFS=$'\n\t'
MODE="${1:-}"; [[ $# -gt 0 ]] && shift
CAND=''; MSHA=''
while [[ $# -gt 0 ]]; do
  case "$1" in
    --candidate) CAND="${2:-}"; shift 2 ;;
    --manifest-sha) MSHA="${2:-}"; shift 2 ;;
    *) printf 'BRAIN_UI_REFUSED=UNKNOWN_ARGUMENT\n'; exit 2 ;;
  esac
done
DOMAIN="${BRAIN_UI_DOMAIN:-superbot-trading.duckdns.org}"
WEB="${BRAIN_UI_ROOT:-/opt/superbot-web}"
LIVE="$WEB/build"
PREV="$WEB/.brain-unico-webui-previous"
BACKUPS="${BRAIN_UI_BACKUPS:-/opt/superbot-v3-backups}"
UNITS="superbot-brain-unico-rc1-exit.service superbot-brain-unico-rc1-runner.service"

say(){ printf 'BRAIN_UI_%s\n' "$*"; }
fail(){ say "REFUSED=$1"; exit 2; }
digest(){ sha256sum "$1/index.html" | cut -d' ' -f1; }
[[ "${BRAIN_UI_TEST_MODE:-0}" == 1 || "$(id -u)" == 0 ]] || fail ROOT_REQUIRED
for c in curl sha256sum systemctl; do command -v "$c" >/dev/null || fail "TOOL_MISSING_$c"; done
[[ -d "$WEB" && ! -L "$WEB" && -s "$LIVE/index.html" && ! -L "$LIVE" ]] || fail LIVE_NOT_VERIFIED

fetch(){ curl -sS --max-time 12 --resolve "$DOMAIN:443:127.0.0.1" -o "$2" -w '%{http_code}' "$1" 2>/dev/null; }
code_of(){ local t c; t="$(mktemp)"; c="$(fetch "https://$DOMAIN$1" "$t" || echo 000)"; rm -f "$t"; printf '%s' "$c"; }
web_ok(){
  local t c a; t="$(mktemp)"; c="$(fetch "https://$DOMAIN/" "$t" || echo 000)"; a="$(sha256sum "$t" | cut -d' ' -f1)"; rm -f "$t"
  [[ "$c" == 200 && "$a" == "$(digest "$LIVE")" ]]
}
api_ok(){ [[ "$(code_of /api/auth/webauthn/status)" == 200 && "$(code_of /api/v3/brain/config)" == 401 ]]; }
units_ok(){ for u in $UNITS; do [[ "$(systemctl is-active "$u" 2>/dev/null || true)" == active ]] || return 1; done; }

case "$MODE" in
  --rollback)
    [[ -d "$PREV" && -s "$PREV/index.html" && ! -L "$PREV" ]] || fail PREVIOUS_MISSING
    BAD="$WEB/.brain-unico-webui-rejected-$(date -u +%Y%m%dT%H%M%SZ)"
    mv -T "$LIVE" "$BAD" || fail MOVE_CANDIDATE_FAILED
    mv -T "$PREV" "$LIVE" || { mv -T "$BAD" "$LIVE" || true; fail RESTORE_FAILED; }
    say "REJECTED_BUILD_PRESERVED=$BAD"
    web_ok || fail ROLLBACK_WEB_CHECK_FAILED_MANUAL_CHECK
    say RESULT=RESTORED_PREVIOUS_UI
    ;;
  --activate)
    [[ -n "$CAND" && -d "$CAND" && ! -L "$CAND" && -s "$CAND/index.html" && -s "$CAND/SHA256SUMS" ]] || fail CANDIDATE_MISSING
    [[ "$MSHA" =~ ^[0-9a-f]{64}$ ]] || fail MANIFEST_SHA_REQUIRED
    [[ "$(sha256sum "$CAND/SHA256SUMS" | cut -d' ' -f1)" == "$MSHA" ]] || fail MANIFEST_SHA_MISMATCH
    (cd "$CAND" && sha256sum --strict --quiet -c SHA256SUMS) || fail CANDIDATE_FILES_MISMATCH
    N_LISTED=$(wc -l < "$CAND/SHA256SUMS"); N_FILES=$(cd "$CAND" && find . -type f ! -name SHA256SUMS | wc -l)
    [[ "$N_LISTED" == "$N_FILES" ]] || fail CANDIDATE_HAS_UNLISTED_FILES
    [[ ! -e "$PREV" && ! -L "$PREV" ]] || fail PREVIOUS_BACKUP_ALREADY_EXISTS
    JS="$CAND/static/js"; [[ -d "$JS" ]] || fail CANDIDATE_JS_MISSING
    has(){ grep -RlqF --include='*.js' -- "$1" "$JS"; }
    if has 'http://51.91.109.45:8002'; then fail HTTP_FALLBACK_PRESENT; fi
    for s in '/api/v3/brain/status' '/api/v3/brain/close' 'BRAIN UNICO' '/api/auth/login' '/api/auth/webauthn/status'; do
      has "$s" || fail "CANDIDATE_WITHOUT_$s"
    done
    for f in manifest.json service-worker.js; do [[ -s "$LIVE/$f" ]] || fail "PWA_FILE_MISSING_$f"; done
    [[ -d "$BACKUPS" && ! -L "$BACKUPS" ]] || fail BACKUPS_DIR_MISSING
    units_ok || fail BRAIN_UNICO_UNITS_NOT_ACTIVE
    web_ok || fail WEB_NOT_HEALTHY_BEFORE
    api_ok || fail BACKEND_NOT_ON_BRAIN_UNICO
    STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
    SAVED="$BACKUPS/brain-unico-webui-before-$STAMP"; STAGED="$WEB/.brain-unico-webui-candidate-$STAMP"
    [[ ! -e "$SAVED" && ! -e "$STAGED" ]] || fail ALREADY_EXISTS
    mkdir -m 0700 "$SAVED"
    cp -a "$LIVE" "$SAVED/build"
    diff -qr "$LIVE" "$SAVED/build" >/dev/null || fail BACKUP_COMPARE_FAILED
    say "BACKUP_VERIFIED=$SAVED/build"
    cp -a "$CAND" "$STAGED"
    rm -f "$STAGED/SHA256SUMS"
    cp -a "$LIVE/manifest.json" "$LIVE/service-worker.js" "$STAGED/"
    if [[ -d "$LIVE/icons" ]]; then mkdir -p "$STAGED/icons"; cp -a "$LIVE/icons/." "$STAGED/icons/"; fi
    chown -R root:root "$STAGED" 2>/dev/null || true
    find "$STAGED" -type d -exec chmod 0755 {} +
    find "$STAGED" -type f -exec chmod 0644 {} +
    cmp -s "$LIVE/manifest.json" "$STAGED/manifest.json" || fail PWA_MANIFEST_CHANGED
    cmp -s "$LIVE/service-worker.js" "$STAGED/service-worker.js" || fail SERVICE_WORKER_CHANGED
    say PWA_IDENTITY_FILES=PRESERVED
    mv -T "$LIVE" "$PREV" || fail LIVE_MOVE_FAILED
    if ! mv -T "$STAGED" "$LIVE"; then mv -T "$PREV" "$LIVE" || true; fail NEW_BUILD_MOVE_FAILED; fi
    if ! ( web_ok && api_ok && units_ok ); then
      REJECT="$WEB/.brain-unico-webui-auto-rejected-$STAMP"
      mv -T "$LIVE" "$REJECT" || true
      mv -T "$PREV" "$LIVE" || fail AUTO_ROLLBACK_FAILED
      say AUTO_ROLLBACK=TRUE
      say "REJECTED_BUILD_PRESERVED=$REJECT"
      exit 2
    fi
    say "NEW_INDEX_SHA256=$(digest "$LIVE")"
    say "ROLLBACK_READY=$PREV"
    say RESULT=SUCCESS_UI_BRAIN_UNICO
    ;;
  *) fail SPECIFY_ACTIVATE_OR_ROLLBACK ;;
esac
