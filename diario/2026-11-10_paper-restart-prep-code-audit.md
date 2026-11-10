# 10 novembre 2026 — SuperBot V3: pacchetto rapido di ripartenza PAPER preparato

**Stato:** codice e configurazioni esaminati, piano pratico pubblicato; **nessuna modifica VPS**, niente restart/merge/deploy/reset/ordine. La priorità resta tornare a fare trading simulato e misurare apprendimento, senza ulteriori controlli massivi.

- Ramo preparazione: `work/paper-restart-prep-20261110`, creato dal commit esatto RC84 `0e29a73a36f668643da4088178bacb8616a45ac0`, senza modificare la PR #80.
- Pacchetto completo: [PAPER-FAST-START-20261110.md](https://github.com/alexiptv82/SuperBot-Trading/blob/work/paper-restart-prep-20261110/docs/v3/PAPER-FAST-START-20261110.md).
- Commit finale preparazione: `492b6f67321e178c38cc901e961780b7e0900f6f` (sola documentazione). PR #80 ancora aperta e Draft, head invariato.

## Evidenze puntuali verificate nel codice RC84
- Profilo Brain esistente `backend/v3/runner/runner_config_brain2000_paper.json`: 2.000 USDT PAPER; rischio aggregato 12%=240 USDT; posizione margine massimo 400 USDT; per 350 USDT margine, cap di perdita teorica 75 USDT (400 margine corrisponde a circa 85,71); leva 20–50x; floor 450 USDT; ciclo decisioni 60 min e DeepSeek daily cap 0,75 USD.
- Il file standard `runner_config.json` è **una fixture da 1.000 USDT e non il profilo di rilascio**. La preparazione della nuova run Brain deve usare il profilo 2000 via `backend.v3.runner.prepare_paper_run`, sotto una directory nuova con pausa e mandato NON approvato; non modificare `brain-v3-rc20261106` on-host perché config hash/mandato sono legati al journal.
- Classici: `backend/desk/cli.py` inizializza `PaperAccount(PORTFOLIO.limits,...)` per stato nuovo, `start_equity=1000` per hawk/bull, posizioni vuote; mantiene Claude `call_claude` e le decisioni SHORT. `trend_change.advisory` è integrato da `signals.py` nel prompt `brain.py`; LONG S25 è `DESK_LONG_S25=1` (opt-in PAPER, spento di default). S25 15x attuale non è la leva 20–50x propria di Brain.
- `backend/desk/live_connector.py`: modalità `DESK_MODE=paper` produce no-op per ordini LIVE, ma il deploy deve verificare realmente tale variabile. Non riavviare i vecchi container per simulare la nuova strategia.
- La dashboard VPS osservata è RC73 e i processi classici sono fermi; servizi `superbot-v3-falco-exit` e `superbot-v3-toro-exit` gestiscono le vecchie directory, non le nuove. Snapshot RC77 locale verificato in lettura il 10/11. Brain V3 vecchia run resta pausata e senza mandato.

## Prossimo lavoro operativo (richiede autorizzazione distinta per installazione/avvio)
1. Preparare **staging della RC84 sulla VPS**, preservando la web RC73 e i dati legacy per rollback, senza scambiare i rami di backup age con il trading.
2. Creare nuove directory distinte Falco/Toro e Brain 2000, **tutte in pausa**; accertare che single-writer/exit-worker Brain e percorsi dashboard si riferiscano alle NUOVE run. Fare smoke test minimo e nessun ordine LIVE.
3. Ottenere consenso esplicito per mandato e sblocco delle tre run PAPER; startup cooldown 15–30 min; poi osservazione 48 ore / 7 giorni con costi, PnL net, drawdown, errori e progressi Brain (NO_TRADE valido).

**La creazione di questa documentazione NON equivale ad avere predisposto su VPS le nuove run.** Non dichiarare servizio attivo prima di prove runtime.
