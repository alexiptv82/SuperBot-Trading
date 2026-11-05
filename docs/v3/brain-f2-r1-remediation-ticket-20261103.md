# Brain V3 F2 — Remediation R1: safety gates before integration (2026-11-03)

**Assignment for Grok (or another implementation AI). Status: design and offline-only source changes. NO merge, deploy, VPS commands, wallet reset, bot restart, live API calls or real-market orders.**

## Ground truth and pinned context

- Repository: `alexiptv82/SuperBot-Trading`.
- Target branch: `work/v3-brain-f2-grok`, [DRAFT PR #33](https://github.com/alexiptv82/SuperBot-Trading/pull/33), based on F1 branch `work/v3-foundations-event-risk-20261102` from [DRAFT PR #29](https://github.com/alexiptv82/SuperBot-Trading/pull/29).
- Review: `docs/v3/brain-f2-grok-review-20261103.md`.
- Baseline CI: [run 41606677413](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/41606677413) Python 3.10 and 3.11 `110 passed, 3 xfailed`.
- The three strict `xfail` tests in `backend/tests/test_brain_f2_safety_contract.py` are **known blockers**: never claim them fixed while marked `xfail`. For each fixed gate remove its marker and show normal `PASS` on both Python versions.

## R1 scope: repair three confirmed P0s, preserve complete isolation

### 1. Fail-closed risk verification for every OPEN

Current `BrainEngine.step` can return `OPEN` with `risk_quoter=None` and `risk_quote=None`. Make it impossible to produce an actionable/approved OPEN unless a valid `RiskQuote.allowed=True` comes from F1 `quote_paper_risk(policy: RiskPolicy, request: RiskRequest)`. The existing F2 signature `risk_quoter(proposal)` is incompatible with F1.

- Introduce a **typed adapter** from validated `OpenProposal`, independent Brain portfolio snapshot, versioned `RiskPolicy`, and fresh market/exchange parameters to F1 `RiskRequest`. Never derive equity/margin from Falco or Toro.
- Require a nonmissing, user-approved policy and a supplied independent portfolio snapshot; do not invent default policy thresholds, coin prices, leverage or USDT capital. Keep the pre-existing absolute protection rule (450 USDT) and ensure it is neither removed nor accidentally relaxed. A policy test value is not production authorization.
- Reject or return `NO_TRADE`/risk-rejected with a machine-readable reason if anything is missing/invalid, if market data are stale, AI unavailable or risk quote raises. Never silently fall back to mechanical trade selection.
- Distinguish a **decision proposal** from `EXECUTED_PAPER`. F2 does not execute orders. Strong types or final guards must guarantee that a suggestion cannot accidentally bypass the risk quote.
- Test both allow/deny paths with actual F1 deterministic risk quotes and synthetic snapshots; verify independent Brain portfolio scope and floor. No real wallet or exchange calls.

### 2. AI unavailable must not crash into unsafe behavior or fallback

Current test `force_no_trade=True` is not a simulation of a network/credit failure. Add tests for an `Analyst.analyze` raising a timeout, provider error/402 credit exhaustion, invalid response, and malformed proposal. Every one must fail closed, return an explicit non-trading outcome and record a sanitized reason. No automatic strategy decision from Hawk/Bull and no silent reopening.

Claude is a selective reviewer, not a mandatory trade source. If reviewer is unavailable during a required review, do not treat the unreviewed draft as approved; fail closed. Preserve valid explicit NO_TRADE and HOLD semantics with clear distinction from provider failures.

### 3. EventJournal integration really stores decisions

Current callback `journal_append` is a no-op `pass`. Use F1 `Event` and `EventJournal.append` with `portfolio_id="brain"`, explicit scoped `run_id`, stable event identifiers, timestamps and sanitized provenance. A decision should not depend solely on `self.memory`; add tests for persistence and journal replay/restart using **temporary SQLite in an offline test directory** only.

Document where idempotency key comes from; do not use a process-local `self.cycle` as sole identity across restarts. Duplicate exact events must be idempotent; conflicting IDs must fail without writing. Journal failure must not signal approval/execute; no orders are performed regardless.

### 4. Separate safety contract for CLOSE and MODIFY_STOP (do not overclaim)

No execution of CLOSE/MODIFY_STOP is part of R1. Define valid position IDs, independent Brain position ownership, fresh quotes, monotonic/non-loosening stop policy, and non-actionable proposals until explicitly reviewed by future risk/execution layers. Stop widening or closing an unrelated portfolio must be rejected; no client/orders.

### 5. Test quality and deliverables

- Keep the 110 F1+F2 existing passing tests, then convert 3 strict expected failures to ordinary passing tests **only when genuinely fixed**.
- Replace tautological `assert ... or True` with meaningful assertions; test Falco/Toro signals remain advisory context.
- Add negative tests for stale inputs, None/NaN/Infinity, malformed enums, wrong portfolio/run, duplicate request, AI exceptions, reviewer exceptions, journal failure, and restart.
- Do not alter `backend/v3/events.py` or `backend/v3/risk.py` in the F1 branch. If F1 changes are needed, report as blockers, don't overwrite F1.
- Deliver source files, a new tarball with code + tests + README (excluding secrets), run logs and exact SHA if available; if the Grok GitHub integration remains 403, **do not request wider GitHub privileges**: provide the downloadable tarball to the user for ChatGPT to review/publish. No claim of automated H24, persistent learning, 3-wallet UI or live AI until built and verified.

**Gate for R1 completion:** on both Python 3.10 and 3.11 all inherited tests and new negative tests pass, **0 xfailed** on the three formerly blocked contracts, typed F1 integration proven offline, and independent review of full diff. Still DRAFT and NO PAPER deployment pending later F0 and user approval.
