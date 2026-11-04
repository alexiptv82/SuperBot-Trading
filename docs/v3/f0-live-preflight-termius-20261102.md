# SuperBot V3 — F0 preliminary live VPS inspection (READ-ONLY)

## Status

The Python preflight tool `backend/v3/f0_host_preflight.py` and synthetic tests are implemented on draft PR #29. It only checks metadata and known worker status; it does not use SSH itself, open the SQLite DB, copy the files, change wallet state or stop containers. No live result has been obtained.

**Do not run the preflight from GitHub Actions with the old root SSH key.** Use an operator-approved console on the Singapore VPS and share sanitized results privately.

## Compact first-pass command for Termius

Use the following shell block, which executes only standard read-only listing/status commands (no code downloaded from GitHub):

```bash
printf '\n=== SUPERBOT: CONTAINER ATTIVI ===\n'
docker ps --format '{{.Names}} | {{.Status}}' | grep -Ei 'superbot|hawk|bull|brain|pool|turbo|sidecar|shadow|deepseek' || true
printf '\n=== SERVIZI SYSTEMD ATTIVI ===\n'
systemctl list-units --type=service --state=running --no-pager --no-legend | grep -Ei 'superbot|brain|pool|shadow|deepseek' || true
printf '\n=== FILE BRAIN (SOLO NOMI E DIMENSIONI) ===\n'
for f in /opt/superbot-brain-free/brain.sqlite3 /opt/superbot-brain-free/brain.sqlite3-wal /opt/superbot-brain-free/brain.sqlite3-shm /opt/superbot-brain-free/learning_log.jsonl /opt/superbot-brain-free/lessons.md; do
  if [ -f "$f" ]; then stat -c '%n | %s byte' "$f"; else printf '%s | ASSENTE\n' "$f"; fi
done
printf '\n=== CLASSICI: MEMORIA E ARCHIVI ===\n'
for p in hawk bull; do
  d="/opt/superbot-desk-data/$p"
  for f in state_v2.json trade_history.jsonl learning_log.jsonl lessons.md; do
    [ -f "$d/$f" ] && printf '%s/%s PRESENTE\n' "$p" "$f" || printf '%s/%s ASSENTE\n' "$p" "$f"
  done
  if [ -d "$d/archive" ]; then
    printf '%s/archive directory presenti: ' "$p"
    find "$d/archive" -mindepth 1 -maxdepth 1 -type d | wc -l
  else printf '%s/archive ASSENTE\n' "$p"; fi
done
printf '\nF0_PRIMO_CONTROLLO_COMPLETATO\n'
```

This preliminary output cannot confirm that *all* processes are stopped. It only shows named containers and units. It does not prove that the historical backup includes WAL, and it does not inspect secret contents. An explicit admin attestation of the stopped host and the authoritative filesystem paths is required before capture.

## Full script preflight (after review and operator authorization)

The reviewed Python helper `backend/v3/f0_host_preflight.py` includes more detailed metadata checks: symlinks, missing `lessons.md`, WAL/-SHM/-journal sizes, archive entries, candidate supplementary Brain memory files and conservative blocking if Docker/systemd status cannot be obtained. It must be run manually from a trusted pinned revision, not piped from a mutable GitHub branch into a privileged shell.

## After a successful preflight

1. Obtain and review service-stopped attestation and source permissions without changing any worker settings.
2. Provision a dedicated least-privileged local operator account for F0 with explicit human authorization. No sudo or Docker group.
3. Record original Brain source COUNT/MAX(seq)/event SHA in a separate trusted record, capturing WAL-aware SQLite through the backup API only after stopped status is fresh.
4. Observe Falco/Toro including current cash, all historical archives, `lessons.md`, and optional `errors.md`.
5. Perform an encrypted independent off-VPS transfer and restore; compare the restored copies against the source witnesses.
6. Only then review F0 PASS/FAIL with Claude/Grok, and later request separate consent to import data into the isolated V3 memory.

## Hard NO-GO

No SSH-root workflow, new service restart, portfolio reset, PR merge, real data import, or secret rotation without a separate reviewed plan. The last automated 105 tests on synthetic data do not certify an authentic off-VPS backup.
