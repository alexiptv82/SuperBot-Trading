# SuperBot V3 — Brain F2 R1.7 audit indipendente NO-GO — 2026-11-03

**Archivio realmente ricevuto:** `v3-brain-f2-r1.7-20261103.tar.gz`, SHA256 `153a266fef82b16c8e38ccd88b3603c65abbfdb96b8dae3f7aa5d4ccc8d1f028`. Estrazione sicura: 17 membri, senza traversal/symlink/link; F1 invariata: Git blob `events.py` `cd4ce09233cdfc41be43dd7083aac791e8e2c56d`, `risk.py` `514159b990c99740aee4f73b3bdd8839226e65bc`.

**Test realmente eseguiti da ChatGPT, Python 3.13.5:** suite F2 consegnata **66/66 PASS**, compileall PASS; 10 test avversariali aggiuntivi **8 FAIL, 2 PASS**. Il report Grok dichiara `171 PASS` su Python 3.10/3.11, ma questi interpreter e la suite F1 integrale non sono stati riprodotti nell'audit locale. Nessuna esecuzione su VPS/exchange/API AI o wallet.

## Otto failure indipendenti
1. Origine AI malformata: `NO_TRADE` conserva `OpenProposal` allegata.
2. Simbolo proposta incompatibile: `NO_TRADE` conserva simbolo non attendibile e token sintetico in risposta e RAM.
3. Confidence `NaN`: `NO_TRADE` conserva proposta invalida.
4. `NO_TRADE` consente `risk_quote` arbitrario iniettato dall'analista (es. dict con token sintetico), visibile in risposta/memory.
5. `OPEN` con proposta dict malformata è rifiutato ma la proposta originale resta nella decisione e nella memoria.
6. `HOLD` con `status` AI di tipo dict viene restituito come dict, non `ProposalStatus`.
7. `policy_verifier` che restituisce stringa `"yes"` (truthy) è trattato come prova autorizzata; il risultato deve essere strettamente booleano valido.
8. Mandato con `portfolio_id='hawk'` e `run_id='unrelated'` accettato su Brain se verifier restituisce True: il contratto non vincola in modo obbligatorio portfolio/run.

## Due controlli PASS
- Senza alcun verifier esterno: no OPEN APPROVED.
- Con verifier iniettato che approva il corretto hash: OPEN APPROVED come **proposta**, senza dichiarare EXECUTED_PAPER.

**Nota sulla fiducia:** la presenza di una callable non dimostra di per sé autenticazione o autorità dell'operatore. Una integrazione reale del verificatore deve avere un trust anchor fuori dal codice dell'analista AI e associare mandato a policy/versione/portfolio/run. Non inventare firme o chiavi.

## Nuovo incarico Grok R1.8
Correggere per classe di problemi, non continuare patch puntuali: introdurre un'unica normalizzazione definitiva che costruisca output nuovo, tipizzato, privo di `proposal` e `risk_quote` non certificato su qualsiasi `NO_TRADE/HOLD/REJECTED`, prima di return, memoria o journal. Validare `ProposalStatus` e ogni input non attendibile. `policy_verifier(...)` deve tornare **esattamente `True`**, e la prova autorizzativa deve avere scope portfolio Brain/run e policy/version/hash; assenza/errore -> fail-closed. La sorgente fidata per il verifier è un **prerequisito esterno da implementare**, non una stringa `approved_by`.

Test riproducibili: `diario/2026-11-03_brain_f2_r18_independent.py` su questo branch, da collocare in `backend/tests/` nel checkout isolato R1.7. Report + codice test + log disponibili in pacchetto audit ChatGPT.

**Gate:** test inclusi + indipendenti PASS, suite F1+F2 Python 3.10/3.11 tramite CI su branch separato, verificare che non ci siano nuove eccezioni/secret leak. Non modificare F1, non bypassare test. Tarball R1.8 scaricabile, SHA256 calcolato sul tarball finale.

**Decisione:** R1.7 NON integrata nella PR #33. PR #33 resta DRAFT. Nessun merge, deploy, restart, reset, operazioni VPS o API AI reali.