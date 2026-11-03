# SuperBot F0 — 2026-11-03 — SSH secret malformed on rerun; F0B64 fix PR #31 ready, tests pass

## Re-test actually performed by ChatGPT

User confirmed `SUPERBOT_F0_SSH_PRIVATE_KEY` updated directly in GitHub after generating a new dedicated Ed25519 key on VPS. Instead of requesting another manual workflow dispatch, the assistant successfully reran failed GitHub Actions job via `mcp__GitHub__rerun_workflow_job` for original job `125738820686` run `41582026933`; connector returned `success:true` for the request to rerun.

New job `125743007163` completed `conclusion=failure`. Directly inspected log lines at `2026-11-03T05:20:35Z`:
```
Load key "/tmp/.../id_ed25519": error in libcrypto
Process completed with exit code 255.
```
The failure is on `ssh-keygen -y -f`, **before SSH**. No VPS command executed and no effect on trading or data. Secret actual value not visible to ChatGPT.

## Correction prepared — PR #31, no merge or live SSH test

- New branch `work/f0-secret-b64-key-fix-20261103` from main.
- [PR #31](https://github.com/alexiptv82/SuperBot-Trading/pull/31), `mergeable:true`, HEAD SHA `01d57af47a900796d30ba2d38cbffc4cb1e8b26d`, still OPEN, not merged.
- Workflow `.github/workflows/f0-restricted-status.yml` supports exact one-line prefix `F0B64:` containing Base64-encoded dedicated private key, restoring binary bytes to ephemeral file. Maintains multiline OpenSSH compatibility with CRLF normalization; verifies header/footer and parses with `ssh-keygen -y -P ''` without echoing key.
- `ops/f0/README.md` documents **operator-run** local command `printf 'F0B64:'; base64 -w0 /root/superbot-f0-setup/github-f0-ed25519; printf '\\n'` to display single-line secret for direct GitHub Actions Secrets paste. Base64 is NOT encryption and must never be posted in chat/screenshot, issue, PR or history. Temp private file on VPS must be removed separately *after* successful verification.
- Updated `.github/workflows/f0-restricted-tests.yml` for syntax lint of the actual status workflow shell and synthetic Ed25519 OpenSSH Base64 encode/decode roundtrip.
- CI run [41583708908](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/41583708908): `SUCCESS`, 8 unit tests PASS plus key roundtrip and workflow script syntax verification.

## Next gates
User authorization required to merge **PR #31 only** into main. After merge, user must update the existing GitHub secret `SUPERBOT_F0_SSH_PRIVATE_KEY` with one-line F0B64 string directly (private, never send to ChatGPT). ChatGPT can rerun failed job itself and read logs for connection attempts. Check forced-command/SSH tests before declaring active. No superbot runtime, wallet, F0 offhost backup or V3 PR #29 changes made.
