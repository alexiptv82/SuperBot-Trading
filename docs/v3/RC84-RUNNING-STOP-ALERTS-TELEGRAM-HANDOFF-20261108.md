# RC84 — integrazione diagnostica runner RUNNING e notifica post-commit (08/11/2026)

**Tipo:** PR DRAFT, codice OFFLINE. **Base esatta:** RC82 PR #79 `1e64684b9d813aad1ca1c7d344872333e451fd05`.
**Branch:** `cursor/rc84-running-stop-health-telegram-20261108`.
**Autorizzazione dell'utente:** «perfetto possiamo procedere» dopo review RC82. **Nessun merge/deploy/riavvio/reset/VPS/nuova run** autorizzato.

## Scopo
Separare chiaramente:
1. RC80 **maintenance-only**: `exit_only_heartbeat.json`, controllo 1m close-only, legacy spento;
2. RC82 **classic runner attivo PAPER**: `heartbeat.json` e `stop_feed` su high/low di barre OHLC 15m, controlli ogni 15/30 min + durata ciclo;
3. Brain: exit-worker/lease e health **propri**, non RC80/RC82.

Non confermare mai stop certificati o ordini exchange. La nuova visualizzazione è **solo lettura**.

## Codice proposto
- `backend/v3/observability/classic_running_stop_health.py`: classificatore puro del heartbeat del runner. Verifica `portfolio`, `exec_mode=paper`, timestamp entro 60s, `last_ok`, completamento di ciclo recente entro 36min, `stop_feed.timeframe=15m`, `bar_ms=900000`, `stop_certified=false`, shape dei report e copertura dei simboli aperti; porta gli allarmi e `new_exposure.blocked_symbols` in forma sanitizzata e limited. `state='observed'` è **solo prova dell'ultimo ciclo**, non protezione continua. Se errato/stale/missing -> `degraded/stale/unverified` fail-visible. `quote_coverage` e `stop_certified` sono SEMPRE false.
- `backend/v3_api.py`: `_classic` distingue il tipo di worker, preferisce RC80 solo con `exit_only`; altrimenti se il runner è attivo/riconoscibile usa la nuova diagnostica. `GET /api/v3/overview` conserva `stop_health` ma cambia `scope` in modo esplicito, senza endpoint di comando.
- `frontend/src/components/ClassicStopNotice.js`: distinto messaggio per `classic_runner_15m_ohlc`, limiti di controllo a intervalli, nessuna promessa di SL certificato; si mostra anche con **zero posizioni** se `blocked_symbols` segnala feed inaffidabile. RC80 rimane invariato.
- `frontend/src/pages/Dashboard.js`: lettura dell'overview separata dalle chiamate Brain; un errore Brain non cancella gli allarmi classici. Errori overview cancellano segnali vecchi.
- `frontend/src/pages/Overview.js`: rendering di Falco/Toro non dipende dalle API Brain status/trades/scoreboard. Se i dettagli Brain falliscono: niente pulsanti Brain e niente PnL aperto inventato.
- `backend/desk/cli.py`: `notify_close` Telegram **dopo** `_prove_protective_close` e `save_state`, mai prima. Se Telegram non risponde, la contabilità resta valida. Invariati stop/priorità, AI, ordini, risk e sizing.

## Test SCRITTI ma NON ancora eseguiti su runner indipendente
- Nuovo `backend/tests/test_v3_rc84_running_stop_health.py`: classificatore, heartbeat stale/futuro, ciclo fallito, modello sbagliato, unverified, portfolio mismatch, feed missing/future/stale, blocked_symbols con zero posizioni, cablaggio `_classic`.
- Integrazione in `backend/tests/test_v3_rc82_active_paper_stops.py`: regressioni su history non durevole, save_state fallito e Telegram down.
- Test Jest ampliati `ClassicStopNotice.test.js`, `ThreePortfoliosNavigation.test.js`, `Overview.test.js`, includono allarmi classici ancora visibili con Brain non disponibile.

**Stato al momento della consegna:** SHA RC84 ancora da pinning, nessuna CI/test/build eseguita da ChatGPT. Richiedere a Grok o Claude collaudo offline SENZA VPS su SHA della PR e log dei comandi. Non chiamare PASS in anticipo.

## Comandi suggeriti — sandbox isolata SENZA segreti né connessioni di mercato
```bash
# checkout sulla SHA esatta della PR, PYTHONPATH=.:backend, no network.
PYTHONPATH=.:backend python3 -m pytest -q -p no:cacheprovider --tb=short \
  backend/tests/test_v3_rc84_running_stop_health.py \
  backend/tests/test_v3_rc82_active_paper_stops.py \
  backend/tests/test_v3_rc81_classic_stop_health.py \
  backend/tests/test_v3_rc80_paper_stop_hardening.py \
  backend/tests/test_v3_rc78_paper_stop_monitor.py \
  backend/tests/test_v3_classic_exit_only.py

cd frontend
CI=true npx --no-install react-scripts test --watchAll=false --runInBand \
  --testPathPattern='ClassicStopNotice|Overview|ThreePortfolios'
CI=true npx --no-install react-scripts test --watchAll=false --runInBand
CI=true BUILD_PATH=/tmp/rc84-frontend-build npx --no-install react-scripts build
```
Eseguire `backend/tests/test_desk.py` in sandbox se la suite veloce è verde; eventuali fixture sintetiche NO edit per mascherare errori. Registrare SHA testato e test PASS/FAIL.

## Gate esplicitamente aperti
- Test in browser autenticato e su smartphone Android, confronto Falco/Toro/Brain, abort/refresh/rete down.
- Controllo dell'effettiva cadenza degli stop del motore attivo e accettazione del modello 15m OHLC, non tick per tick; wick ingresso invisibile.
- Brain RC83: test offline 4.849 PASS riferiti da Claude, ma sidecar non presente/certificato sulla VPS. `--legacy-exits-disabled` è solo un'asserzione, NON spegne il writer storico: handover tecnico single-owner da certificare.
- Backup off-host + restore, preflight VPS READ-ONLY su mandato distinto, integration branch/release candidate pinned e approvazione specifica del nuovo run PAPER Falco/Toro 1.000 / Brain 2.000, storici preservati.

**NO MERGE / DEPLOY / VPS / RESTART / RESET / OREDINI REALI.**
