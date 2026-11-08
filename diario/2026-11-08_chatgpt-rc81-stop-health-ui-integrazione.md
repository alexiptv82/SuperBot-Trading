# RC81 — Integrazione dello stato stop PAPER nella V3, 8 novembre 2026

**Autorizzazione utente:** «ok procediamo» dopo la review statica RC80. Perimetro: sviluppo/inventario offline, **non** autorizzazione a merge/deploy/riavvio/reset/VPS.

## Repository e branch
- Branch isolato `cursor/rc81-stop-telemetry-ui-chatgpt-20261108` da RC80 `50b75b9643680b9c758047d3890f3599b051f325`. Branch `cursor/` scelto per evitare trigger workflows VPS.
- [PR #78 DRAFT](https://github.com/alexiptv82/SuperBot-Trading/pull/78) verso PR #77 / RC80, non verso main.
- File modificati: `backend/v3/observability/classic_stop_health.py`, `backend/v3_api.py`, `frontend/src/components/ClassicStopNotice.js`, `frontend/src/pages/Overview.js`, `frontend/src/pages/Dashboard.js`; test `backend/tests/test_v3_rc81_classic_stop_health.py` e `frontend/src/pages/ClassicStopNotice.test.js`, handoff `docs/v3/RC81-CLASSIC-STOP-HEALTH-UI-HANDOFF-20261108.md`.
- PR #74 Brain, PR #72 dashboard (già antenate di RC80), PR #76 RC79 diagnostica (ramo separato) non modificate.

## Cosa fa
- API `/api/v3/overview` espone per Falco/Toro `stop_health` da heartbeat `exit_only_heartbeat.json`, lettura senza side effect e con controlli per identità, stale/future, stop opt-in, telemetria, modello close-only.
- UI **I tre portafogli** e **Classici**: avviso in presenza di posizioni PAPER quando stato stop non verificato, feed blind/partial, telemetria fallita o worker non attivo. Mai proclamare copertura stop certificata: `covered` = prezzi recenti di candele 1m chiuse, senza fill intrabar.
- Dopo errore di fetch API su `Classici`, azzera vecchi indicatori invece di mostrare `covered` ormai scaduto.
- Non cambia engine, Claude/DeepSeek, strategie, trading loop, margine, policy o prezzo di uscita.

## Stato test e sicurezza
- **Test sintetici scritti, NON eseguiti indipendentemente finora**. Nessun workflow CI/GitHub Actions o preflight VPS lanciato. PR #78 deve restare Draft.
- Servono comandi pytest e Jest + build su SHA esatto in sandbox senza segreti/VPS, poi review indipendente e test e2e.
- La protezione RC80 è valida solo con classici FERMI; gli stop durante trading RUNNING sono un gate separato. Stop close-only 1m non equivale a stop eseguito sui wick/intraminuto. Non autorizzare avvio finché non è una policy cosciente e verificata.
- Backup esterno NON certificato; Brain PR #74 chiusura manuale offline; nuova run 1000/1000/2000 NON avviata; storico precedente intatto. Ultimo audit VPS RC77 Falco/Toro 0 posizioni PAPER, Brain paused. Nessun audit VPS in questa attività.

**Prossimo passo:** collaudo offline riproducibile su commit RC81 + regressioni RC80, verifica UI Android e coerenza con Brain, analisi protezione degli stop del motore RUNNING. Poi backup/off-host, preflight VPS in sola lettura e consenso specifico prima di ogni nuova run/deploy.
