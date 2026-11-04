# Fase F4 — HTTP transport + budget ledger: 113/113 PASS

**Data:** 2026-11-04 (sessione Claude Sonnet 4.6)
**AI:** claude
**Branch:** work/v3-f4-transports-budget-20261104 (commit `af18aed`)
**PR:** [#37](https://github.com/alexiptv82/SuperBot-Trading/pull/37) DRAFT

---

## Cosa è stato fatto

Completamento Fase F4: implementati i due componenti concreti che soddisfano
le interfacce `Transport` e `SpendingGate` definite in F3 (`brain_f3/providers.py`).

### `backend/v3/transport.py`

- `deepseek_transport()`: factory → callable `Transport` per DeepSeek chat completions
  (`https://api.deepseek.com/v1/chat/completions`)
- `claude_transport()`: factory → callable `Transport` per Anthropic Messages API
  (`https://api.anthropic.com/v1/messages`)
- **stdlib only** — `urllib.request`, `ssl`, `json` — zero pip installs
- API key letta dalla env var **al momento della chiamata** (non memorizzata nella closure)
- Fail-safe: qualsiasi errore → `ProviderUnavailable("provider_unavailable")` senza leakage
  di credential, URL o response body nel messaggio
- Timeout 30s, cap 64 KiB response, SSL strict (CERT_REQUIRED + hostname check)
- Versione header Anthropic: `2023-06-01` (configurabile)

### `backend/v3/budget.py`

- `BudgetLedger`: tabella SQLite append-only (no UPDATE, no DELETE)
- `spending_gate()` factory → `SpendingGate` callable
- Limiti per provider:
  - **daily**: unità per giorno UTC, persistente su file SQLite
  - **session**: unità per lifetime del processo, si azzera al restart
- Fail-closed: provider non in `daily_limits` → deny; qualsiasi errore DB → deny
- Thread-safe (threading.Lock + WAL mode)
- Helper diagnostico `all_spend(provider)` per test/debug

### `backend/tests/test_brain_f4_transports.py`

30 test offline:
- 15 `TestBudgetLedger`: record/read, gate allow/deny per tutti i casi limite,
  persist across instances, thread safety (5 thread × 10 record)
- 7 `TestTransportFactory`: no API key, custom env var, HTTP error → ProviderUnavailable,
  non-200 → ProviderUnavailable, 200 OK → TransportResponse (urllib mockato)
- 8 `TestAdapterWithMockTransport`: NO_TRADE parsed, OPEN parsed, gate deny,
  disabled adapter, transport error, Claude APPROVE, Claude REJECT,
  BudgetLedger integration

### Fix legacy carry-forward

`test_brain_f2.py` e `test_brain_f2_safety_contract.py` corretti con i parametri
obbligatori BrainEngine (`risk_policy`, `portfolio_snapshot`, `market_params`, `journal`)
su tutti i test (erano stati fixati localmente nella sessione precedente ma non pushati
sul branch remoto di integrazione).

---

## Risultati finali

```
test_brain_f2_independent_claude.py    33/33 PASS
test_brain_f2.py                        5/5  PASS
test_brain_f2_safety_contract.py       10/10 PASS
test_brain_f3_boundaries.py            17/17 PASS
test_brain_f3_f2_integration.py         2/2  PASS
test_brain_f4_transports.py            30/30 PASS  ← NUOVO
─────────────────────────────────────────────────────────────────────────────
TOTALE                                113/113 PASS  (Python 3.13.16, 0.54s)
```

---

## Status gate

- ✅ Fase F4 completata — 113/113 PASS
- ✅ PR #37 DRAFT aperta
- ⛔ Nessun merge/deploy
- ⛔ Nessuna API key nel codice (solo env var a runtime)
- ⛔ DESK_MODE=paper invariato
- ⛔ Hawk/Bull non toccati, cervello intatto

## Gate ancora aperti

- Trust anchor Ed25519 reale per policy_verifier (solo mock sintetico)
- Executor PAPER reale (F5 non iniziato)
- Dashboard (F6 non iniziato)
- Brain evolutivo (F7 — Grok)
- Integrazione e release (F8)
- Backup off-host certificato (F0 VPS — richiede OK utente + Termius)
- Import 534 trade legacy (bloccato fino a backup certificato)

## Prossimo: F5 — PAPER executor
