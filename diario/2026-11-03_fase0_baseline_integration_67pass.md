# Fase 0 — Baseline integration F1+F2(P0/P1)+F3: 67/67 PASS, PR #36 DRAFT

**Data:** 2026-11-03 (sessione Claude Sonnet 4.6)
**AI:** claude
**Branch:** work/v3-integration-baseline-20261103 (commit `12dc78f`)
**PR:** [#36](https://github.com/alexiptv82/SuperBot-Trading/pull/36) DRAFT

---

## Cosa è stato fatto

Creato branch di integrazione `work/v3-integration-baseline-20261103` che riunisce
le tre fondamenta V3 in un'unica stack verificabile.

### Punto di partenza

Branch F3 (`627045e` — `work/v3-brain-f3-offline-20261103`) già include F2 stacked.
La storia delle branch è divergente (nessuna storia comune) — il merge git non è
applicabile. Approccio corretto: sovrapporre i file corretti (engine.py P1) su F3.

### Componenti integrate

| Layer | Sorgente | Commit | File chiave |
|-------|----------|--------|-------------|
| F1 | `work/v3-foundations-event-risk-20261102` | `91e6040` | `events.py`, `risk.py` |
| F2 P0+P1 | `work/v3-f2-review-claude-20261103` | `02e1f08` | `brain_f2/engine.py` |
| F3 | `work/v3-brain-f3-offline-20261103` | `627045e` | `brain_f3/authorization.py`, `providers.py` |
| Test Claude | `work/v3-f2-review-claude-20261103` | `02e1f08` | `test_brain_f2_independent_claude.py` |

### Risultati test (Python 3.13.16)

```
test_brain_f2_independent_claude.py    33/33 PASS  (Claude independent review — P0+P1)
test_brain_f3_boundaries.py            17/17 PASS  (F3 boundary contracts)
test_brain_f3_f2_integration.py        17/17 PASS  (F3+F2 cross-component integration)
─────────────────────────────────────────────────────────────────────────────────
TOTALE                                 67/67 PASS
```

### Regressions note — debito tecnico Grok (non introdotte da questa integrazione)

`test_brain_f2.py` (5 test) e `test_brain_f2_safety_contract.py` (10 test) falliscono
perché chiamano `BrainEngine()` senza `risk_policy=` e `journal=`. Erano suite scritte
prima dei P0 fix di Grok. Con il vecchio engine.py su F3 passavano; con il P1 engine.py
(che rende obbligatori risk_policy e journal) falliscono. **Non è una regressione
introdotta da questa integrazione.** Grok deve aggiornare le proprie vecchie suite
in `work/v3-brain-f2-grok`.

### P1 fix verificato nell'integrazione

```python
# engine.py riga ~368 — defense-in-depth, indipendente da F1
if mp["paused"] or not mp["market_data_fresh"] or mp["daily_loss_latched"]:
    decision.kind = DecisionKind.NO_TRADE
    decision.status = ProposalStatus.RISK_REJECTED
    decision.rationale = "market_gate"
    return decision
```

---

## Status gate

- ✅ Fase 0 completata
- ✅ PR #36 DRAFT aperta
- ⛔ Nessun merge/deploy
- 🔜 Prossimo: Grok corregge 15 suite legacy (`risk_policy=`, `journal=`), poi Fase F4

## Gate aperti (invariati)

- Trust anchor Ed25519 reale per policy_verifier (solo mock sintetico)
- Trasporto HTTP DeepSeek/Claude + budget ledger (F4 non iniziato)
- Executor PAPER reale (F5 non iniziato)
- Backup off-host certificato (F0 VPS — richiede OK utente + Termius)
- Import 534 trade legacy (bloccato fino a backup certificato)
- DESK_MODE=paper (invariato)
- Hawk/Bull: non toccati
