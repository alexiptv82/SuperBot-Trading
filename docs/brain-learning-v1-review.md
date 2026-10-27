# Brain episodic learning V1 — design and review handoff

User mandate (26 October 2026): implement durable learning from Brain trades as a priority. This branch contains code and offline verification only. No merge, deploy, trigger, container operation, reset or modification of production data is authorized by this implementation handoff.

## Result

Brain gains an evidence/retrieval loop. Completed trades become structured episodes. Relevant historical weaknesses/strengths and recent cases enter the next ordinary DeepSeek prompt. Future trade outcomes retain the IDs of the supplied lessons. This is episodic memory/in-context adaptation, **not model retraining**, autonomous code modification, or evidence of better returns. No extra model call is made; prompt tokens increase within existing API budget gates.

## Data flow and persistence

1. At execution, code records actual 1d/4h trend regime, decision-policy version, model identifier and supplied lesson IDs in position features. Provider output cannot set this provenance. Free-text reasoning is not promoted into memory instructions.
2. A small additive `learning_open_contexts` map in existing state preserves that context through partial and final closes, including a position opened and stopped in one bar. Migrated positions without factual entry context remain `legacy_unknown`.
3. The existing SQLite `events` trade rows are authoritative. Cursor-based replay incorporates history in batches of at most 1,000 rows per checkpoint. It never imports mutable JSONL copies, edits old events or touches Hawk/Bull. Catch-up continues after restart; lessons are unavailable during incomplete backfill.
4. State, new trade rows, learning cache/cursor and `learning_update` audit events commit in the **same SQLite transaction**. No new database or table is required. Optional `brain_learning.jsonl` is an idempotent append projection of learning events. If that projection is damaged/unwritable it is left untouched and reported unavailable; SQLite audit remains authoritative and protective management continues.
5. Exact selected memory, evidence IDs and digest are journaled in `model_attempt` before the existing spend reservation/network call. This records exposure to lessons, not proof that the model followed them. Completed exposed outcomes are summarized separately without causal claims.

Existing `trade_history.jsonl` only receives the usual new closes, now with additive factual context. Existing prefixes are preserved. `learning_log.jsonl`, `lessons.md`, `errors.md`, account values and historical trades are never rewritten.

## Episode and evidence semantics

- Identity is account + position ID + open timestamp + symbol + side. Partial realizations are accumulated; only final close creates one completed episode. Net P&L sums the engine records, including their costs; net R uses the original planned risk. Missing risk means no normalized lesson.
- Deduplication uses the durable event cursor and fingerprints for partials plus retained final episode identities. Export replay never re-ingests JSONL. This is not an importer for arbitrary duplicated old trade events beyond the retained cache.
- Up to 500 completed episodes are materialized; source history remains complete. Retrieval considers 90 days and requires latest cohort evidence no older than 7 days.
- Cohorts separate direction, entry regime, policy and model. Current regimes retrieve matching cohorts; unknown legacy regimes are never reconstructed from current prices. This coarse regime is explicitly EMA-derived input, not a market-cycle oracle. Results across symbols can be correlated.
- A lesson requires at least 12 completed episodes across at least 3 UTC days. The first two thirds are training, last third validation. Training episodes whose closes overlap or follow the earliest validation entry are purged. Require >=8 training and >=4 validation episodes, with validation spanning >=2 UTC days.
- Historical weakness/strength requires matching signs of mean net R in both subsets and a 95% Wilson win-rate interval entirely below/above 50% in validation. This combines expectancy sign with a conservative consistency filter, **not a proof of edge**. Repeated holdout selection is not independent out-of-sample research; no claim of statistical significance or guaranteed predictive accuracy.
- Invalid source records are counted and suppress supported lessons (`data_quality_warning`), rather than silently creating favorable selection bias. Incomplete positions are not counted as completed wins/losses.
- At most 6 lessons and 3 factual cases enter a prompt (14,000-character maximum). No untrusted historical prose is reinterpreted as instructions. Small samples return `insufficient_data`; they never force a LONG/SHORT quota.

These thresholds are experimental engineering defaults for review and PAPER evaluation, not optimized trading parameters. There are no hard trade vetoes, risk/size multipliers or automatic threshold changes based on learned evidence. The model is asked to explain how current evidence supports or contradicts memory in its existing `reason`; V1 does not certify that explanation's quality.

## Compatibility and failure behavior

- Existing state version remains loadable; new metadata is additive. Legacy pending entries may execute without learning provenance and stay unknown. Old positions, protective orders, capital, budgets and daily-stop latch remain intact.
- ATR sizing, 20% UTC stop, exposure gates, fees, leverage, SL/TP and execution timing are unchanged. The only authorized behavioral extension is memory context/instructions to DeepSeek.
- `BRAIN_LEARNING_ENABLED=1` is the default **in this candidate image only**. `0` disables replay/retrieval/provenance on new orders and preserves the saved cache. Applying this environment setting to a production container is a separate operation.
- Learning computation exceptions return unavailable memory and do not block protective decisions. Authoritative SQLite/account failures retain the original fail-stop policy; this feature does not hide them.
- SQLite backups and the existing stateful upgrader copy all additive state/events. The Docker image already copies the whole package; no Dockerfile or operational deploy workflow/trigger change is needed. The CI branch filter alone adds this development branch.
- No runtime is upgraded here. Review and explicit deploy authorization remain separate. Rollback must use the existing state-preserving workflow and must not restore an old financial snapshot over newer trades.

## Validation and review checklist

Offline suite covers legacy migration, full-history catch-up, replay/restart, partial aggregation, duplicate protection, risk normalization, sample minimums, later validation failure, purge against temporal overlap, future/stale/regime/model isolation, bounded retrieval, atomic rollback, append-only source preservation, learning and optional-export failures, provenance spoofing, same-bar close and unchanged risk limits. CI includes Python 3.10/3.11, Docker smoke import and the existing real-container five-position migration probe.

Review before merge: checkpoint atomicity, episode identity, legacy unknown handling, temporal purge and failure isolation. Before any deployment: inspect actual source-record quality and data coverage read-only; back up, use a frozen application SHA and preserve open positions/history. Later assess chronological PAPER outcomes versus a frozen baseline; aggregate `subsequent_exposed_outcomes` alone cannot establish improvement. A/B execution and PWA learning cards are separate future work.


## Extension: Research methods and classical-bot experience

PR#12 also adds `experience.py`, `knowledge.py`, dedicated tests and `docs/brain-experience-transfer-review.md`. Source evidence lives in a separately reviewed immutable seed file, never in the Brain's own win-rate/cash/history. Includes source provenance/quality, fixed research/validation boundary, factual cases, source-scoped historical lessons, engineering notes and bundle-selection audit. See the extension document for capacity, mode attestation, missing-data and non-causal limitations. The live source archives have not been collected/imported and no seed has been installed.


## Operator mandate extension — user clarification 26 October

The user explicitly requests that Brain apply their trading idea using classical Hawk/Bull experience: adaptive short trades, useful net profit capture, capital rotation, and meaningful margin with Bull as reference. `mandate.py` now supplies a versioned `operator_mandate` in each model input, with source-experience availability and actual execution capabilities. The exact mandate is journaled before the model call. This is a prepared candidate change, not a production Brain release.

The discretionary exit prompt no longer asks to wait for about 25–30% margin ROI or an aged winner before considering profit protection. It asks for useful estimated net profit when continuation weakens, while allowing evidence-based extensions. This **is an authorized qualitative prompt behavior change**, beyond passive learning; it needs review as such. No numeric profit target, holding deadline, risk, margin or leverage limit is raised. The requested Bull margin reference is labeled not applied.

The existing 15m decision/execution cadence, 1h ATR and medio engine classification remain explicitly reported as active capabilities. `readiness=full_scalp_engine_not_implemented` and `fast_exit_supervisor=false` prevent a false claim of 1–5min supervision. Live classical signal inputs remain not connected; historical experience remains not imported until a reviewed real seed is prepared. Full adaptive-scalp data/exit/sizing implementation is still outstanding and requires dedicated tests before deployment.

The new operator policy version is tracked in entry context and learning cohorts; missing old version is unknown rather than retroactively assigned. Old/new operator mandates cannot pool statistical evidence. This change does not claim the new operational objective is already achieved or profitable.

## Clarification: actual Hawk/Bull methods plus adaptive intelligence H24

The final operator instruction supersedes the narrower idea of a separate Bull-like sizing profile: **use the actual Hawk and Bull methods, with adaptive intelligence 24h/7d**. The new mandate version is `operator-classical-adaptive-h24-20261026`. It requires both named profiles and preserves their individual rules, size/leverage policies and executable controls. It does not fabricate a second running account or silently import a risk cap from another profile's development work.

The standalone sizing prototype was discarded before integration: no new sizing module, environment switch, margin/leverage/risk value or account migration is included in this extension. The current production and candidate execution path remain the single Brain account. Prompt/mandate changes alone do not deliver the requested architecture.

The implementation still required is concrete:

| Component | Required behavior | Current candidate |
|---|---|---|
| Classical method adapter | Consume the actual versioned Hawk/Bull readings, decisions and profile configuration; reuse the classical implementation instead of a third sizing formula | Not connected |
| Adaptive decision layer | Explain a continuation, entry adjustment or exit against both current market evidence and the selected classical profile; deterministic controls arbitrate | Operator intent only |
| Profile/account routing | Keep the two profiles' capital, positions, risk, history and provenance separate; preserve the existing Brain account without resetting or duplicating capital | Not implemented |
| H24 execution and protection | Evaluate opportunities and manage exposure around the clock, subject to valid data, pauses and risk stops; fast exits independent of API availability | Existing 15m engine only |
| Model availability | Budgeted API calls distributed over the day; explicit AI/fallback provenance; no implicit spend increase or false claim of continuous model coverage | Existing API caps unchanged |
| Validation | Causal PAPER replay with fees/slippage, both directions, outages/restarts and fresh data; compare each classical profile to its adaptive counterpart | Future integration tests |

The existing `work/director-v1-unified` (`d2b351e0`, `backend/director/arbitro.py` and contracts) is a source to review for arbitration, not an already-connected component. Classical runtime/fixes are evolving on separate branches; use a pinned, reviewed version at integration, never this older learning branch's copied classical files as an assertion of the latest method. No decision here promotes the pending Hawk/Bull regime implementation to a deployed or profitable strategy.

This version records requested continuous coverage separately from `adaptive_h24_status=not_implemented`. H24 does not mean forced entries or an API call on every tick. The mandate requires protective management during API failure and labels classical fallback honestly. The new operator version also separates old/new learning cohorts. No merge, restart or deployment is included.
