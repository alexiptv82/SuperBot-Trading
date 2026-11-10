# SuperBot V3 — ripartenza PAPER rapida e misurazione risultati (10/11/2026)

**Obiettivo:** avere **Falco, Toro e Brain** in esecuzione PAPER e poter misurare trading e apprendimento, senza trasformare la ripartenza in un nuovo progetto di sicurezza.

**Stato di questo documento:** procedura preparata, **NON eseguita sulla VPS**. Deriva dalla RC84 Draft `0e29a73a36f668643da4088178bacb8616a45ac0` (PR #80), non da un merge. Nessun reset, deploy, riavvio, nuovo wallet o ordine effettuato creando questo documento. Prima di operare sulla VPS serve un OK separato al rilascio/avvio. Ultimi inventari veri: [#42891405554](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/42891405554), [#42893620386](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/42893620386), [#42893962748](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/42893962748).

## Stato verificato sulla VPS Singapore
- `superbot`/dashboard: running, build RC73, PAPER, cutover web in sola lettura. **Non è la RC84 candidata**.
- `superbot-desk-hawk` e `superbot-desk-bull`: exited, restart=no, DESK_MODE=paper, pause.flag presente, **0 posizioni aperte**; storici e apprendimento presenti. Servizi legacy `superbot-v3-falco-exit` e `superbot-v3-toro-exit` attivi e attualmente separati dai processi di strategia spenti.
- Backup locale RC77: esiste una copia per cui tutti gli hash elencati nel manifesto coincidono con quelli dei file classici correnti; il manifesto registra una prova di ripristino precedente **PASS**. Non è un backup fuori host, ma è sufficiente come punto di ripristino locale per una prova PAPER controllata, se resta invariato.
- Brain V3: `/opt/superbot-v3-paper-runs/brain-v3-rc20261106` è una vecchia run **preparata, in pausa e con mandato NON approvato**. Ha journal e budget ma nessun heartbeat attivo. La configurazione on-host **non prova** min leverage 20 / max 50 (campi mancanti, null o non interi). **Non modificare in-place né cancellare questa run**.
- `V3_ALLOW_BRAIN_SINGLE_CLOSE` sulla web attuale non è abilitato; nessun exit worker Brain operativo attestato. NON dichiarare il tasto Brain pronto sul server.

## Configurazione di ripartenza da rispettare (non attiva)

| | Falco | Toro | Brain |
|---|---|---|---|
| Equity iniziale PAPER | 1.000 USDT | 1.000 USDT | 2.000 USDT |
| Strategia | SHORT storica + Claude + LONG S25 + osservazione trend | SHORT storica + Claude + LONG S25 + osservazione trend | DeepSeek + journal decisioni e uscite + feedback dai classici in sola lettura quando disponibile |
| Stato | NUOVA directory dati, storici legacy preservati | NUOVA directory dati, storici legacy preservati | NUOVA run con journal/budget/mandato distinti |
| Chiusura manuale | Sì, nella nuova run dopo prova | Sì, nella nuova run dopo prova | Sì, solo dopo health reale dell'exit-sidecar e opt-in web |

Brain, configurazione già esistente sul ramo RC84: `backend/v3/runner/runner_config_brain2000_paper.json`. Valori verificati sul file: leva min20 max50; quota massima margine per trade 20% di 2000 = 400 USDT; rischio di perdita stimata per margine 0,214285714... = **75 USDT su 350**; rischio stimato aperto aggregato 12% di 2000 = **240 USDT**; margine totale max 55% = **1.100 USDT**; protezione 450. La perdita teorica su 400 USDT potrebbe raggiungere circa 85,71 se consentita dagli altri gate: **non dire che il massimo globale è sempre 75 USDT**. Cap/day DeepSeek 0,75 USD; cycle_minutes 60; NO_TRADE è valido.

I classici in RC84 consultano effettivamente Claude tramite `backend/desk/cli.py`. Il modulo `trend_change.py` entra tramite `signals.py` e viene incluso nel prompt in `brain.py`. S25 è **opt-in** esclusivamente PAPER: `DESK_LONG_S25=1`; mai attivarlo in LIVE come effetto di questo piano. Le posizioni SHORT storiche non vanno cambiate retroattivamente. La strategia S25 sceglie leva 15x di default: non confondere con il requisito 20–50x **del solo Brain**.

## Procedura breve — fasi ordinate, con stop espliciti

### A. Preparazione tecnica non operativa
1. Pin della RC84 esatta, senza modificare PR #80 o ramo `rule-pool`; non mescolare backup age V2 o PR diagnostica. Identificare staging isolato con codice completo e la build front-end da pubblicare **solo dopo OK**; osservare quale codice classico è effettivamente in produzione (oggi vecchi container fermati).
2. Ricontrollare **una sola volta al momento del rilascio** modalità PAPER del runtime web e dei tre motori, contenitori senza permesso di inviare ordini LIVE. Non leggere o stampare chiavi. Il classico ha il modulo `LiveConnector`: la modalità `DESK_MODE=paper` deve rimanere esplicita e verificata. Feed Bitget per dati pubblici; aperture/uscite sono nel simulatore, non su Bitget.
3. Verificare che il backup locale RC77 non sia cambiato (già PASS al 10/11). Conservare vecchie run e posizioni/chiusure nei loro archivi, non resettare storici.

### Verifica aggiuntiva del bootstrap classico (lettura codice RC84)

`backend/desk/cli.py` costruisce `PaperAccount(PORTFOLIO.limits, "main")` quando lo stato non contiene `main`; i profili `_make_hawk_config` e `_make_bull_config` hanno entrambi `start_equity=1000`. `PaperAccount.__init__` inizializza cassa a `start_equity` e posizioni vuote. Questo dimostra il comportamento previsto **del codice candidato**, non dimostra ancora che la versione realmente installata sul server parta correttamente su un volume nuovo. Prima del primo start creare `pause.flag` sulla NUOVA directory e configurare esplicitamente `DESK_MODE=paper`, `DESK_PORTFOLIO=hawk|bull`, `DESK_DATA_DIR=<nuova dir>`. `live_connector.py` conferma che con `DESK_MODE=paper` il ramo ordini reali rimane no-op: ricontrollare i flag sul processo effettivo appena attivato.

### B. Tre nuove identità PAPER, inizialmente in PAUSA
1. **Falco/Toro:** due nuove directory con 1.000 USDT PAPER ciascuna, rispettivi portafogli/identità. Non fare `reset_portfolio.flag` sulla directory legacy. Prima di avviare verificare che i vecchi exit-only worker continuino a puntare esclusivamente alle directory legacy e che i nuovi motori si riferiscano solo alle nuove directory. Il percorso di bootstrap dei classici va verificato nel codice effettivo prima di creazione; non improvvisare copia delle vecchie posizioni.
2. **Brain:** una nuova directory mai esistita sotto `/opt/superbot-v3-paper-runs`; usare il preparatore versionato `backend.v3.runner.prepare_paper_run`. Esempio **da completare solo sullo staging approvato, NON eseguire ora**:
   ```bash
   DESK_MODE=paper PYTHONPATH="$STAGE_ROOT" python3 -m backend.v3.runner.prepare_paper_run \
     --parent /opt/superbot-v3-paper-runs \
     --run-name brain-v3-paper20261110 \
     --run-id brain-v3-paper20261110 \
     --config "$STAGE_ROOT/backend/v3/runner/runner_config_brain2000_paper.json" \
     --prepare-paper-paused --expected-initial-equity 2000
   ```
   Il comando crea file **solo nella nuova run** con `pause.flag`, `mandate.approved=false`, `journal.db`, `budget.db` e `PREPARED_PAUSED_ONLY.json`; non avvia motori. Usare un nome diverso se quello dell'esempio è già occupato. Il percorso `$STAGE_ROOT` è segnaposto: non supporre che il codice RC84 sia già installato in VPS.
3. **NON approvare il mandato Brain automaticamente.** Preparare e confrontare `policy_hash` e la configurazione nuova; la firma `approved:true` deve seguire l'OK specifico dell'utente per lo sblocco.

### C. Handover e smoke test minimo (rilascio separatamente autorizzato)
1. Exit-owner unico: per ogni run deve esserci esattamente un servizio autorizzato a scrivere chiusure. Brain: prima exit-sidecar PAPER con lease e heartbeat coerente, poi runner decisionale in split-mode; finché exit-sidecar non è sano, **niente nuove aperture**. Non consentire doppio monitor STOP.
2. Collegare web RC84 alle **nuove** run, con mount e `run_id` coerenti; non mostrare dati legacy come posizioni nuove. Abilitare Chiudi Brain solo dopo exit-sidecar attivo e test su run sintetica isolata.
3. Test minimo senza spendere ore: API/tre portafogli coerenti; pause blocca nuove aperture; heartbeat fresco; stop/manual close disponibili; due motori PAPER isolati da LIVE; chiamate dati pubblici Bitget; una prima chiamata DeepSeek solo con credito disponibile e tetto AI, senza ordini reali.
4. Solo con ulteriore consenso esplicito togliere pausa dalle nuove run, **startup cooldown 15–30 min**, nessuna chiusura forzata a mezzanotte, slot vuoto = scelta valida. Non forzare aperture per «provare» il sistema.

### D. Valutazione reale del motore PAPER (prime 48 ore e poi 7 giorni)
- Per ciascuno: numero segnali, LONG/SHORT/NO_TRADE, trade realmente PAPER, esiti netti con costi/slippage, max drawdown, posizioni non chiuse, stop/outage, motivazione errore in post-trade. Per Brain: separare decisione AI, fill simulato, outcome e aggiornamento memoria (non chiamare «apprendimento» una mera annotazione).
- Confrontare Brain con i due classici e con una baseline semplice sulle **stesse finestre**; non promettere profitti. Non giudicare da poche operazioni. Se un trade è perdente, registrare **perché** (es. trend avverso, stop, liquidazione simulata, quote vecchie, sizing) senza retrofittare la strategia sul singolo caso.
- Nessuna automazione di nuovi deploy o Actions ripetute; GitHub Actions condivise vicine al limite, preferire diagnostica mirata.

## GO/NO-GO
**GO per preparare lo staging del rilascio e studiare la nuova run**. **NON ancora GO per deploy/merge/start**: mancano installazione della RC84, nuove run su VPS, single owner Brain, collegamento della web a nuove directory, verifica runtime PAPER-only e mandato dell'utente. I backup remoti age V1/V2 sono un filone **separato**; non impediscono una prova PAPER con snapshot locale valido. L'obiettivo successivo è **operatività PAPER osservabile**, non altri test generici.
