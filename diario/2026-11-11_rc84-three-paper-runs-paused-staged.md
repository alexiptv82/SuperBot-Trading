# 11 novembre 2026 — RC84 staging Singapore riuscito, tre nuove run PAPER preparate in PAUSA

**FATTO, VERIFICATO DA LOG GITHUB ACTIONS:** [run 42967077990](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/42967077990) STATUS=completed, CONCLUSION=success, job 130346659552 SUCCESS, commit trigger `6a67c5e4b24451f736e032e87efb9ffc43b4de02`. Alle 05:38:27–05:38:47 UTC del 2026-11-11 (06:38 Europe/Rome) i due script hanno operato in maniera isolata sulla VPS Singapore.

**Autorizzazione:** utente «perfetto puoi andare avanti» dopo il piano di preparazione staging e tre run in pausa. **Ambito eseguito:** staging del codice e creazione delle tre NUOVE directory PAPER PAUSED. **NON** autorizzata o eseguita attivazione strategie, rimozione pausa, mandato Brain, merge PR #80, modifica al web produttivo o ordini Bitget.

## Sequenza eseguita e output verificato

1. Workflow di scopo esclusivo `.github/workflows/v3-paper-paused-stage-once.yml` sul ramo `main`, path trigger `deploy/v3-paper-stage.trigger`; esecuzione GitHub Actions singola.
2. Checkout degli script da commit PIN `136373351a75238f101df20d46c2d257c99de822` del ramo `work/paper-restart-prep-20261110`; verifica hash blob GitHub e sintassi Bash riuscite.
3. Connessione SSH Singapore con host key ed25519 pinned e segreto GitHub (mai stampato).
4. `v3-rc84-stage-source-only.sh --dry-run`: `RC84_STAGE_SOURCE_DRY_RUN=PASS`, nessuna scrittura.
5. `--stage-source`: `RC84_STAGE_SOURCE_PINNED=0e29a73a36f668643da4088178bacb8616a45ac0`, `RC84_STAGE_ONLY_FILES_INSTALLED=True`, `RC84_PRODUCTION_UNCHANGED=True`.
6. `v3-rc84-prepare-three-paper-paused.sh --dry-run`: `RC84_PREP_DRY_RUN=PASS`, tutte e tre le directory nuove disponibili.
7. `--prepare-paused-paper`: `RC84_THREE_PAPER_RUNS_PREPARED_PAUSED=True`, `RC84_BRAIN_MANDATE_APPROVED=False`, `RC84_NO_CONTAINER_STARTED=True`, `RC84_NO_LEGACY_FILES_TOUCHED=True`, `RC84_RELEASE_NOT_INSTALLED=True`.
8. Output finale `RC84_STAGE_WORKFLOW_COMPLETED_PAUSED_ONLY=True`, `RC84_NO_PRODUCTION_DEPLOY_NO_START=True`. Job SUCCESS.

## Nuove directory PAUSED

- Falco/Hawk: `/opt/superbot-v3-paper-runs/classic-hawk-paper20261111`; `pause.flag`, metadato PAPER 1000 USDT. **Nessun `state_v2.json` iniziale**: il vero conto sarà inizializzato dal motore classico al primo avvio separatamente autorizzato, mantenendo la pausa.
- Toro/Bull: `/opt/superbot-v3-paper-runs/classic-bull-paper20261111`; come sopra, 1000 USDT.
- Brain: `/opt/superbot-v3-paper-runs/brain-v3-paper20261111`; bootstrap con `backend.v3.runner.prepare_paper_run`, profilo RC84 `runner_config_brain2000_paper.json`: capitale PAPER 2000, leva 20–50x, rischio aggregato 12%, floor 450. Contiene journal SQLite, budget, `pause.flag`, marker e **mandato non approvato**.

**Le vecchie directory e dashboard RC73 non sono state migrate/aggiornate.** L'originale `brain-v3-rc20261106` non è stato modificato. Servizi `superbot-v3-falco-exit` e `superbot-v3-toro-exit` esistenti non sono stati fermati né ripuntati alle nuove directory.

## Prove locali prima dell'operazione
- Script staging e preparatore: `bash -n` OK su byte identici al GitHub blob.
- Preparatore: **5 test procedurali in ambiente sintetico, 5 PASS**, eseguiti localmente: default dry run senza scritture, creazione in pausa con stub Brain, rifiuto staging dirty, rifiuto Python venv assente prima di scrivere, rifiuto secondo prepare / modalità sconosciuta. **Non** equivalgono a test integrati del vero runner Brain, che è invece stato usato dallo script sul VPS e ha completato il bootstrap in modo positivo.
- Nessuna suite massiva CI V3 ripetuta; costo Actions limitato a **un singolo workflow di staging**.

## Stato e prossime operazioni (non eseguite)
- **PAPER in produzione ancora FERMO**: nessun runner strategia Falco/Toro/Brain avviato, nessun nuovo ordine.
- Prossima fase: predisporre montaggio web RC84 alle **nuove** directory e i servizi PAPER, senza doppio exit owner; testare UI e heartbeat con tutte e tre le run in pausa. Il tasto `Chiudi ora` Brain va abilitato soltanto dopo exit-sidecar indipendente sano e coerente con run_id; nel web RC73 è disabilitato.
- Prima di attivare le nuove aperture: consenso distinto dell'utente per **rilascio web/servizi, mandato Brain e rimozione delle pause**. Mantenere startup cooldown 15–30 min, no LIVE, no forzatura slot, niente chiusure a mezzanotte. Alla prima operatività raccogliere PnL netto simulato, stop, costi e outcome AI.
- Backup remoto age V2 è filone separato: snapshot locale RC77 dei classici ancora l'ultimo verificato in sola lettura; non confondere con un nuovo backup di Brain.

**Consegna codice:** [ramo work/paper-restart-prep-20261110](https://github.com/alexiptv82/SuperBot-Trading/tree/work/paper-restart-prep-20261110), [PR #80 Draft](https://github.com/alexiptv82/SuperBot-Trading/pull/80) invariata; niente merge.
