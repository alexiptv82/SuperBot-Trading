# SuperBot V3 — 2026-11-03 — Brain F2 R1.4 audit indipendente NO-GO

**Pacchetto realmente ispezionato:** `v3-brain-f2-r1.4-20261103.tar.gz` SHA256 `0e244fa37786583dad1944bc4711cc79df91af01efd975025e1bd8ffb99479e2`.
Estrazione sicura; blob F1 `events.py` `cd4ce09233cdfc41be43dd7083aac791e8e2c56d` e `risk.py` `514159b990c99740aee4f73b3bdd8839226e65bc` rimasti invariati.

## Test realmente eseguiti
- Python 3.13.5, 5 moduli F2 inclusi: **44/44 PASS**.
- Python 3.13.5, 8 nuovi casi avversariali: **7 FAIL, 1 PASS**.
- La dichiarazione Grok `149 PASS` su 3.10/3.11 non è stata riprodotta indipendentemente, poiché la suite F1 completa e quei runtime non sono nel pacchetto.

## Sette fallimenti in sei categorie
1. `BrainDecision(kind=NO_TRADE, status=APPROVED)` non è normalizzata: status APPROVED non deve essere permesso per NO_TRADE (FAIL).
2. `BrainDecision(kind=HOLD, status=APPROVED)` non è normalizzata (FAIL).
3. Una rationale AI `API_KEY=EXAMPLE_PRIVATE_TOKEN_123456789` resta in output e memoria; scrub per parole chiave insufficienti (FAIL).
4. `complexity_threshold=NaN` bypassa il reviewer, che non viene chiamato, permettendo OPEN/APPROVED (FAIL).
5. Per un singolo OPEN approvato `journal.append` è chiamato **due volte**: una nel gate OPEN e una in `_persist_and_return`; la seconda con nuovo nonce provoca conflitto silenzioso (FAIL).
6. OPEN/APPROVED ottenuto con policy F1 solo numerica, senza version-id né approvazione dell'operatore; F2 deve richiedere un mandato/versione separato senza alterare F1 (FAIL).
7. `complexity_threshold='bad'` produce TypeError invece di fail-closed (FAIL).

Il test su rationale non-string di tipo dizionario è PASS, ma non dimostra la sanitizzazione dei segreti.

## Incarico R1.5 a Grok
Partire dal **proprio R1.4**. Definire matrice kind/status completa; normalizzare le decisioni non azionabili; no `EXECUTED_PAPER`; sanificare testi non attendibili tramite allowlist prima di output, memory, SQLite; validare review threshold finito e 0..1 (no review bypass); rendere la scrittura di una decisione esattamente una sola, con prova idempotenza e crash/restart; introdurre nell'adapter F2 identificativo/versione e certificazione di approvazione della policy senza modificare F1; coprire i casi nel codice di test autonomo. Nessun limite economico inventato o modifica automatica della protezione assoluta 450 USDT.

**NON-GO:** la PR #33 rimane DRAFT e il tarball R1.4 NON è integrato. No merge, deploy, reset, VPS, AI a pagamento o wallet.
