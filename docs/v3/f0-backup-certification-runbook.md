# SuperBot V3 — F0 backup certification (OFFLINE ONLY)

Status: **implementation and tests prepared; user-data certification NOT DONE**. This runbook cannot replace a trusted external backup.

## Purpose and prerequisites

Certify that the historical Brain SQLite database and the Falco/Toro run archives survive a consistent capture, independent restore, and exact source-to-copy comparison, without changing live bots or rewriting trade history.

Before capture: verify that **all trading services are stopped**, establish the authoritative source paths and the exact host identity, and use an OS-restricted operator account. A prior audit showing services stopped is not current evidence. The old GitHub SSH-root workflow was removed from the V3 branch and MUST NOT be reused. No deployment, V3 import, portfolio reset, exchange access, or restart belongs to F0.

Do not treat `PRAGMA integrity_check=ok` or an absent WAL file as proof that a raw file copy includes all committed transactions. SQLite `immutable=1` can ignore a WAL from which transactions have not been checkpointed.

## Brain: independent source observation and consistent copy

Module: `backend/v3/backup_certification.py`.

1. On the authoritative **stopped** Brain database, obtain a separately retained source observation with `observe_brain_source_readonly(source_db)`. It returns `event_count`, `max_event_seq`, `events_sha256`, and `state_sha256`. Record its exact bytes/hash outside the VPS and outside the destination backup. This step opens SQLite in normal read-only mode, NOT immutable mode, so it can observe committed WAL content. The source must be accessible in read-only mode; the operator must verify at the OS level that the source is an allowed snapshot.
2. Run `capture_brain_copy(source_db, new_snapshot_directory)` ONLY in an isolated lab or safely stopped capture environment. The destination must not exist. It uses SQLite's `Connection.backup()`, holds a source observation, confirms the copied data and a second source observation match, fsyncs the destination, and publishes `manifest.json` last. Never use a raw `cp brain.sqlite3` in place of the backup API when WAL may exist.
3. Save `manifest_sha256` from the returned receipt outside the copy, via a trusted independent channel. Do not consider the embedded manifest an independent witness of itself.
4. Transfer the directory, with its `brain.sqlite3` and `manifest.json`, to **different storage/machine** using encryption and integrity-preserving tools. Test restoration into a new isolated directory, not alongside the original DB.
5. In that restored directory invoke `verify_brain_offhost(..., expected_manifest_sha256=..., expected_events_sha256=..., expected_event_count=..., expected_max_event_seq=...)`, supplying values stored independently in steps 1 and 3. It re-opens the *captured* DB in immutable/read-only mode, checks SQLite integrity, row contents, state, SHA-256 database bytes, and external values. Anything missing/mismatched is **FAIL CLOSED**.

Example application-side usage (only on authorized, stopped/offline source paths, **not** a ready-to-run VPS command):

```python
from v3.backup_certification import (
    observe_brain_source_readonly, capture_brain_copy, verify_brain_offhost
)

source = "/offline/input/brain.sqlite3"
independent = observe_brain_source_readonly(source)
# Preserve independent externally BEFORE making the capture.
receipt = capture_brain_copy(source, "/offline/output/new-brain-f0")
# Preserve receipt.manifest_sha256 in a DIFFERENT trusted location.
# Following a genuine encrypted off-host transfer and restore:
verified = verify_brain_offhost(
    "/restored/brain-f0",
    expected_manifest_sha256=receipt.manifest_sha256,
    expected_events_sha256=independent["events_sha256"],
    expected_event_count=independent["event_count"],
    expected_max_event_seq=independent["max_event_seq"],
)
```

For stronger provenance, retain the external witness with date, host, stopped-service confirmation, backup snapshot ID, operator identity and checksum in a separately access-controlled record. **The code cannot authenticate these real-world assertions.**

## Falco/Toro: file-level witness and archive consistency

Module: `backend/v3/f0_classic_certificate.py`.

- On the stopped, authoritative source run directory (including `archive/*`), call `observe_classic_source_readonly(directory, "hawk")` and likewise for `"bull"`.
- Preserve `files_sha256`, `total_closed`, `historical_run_count` and `current_run` separately from the backup. `files_sha256` binds the current state/history/learning and the archived `state_v2.json`, `trade_history.jsonl` and `summary.json` files.
- After encrypted off-host backup and restoration, call `verify_classic_offhost(restored_directory, portfolio_id, expected_files_sha256=..., expected_total_closed=..., expected_historical_runs=..., expected_current_run=...)`.
- It rechecks every archived run, per-run cash and P&L, cumulative close matching, current cash/margin and external file witness. Missing or changed archives FAIL CLOSED.
- Positions left open in the paused snapshot remain historical OPEN records; do not fabricate exit prices or claim a new mark-to-market equity.

## Certification gate (everything required)

| Criterion | Required to mark F0 certified? |
| --- | --- |
| Current services stopped, source paths authenticated, minimal OS permissions | YES |
| Brain capture via SQLite backup API with source observation and WAL visibility | YES |
| Capture output manifest SHA-256 and independent source-side event digest/count/seq | YES |
| Falco/Toro source-side file manifest, all run summaries reconciled | YES |
| Encrypted copy on an independent host/storage, tested successful restore | YES |
| Independent off-host verification matches **all** source witnesses | YES |
| Private backups, original logs and AI memory remain untouched | YES |
| No PR merge or runtime deployment, no real-data import until explicit next gate | YES |

Current status remains **NO-GO**. Test fixtures are synthetic, even if Python 3.10/3.11 CI is green. The previously mentioned local backup path and earlier Brain count (8,447) do not prove that an omitted WAL was never present. Do not claim data loss or complete preservation solely from that number.

## Security notes

- The old SSH-root GitHub Actions workflow and trigger have been removed from this branch, but **no key rotation or audit of every other credential/pipeline is attested**. Before automated VPS access, require OS-enforced least privilege, a restricted command and host-key validation, with a separate approval.
- The source-side SQLite read may require existing WAL/-shm coordination. Run only in the approved stopped snapshot environment and verify permissions/filesystem side effects separately; do not claim it cannot update any sidecar under all operating modes.
- Existing evidence files should not include API keys, individual AI prompts, exchange secrets, or personal identifiers.
- The independent SHA witness proves exact match only if its origin/authenticity is genuinely independent and trusted. It is not a digital signature.
- Final F0 acceptance is a **separate user-approved operation**, not automatically triggered by pushes or by a green CI badge.


### Memory-file preservation gate (classics)

F0 classic witnesses include, in addition to the trade ledger and `archive/*`, the mandatory `lessons.md` and the optional `errors.md` (its absence is itself bound into the witness). A restored backup missing or altering the lessons file fails verification. These documents are **preserved as bytes**, not yet parsed or imported into the new AI structured memory. Brain's SQLite verification covers the database only: any additional Brain files or AI memory outside `brain.sqlite3` require a separate inventory and backup contract before declaring the complete Brain memory protected.
