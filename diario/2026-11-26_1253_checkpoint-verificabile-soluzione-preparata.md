# Checkpoint verificabile SuperBot-Trading — 26/11/2026 12:53 Europe/Rome

## Esito, fonti e limiti

Checkpoint append-only di ripresa di `alexiptv82/SuperBot-Trading`, esclusivamente PAPER. Fonti consultate:

1. GitHub, ramo `diario`: `STATO.md`, checkpoint delle 11:52, RC84 PR #80 e ricerca commit/branch;
2. `/SuperBot-Ripresa/ULTIMO-STATO-SUPERBOT.md`, Library `libfile_754adf32b63881919d64ef3bc26b222a`, versione 153 prima di questa scrittura;
3. conversazioni recenti effettivamente accessibili del progetto, limitatamente ai risultati successivi alle 11:52.

Questa esecuzione non ha eseguito comandi sulla VPS, chiamate AI a pagamento, test software o azioni operative. Nessuna chat persa è stata ricostruita e nessun segreto è stato letto o pubblicato. Le prove operative restano puntuali e non certificano lo stato successivo.

## Novità verificata: soluzione rapida soltanto preparata

- Alle 12:28 Europe/Rome l'utente ha chiesto: «ok trova una soluzione rapida».
- La risposta successiva ha mantenuto i filtri di sicurezza: 25 LONG contro trend, 19 segnali sotto confidenza 0,56, 3 costi eccessivi, 3 contestazioni Claude; budget applicativo DeepSeek residuo stimato circa 0,12 USD.
- È stata proposta una nota strategica Live Evolution tramite i comandi preparatori `sudo superbot-strategia stato` e `sudo superbot-strategia proponi "Nota strategica: ..."`.
- La procedura prepara soltanto una proposta da sottoporre ad approvazione: non attiva modifiche. Non risultano prova di esecuzione, proposta generata, approvazione, installazione o cambiamento di capitale, leva, stop, soglie, servizi o budget.
- Una conversazione recente ha inoltre riferito un presunto commit EX-08B `cb31997f` con 15/15 test; la verifica GitHub sul repository non ha trovato né quel commit abbreviato, né commit/branch `EX-08B`. È quindi escluso dallo stato verificato e registrato come elemento da riconciliare, non come modifica eseguita.

## Obiettivi e decisioni invarianti

- Tre portafogli distinti e confrontabili: Falco, Toro e Brain; capitale simulato, EventJournal, archivi e sessioni di apprendimento preservati.
- Trading esclusivamente PAPER. `NO_TRADE` e slot vuoti restano risultati validi; nessun passaggio LIVE implicito.
- Nessun allentamento automatico di trend, confidenza, costi o veto Claude per riempire gli slot.
- Ogni modifica operativa, di rischio o budget richiede approvazione separata. La richiesta di una soluzione rapida non equivale ad autorizzazione a eseguire i comandi preparati.

## Tre portafogli PAPER: desiderato contro implementato

| Portafoglio | Desiderato | Implementato/verificato | Stato più recente dimostrabile |
|---|---|---|---|
| Falco | classico distinto, strategia e storico preservati; evoluzione solo con autorizzazione | Falco classico preservato; Falco Evoluto installato il 23/11, poi archiviato/disabilitato con la nuova sessione Brain V2 | nessun nuovo controllo live |
| Toro | classico distinto e storico preservato | storico preservato; resta `semantic_not_certified`, quindi integrità tecnica non equivale a correttezza semantica | non è il bot corrente mostrato dalla dashboard Brain |
| Brain | portafoglio unico PAPER da 2.000 USDT, DeepSeek principale, Claude revisore, memoria collegata | run `brain-scalp-paper-p1`, 27 strumenti, 10 slot; vecchia run archiviata con 539 eventi e tre sessioni collegate in sola lettura | ultima prova operativa resta quella delle 11:28: runner/uscite sani, zero aperture, filtri attivi; nessuna prova live più recente |

## Configurazione e rischio: desiderato contro implementato

- Profilo B precedente: tetto esplicito di quattro posizioni e rischio aperto comprensivo dei costi; integrazione `c11e6d7d…`, piano `302e94d2…`.
- Issue #124: correzione `0f71d0be…`, integrazione `5f110379…`, chiusa il 22/11. Il latch deve bloccare nuove aperture senza impedire le uscite.
- Brain V2 documentato come installato: ciclo 30 minuti; leva dinamica 15–50×; margine massimo 400 USDT per trade; margine totale 55%; rischio per trade 4,3%; rischio aperto 12%; stop giornaliero 25%; 27 strumenti e 10 slot.
- DeepSeek: confidenza minima 0,56. Claude conserva il veto. Fallback senza Claude a rischio dimezzato disattivato. LONG soltanto con trend 1h+4h. Costi e slippage proposti entro il 30% di 1R.
- La proposta Live Evolution non modifica questi valori: è preparata ma non approvata né eseguita.

## Servizi, dashboard, contabilità e apprendimento

- Ultima prova puntuale, ore 11:28: runner `running`, servizio uscite `healthy`, errori `None`, heartbeat recenti; nelle tre ore precedenti 146 `NO_TRADE` da `deepseek:analysis`, 16 `ai_unavailable`, zero aperture.
- Filtri osservati: 25 `long_against_trend`, 19 `confidence_below_floor`, 3 `cost_too_high_for_stop`; 3 consulti `claude_contested`. Budget applicativo DeepSeek 3,8811/4 USD. Sono contatori applicativi, non saldo provider o fattura certificati.
- Dashboard 09:33: equity a mercato 2.209,73 USDT, totale contabile 2.393,80 USDT, netto sessione -3,54 USDT; valori ancora non riconciliati.
- Web-only del 25/11: `APP_PAPER_INSTALLATA_E_VERIFICATA`, `WEB_EXIT_CODE=0`, senza riavvio di runner, uscite o bridge.
- `work/brain-v2-web-counts-20261125` @ `6e305ed027e6aca132b0b3c1f27f42933ef902cd`: correzione web verificata; runner/memoria delle riduzioni parziali non certificati.

## Backup e chiavi, senza dati sensibili

- `claude/extbackup-storici-20261121` @ `1588c95af8411b48616d73203d5d10211d38e246`.
- Il backup cifrato definitivo del 22/11 è documentato come inviato e verificato da clone nuovo; restore Windows ancora incompleto; Android/Termux e copia aggiuntiva preparati ma non eseguiti.
- `work/extbackup-bot-stopped-20261109` @ `3dc2116a08058f57fc14b695431f6e3fa1a1ca45`: backup esterno storico preparato, non installato né certificato; preservato.
- Copia cifrata della chiave age sul PC: output PowerShell `ESITO: VERIFICA OK`; chiave pubblica derivata coincidente. È una prova locale e non certifica backup, presenza o ripristinabilità sulla VPS.

## Branch, PR, issue e SHA verificati

- `diario` prima di questa scrittura: `5f9d10f8b572a28d8c1e687e212182abbd927ff0`.
- `main`: `a1e9722a1a9af32ee045ebf61d7e43858c9a1d5e`.
- `integration/brain-unico-20261119`: `f50f7ae40c78e7994f33d0dabf40f91d57d7873f`.
- `claude/tetto-posizioni-20261121`: `887fc9616b5eedc2b4441357618fd5469ab5977d`.
- `claude/extbackup-storici-20261121`: `1588c95af8411b48616d73203d5d10211d38e246`.
- `claude/live-evolution-20261124`: `d1bc0628bb0fea6f1f5012ede6148cb1d93c0ccd`.
- `work/brain-v2-web-counts-20261125`: `6e305ed027e6aca132b0b3c1f27f42933ef902cd`.
- `work/extbackup-bot-stopped-20261109`: `3dc2116a08058f57fc14b695431f6e3fa1a1ca45`.
- RC84 PR #80: open, draft, non merged; head `0e29a73a36f668643da4088178bacb8616a45ac0`; ultimo aggiornamento 09/11/2026.
- Issue #124: closed/completed il 22/11/2026.
- EX-08B `cb31997f`: non riscontrato su GitHub; non trattarlo come SHA verificato.

## Test e fonte

- Tetto quattro posizioni/rischio: ramo `887fc961…`; risultati ereditati dal repository, non rilanciati qui.
- Issue #124: quattro test dedicati; tre rossi prima della correzione; suite V3 dichiarata 5.414.
- Brain V2 `6a96e599…`: V3 5.588, Builder 158, Jest 212, ripartenza 13/13, simulatore 2/2, come dichiarato nei materiali di rilascio.
- Integrazione app `f50f7ae4…`: V3 5.500 con un test skipped, Builder 158, Jest 210, Android 126/126.
- Correzione conteggi `6e305ed…`: regressione mirata documentata; nessuna full suite o GitHub Actions rilanciata da questo checkpoint.
- I 15/15 test attribuiti a EX-08B restano non verificati perché il commit non è stato trovato nel repository.

## Eseguito, preparato, non approvato

### Eseguito/verificato prima o fuori da questo checkpoint

- Brain V2 PAPER e web-only; backup cifrato definitivo del 22/11; verifica locale age.
- Diagnostica read-only delle 11:28 sui filtri e sulle zero aperture.
- In questa esecuzione: sole letture e doppia documentazione append-only.

### Preparato ma non eseguito/installato

- proposta strategica Live Evolution tramite `superbot-strategia stato/proponi`;
- backup storico `work/extbackup-bot-stopped-20261109`;
- restore Windows, procedura Android/Termux e copia aggiuntiva;
- riconciliazione equity/contabilità e certificazione `paper_reduce` tra web, runner e memoria.

### Non approvato e non eseguito qui

- esecuzione dei comandi strategici, approvazione/installazione della proposta Live Evolution;
- modifica di soglie, capitale, leva, stop, budget, watchdog o unità systemd;
- restart, reset, deploy, merge, Actions, modifiche VPS, ordini o API a pagamento.

## Blocker, prossime attività e istruzioni di ripresa

1. Leggere `STATO.md`, questo checkpoint e la prima sezione del file Library; verificarne la coincidenza prima di assumere continuità.
2. Se l'utente vuole procedere con la soluzione rapida, distinguere tre fasi: stato read-only, proposta generata, approvazione esplicita. Non saltare direttamente all'installazione.
3. Non rilassare filtri o rischio per ottenere aperture. Prima analizzare quantitativamente i NO_TRADE e il budget DeepSeek quasi esaurito.
4. Riconciliare il riferimento EX-08B: chiedere branch/SHA completo o altra fonte verificabile; fino ad allora non attribuire codice o test al repository.
5. Riconciliare equity 2.209,73, totale contabile 2.393,80 e netto sessione -3,54 senza sommare grandezze diverse.
6. Verificare in sola lettura la causa del watchdog del 25/11 e `paper_reduce`, preservando EventJournal, archivi e memoria.
7. Conservare Falco, Toro, Brain, backup storico non installato e tutte le sessioni.
8. Se una delle due scritture fallisce, il checkpoint successivo deve recuperare prima quella destinazione.

## Azioni escluse

Nessuna modifica di codice operativo, merge, deploy, GitHub Actions, VPS, reboot/riavvio, reset, ordine o API a pagamento. Nessun segreto letto o esposto.

