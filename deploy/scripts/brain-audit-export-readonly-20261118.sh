#!/usr/bin/env bash
# Brain storico PAPER — esportazione in SOLA LETTURA per l'audit del peggioramento (18/11/2026).
# Non ferma, non riavvia, non modifica nulla del Brain, dei servizi uscite o dell'Arena. Nessuna chiave stampata.
# Scrive SOLO in /root/brain-audit-<ora>/ (0700) e in una cartella temporanea.
#   bash brain-audit-export-readonly-20261118.sh --sha <40hex del commit con journal_export.py>
set -uo pipefail
umask 077
SHA=''
[[ "${1:-}" == "--sha" ]] && SHA="${2:-}"
[[ "$SHA" =~ ^[0-9a-f]{40}$ ]] || { echo 'BRAIN_EXPORT REFUSED=SHA_REQUIRED'; exit 2; }
RUN_ID="${BRAIN_RUN_ID:-brain-v3-paper20261111}"
RUN="/opt/superbot-v3-paper-runs/$RUN_ID"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="${BRAIN_EXPORT_DIR:-/root}/brain-audit-$TS"
say(){ echo "BRAIN_EXPORT $*"; }
redact(){ sed -E 's/(sk-[A-Za-z0-9_-]{6})[A-Za-z0-9_-]+/\1***REDACTED***/g; s/((KEY|TOKEN|SECRET|PASSWORD)[A-Za-z0-9_]*[=:][[:space:]]*)[^[:space:]"]+/\1***REDACTED***/Ig'; }
[[ -d "$RUN" && -f "$RUN/journal.db" ]] || { say "REFUSED=RUN_NOT_FOUND"; exit 2; }
mkdir -m 0700 "$OUT" || { say 'REFUSED=OUTPUT_EXISTS'; exit 2; }

{
echo "## utc=$TS run_id=$RUN_ID"
for u in superbot-v3-paper-brain-runner superbot-v3-paper-brain-exit superbot-v3-paper-single-close-bridge; do
  echo "### unit $u"
  systemctl show "$u" -p ActiveState -p SubState -p MainPID -p NRestarts -p ActiveEnterTimestamp -p WorkingDirectory -p ExecStart -p FragmentPath 2>/dev/null | redact
  pid="$(systemctl show -p MainPID --value "$u" 2>/dev/null)"
  if [[ -n "$pid" && "$pid" != 0 && -d "/proc/$pid" ]]; then
    echo "proc_cwd=$(readlink "/proc/$pid/cwd")"
    echo "proc_cmdline=$(tr '\0' ' ' < "/proc/$pid/cmdline" | redact)"
    echo "proc_python=$(readlink "/proc/$pid/exe") $("$(readlink "/proc/$pid/exe")" -c 'import sys;print(sys.version.split()[0])' 2>/dev/null)"
    tr '\0' '\n' < "/proc/$pid/environ" 2>/dev/null | grep -E '^(DESK_MODE|TRADING_MODE|PYTHONPATH|V3_[A-Z0-9_]+)=' | grep -viE 'KEY|TOKEN|SECRET|PASSWORD' | sed 's/^/proc_env /'
    echo "proc_env_names=$(tr '\0' '\n' < "/proc/$pid/environ" 2>/dev/null | cut -d= -f1 | sort | xargs)"
  fi
done
} > "$OUT/running-units.txt" 2>&1
say "unita_lette=$(grep -c '^### unit' "$OUT/running-units.txt")"

# Cartelle di codice usate dai processi (cwd + PYTHONPATH): SHA, file modificati, diff con oscuramento
dirs="$(grep -hoE '^(proc_cwd=|proc_env PYTHONPATH=)[^ ]+' "$OUT/running-units.txt" | sed -E 's/^(proc_cwd=|proc_env PYTHONPATH=)//' | tr ':' '\n' | sort -u)"
{
for d in $dirs; do
  [[ -d "$d/.git" ]] || { echo "### $d (non git)"; continue; }
  echo "### $d"
  echo "head=$(git -C "$d" rev-parse HEAD) branch=$(git -C "$d" rev-parse --abbrev-ref HEAD)"
  git -C "$d" status --porcelain
  git -C "$d" status --porcelain | awk '{print $2}' | while read -r f; do
    [[ -f "$d/$f" ]] && echo "sha256 $(sha256sum "$d/$f")"
  done
  echo "#### diff"
  git -C "$d" diff -- '*.py' '*.json' | redact
done
} > "$OUT/running-code.txt" 2>&1
say "codice=$(grep -c '^### ' "$OUT/running-code.txt") cartelle"

# Config effettiva (percorso preso dalla riga di comando del runner) e policy di uscita
cfg="$(grep -A0 -m1 -oE -- '--config [^ ]+' "$OUT/running-units.txt" | awk '{print $2}')"
{
  for f in "${cfg:-$RUN/runner_config.json}" $(for d in $dirs; do echo "$d/backend/v3/runner/exit_policy.json $d/backend/v3/brain_market/market_view_params.json"; done); do
    [[ -f "$f" ]] || continue
    echo "### $f sha256=$(sha256sum "$f" | cut -c1-64)"
    redact < "$f"; echo
  done
} > "$OUT/effective-config.txt" 2>&1
say "config_file=$(grep -c '^### ' "$OUT/effective-config.txt")"

# Esportazione del journal (copia coerente in temporaneo, nessuna scrittura nella run)
tmpd="$(mktemp -d)"
if curl -fsSL "https://raw.githubusercontent.com/alexiptv82/SuperBot-Trading/$SHA/research/brain_guardian/journal_export.py" -o "$tmpd/journal_export.py"; then
  say "export_tool_sha256=$(sha256sum "$tmpd/journal_export.py" | cut -c1-64)"
  /usr/bin/python3 -I "$tmpd/journal_export.py" --run-dir "$RUN" --run-id "$RUN_ID" --out "$OUT/journal-export.json"
else
  say 'ERRORE=DOWNLOAD_EXPORT_TOOL'
fi
rm -rf "$tmpd"
for f in "$OUT"/*; do sha256sum "$f"; done > "$OUT/SHA256SUMS"
tar -C "$(dirname "$OUT")" -czf "$OUT.tar.gz" "$(basename "$OUT")" && chmod 0600 "$OUT.tar.gz"
say "pacchetto=$OUT.tar.gz dimensione=$(stat -c %s "$OUT.tar.gz") sha256=$(sha256sum "$OUT.tar.gz" | cut -c1-64)"
say "NESSUN_SERVIZIO_TOCCATO=TRUE NESSUNA_SCRITTURA_NELLA_RUN=TRUE"
