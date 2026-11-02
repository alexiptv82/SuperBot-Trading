# SuperBot V3 — F0 operator access gate (NOT YET ENABLED)

## Why there is no automatic VPS run

The previous V3 GitHub Actions workflow could send arbitrary branch Python over SSH as `root`, so it was removed from the V3 branch. **Other earlier workflows still exist and use the Singapore root SSH key**, including:

- `.github/workflows/sg-extbackup-watch.yml`: daily backup-status read over `root@...`, using the shared `SINGAPORE_SSH_PRIVATE_KEY`.
- `.github/workflows/v3-vps-inventory.yml`: diagnostic read over `root@...`.
- `.github/workflows/v3-stop-paper-workers.yml`: privileged maintenance/shutdown command via `root@...` (it is not appropriate as an F0 read/capture tool).
- Legacy deploy/diagnostic workflows must be inventoried separately before reuse. **Removing the V3 workflow did not revoke the existing SSH key or disable these jobs.**

This is a code inspection finding, not a live credential or VPS permission audit. Do not print, copy, re-publish, or transmit the private key in the repository or this document.

## Minimal access design for F0

**The safest initial path is a human-authorized local capture on a stopped machine, followed by independent off-host verification.** Do not add an SSH automation until the following constraints are met:

1. A dedicated operating-system account `superbot-f0`, **not root**, without `sudo`, Docker-group membership, writable code directories, or the ability to invoke shell commands supplied by GitHub branches.
2. Grant only read access to the narrowly identified **stopped PAPER source files** plus WAL sidecars where present, and write access to a separate empty F0 output directory. Do not grant write access to legacy source directories, wallet configurations, application binaries, API secrets, or trading sockets.
3. Identify the exact Brain SQLite file and classic run directories with the operator. Require an explicit, fresh service-stopped check performed locally by an authorized administrator. Do not infer this from old screenshots or old GitHub job logs.
4. Source witness first: obtain count/max sequence/event digest from the original Brain database with WAL visibility; obtain complete file+archive witnesses from Falco and Toro. Store witness copies outside the VPS with authenticated provenance.
5. A new destination directory receives a copy produced by SQLite backup API, never an overwrite of legacy. Encrypt and copy the snapshot to an independent host/store, then restore and verify with the external witnesses.
6. A future SSH key, if needed, must be *separate* from the old root/deploy key, authorized to run only a fixed, reviewed helper (forced command, no port/agent/X11 forwarding, no PTY). Use host-key pinning and narrowly scoped GitHub permissions. Do not allow `bash -s`, `python3 -` or arbitrary commands from a mutable branch.
7. Request explicit authorization for the one-time credential/ACL provisioning. Once verified, record the new account scope and test both allowed and denied operations. Rotate/revoke prior keys separately with an appropriate rollback plan; changing keys without a rollback plan can break backups/alerts.

**No automatic F0 workflow has been created.** A stopped-service certificate, real backup hash, off-VPS encrypted copy and independent restored check are all still missing.

## Human-operated offline CLI (no SSH)

Run from a trusted, reviewed checkout with `PYTHONPATH=backend`, on an already stopped source or independently restored copy. The commands below are templates only; `/offline/...` paths must be replaced after a fresh source inventory.

```bash
# Brain source observation — preserve stdout as independent evidence.
PYTHONPATH=backend python3 -m v3.f0_cli observe-brain \
  --source /offline/input/brain.sqlite3

# Brain capture (writes ONLY to new output directory).
PYTHONPATH=backend python3 -m v3.f0_cli capture-brain \
  --source /offline/input/brain.sqlite3 \
  --new-directory /offline/output/brain-f0-new

# AFTER a real encrypted off-host transfer and restore:
PYTHONPATH=backend python3 -m v3.f0_cli verify-brain \
  --restored-directory /offhost/restored/brain-f0-new \
  --external-witness /independent-evidence/brain-source.json \
  --external-manifest-sha256 <trusted-64-hex-hash>

# Repeat for classic portofolios, first observing, then verifying
# against independently retained witness files:
PYTHONPATH=backend python3 -m v3.f0_cli observe-classic \
  --source /offline/input/hawk --portfolio hawk
PYTHONPATH=backend python3 -m v3.f0_cli observe-classic \
  --source /offline/input/bull --portfolio bull
PYTHONPATH=backend python3 -m v3.f0_cli verify-classic \
  --restored-directory /offhost/restored/hawk \
  --portfolio hawk --external-witness /independent-evidence/hawk-source.json
```

Use output redirection to retain the source observation *outside* the backup; never treat a witness stored only inside the backup as independent. The example is not a claim that a local directory is an off-host backup. Keep evidence access-controlled, avoiding AI prompts/API keys in logs.

## What constitutes F0 PASS

An operator with restricted access verifies the current stopped state, authenticates the source paths, records witnesses outside the VPS, captures Brain with committed WAL content, validates Falco/Toro archives, produces an encrypted off-VPS copy, restores it elsewhere and passes the separate source-witness verifier. A reviewer checks the evidence without seeing secrets. Only then may we label F0 certified.

Until then: **NO-GO for real historic import**, PR #29 remains DRAFT, all PAPER wallets unchanged, and no runtime/deploy approval is implied.
