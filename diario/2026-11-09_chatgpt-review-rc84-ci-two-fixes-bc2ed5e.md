# SuperBot V3 — ChatGPT review RC84 CI offline a due stati e timeout (09/11/2026)

## GitHub e vincoli
- [PR #80 Draft](https://github.com/alexiptv82/SuperBot-Trading/pull/80) head `bc2ed5e909a156961a8a73ae8d6fd59480cd3112`, base RC82 `1e64684b9d813aad1ca1c7d344872333e451fd05`, non mergeata, non deployata.
- Codice/test/documento commit `a3369810638a711cee31dd870e7b97658c66212d`; commit finale modifica solo handoff.
- [Commento review ChatGPT su PR #80](https://github.com/alexiptv82/SuperBot-Trading/pull/80#issuecomment-6748735015).
- Il file `.github/workflows/rc84-offline-verify.yml` è **ASSENTE (404 verificato)**, YAML ancora soltanto nel documento `docs/v3/RC84-CI-OFFLINE-PROPOSAL-20261109.md` e **nessun workflow Actions su HEAD**. Nessun accesso VPS, merge, deploy, restart, reset o ordine.

## Esito code review: i due ultimi mini-fix sono implementati
1. Il vecchio test proponeva workflow solo assente, impossibilitando la prima CI. `backend/tests/test_v3_rc84_ci_proposal.py` ora usa `workflow_state_problems()` per ammettere due stati: file `.github/workflows/rc84-offline-verify.yml` assente (proposta inerte); file presente esattamente uguale al YAML del documento (futuro publish autorizzato). Normalizzazione limitata CRLF/spazi terminali/righe perimetrali; altri workflow con stesso nome, copie, symlink e file manomessi rifiutati. 25 test dichiarati con directory temporanee, inclusi 11 mutazioni.
2. `backend/tests/test_superbot.py::_Guarded` impone timeout default 10, massimo 30 secondi; `_valid_timeout` rifiuta prima di HTTP None, bool, non numerici, nan, inf, zero, negativo e >30. Coperto da test parametrizzati con spia HTTP; restano URL effettivo whitelist localhost/stessa porta, nessun redirect, trust_env=False no proxy.
3. Altri file: aggiornamenti soltanto ai due test precedenti e documento proposta + handoff; nessuna logica applicativa trading, AI, risk, Brain, D1, D2, UI toccata.

## Evidenza test dichiarata da Claude (NON rieseguita da ChatGPT)
Backend offline Python3.11, namespace rete vuoto, due copie con file workflow reale assente / scratch con YAML approvato identico: **7.003 PASS / 0 FAIL / 9 deselected / 3 xfailed**. Frontend Jest **124/124 PASS**, build React `CI=true` PASS. 9 integrazioni server **non eseguite**; 3 xfail attesi. Nessuna CI GitHub sullo SHA.

## Decisione e prossimo consenso
**Proposta CI OFFLINE APPROVED per passare all'attivazione controllata, MA SOLO previo OK esplicito utente; nessuna azione è stata eseguita.** Se autorizzato, pubblicare in singolo commit **solo** YAML approvato di `docs/v3/RC84-CI-OFFLINE-PROPOSAL-20261109.md` dentro `.github/workflows/rc84-offline-verify.yml`, sul ramo Draft della PR #80, commit senza `[skip ci]`, nessuna modifica main né a workflow operativi. Il push può attivare automaticamente CI con due job backend/frontend senza segreti, rete isolata (`sudo -n unshare -n`), `integration` esclusi. Il preflight su runner GitHub-hosted Ubuntu24.04 **non provato** può fallire; fallimento deve bloccare i test (mai fallback con rete aperta). Revisionare run e SHA generato, report GitHub con conteggi e log. 
Release resta **NO-GO**: browser autenticato/Android, stack PR #76 e due commit main, staging password bootstrap statica da rimuovere/ruotare se attiva previa mandato, backup off-host restore, Brain legacy→sidecar test su sistema reale solo con mandato, preflight VPS read-only separato, accettazione stop classici OHLC 15m periodici, nuova run **SOLO PAPER** Falco/Toro 1000 USDT Brain 2000 USDT con storico/learning intatti e autorizzazione utente esplicita.

**NO MERGE / DEPLOY / VPS / RESTART / RESET / ORDINI.**
