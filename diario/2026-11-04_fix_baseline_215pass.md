# 04/11 — Fix baseline R12/R13/R19: 215/215 PASS

**AI:** Claude Sonnet 4.6
**Branch:** `work/v3-f5-paper-executor-20261104` (commit `b7cf0bd`)

---

## Cosa è stato fatto

Corretti 9 test pre-esistenti scritti da altre AI (Grok/ChatGPT) contro il
vecchio contratto `BrainEngine` dove `journal=None` produceva `NO_TRADE` da
`step()`. Il contratto corrente lancia `ValueError("journal is required")`
al costruttore.

### File modificati

**`backend/tests/test_brain_f2_r12_independent_negative.py`** (7 fix):
- `test_must_not_approve_without_persistent_journal` → `pytest.raises(ValueError, match='journal is required')`
- 5 test che omettevano `journal=` → aggiunto `EventJournal` reale via `TemporaryDirectory`

**`backend/tests/test_brain_f2_r13_independent_negative.py`** (1 fix):
- `test_no_trade_cannot_claim_executed` → aggiunto journal reale via tmpdir

**`backend/tests/test_brain_f2_r19_independent.py`** (1 fix):
- `test_missing_journal_denial_has_no_proposal_or_risk_quote` → `pytest.raises(ValueError)`

### Principio adottato

Correzione **minima**: la semantica di ogni test è preservata (fail-closed,
nessuna approvazione senza journal). Solo il meccanismo cambia: il motore
fallisce al costruttore invece che a `step()`, il che è più sicuro.

---

## Risultato

```
test_brain_f2*.py     (R12/R13/R19 inclusi)   PASS
test_brain_f3*.py                              PASS
test_brain_f4*.py                              PASS
test_brain_f5*.py                              PASS
─────────────────────────────────────────────────
TOTALE                215/215 PASS  (Python 3.13.16, 6.36s)
```

---

## Status gate

- ✅ Baseline pulita: 215/215 PASS
- ✅ Commit `b7cf0bd` pushato su branch F5
- ⛔ Nessun merge/deploy
- ⛔ Hawk/Bull non toccati, cervello intatto
- ⛔ DESK_MODE=paper invariato

## Prossimo: F6 — Dashboard unificata

Falco + Toro + Brain status in un'unica view.
