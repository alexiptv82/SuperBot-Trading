# Brain: actual Hawk/Bull methods with adaptive intelligence H24 — candidate

## Operator objective and implemented scope

Alessandro explicitly requires the actual Hawk and Bull methods, with adaptive intelligence 24h/7d, adaptive scalp, useful net profit capture and capital rotation. A third sizing formula or a prompt-only instruction does not satisfy this. This candidate adds a dedicated runtime that calls **the real `desk.cli.run_cycle`**, real profile factories, `read_symbol`, `rules_decisions`, account engine and admission controls. **No `backend/desk/*` file changes.** This branch starts from rule-pool `e5d45f9`; its classical files are byte-identical to the documented deployed `35f08cf8d16097d8ca365892a3f9a9ef23996709`. The pending regime/P1 alternatives and Bull 250 cap on Claude's development branch are not silently adopted.

This feature includes the candidate learning/transfer/mandate dependency from PR#12 `41161f42`. It does not merge or deploy either PR. Director V1's Arbitro was inspected: its 1%-risk sizing/four-slot defaults would recreate a different method, so it is not substituted for the classical executor.

**Current baseline update,27October:** while preparing the paired app, rule-pool advanced through the separately user-approved regime/classic-score integration `89b0dca` and deploy trigger `dd7c71d`, then read-only audits to `e0efa6e7b6b19bb9ab3760d06fd844c1f8cca083`. This candidate incorporates that current classical source unchanged. The earlier35f08cf/e5 baseline description above is historical. The current inherited policy uses classic score weights, the production regime entry filter (ratchet/flip off by default) and Bull250 risk cap. No independent threshold was chosen for Brain. The PR merge test correctly vetoed the old SHORT-in-uptrend fixture; fixtures now test valid SHORT/down and LONG/up plus explicit opposite-regime vetoes, without disabling the real filter. Runtime method identity includes actual score/regime configuration, not source files alone. Actual VPS version/settings must still be verified by the preflight.

## Two isolated profiles, actual limits

| Setting inherited from classical code | Brain Hawk | Brain Bull |
|---|---:|---:|
| Explicit fresh PAPER initialization | $1,000 | $1,000 |
| Maximum margin/position | $100 | $350 |
| Guardrail minimum proposal margin | $50 | $150 |
| Guardrail minimum proposed leverage | 10x | 10x |
| Guardrail forced margin/leverage | $60 / 15x | $200 / 15x |
| Maximum positions | 10 | 6 |
| Maximum total margin, still limited by actual cash | $1,000 | $1,050 |
| Daily equity stop | 10% | 10% |
| Absolute kill equity | $450 | $450 |

These are the selected **classical** policies, not newly selected risk parameters. The old single Brain's20% stop and1%-risk sizing remain unchanged in its original runtime; they are not presented as the policies of these profiles. Classical guardrail forcing can change a low proposal to Hawk scalp or Bull medio; native cooldowns, split/DCA rules, confidence thresholds, R/R, leverage tiers, liquidation checks, the approved Bull250 risk/2% BTC-short veto and regime filter remain inherited from the synchronized classical source.

DeepSeek proposes the classical JSON schema; the native executor can refuse it. The real rule fallback proposes its original margin/leverage formula. There is no artificial small 1%-risk rescaling of an admitted classical trade. Tests demonstrate the same 200 margin/15x proposal becomes Hawk 100/15x and Bull 200/15x through native controls. Higher exposure increases losses as well as profits; no profit/turnover claim follows from the synthetic tests.

## Execution and adaptation

- A dedicated process selects exactly one profile before importing `desk.cli`; process-local adapters leave the classic bots' entrypoint unchanged. The code rejects live mode before importing the connector. The image has no exchange SDK, keys or notifications; no hidden Anthropic call or Telegram send. A caller cannot reuse an already imported CLI with a different profile.
- Each worker targets a 60-second iteration continuously, with no 14–22 calendar copied from the classic accounts. Native entry signals still come from 15m/native macro data; this is **not** a newly validated 1m entry alpha. Native entry cooldowns still constrain repeat entries. H24 does not mean forced trades.
- Fast 1m protection and slow public entry/macro history downloads use separate workers. Financial state has one writer. The writer never waits for a pending model or public-data request; stale/missing required BTC/ETH/position data drains new exposure, rather than inventing a price.
- Closed 1m bars go through the real paper engine, with its conservative stop-first OHLC approximation. The minute containing entry is excluded to avoid using pre-entry extremes. Observed latest-candle prices can trigger protection at the observed price with native costs. Data snapshots and model results expire after 120 seconds. This is polling, **not tick execution, a latency guarantee, or a bid/ask liquidity simulation**.
- Experimental local profit protection closes a useful net winner when two completed minute returns fail to advance in its direction. Estimated net proceeds must exceed estimated costs (entry/exit fees, exit slippage and accrued engine funding). Strong continuation can run; neither 5 nor 15 minutes forces an exit, and no fixed high ROI is required. This deterministic heuristic is identified separately from an AI decision and needs chronological PAPER observation; it is not a learned/proven optimal exit rule. Entry slippage is already in the engine entry price. Protective SL/TP remains active regardless of profitability.
- DeepSeek runs asynchronously. Pending/error/budget exhaustion uses explicit classical fallback. A completed result is rejected after 120 seconds, changed cash/exposure/levels, invalid numbers/schema, or entry price drift beyond half the requested stop (capped at 0.5%). No repeated paid call in the same profile/minute, including after restart.
- The AI gets the actual classical prompt/profile settings, both directional scores, recent available fast bars, versioned operator objective, own episodic evidence and any separately verified transferred seed. It is asked to protect useful net profit and explain continuation/extension. Missing transferred history stays `not_imported`; **no production history was collected/imported by this implementation**.

Public-feed outages can make supervision unavailable; status says so. A missing interval beyond the available history sets a persistent coverage-unresolved flag: no new exposure and no statistical lessons from those realizations. The account is not silently reset or its missing path reconstructed. An operator recovery review is required to resolve that flag. A backwards execution clock is rejected.

## State, evidence and spending preservation

The parent directory must be separate from known classic/legacy Brain paths. Accounts live in `brain-hawk/` and `brain-bull/`, each with its own locked SQLite WAL state/events and append-only journal/trade projections. Unknown nonempty directories require recovery, not initialization. The old Brain database and Hawk/Bull volumes are never opened or modified. New PAPER capital requires `--initialize-paper` on an empty profile directory; restart loads the existing account. This implementation does not convert or split the old Brain balance.

The existing Store commits account, close events and derived learning in one transaction. Native file writes are captured into that transaction; the CLI's JSON file is not authoritative here. Protective changes commit before optional entry evaluation; a failed entry cycle cannot revert them. Outbox exports replay on restart. An actual SQL abort test proves no close or changed balance survives a rejected close transaction, then the same observation closes exactly once after recovery.

Memory accepts the distinct account identities `brain-hawk`/`brain-bull`, and adds a whitelisted strategy-version cohort. The classical trend semantics are explicitly EMA50/200, not the old Brain EMA20/50; snapshots and entry context carry the actual method/profile version and decision provider. Old/missing strategy versions stay unknown, and different versions cannot pool lessons. The account, code/config identity and raw outcome source persist. This is bounded statistical memory, not model retraining or evidence of profitability.

**One shared API ledger** caps both workers together at the existing Brain defaults ($0.50/day, $12/month), with conservative pre-call reservations, fair per-profile pacing over UTC day and pacing over the calendar month. No implicit increase, restart reset, refund after uncertain billing, or claim that this allowance funds continuous model reasoning. Fixed-budget H24 means local protection/classical operation is continuous; AI calls are intermittent and honestly labeled.

Activation requires a **verified copy of the old Brain `spend.jsonl`**. `budget.baseline_from_spend(copy_path)` reads it, validates complete records and produces `{version, mode, source_sha256, by_day}` for `api_budget_baseline.json` in the new parent. It does not overwrite the source. Copy provenance/mode must be independently verified; the hash only checks integrity. The shared ledger imports that prior spend once. Missing/invalid baseline fails, rather than restoring a free budget. Per-profile state checkpoints detect a rolled-back/recreated shared ledger. The baseline and new reservations remain across restarts. The existing tariff estimator is reused; reservations are not provider invoices or proof a future tariff will remain unchanged.

## Test evidence and packaging

`test_brain_classical_adaptive.py` covers both profiles and both directions using the actual CLI and synthetic data/model responses in separate processes. It verifies native sizing, source identity, stop costs, same-minute causality, useful net exits/continuation, partial-entry cancellation, stale data, async API/feed failure isolation, schema/price/exposure rejection, budget concurrency/pacing/import/restart, no empty-directory reset, SQL rollback, recovery and learning separation. Healthcheck is read-only and cannot initialize a wallet. Existing Brain learning/transfer/mandate/upgrader tests remain in CI.

`Dockerfile.brainclassical` starts with help by default, has no exchange SDK and needs an explicit profile/output/initialization flag. CI builds the real image and runs the native Hawk/Bull LONG/SHORT probes with **network disabled**, a read-only image and temporary fixture storage. No deploy workflow, SSH action, server control or production key is added.

## Release gates still outstanding

1. Review the process-local CLI adapters, async result validity, transaction interception, local profit heuristic and statistical cohort separation. Current source/runtime equivalence is an integration baseline, not an efficacy backtest.
2. Run chronological PAPER observation against each frozen classical baseline, including cost/slippage sensitivity and denied opportunities. No historical profitability comparison is claimed here.
3. Prepare a separately authorized deployment with verified backup/restore and exact image SHA. Freeze old Brain API/exposure through its existing pause mechanism while retaining management, acquire the verified spend baseline, and preserve its original account/history. Do not launch two instances on one profile directory.
4. The PWA currently shows the **old single Brain**; a dedicated paired-profile reader/UI and explicit display of archived versus candidate accounts are a separate app change before a user-visible paired rollout. Do not relabel old data as new profiles.
5. Rollback must preserve all new account outcomes and spending. Pause/drain new exposure using the retained image if needed, keep protection active for open PAPER positions, and reconcile spending before re-enabling another model worker. Never restore an older financial snapshot over newer trade history.

No VPS change, runtime upgrade, live trade, reset, collector startup, or dashboard deployment is performed by this PR.

## Review extension and paired app preparation

App PR#15 adds a separate authenticated reader/UI for the two profiles and the previous Brain, without merging app/bot histories. This runtime extension records per-symbol actual quote receipt times, prefers a newer fast quote when valuing existing exposure, counts completed steps and journals AI advice as a **proposal**, separately from execution. An event-kind index supports the read-only views. Native account/risk/entry policies are unchanged; the real-image probes assert the timestamp/counter/advice contract.

`brain_classical_preflight.py` and its trigger-only `brain-classical-preflight.yml` provide **inventory and verified backup only**. They validate PAPER container/source identity and immutable legacy SHA, use the already-tested online SQLite backup helper, actually restore/reopen a separate copy and compare state/events, copy append-only exports and create a private verification manifest. Container metadata must remain identical before/after. Only a new protected backup and temporary control checkout are written; no pause flag, account/budget source, container, key or trading state is changed. The script never prints Docker environments or raw provider errors. The source can continue running, so this backup is explicitly **not a frozen activation-spend baseline**. Unit tests cover source-byte preservation, real restore, private permissions, no overwrite and PAPER/secret filtering.

The workflow is unarmed on the feature branch: only a specific trigger-file push on rule-pool runs the read-only backup. Installing/running that control does not authorize activation. New-runtime deployment must still acquire a quiescent verified old spend ledger and retain management for all old positions. The PWA source and actual activation are separate reviewable artifacts.

## Explicit PAPER rollout control

`brain_classical_activate.py` / `brain-classical-activate.yml` require an explicit approved PAPER trigger and full immutable runtime/classical/legacy/app SHAs. They verify unchanged current classical code/settings, healthy PAPER inventory, an already-deployed paired app with readonly mount, no existing target containers/data, enough memory and a newly verified backup. They build the fixed image before touching the old pause. The legacy process stays running and managing its positions; a completed non-calling cycle after its pause flag proves API quiescence before the old spend ledger is frozen/imported.

New profiles start paused, with explicit empty PAPER initialization and no paid model calls. Only a pause flag is permitted in such an explicitly initialized empty profile; unknown state/files still reject initialization. The control verifies identities, unchanged initial balances, zero exposure, fresh feeds, Docker health and the actual app reader before allowing entries. Old spend/checksum and classic runtime metadata must remain unchanged. There is no source financial reset, container duplication or automatic restoration of older balances. Before any new spending/exposure, failure can stop only workers created by that control and undo only its own legacy pause. If spending/exposure exists or is uncertain, it keeps management running and pauses new entries instead of hiding outcomes or resetting budgets. New data/archives are always retained.

The control remains inert unless its separate activation trigger says `approved=yes`; source/UI preparation and a read-only backup alone do not run it. Pure tests cover quiescence, readonly initial-account validation, and private exclusive control files, in addition to real-image paused warmup and native entry/protection probes. Final post-deploy observations must report actual status and whether AI or fallback produced decisions; no trade is forced to manufacture a successful demonstration.

The final H24 review also avoids full input archives for budget-denied/pending polls: an exact system/user input is persisted only after a durable budget reservation and before an actual background submission. A failed audit blocks the API, retaining the conservative reservation. The new runtime's `CachedStore` reconciles/validates complete append-only projections once on startup or external change, then exports only new sequences. It retains SQLite authority, restart deduplication and torn/corrupt-line refusal while avoiding full-history JSONL scans at each minute checkpoint. This optimization is isolated from the previous Brain runtime. Tests verify incremental IO, unchanged prefixes, restart deduplication and no overwrite of torn projections; simulated control tests verify successful paused warmup/spend carryover, no old pause on a build failure, and retained management when exposure is uncertain.
