# SuperBot V3 — 2026-11-03 — ChatGPT audit Brain F2 R1.3: NO-GO (9 FAIL, 1 PASS)

**Evidenza:** archivio caricato dall'utente `v3-brain-f2-r1.3-20261103.tar.gz`, 15374 byte, SHA256 realmente calcolato `8887cbf58c1148e425a6519bf9c0c84ff7bf1de90d5578a4f393e59840e2324f`. Tar con 13 elementi, estrazione isolata verificata senza symlink/traversal. I Git blob F1 inclusi `events.py` (`cd4ce09233cdfc41be43dd7083aac791e8e2c56d`) e `risk.py` (`514159b990c99740aee4f73b3bdd8839226e65bc`) coincidono con PR #33.

## Test verificati indipendentemente
- Python **3.13.5**, quattro moduli F2 inclusi: **34/34 PASS**.
- Python **3.13.5**, 10 nuovi test di sicurezza: **9 FAIL, 1 PASS** (enum DecisionKind sconosciuto respinto correttamente).
- Dichiarazione Grok **139 PASS** su Python 3.10/3.11: **non riprodotta** da ChatGPT con tali interpreti, né suite F1 completa nel pacchetto.
- Nessun test ha avuto accesso a VPS, API AI, exchange, wallet o mercato vero; solo SQLite temporaneo.

## Blocchi riprodotti, priorità R1.4
1. **4 input NaN approvati:** in `_apply_risk_gate`, `_finite(...) or Decimal("0")` tratta `NaN` in `margin_used`, `existing_open_risk`, `maintenance_fraction` e `minimum_notional` come zero e permette `OPEN/APPROVED` (risk quote allowed). Fail-closed obbligatorio; mai default zero su input malformato.
2. **Journal non durevole aggirabile:** sottoclasse di `EventJournal` con `append()` no-op passa `isinstance` e permette APPROVED senza registrazione. Verificare contratto append / persist e ritorno; robustezza a wrapper non affidabili.
3. **Prezzi incoerenti:** contesto 50000 e proposta entry 1000/stop 980 (stesso simbolo) genera APPROVED. Validare market price/quote con tolleranza esplicita e fresca; non inventare soglie operative.
4. **AI input malformato:** `sources=[{}]` causa `TypeError: unhashable type: dict`, non fail-closed.
5. **Leak risposta/memoria:** rationale non attendibile contenente stringa fittizia simile a token è riportata in output e `self.memory`, anche se payload SQLite è ridotto/sanitizzato.
6. **Concorrenza:** due engine su stesso SQLite, sincronizzati fra `list_run` e `append`, ricevono **due OPEN/APPROVED e un solo evento**. Time-of-check/time-of-use: EventJournal.append idempotente restituisce evento esistente, ma engine considera entrambe le append nuove. Serve claim/idempotenza atomica, non solo pre-lettura.

**Test riproducibili su GitHub:** `diario/2026-11-03_brain_f2_r14_independent_regressions.py` (commit `a7a9fcfe18e16c3d1e89165b2cf4a8fb7bbcaf9e`). Eseguire su tarball R1.3 estratto in workspace offline, collocando il test in `backend/tests/` e usando `PYTHONPATH=. python -m pytest -q backend/tests/test_brain_f2_r14_independent_regressions.py`.

## Altri gate da chiarire
F1 `RiskPolicy` non espone un campo di versione né una prova dell'approvazione dell'operatore. Il vincolo di policy approvata e versionata non è certificato dal solo adapter F2; definire un contratto/metadata prima di promozione. Nessuna modifica automatica a F1.

## Decisione
R1.3 **NON accettata** e **NON integrata in PR #33**. Rimane DRAFT. Richiesto ciclo Grok **R1.4 offline**: correggere i 9 fail, preservare contratti F1, rieseguire i test e la suite F1+F2 su Python 3.10/3.11, consegnare tarball scaricabile e SHA256 calcolato sul file finale. Nessun merge/deploy/reset/restart/VPS.
