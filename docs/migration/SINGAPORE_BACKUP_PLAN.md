# Singapore migration: backup and rollback gates

Status: PLAN ONLY. No migration or backup execution authorized by this document.

## Verified from read-only inventory (2026-10-17)
- Old VPS: 51.91.109.45, shared with HI-TV. Never stop/restart host, Docker daemon or HI-TV.
- Destination: 51.79.205.82, Ubuntu 24.04.4, Docker 29.1.3.
- Hawk bind mount: /opt/superbot-desk-data/hawk -> /app/data/desk/hawk.
- Bull bind mount: /opt/superbot-desk-data/bull -> /app/data/desk/bull.
- Main app data: /opt/superbot/data -> /app/data; contains superbot.db.
- Hawk/Bull: state_v2.json, trade_history.jsonl, learning_log.jsonl, heartbeat.json, macro_events.json, lessons.md, archive/, and other files.
- Additional source configuration and mounts must be inventoried before final cutover. Do not publish or log .env contents.

## Mandatory gates before transfer
1. Confirm bot writers and exact storage semantics from code. Check whether superbot.db uses SQLite and whether WAL files exist. Determine safe consistent snapshot method for JSON/JSONL plus DB.
2. Define secret-handling, secure transfer, file ownership and permissions. No credentials in GitHub logs or artifacts.
3. Create an initial recoverable snapshot without stopping HI-TV; verify archive checksums, file counts, JSON parsing, JSONL parsing, database integrity where applicable, and a restore rehearsal on an isolated destination directory. A copy alone is not a verified backup.
4. Prepare destination containers and configuration without enabling trading/schedulers; confirm networking and health checks.
5. At explicit cutover approval, stop ONLY the relevant bot writers, confirm quiescence, take final consistent snapshot and record hashes; leave HI-TV running.
6. Restore and verify data on Singapore, then start ONLY destination bots and verify paper mode, exchange/API permissions, state, open paper positions, scheduler uniqueness and absence of double execution.
7. Preserve untouched source data and rollback path. If verification fails, stop destination bot writers before resuming old ones.

## Prohibited before explicit cutover
- Starting a second active Hawk/Bull instance
- Resetting or deleting state/history
- Restarting Docker daemon on shared old VPS
- Publishing secrets or copying .env into workflow logs
- Assuming live JSON/JSONL file copy is an atomic consistent backup

## Second code-review findings (2026-10-17)
- backend/desk/cli.py selects Hawk/Bull data directory using DESK_DATA_DIR and DESK_PORTFOLIO; confirm actual runtime env by redacted checks before migration.
- backend/desk/learning.py documents learning_log.jsonl as append-only, persistent across portfolio resets. Never reset or truncate it.
- backend/desk/brain.py appends closed trades to trade_history.jsonl; preserve history in full.
- Existing .github/workflows/desk-snapshot.yml archives Hawk/Bull while running and checks only state_v2.json parseability; that does NOT establish a consistent multi-file snapshot. Do not trigger it as a migration-quality backup.
- Existing .github/workflows/deploy.yml contains a SQLite backup path for superbot.db, with fallback raw copy. Validate DB consistency with SQLite backup API and integrity_check; do not assume a raw copy is valid.
- No evidence yet of a successful restored backup. Do not claim recovery readiness.
