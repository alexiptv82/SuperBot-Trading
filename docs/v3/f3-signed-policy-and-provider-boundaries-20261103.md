# SuperBot V3 — F3-A/B offline: signed mandate + provider boundaries

**2026-11-03 | DRAFT / NO MERGE / NO DEPLOY / NO VPS / NO REAL AI REQUESTS**

## Dependencies and status

This work branches from the exact R1.9 head `ec999f896addd7d90be6d85075ad4d7e09f8b667` of F2 PR #33. PR #29 F1 and PR #33 F2 remain unmodified. The new `backend/v3/brain_f3/` package is opt-in and has no import-time network, file or credential side effects. All tests use synthetic keys, market contexts and mocked transports.

## F3-A: operator trust boundary

`SignedPolicyVerifier` implements the **existing** F2 `policy_verifier(mandate, risk_policy)` hook, so F2 itself is unchanged. It verifies Ed25519 signatures using operator **public keys only**. No `return True` callback, AI-provided `approved_by`, or truncated policy hash alone suffices.

A valid mandate binds: fixed PAPER risk-policy purpose; `approved=true`; F2-compatible policy hash *and* SHA256 of all seven F1 risk policy values; version; Brain portfolio; one explicit run; trusted key ID and operator identity; approval ID; issue/expiration times (max 24h), and the operator signature over canonical JSON. Strictly reject missing/extra fields, unknown/revoked key, bad signature, failed expiry/clock checks, wrong type, wrong portfolio, changed policy and revoked approval. The F2 engine separately checks that the signed run equals its `run_id`, and retains the F1 deterministic risk quote and append-only journal gates. This produces, at most, **OPEN/APPROVED proposal**, NEVER an executed order.

The operator's private Ed25519 key is **not** generated, stored or loaded in this package. Provisioning authentic operator identities, securing the separate signer, distributing trusted public keys, signed revocation/rotation, trusted clock and non-AI configuration must be implemented and audited before enabling live PAPER. An operator key stored in the same AI/trading process would invalidate the intended separation. **The sample test key is ephemeral and not an authorization.**

## F3-B: DeepSeek / Claude offline adapters

`DeepSeekAnalystAdapter` implements F2 `Analyst.analyze`, `ClaudeReviewerAdapter` implements F2 `Reviewer.review`. Both default to `enabled=False`. No transport or secret is instantiated automatically. Invocation needs explicit `enabled=True`, a model name, an injected transport, and a separate budget callback returning literal `True`. This callback is only an offline hook: it is **NOT** persistent cost metering or an authorization to spend.

- DeepSeek request has `model`, non-streaming `/chat/completions`-style `messages`, JSON response format, a small output token cap. Only market symbol/price/timestamp/regime and *count* of positions are sent. No wallet, free-form Falco/Toro signals or credentials are passed. Only exact, bounded `NO_TRADE` and `OPEN` schema are accepted; no `CLOSE`/stop-change. Sanitized F2 proposals must still pass review, risk, signed mandate, journal.
- Claude request has `/v1/messages`-style `system`, `messages`, `max_tokens`. Only whitelisted candidate fields are sent. Only exact `APPROVE` or `REJECT` JSON is accepted, with Claude approval explicitly **DRAFT review only**. F2 risk and policy authorization remain mandatory.
- Missing transport, budget refusal, HTTP error including 402/429, timeout, exception, malformed/duplicate JSON, unexpected model fields, incomplete generation or oversized response raise `ProviderUnavailable` with a fixed error code; no raw model body, API key, provider error or prompt is placed into F2 memory/journal.

**No real HTTP client implemented in F3-A/B**; the injection seam is for future isolated network transport with explicit secure config, bounded retries, durable request dedup, independent budget ledger and no automatic trading. There are zero API calls in this PR. API structures reference the official docs (review again before implementation):

- https://api-docs.deepseek.com/api/create-chat-completion/
- https://platform.claude.com/docs/en/api/messages/create

## Test and release gates

Local test development (Python 3.13): F3 isolated tests, signatures and negative provider output. GitHub CI on Python 3.10 and 3.11 exercises **existing F1/F2 tests AND new F3 tests**, `compileall`, no secrets, no credentials, no network clients (other than normal CI package installation).

Follow-on gates (NOT satisfied): authenticated operator key lifecycle/secure signer; actual persisted revocation and trusted clock; real DeepSeek and Claude HTTP transports with credential isolation, timeout/budget/402 behavior; durable cost reconciliation; PAPER execution and position management; backup/restore and dashboard; user-approved deployment and migration preflight. Do not infer runtime readiness from passing unit tests.
