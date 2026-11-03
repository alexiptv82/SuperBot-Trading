# SuperBot V3 — 2026-11-03 — F0 remote diagnostics follow-up and external backup reuse analysis

## Current facts verified on GitHub

1. PR #29 V3 remains DRAFT, `merged:false`; no runtime deploy or wallet reset.
2. Restricted F0 GitHub/VPS SSH diagnostic is already working: Actions [run 41596313485](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/41596313485) success with remote JSON `OBSERVATION_ONLY`. Brain `brain.sqlite3` 469327872 bytes, WAL 4309552 bytes. Hawk/Bull parent directory `PRESENT`, but `state_v2.json`, `trade_history.jsonl`, `learning_log.jsonl`, `lessons.md`, archive `UNAVAILABLE` to `superbot-f0`. Previous root observations showed those files present. Diagnosis: probable directory traverse/ACL permissions; **not proof of file deletion**. Existing `processes.NO_NAME_MATCH` is NOT a complete fuser/stop-state certificate.
3. Prepared independent **DRAFT PR #32** `work/f0-classic-metadata-acl-20261103`, [PR #32](https://github.com/alexiptv82/SuperBot-Trading/pull/32), no merge. Script `ops/f0/classic_metadata_acl.sh` defaults `--check` with no changes, and `--apply` requires explicitly running as local admin (never via restricted SSH), granting **only** `user:superbot-f0:--x` on Hawk and Bull source directories. Validates exact locations/file existence/symlink, privilege groups, masks, stores original root-only ACL and rolls back on failed post-test. No file read rights, recursive chmod, Docker/sudo/root-SSH permissions. Requires `getfacl`/`setfacl` present (does not install). `ops/f0/README.md` updated with limited procedure and recorded live SSH success. No changes have been made on VPS by this PR.
4. CI [run 41598191790](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/41598191790): **SUCCESS**, Bash syntax, non-root fail-closed apply, 8 existing Python tests and Base64 SSH tests.

## Key discovery: EXISTING encrypted off-host backup infrastructure

The repo already has `.github/workflows/sg-extbackup-watch.yml`, a scheduled GitHub Actions sentinel for an off-server encrypted `age` backup, reading `/opt/superbot-extbackup/status.json` through a **legacy root SSH key** `SINGAPORE_SSH_PRIVATE_KEY`, checking last success within 36h, and notifying via Telegram on failure or staleness. We did **not** rerun/change this privileged workflow.

The last matching GitHub Actions [run 41447751395](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/41447751395) at 2026-11-02 12:48:53 UTC was `success`; job log reported:
`OK ultimo backup esterno riuscito 2026-11-02T03:28:45Z (9.3 ore fa): superbot-backup-20261102T032845Z.tar.gz.age`.

This proves only the **existing sentinel's reported status**, not archive content, independent offhost actual storage, encryption recipient/key recoverability, time retention, inclusion of the 8,447 Brain events and 534 classic trade closures, preserved lessons, or a tested restore matching source hashes. It **does not** meet F0 certification. Existing backup script `external_backup.py` lives at `/opt/superbot-extbackup` per repo comments but its contents/provider/manifest are not yet independently verified. Need safely inspect the backup system through an approved restricted fixed-command or operator audit before deciding to reuse the mechanism; never fall back to arbitrary root SSH Actions.

## Next steps / gates
- Review PR #32 CI and approve separately before any merge; apply ACL `--x` only after new explicit user authorization and trusted pinned script review.
- Audit actual existing encrypted external backup pipeline, recipient, destination, manifest and restore procedure without revealing keys. Determine whether the already captured Brain F0 local snapshot `/opt/superbot-v3-backups/f0-brain-20261103T035500Z` and classic histories can be transferred through existing storage infrastructure with independent witnesses.
- Protect temporary dedicated F0 private key `/root/superbot-f0-setup/github-f0-ed25519` generated on VPS; after verified SSH success, propose one-time secure cleanup/rotation. Do not print or store private key in chat.
- Before any Brain/Falco/Toro V3 historic import: encrypted independent offhost copy + restore + source witness verification, separately approved. Portfolio reset/deployment still prohibited.
