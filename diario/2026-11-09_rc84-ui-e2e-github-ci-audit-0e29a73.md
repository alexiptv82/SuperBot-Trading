# 09/11/2026 — SuperBot V3 RC84, audit CI reale e browser autenticato su ambiente sintetico

## Identità e provenienza
- PR #80 DRAFT, HEAD `0e29a73a36f668643da4088178bacb8616a45ac0`, base PR #79 RC82 `1e64684b9d813aad1ca1c7d344872333e451fd05`, NON mergeata.
- Report dettagliato di Claude trasmesso dall'utente: 71/71 verifiche browser Playwright locale con FastAPI reale, ticker/exchange finto, frontend build reale, dati PAPER sintetici, sessione sintetica, namespace isolato, nessuna richiesta di trading, 22 screenshot su scratchpad Claude (NON pubblicati).
- [Review indipendente ChatGPT in PR #80](https://github.com/alexiptv82/SuperBot-Trading/pull/80#issuecomment-6750809202).

## CI GitHub ora verificata direttamente dai log
- Run **42681449471**: https://github.com/alexiptv82/SuperBot-Trading/actions/runs/42681449471 ; è la CI offline `RC84 offline verification (TEST ONLY)` #1, 2/2 job SUCCESS.
- Job backend **129376764231**, connettore `fetch_workflow_job_logs`: riga esatta `7003 passed, 9 deselected, 3 xfailed, 110 warnings in 340.02s (0:05:40)`; quindi 0 fail nei risultati test. Python 3.11 su GitHub runner.
- Job frontend **129376764717**, log: `Test Suites: 14 passed, 14 total`, `Tests: 124 passed, 124 total`; React build `Compiled successfully.` Node22.
- Artefatti restituiti da `fetch_workflow_run_artifacts`: backend `13701834758` (116.922 bytes) e frontend `13702971052` (4.991 bytes), entrambi `expired=false`. Non scaricati; conteggi ricavati dai **log** indipendenti, NON soltanto dal report Claude. 9 integrazioni server erano `deselected`, NON PASS; 3 xfail attesi; 110 warning backend ancora disponibili per futuro triage.
- Nei log GitHub appaiono warning di deprecazione Node20 sulle action ufficiali PINNATE e applicazione del forcing Node24; CI riuscita, pianificare aggiornamento action successivo senza destabilizzare questa RC.

## Browser Playwright da report Claude (non test ChatGPT)
**71/71 PASS** su FastAPI reale `backend/server.py`, browser Chromium Playwright, build React, fake exchange `get_ticker`, exit service senza chiusure, capitale seed Falco 1.000/Toro 1.000/Brain 2.000 USDT, auth e API senza token 401 nel proxy locale, posizioni LONG/SHORT, prezzi/leva/PnL e closed trades, close manuale UI Falco/Toro/Brain (solo pending, niente esecuzione), 409 secondo close, notifiche stop observed/alarm/stale, claim pending/conflict/unknown, Brain down senza falsi 0 PnL, mobile emulato Pixel7/GalaxyS9+ con navigazione a bottoni. **Non** test Android fisico né VPS; script, risultati e 22 screenshot NON committati/pushati; non certificare come E2E su dispositivo reale o trading reale.

## Rilievi e stato decisionale
1. `backend/server.py`: catchall SPA `@app.get('/{path:path}')` installato quando `frontend/build` esiste, prima dei router desk e V3; in packaging con frontend build dentro al filesystem del backend intercetta le GET /api/desk /api/v3 e restituisce HTML 200 anche senza auth invece dei normali 401/JSON. Bug confermato dalla lettura codice, *non* prova esposizione di dati protetti: restituisce la pagina statica. Dockerfile backend attuale copia **solo backend/**, non `frontend/build`, quindi nel container normale il catchall non si abilita. **P2 condizionato** per configurazione di deploy attuale; **P1** se si prevede una build combinata. Da correggere con test di routing e auth prima di cambiare packaging, non ora senza motivo.
2. Tre CDN icone in `Dashboard.js`: jsdelivr, coincap, coinicons-api, con fallback sigla quando falliscono; P2 privacy/performance/resilienza offline. Richieste esterne sono per icone, NON API di trading.
3. Pulsante `Chiudi ora` ~77x26 px su emulazione mobile secondo Claude: target tocco ridotto rispetto a 44px consigliati; P2 accessibilità da migliorare prima di validazione fisica Android.
4. Brain formattazione PnL a 8 decimali e leva disomogenea `x10/10×`: P3 UI; unificare senza ricalcolare importi e senza cambiare i dati.
5. Scaricamento artifact non disponibile in Claude sandbox; ora **non blocker** per conteggi CI perché letti indipendentemente dai log.

## Branch e release scope
- PR #76 RC79 analizzatore post-trade offline puro, 4 file e 15 test, non antenato di #80: **rimandare integrazione read-only** con adapter e fonte verificata, senza modificare RC84 CI-green.
- Due commit PR #30/#31 F0 su main non presenti RC84 e non sono codice trading: **NON cherry-pickare ora**. PR #80 Draft, nessun merge/deploy.
- Resta ancora ignoto lo stato VPS (nessun preflight), unità Brain aggiornate non testate sotto systemd reale, backup off-host/restore, password bootstrap statica workflow staging e altri hardcoded da audire, UI Android fisico non testata, stop classici OHLC periodico non tick continuo, consenso separato per nuova run PAPER 1000/1000/2000 USDT, learning e storico preservati.

## Prossima fase proposta
Congelare SHA RC84 verificato (`0e29a73...`) e **non** pubblicare harness/screenshot senza audit di dati sensibili, pertinenza e permesso. Procedere a **audit offline codice GitHub sicurezza staging/credenziali + piano backup off-host e restore**, senza accessi VPS, workflow operativi o rotazione prima di un mandato esplicito. Preparare checklist preflight VPS read-only separata per prossima approvazione. Ulteriori fix UI in batch prima del test Android fisico, non una catena infinita di patch.

**NO MERGE / DEPLOY / VPS / RESTART / RESET / ORDINI. SOLO PAPER.**
