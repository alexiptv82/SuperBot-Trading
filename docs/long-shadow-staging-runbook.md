# LONG Shadow — Staging Read-Only Runbook

Status: development branch only. No deploy, no merge, no PAPER trading or broker access.

## Prepared components

- GET /api/long/shadow requires an authenticated session, Cache-Control no-store, and has no POST equivalent.
- backend/long_shadow_readonly.py reads the classic Hawk and Bull wallets from state_v2.json and heartbeat.json, validating account identity, timestamp freshness and existing LONG/SHORT flags; missing or stale is unavailable, never an empty portfolio.
- Brain sqlite reader is explicitly gated by source kind (pilot or free) and readonly mode; source selection has not been confirmed for live runtime.
- frontend/src/pages/LongShadowDashboard.js displays each account separately and marks any CANDIDATE as non-executable. The link appears in the PAPER Dashboard.
- backend/long_shadow_capture_context.py extracts observed startup MTF snapshots and bid/ask from the 15-minute Bitget capture after checking file and frame SHA. Historical candles become available at the actual snapshot receipt, not retroactively at candle close.

## Not yet implemented or tested

- No H24 live worker or continuous feed has been installed. The GET endpoint does not run LONG V6.1.1 or generate trade signals.
- No record writer or dashboard end-to-end runtime validation; any external advice record remains explicitly unverified.
- No 1H/4H live rollover validation, real execution economics or PAPER eligibility.
- Branch CI workflow exists and covers Python reader, snapshot contracts, React rendering and build, but GitHub Actions results have not yet been confirmed. Do not label CI green.

## Safety guarantees

- No change to LONG V6.1.1 or TC02.4 R1/R2; no edits to classic SHORT, capital manager or 450 USDT protection.
- No broker/account imports into the GET-only reader; no modifying wallets; no private keys.
- A candidate is non-binding advice. NO_TRADE remains valid.
- REAL_EXECUTION=UNVERIFIED; ECONOMIC_EVIDENCE=INSUFFICIENT; PAPER_ELIGIBLE=NO.

## Remaining pre-release gates

1. Verify actual CI results, and repair any failing tests before claiming success.
2. Identify the authoritative current Brain wallet source, not guess from historical branches.
3. Implement and test a separate shadow-only worker with MTF receipts and authoritative wallets, no order API.
4. Verify the authenticated GET endpoint and the frontend in staging.
5. Request explicit user approval before deploying shadow. PAPER requires separate approval.
## Pinned offline evaluation probe added

- backend/long_shadow_offline_probe.py combines the verified capture startup context, read-only wallet status and frozen LONG engine, checked against SHA256 36f8c62be8d205d909ae16f5652209710de56ae710fedb6b75a601b96486fe72.
- It is manually invoked for an archive and writes only to a NEW research directory (not inside any wallet). It creates advisory-only records with zero executable order capability. Missing wallets produce NO_TRADE / WALLET_UNAVAILABLE, never an assumed empty wallet.
- It is NOT a live H24 service, and reading a past capture with a currently fresh wallet fails closed on timestamp mismatch. Do not deploy or connect it to a production writer.
- Four additional unit tests cover pinned hash failure, missing wallets, unauthorized engine flags and no overwrite. CI evaluation is still not confirmed.
