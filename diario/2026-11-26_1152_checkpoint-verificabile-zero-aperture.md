# Checkpoint verificabile SuperBot-Trading — 26/11/2026 11:52 Europe/Rome

## Esito, fonti e limiti

Checkpoint append-only di ripresa di `alexiptv82/SuperBot-Trading`, esclusivamente PAPER. Fonti consultate:

1. GitHub, ramo `diario`: `STATO.md`, checkpoint del 26/11 ore 09:44, RC84 PR #80 e issue #124;
2. `/SuperBot-Ripresa/ULTIMO-STATO-SUPERBOT.md`, Library `libfile_754adf32b63881919d64ef3bc26b222a`, versione 152 prima di questa scrittura;
3. conversazione recente effettivamente accessibile `Ripresa diagnosi Brain Evolution`, limitatamente al messaggio «ancora 0 aperture» e alla schermata Termius delle 11:28.

La schermata mostra l'esito di una diagnostica in sola lettura già eseguita dall'utente sui registri delle ultime tre ore. Questo checkpoint non ha eseguito comandi sulla VPS, chiamate AI, test software o azioni operative. I dati valgono per la finestra mostrata e non certificano lo stato successivo. Nessuna chat persa è stata ricostruita; nessun segreto è stato letto o pubblicato.

## Novità verificata: zero aperture spiegato dai filtri

- Alle 11:28 `heartbeat.json` risultava `running`, errore `None`, età 1; `exit_heartbeat.json` risultava `healthy`, errore `None`, età 2. È una prova puntuale di runner e servizio uscite, non salute H24.
- Nelle ultime tre ore la diagnostica contava 162 decisioni: 146 `NO_TRADE_DRAFT` con motivo `deepseek:analysis` e 16 `NO_TRADE_REJECTED` con motivo `ai_unavailable`.
- Filtri d'ingresso mostrati: 25 `long_against_trend`, 19 `confidence_below_floor`, 3 `cost_too_high_for_stop`; consulti Claude: 3 `claude_contested`.
- Aperture reali: 0. Eventi totali letti: 380.
- Budget DeepSeek mostrato: `USATO_USD=3.8811`, `LIMITE_USD=4`, cioè circa 97% del tetto e circa 0,12 USD residui. È un contatore applicativo, non una fattura o una lettura certificata del saldo provider.
- Zero aperture è quindi coerente con selezione e filtri attivi, non prova di malfunzionamento. Non allentare trend, confidenza, costi o veto Claude soltanto per riempire gli slot. Resta però un rischio operativo il tetto DeepSeek quasi esaurito e la presenza di 16 indisponibilità AI.

## Obiettivi e decisioni invarianti

- Tre portafogli distinti e confrontabili: Falco, Toro e Brain; capitale simulato, EventJournal, archivi e sessioni di apprendimento preservati.
- Trading esclusivamente PAPER. `NO_TRADE` e slot vuoti sono risultati validi; nessun passaggio LIVE implicito.
- Nessun reset, merge, deploy, GitHub Actions, modifica VPS, reboot/riavvio, ordine o API a pagamento in questa attività.
- Ogni modifica operativa, di budget o di rischio richiede consenso separato; il checkpoint registra soltanto fatti osservati o lavori già preparati/eseguiti altrove.

## Tre portafogli PAPER: desiderato contro implementato

| Portafoglio | Desiderato | Implementato/verificato | Stato più recente dimostrabile |
|---|---|---|---|
| Falco | classico distinto, strategia e storico preservati; evoluzione solo con autorizzazione | Falco classico preservato; Falco Evoluto installato il 23/11, poi archiviato/disabilitato con la nuova sessione Brain V2 | nessun nuovo controllo live |
| Toro | classico distinto e storico preservato | storico preservato; resta `semantic_not_certified`, quindi integrità tecnica non equivale a correttezza semantica | non è il bot corrente mostrato dalla dashboard Brain |
| Brain | portafoglio unico PAPER da 2.000 USDT, DeepSeek principale, Claude revisore, memoria collegata | run `brain-scalp-paper-p1`, 27 strumenti, 10 slot; vecchia run archiviata con 539 eventi e tre sessioni collegate in sola lettura | alle 11:28 runner/uscite sani; 162 decisioni/3h, 146 analisi concluse in NO_TRADE, 16 indisponibilità AI, zero aperture; budget applicativo 3,8811/4 USD |

## Configurazione e rischio: desiderato contro implementato

- Profilo B precedente: tetto esplicito di quattro posizioni e rischio aperto comprensivo dei costi; integrazione `c11e6d7d…`, piano `302e94d2…`.
- Issue #124: correzione `0f71d0be…`, integrazione `5f110379…`, chiusa il 22/11. Il latch deve bloccare nuove aperture senza impedire le uscite.
- Brain V2 documentato come installato: ciclo 30 minuti; leva dinamica 15–50×; margine massimo 400 USDT per trade; margine totale 55%; rischio per trade 4,3%; rischio aperto 12%; stop giornaliero 25%; 27 strumenti e 10 slot.
- DeepSeek: confidenza minima 0,56. Claude conserva il veto. Fallback senza Claude a rischio dimezzato disattivato. LONG soltanto con trend 1h+4h. Costi e slippage proposti entro il 30% di 1R.
- La diagnostica conferma che trend, soglia di confidenza, costi e contestazione Claude stanno effettivamente bloccando proposte. Non prova che ogni decisione sia economicamente corretta e non autorizza modifiche alle soglie.

## Servizi, dashboard, contabilità e apprendimento

- Evidenza storica del 25/11: watchdog uscite scaduto alle 18:05:56; `BindsTo` fermò anche il runner; uscite ripartite alle 18:09:01, runner rimasto fermo. Causa originaria del timeout non dimostrata.
- Alle 08:03 del 26/11 servizi/heartbeat erano sani, Guardian `NORMAL`, ma 216/216 decisioni risultavano `ai_unavailable` per credito non utilizzabile. L'utente ha poi dichiarato la ricarica completata.
- Alle 09:40 la ripresa post-ricarica era stata verificata con 50 risposte DeepSeek con usage, 4 fallite e zero aperture. La nuova finestra 11:28 mostra continuità del ciclo e spiega lo zero aperture soprattutto con decisioni selettive e filtri, ma anche 16 indisponibilità AI.
- Dashboard 09:33: equity a mercato `2.209,73 USDT`, totale contabile `2.393,80 USDT`, netto sessione `-3,54 USDT`; grandezze ancora non riconciliate.
- Web-only del 25/11 ore 06:35: `APP_PAPER_INSTALLATA_E_VERIFICATA`, `WEB_EXIT_CODE=0`; runner, uscite e bridge non riavviati da quell'operazione.
- `work/brain-v2-web-counts-20261125` @ `6e305ed027e6aca132b0b3c1f27f42933ef902cd`: arrotondamento `paper_reduce` corretto nella web; runner/memoria delle riduzioni parziali non ancora certificati.
- Live Evolution installato/simulato V2→V3 con posizione aperta; collaudo operativo completo ancora pendente. Signal Lab, Evolution X e Ghost Trading restano separati dal Brain operativo.

## Backup e chiavi, senza dati sensibili

- `claude/extbackup-storici-20261121` @ `1588c95af8411b48616d73203d5d10211d38e246`.
- Il 22/11 il proprietario ha inviato il backup cifrato definitivo e lo ha verificato da clone nuovo: indispensabili tecnicamente certificati; storici tecnicamente integri; Falco/Toro non certificati semanticamente.
- Restore Windows dei nuovi archivi ancora incompleto. Procedura Android/Termux e copia aggiuntiva degli indispensabili preparate ma non eseguite.
- `work/extbackup-bot-stopped-20261109` @ `3dc2116a08058f57fc14b695431f6e3fa1a1ca45`: artefatto storico preparato, non installato né certificato; preservato.
- Copia cifrata della chiave age sul PC: output PowerShell `ESITO: VERIFICA OK`; chiave pubblica derivata coincidente. È una prova locale e non certifica backup, presenza o ripristinabilità sulla VPS.

## Branch, PR, issue e SHA verificati

- `diario` prima di questa scrittura: `d00fa37a41f7f2376ce0773bb29c668041f46236`; `STATO.md` blob `18c07b08e281c358e9a3c7b6d5e29b77eaa16d0d`.
- `main`: `a1e9722a1a9af32ee045ebf61d7e43858c9a1d5e`.
- `integration/brain-unico-20261119`: `f50f7ae40c78e7994f33d0dabf40f91d57d7873f`.
- `claude/tetto-posizioni-20261121`: `887fc9616b5eedc2b4441357618fd5469ab5977d`.
- `claude/extbackup-storici-20261121`: `1588c95af8411b48616d73203d5d10211d38e246`.
- `claude/live-evolution-20261124`: `d1bc0628bb0fea6f1f5012ede6148cb1d93c0ccd`.
- `work/brain-v2-web-counts-20261125`: `6e305ed027e6aca132b0b3c1f27f42933ef902cd`.
- `work/extbackup-bot-stopped-20261109`: `3dc2116a08058f57fc14b695431f6e3fa1a1ca45`.
- RC84 PR #80: open, draft, non merged; head `0e29a73a36f668643da4088178bacb8616a45ac0`; ultimo aggiornamento 09/11/2026.
- Issue #124: closed/completed il 22/11/2026.

## Test e fonte

- Tetto quattro posizioni/rischio: ramo `887fc961…`; risultati ereditati dal repository, non rilanciati qui.
- Issue #124: quattro test dedicati; tre rossi prima della correzione; suite V3 dichiarata 5.414.
- Brain V2 `6a96e599…`: V3 5.588, Builder 158, Jest 212, ripartenza 13/13, simulatore 2/2, come dichiarato nei materiali di rilascio.
- Integrazione app `f50f7ae4…`: V3 5.500 con un test skipped, Builder 158, Jest 210, Android 126/126.
- Correzione conteggi `6e305ed…`: regressione mirata documentata; nessuna full suite o GitHub Actions rilanciata da questo checkpoint.
- Nuova fonte: schermata Termius 11:28 con diagnostica read-only già eseguita dall'utente. Nessun test software o comando VPS rilanciato da questo checkpoint.

## Eseguito, preparato, non approvato

### Eseguito/verificato prima o fuori da questo checkpoint

- Brain V2 PAPER e web-only; backup cifrato definitivo del 22/11; verifica locale age.
- Ricarica dichiarata dall'utente; ripresa delle risposte DeepSeek e successiva finestra di 3 ore con filtri/NO_TRADE verificati nelle schermate.
- In questa esecuzione: sole letture e doppia documentazione append-only.

### Preparato ma non installato/completato

- backup storico `work/extbackup-bot-stopped-20261109`;
- restore Windows, procedura Android/Termux e copia aggiuntiva;
- riconciliazione equity/contabilità e certificazione `paper_reduce` tra web, runner e memoria.

### Non approvato e non eseguito qui

- modifica/reset/acquisto dei budget DeepSeek/Claude, allentamento dei filtri, forzatura di aperture o modifica del profilo di rischio;
- modifica watchdog/unità systemd;
- restart, reset, deploy, merge, Actions, modifiche VPS, ordini o API a pagamento.

## Blocker, prossime attività e istruzioni di ripresa

1. Leggere `STATO.md`, questo checkpoint e la prima sezione del file Library; verificarne la coincidenza prima di assumere continuità.
2. Trattare zero aperture come esito selettivo finché i filtri mostrano motivi coerenti; non rilassare le soglie senza analisi quantitativa separata.
3. Monitorare il budget applicativo DeepSeek quasi esaurito e le 16 indisponibilità AI; verificare separatamente saldo provider e budget solo se autorizzato, senza esporre segreti né generare chiamate superflue.
4. Verificare in sola lettura se i 146 NO_TRADE sono distribuiti su mercati/regimi diversi e se i 25 LONG contro trend riflettono correttamente 1h+4h; nessun cambio automatico.
5. Riconciliare equity `2.209,73`, totale contabile `2.393,80` e netto sessione `-3,54`; non sommare grandezze diverse.
6. Determinare dai log la causa originaria del timeout watchdog del 25/11 senza modificare i servizi.
7. Verificare `paper_reduce` tra web, runner e memoria senza modificare EventJournal o sessioni archiviate.
8. Conservare Falco/Toro/Brain, EventJournal, archivi, memoria e backup storico non installato.
9. Se una delle due scritture fallisce, il checkpoint successivo deve recuperare prima quella destinazione.

## Azioni escluse

Nessuna modifica di codice operativo, merge, deploy, GitHub Actions, VPS, reboot/riavvio, reset, ordine o API a pagamento. Nessun segreto letto o esposto.
