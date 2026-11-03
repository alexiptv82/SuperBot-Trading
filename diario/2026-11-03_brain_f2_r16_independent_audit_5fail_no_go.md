# SuperBot V3 — Brain F2 R1.6 audit indipendente, 2026-11-03

**VERDETTO: NO-GO, NO MERGE/DEPLOY/VPS.** Archivio reale `v3-brain-f2-r1.6-20261103.tar.gz` (18.837 byte); SHA256 `664dcb0673101d74e566de5493621626b3b84f4c0f2b2780715073dfbc904452`. Estrazione sicura (16 elementi). Test R1.6 del pacchetto: **61/61 PASS Python 3.13.5**. Nuovi test indipendenti: **5 FAIL, 2 PASS**. Il rapporto Grok dice 166 PASS per Python 3.10/3.11: non verificato dall'auditor, interpreti e suite F1 completa non disponibili.

F1 invariata, verificati Git blob:
- `backend/v3/events.py` `cd4ce09233cdfc41be43dd7083aac791e8e2c56d`
- `backend/v3/risk.py` `514159b990c99740aee4f73b3bdd8839226e65bc`.

## Cinque blocker riprodotti

1. **Autorizzazione policy falsificabile:** `_TRUSTED_APPROVERS={'operator','system-admin'}` non autentica alcun operatore. L'engine accetta una policy mandate costruita interamente dal chiamante, con `approved_by='operator'`, `approved=True` e hash calcolabile `_policy_hash(policy)`, producendo OPEN/APPROVED. Binding dell'hash != verifica dell'autorità. Non c'è trust anchor esterno reale: deve essere **NO_TRADE** fino a verifica autentica.
2. `OpenProposal.context_hash` accetta contenuto sintetico sensibile e lo restituisce in output e memoria RAM senza validazione/normalizzazione.
3. `OpenProposal.rationale` non-string (esempio dict) conserva dati sensibili sintetici in output e memoria; filtro agisce solo se tipo str.
4. `NO_TRADE` con `OpenProposal` allegata rimane con proposta in risposta e memoria; nessuna esecuzione reale osservata, ma rappresentazione ambigua/non sanificata.
5. `originating_ai` di tipo dict genera `TypeError: unhashable type: dict` anziché fail-closed.

Due controlli PASS: OPEN valido resta proposta, non esecuzione, con un evento SQLite; un mandate con hash policy errato viene rifiutato.

## Correzione successiva proposta (R1.7, offline)

- Separare **autenticazione** dal semplice confronto di stringhe: interfaccia verificatore fidato/receipt verificabile, vincolato a policy/versione, portfolio/run, identità operatore; in assenza di prova genuina, NO_TRADE.
- Validation boundary che **ricostruisca** decisione/proposta con valori validati (allowlist e tipi stretti) prima di esporre/memorizzare input AI. Controllare `context_hash`, rationale non-string, origine non-string, e ripulire qualsiasi proposta quando `NO_TRADE/HOLD/REJECTED`.
- No indebolimento test, test avversariali + fuzz/property-based sui campi ai, suite F1+F2 su Python 3.10/3.11, report e tarball scaricabile con SHA finale.
- Non modificare F1 senza ticket specifico; R1.6 **NON integrata** in PR #33.

**File di riproduzione:** `diario/2026-11-03_brain_f2_r17_independent_adversarial.py` e pacchetto consegnabile da ChatGPT con output pytest. Nessun comando VPS, trading reale/PAPER, chiave, merge, deploy, reset o restart.