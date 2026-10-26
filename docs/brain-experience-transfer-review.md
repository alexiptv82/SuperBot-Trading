# Research Console methods + Hawk/Bull experience transfer — review handoff

## Scope and authorization

User approved selective recovery of data-quality/provenance/validation methods from `alexiptv82/SuperBot-Research-Console`, and a historical experience bridge from classical Hawk/Bull to Brain. Extends draft PR #12 on `work/brain-learning-v1`. This is code/tests/documentation only: no production source collection, seed installation, merge, deploy, restart, collector launch or change of trading risk. Real source data has **not** been imported into the running Brain.

## What is reused

Methods adapted from Research Console commit `bd9b04277dda8ed6a1ab310220a9b96e6234a0ed`:

- Explicit quality verdicts, hash-addressed provenance and no fabricated pass for missing evidence.
- A fixed chronological research/validation boundary, excluding positions that span it.
- Immutable dataset identity and append-only intake/selection audit.
- Distinguish published research conclusions from independent reproduction and economic utility.

This is a small native implementation. It does not copy/import the old application, database, authentication, collector, source analysis formulas, 100ms sampling or incomplete FrozenAnalysisEngine. No synthetic trading alpha is reconstructed from reports. The microstructure finding enters a curated note with its rejected directional-alpha conclusion and non-reproduction caveat.

## End-to-end flow

1. An operator prepares stable copies of PAPER `trade_history.jsonl` and optional `learning_log.jsonl` for each source. The builder only opens sources read-only, refuses symlinks/nonregular files, checks source inode/size/mtime/ctime consistency during reads, and records full SHA256 values. Runtime never mounts or reads the source bot folders.
2. `python -m director.brain_pilot.experience` builds a sanitized immutable `experience_seed.json` in a **separate prepared output directory**. Explicit `--confirm-paper` and `--validation-start-ms` are required. No implicit default split based on observed profits. The PAPER flag is operator attestation, **not cryptographic proof of the historical execution mode**; known LIVE markers are rejected. Unmarked sources require independent provenance review.
3. Source identities include bot/run/position/symbol/side/open time. Close rows remain authoritative; partials aggregate into one completed position. Duplicates are suppressed independently of export IDs; conflicting finals or opening provenance fail intake. Pending-only positions are counted but never promoted to completed wins.
4. Entry features come only from an exact matching historical `open` event: same bot/run/id/symbol/side and `ts == open_ms`. Entry code version is never inferred from closing version, latest deployment or current candles. Context uses the original classical `daily_trend` and `ema50_200_4h` feature values, explicitly different from Brain's EMA20/50 summary. Missing context/version/source remains unknown. Missing planned risk means no normalized lesson.
5. The bundle contains every completed normalized episode in the accepted bounded snapshot, with source bot/run/version, net result, original-risk R, costs already included in engine net, close reason class, parts and available MAE/MFE. MAE/MFE are engine estimates with its intrabar limits, not precise event-level paths. Raw reasons, model prose, live details, credentials and absolute source paths are excluded.
6. Atomic create-only publication uses a private temporary file + fsync + hard link: no overwrite or half-written target. Source directories/protected filenames are refused. Capacity is explicit (64MiB/source, 256KiB/line, 100k rows/source, 5k completed episodes, 8MiB bundle). Oversize or malformed input fails rather than dropping old/loss records. A larger history requires a separately reviewed partitioning plan; do not silently sample it.
7. After a **separate reviewed installation** places the bundle inside the Brain's own data root, runtime reads only `experience_seed.json`. Hash/strict-schema/source-count/identity/partition checks apply. The hash proves integrity relative to the reviewed bundle, **not authenticity against an attacker who can replace it and recompute hashes**. Source hashes must be compared with approved snapshots. Extra text cannot become memory instructions.
8. Relevant source cases and lessons enter `episodic_memory.transferred_experience`, separate from Brain's own episodes, cash, trade count and win rate. `engineering_research_notes` contains three curated source-linked facts: counter-evidence contract, Profit Guardian's declared shadow module, and microstructure limits. Code presence/intent is never labeled as runtime activation or demonstrated profitability. Notes are time-gated by their source commit times.
9. The exact selected memory continues to be recorded before each ordinary model call. An `experience_intake` journal event records changes of selected bundle ID, prior ID, quality and split; identical reuse/restart does not create a second intake transition. New entries retain external lesson IDs and bundle ID in their provenance, separate from own-Brain lesson IDs. No extra LLM call, risk tuning, veto or trade quota is added.

## Evidence and QA

- QA `UNRESOLVED`: missing entry context/version/decision source or planned risk; no external supported lessons. Factual cases remain explicitly unknown. Structural corruption/conflicting records fail the builder entirely; runtime returns unavailable for a rejected/damaged bundle.
- `PASS_WITH_WARNING`: well-formed sources with exact duplicates, incomplete positions or split-overlap exclusions. Their counts remain visible. `PASS` only means intake/provenance checks passed, **not that the strategy is profitable or data-independent**.
- Each source cohort separates bot, run, entry revision, decision source, direction and classical entry regime. No pooling of Hawk/Bull or old/new code. Minimum eight research and four later-validation complete positions, three days total and two validation days. Research closes strictly before the fixed boundary; validation opens on/after it. Overlap is excluded; no position can cross partitions.
- Positive/negative expectancy sign must agree in both partitions and the later 95% Wilson win-rate interval must lie above/below 50%. Defaults remain experimental. This historical split is not a prospective experiment; repeated choices of boundary or correlated trades can still overfit. The audit makes dataset identity/boundary reviewable rather than claiming independence or improved returns.
- Only source cohorts relevant to current coarse regime are retrieved. Evidence ages out after seven days (90-day window). At most two source lessons and four cases, <=8.5k bytes. Cases intentionally show latest positive and nonpositive examples per source; they are **illustrations, not an unbiased performance sample**. Full cohort stats include both outcomes.

## Failure and compatibility

Absent seed -> `not_imported`. Damaged hash/schema, future-exported seed, too-large payload or read error -> unavailable external memory, protective management remains available. `BRAIN_LEARNING_ENABLED=0` disables own and transferred memory while preserving saved data. No shared engine, Hawk/Bull code, deploy trigger or strategy risk limit is changed. Existing state is additive; SQLite backups/upgrader preserve new metadata.

The classical close strings `stop loss` / `take profit` are now recognized in both own and transferred episode labeling. This is an audit-label correction only.

## Example preparation (offline copies only)

```bash
PYTHONPATH=backend python -m director.brain_pilot.experience \
  --hawk-history /copied-paper/hawk/trade_history.jsonl \
  --hawk-learning /copied-paper/hawk/learning_log.jsonl \
  --bull-history /copied-paper/bull/trade_history.jsonl \
  --bull-learning /copied-paper/bull/learning_log.jsonl \
  --validation-start-ms <predeclared-UTC-milliseconds> \
  --confirm-paper \
  --output /prepared-output/experience_seed.json
```

The source and output paths are placeholders. This command has not been run on production history. The command does not install the bundle or modify the runtime. Output is private operational PAPER evidence; do not commit source archives or this generated seed as an ordinary code fixture.

Review next: provenance matching, source completeness/quality, fixed-boundary semantics, non-PAPER rejection, append-only registry, runtime failure isolation, and consistency of curated notes against their pinned source. Then obtain read-only source snapshots, inspect actual quality/coverage, review a frozen seed hash and arrange a separately authorized Brain rollout. No raw archive availability or transferred improvement has been certified here.
