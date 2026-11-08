# RC81 — Monitor stop PAPER: visibilità in dashboard V3 (solo read-only)

Data: 8 novembre 2026. **Branch:** `cursor/rc81-stop-telemetry-ui-chatgpt-20261108`, creato da RC80 HEAD `50b75b9643680b9c758047d3890f3599b051f325`. PR verso RC80, NON verso main. Nessun deploy.

## Obiettivo e confini
Mostrare Falco/Toro la salute del **sidecar di manutenzione PAPER** RC80, evitando di confondere il servizio di chiusura manuale con una protezione stop certificata. Il branch modifica solo lettura API/visualizzazione, non gli algoritmi, SL/TP, capitale, worker o ordini.

## Patch
- `backend/v3/observability/classic_stop_health.py`: legge esclusivamente `exit_only_heartbeat.json` nel data dir fornito dal server. Rifiuta file symlink, eccessivi, malformed, portfolio differente, mode non PAPER, heartbeat troppo vecchio/futuro, opt-in spento, modello di esecuzione inatteso, telemetria guasta. Usa la funzione pura `protection_alarm()` RC80 per il controllo temporale. Restituisce `stop_certified=False` **sempre**, `quote_coverage=True` solo per `covered` con heartbeat recente, identità corretta, opt-in ON e modello `closed_1m_close_only`.
- `backend/v3_api.py`: `_classic` include `stop_health` in ogni portfolio Falco/Toro del GET autenticato `/api/v3/overview`; nessun endpoint POST o file-comando nuovo.
- `frontend/src/components/ClassicStopNotice.js`: avviso comprensibile per le posizioni aperte, nessun disclaimer nascosto: `covered` significa *solo quotazioni recenti* e **non** stop garantito. Riporta il limite degli attraversamenti intraminuto.
- `frontend/src/pages/Overview.js`: mostra il componente nella schermata dei 3 portafogli.
- `frontend/src/pages/Dashboard.js`: lo riusa nella pagina **Classici**; i dati arrivano dalla stessa richiesta GET già esistente. Se il fetch fallisce, cancella l'ultima copertura invece di lasciarla obsoleta.
- `backend/tests/test_v3_rc81_classic_stop_health.py` e `frontend/src/pages/ClassicStopNotice.test.js`: casi sintetici positivi/negativi, stato `blind/partial/blocked/off/stale`, tipo heartbeat, modello non verificato e passaggio API / presentazione UI.

## Importante: limiti e gate
1. Il codice è **solo proposta in PR Draft**, non installato in VPS. In questo incarico i test sopra sono **scritti ma non eseguiti indipendentemente**: serve runner pulito con suite backend e frontend e build.
2. La visualizzazione RC80 è valida **solo per manutenzione con classici fermi**. Per bot con motore di trading attivo, `worker_mode != exit_only` produce `unverified`, senza affermare protezione attiva. Occorre un gate separato per stop/TP/liquidazione del motore RUNNING.
3. `covered` riguarda la presenza di una **candela conclusa di 1 minuto**, non un trigger intrabar; richiede accettazione esplicita della policy PAPER prima del nuovo avvio.
4. PR #74 Brain manual-close, PR #72 dashboard 3 portafogli (già antenate nel ramo), PR #76 RC79 diagnosi post-trade (ramo distinto), backup off-host e run iniziale `Falco=1000,Toro=1000,Brain=2000` non vengono attivati o alterati.
5. Prima del deploy: rieseguire una CI offline senza accesso VPS, validare API e frontend su tre wallet, controllare stato auth/readonly/legacy, poi preflight VPS read-only con autorizzazione separata. Prima della nuova run serve OK esplicito e backup verificato.

## Comandi suggeriti per collaudo **locale senza VPS**
```sh
PYTHONPATH=.:backend python3 -m pytest -q -p no:cacheprovider backend/tests/test_v3_rc81_classic_stop_health.py backend/tests/test_v3_rc80_paper_stop_hardening.py backend/tests/test_v3_rc78_paper_stop_monitor.py backend/tests/test_v3_classic_exit_only.py
cd frontend && CI=true npm test -- --watch=false --runInBand --runTestsByPath src/pages/ClassicStopNotice.test.js src/pages/Overview.test.js src/pages/ThreePortfoliosNavigation.test.js
cd frontend && npm run build
```
Non chiamare PASS finché l'esecuzione reale non produce log e SHA verificabili.

## Collaborazione
Grok è fermo per evitare conflitti. Se serve un carico pesante può effettuare **solo test indipendenti in sandbox**, senza cambiare questi file, prima di eventuale revisione di Claude. Il ramo canonico `diario` è gestito da ChatGPT.

**NO MERGE / DEPLOY / RESTART / RESET / VPS / REAL ORDERS.** Tutto PAPER.
