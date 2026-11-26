# Checkpoint verificabile SuperBot-Trading — 26/11/2026 08:50 Europe/Rome

## Esito, fonti e limiti

Checkpoint append-only di ripresa di `alexiptv82/SuperBot-Trading`, esclusivamente PAPER. Fonti consultate:

1. GitHub, ramo `diario`: `STATO.md`, checkpoint del 26/11 ore 05:45, branch elencati sotto, RC84 PR #80 e issue #124;
2. `/SuperBot-Ripresa/ULTIMO-STATO-SUPERBOT.md`, Library `libfile_754adf32b63881919d64ef3bc26b222a`, versione 150 prima di questa scrittura;
3. conversazione recente effettivamente accessibile `Ripresa diagnosi Brain Evolution`, limitatamente ai riepiloghi verificabili dei tre screenshot Termius delle 08:03–08:08 e alle dichiarazioni successive dell'utente.

Questo checkpoint non ha eseguito comandi sulla VPS: registra il controllo diagnostico già svolto nella conversazione e gli screenshot relativi. Le osservazioni valgono soltanto per quei momenti; la ricarica dichiarata dall'utente non certifica saldo utilizzabile, ripresa delle decisioni AI o stato successivo. Nessuna chat persa è stata ricostruita e nessun segreto è stato letto o pubblicato.

## Novità verificata dal checkpoint precedente

- Controllo mostrato negli screenshot Termius delle 08:03: runner, servizio uscite e heartbeat risultavano sani; Guardian `NORMAL`; zero posizioni.
- Il Brain aveva prodotto 216 decisioni, tutte rifiutate con motivo `ai_unavailable`, e nessuna apertura. Il problema non era quindi mancanza di ciclo o blocco del Guardian, ma indisponibilità dell'analisi AI nel punto osservato.
- La diagnostica riportava DeepSeek `3,3614/4,00 USD`; 216 chiamate `estimate_failed_call`, con costo stimato `1,7936 USD`. I contatori sono quelli mostrati, non una fattura verificata da questo checkpoint.
- Il controllo API mostrava chiave caricata, risposta HTTP 200 e modello disponibile, ma saldo utilizzabile `False`: diagnosi coerente con credito insufficiente, senza leggere o esporre la chiave.
- L'utente ha confermato esplicitamente che il credito era finito e alle 08:13 circa ha dichiarato la ricarica completata con `ok fatto✅`.
- Non esiste ancora, nelle fonti accessibili, una prova successiva alla ricarica che mostri saldo utilizzabile, nuove decisioni AI valide, apertura di posizioni o continuità del runner. La ricarica è una dichiarazione utente, non una certificazione operativa.
- Restano storici i valori dashboard delle 04:56: equity `2.209,73 USDT`, totale contabile `2.393,80 USDT`, salvadanaio `393,80 USDT`, realizzato netto `386,52 USDT`, costi AI `7,28 USDT`; non sono ancora riconciliati.

## Obiettivi e decisioni invarianti

- Tre portafogli distinti e confrontabili: Falco, Toro e Brain; capitale simulato, EventJournal, archivi e sessioni di apprendimento preservati.
- Trading esclusivamente PAPER. `NO_TRADE` e slot vuoti sono risultati validi.
- Nessun reset, merge, deploy, GitHub Actions, modifica VPS, reboot/riavvio, ordine o API a pagamento in questa attività.
- Ogni modifica operativa o di rischio richiede consenso separato; il checkpoint registra soltanto fatti già osservati o lavori già preparati/eseguiti altrove.

## Tre portafogli PAPER: desiderato contro implementato

| Portafoglio | Desiderato | Implementato/verificato | Stato più recente dimostrabile |
|---|---|---|---|
| Falco | classico distinto, strategia e storico preservati; evoluzione solo con autorizzazione | Falco classico preservato; Falco Evoluto installato il 23/11, poi archiviato/disabilitato con la nuova sessione Brain V2 | nessun nuovo controllo live |
| Toro | classico distinto e storico preservato | storico preservato; resta `semantic_not_certified`, quindi integrità tecnica non equivale a correttezza semantica | non è il bot corrente mostrato dalla dashboard Brain |
| Brain | portafoglio unico PAPER da 2.000 USDT, DeepSeek principale, Claude revisore, memoria collegata | run `brain-scalp-paper-p1`, 27 strumenti, 10 slot; vecchia run archiviata con 539 eventi e tre sessioni collegate in sola lettura | alle 08:03 servizi/heartbeat sani e Guardian NORMAL, ma 216/216 decisioni `ai_unavailable`, zero posizioni; ricarica dichiarata, esito post-ricarica non verificato |

## Configurazione e rischio: desiderato contro implementato

- Il profilo B precedente ha ricevuto tetto esplicito di quattro posizioni e rischio aperto comprensivo dei costi; integrazione `c11e6d7d…`, piano `302e94d2…`.
- Issue #124: correzione `0f71d0be…`, integrazione `5f110379…`, chiusa il 22/11. Il latch deve bloccare le nuove aperture senza impedire le uscite.
- Brain V2 documentato come installato: ciclo 30 minuti; leva dinamica 15–50×; margine massimo 400 USDT per trade; margine totale 55%; rischio per trade 4,3%; rischio aperto 12%; stop giornaliero 25%; 27 strumenti e 10 slot.
- DeepSeek: confidenza minima 0,56. Claude conserva il veto. Fallback senza Claude a rischio dimezzato disattivato. LONG soltanto con trend 1h+4h. Costi e slippage proposti entro il 30% di 1R.
- Nessuna modifica successiva del profilo V2 risulta approvata. Il precedente HALT budget non autorizza aumento/reset dei tetti o aggiramento del gate.

## Servizi, dashboard e apprendimento

- Evidenza storica del 25/11: watchdog uscite scaduto alle 18:05:56; il legame systemd `BindsTo` fermò anche il runner; uscite ripartite alle 18:09:01, runner rimasto fermo. La causa originaria del timeout non è dimostrata.
- Un riavvio fu eseguito dall'utente e il runner venne osservato brevemente `running`, poi `HALTED` per budget. Contatori riportati: DeepSeek 953 chiamate e `4,0025/4,00 USD`; Claude 58 chiamate e `0,81/3,00 USD`.
- Dashboard RUNNING alle 04:53 del 26/11 con zero posizioni; controllo successivo delle 08:03 con servizi e heartbeat sani ma analisi AI indisponibile per credito non utilizzabile.
- La ricarica è stata eseguita/dichiarata dall'utente fuori da questo checkpoint. Non è stato aumentato o modificato qui alcun budget e non è stata effettuata una chiamata API a pagamento.
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

- `diario` prima di questa scrittura: `9454fd241df0638fdfdd5fed75b0df772138b135`.
- `main`: `a1e9722a1a9af32ee045ebf61d7e43858c9a1d5e`.
- `integration/brain-unico-20261119`: `f50f7ae40c78e7994f33d0dabf40f91d57d7873f`.
- `claude/tetto-posizioni-20261121`: `887fc9616b5eedc2b4441357618fd5469ab5977d`.
- `claude/extbackup-storici-20261121`: `1588c95af8411b48616d73203d5d10211d38e246`.
- `claude/live-evolution-20261124`: `d1bc0628bb0fea6f1f5012ede6148cb1d93c0ccd`.
- `work/brain-v2-web-counts-20261125`: `6e305ed027e6aca132b0b3c1f27f42933ef902cd`.
- `work/extbackup-bot-stopped-20261109`: `3dc2116a08058f57fc14b695431f6e3fa1a1ca45`.
- RC84 PR #80: open, draft, non merged; head `0e29a73a36f668643da4088178bacb8616a45ac0`; ultimo aggiornamento 09/11/2026. Test scritti, non dichiarabili indipendentemente eseguiti/verdi.
- Issue #124: closed/completed il 22/11/2026.

## Test e fonte

- Tetto quattro posizioni/rischio: ramo `887fc961…`; risultati ereditati dal repository, non rilanciati qui.
- Issue #124: quattro test dedicati; tre rossi prima della correzione; suite V3 dichiarata 5.414.
- Brain V2 `6a96e599…`: V3 5.588, Builder 158, Jest 212, ripartenza 13/13, simulatore 2/2, come dichiarato nei materiali di rilascio.
- Integrazione app `f50f7ae4…`: V3 5.500 con un test skipped, Builder 158, Jest 210, Android 126/126.
- Correzione conteggi `6e305ed…`: regressione mirata documentata; nessuna full suite o GitHub Actions rilanciata da questo checkpoint.
- La diagnosi AI/credito proviene dai tre screenshot Termius e dal riepilogo accessibile della conversazione; la ricarica proviene dalla dichiarazione dell'utente. Questo checkpoint non ha rilanciato comandi o chiamate API.

## Eseguito, preparato, non approvato

### Eseguito/verificato prima o fuori da questo checkpoint

- Brain V2 PAPER e web-only; backup cifrato definitivo del 22/11; verifica locale age; precedenti osservazioni di restart/HALT; servizi/heartbeat sani alle 08:03 con 216 decisioni AI indisponibili.
- Ricarica del credito dichiarata completata dall'utente alle 08:13 circa; non ancora verificata tecnicamente.
- In questa esecuzione: sole letture e doppia documentazione append-only.

### Preparato ma non installato/completato

- backup storico `work/extbackup-bot-stopped-20261109`;
- restore Windows, procedura Android/Termux e copia aggiuntiva;
- riconciliazione equity/contabilità e certificazione `paper_reduce` tra web, runner e memoria.

### Non approvato e non eseguito qui

- modifica o reset dei budget DeepSeek/Claude da parte di questo checkpoint; la ricarica utente è soltanto documentata;
- modifica di watchdog o unità systemd;
- restart, reset, deploy, merge, Actions, modifiche VPS, ordini o API a pagamento.

## Blocker, prossime attività e istruzioni di ripresa

1. Leggere `STATO.md`, questo checkpoint e la prima sezione del file Library; verificarne la coincidenza prima di assumere continuità.
2. Eseguire soltanto una verifica read-only post-ricarica: saldo utilizzabile, chiamata AI riuscita, scomparsa di `ai_unavailable`, heartbeat/ciclo e posizioni PAPER. Non forzare aperture e non riavviare nulla.
3. Determinare dai log la causa originaria del timeout watchdog delle 18:05:56; non confonderla con l'effetto `BindsTo` già dimostrato.
4. Verificare che i contatori 216/216 `ai_unavailable` non continuino dopo la ricarica; se persistono, distinguere saldo, autenticazione e disponibilità modello senza esporre segreti.
5. Riconciliare equity `2.209,73`, totale contabile/salvadanaio `2.393,80`, realizzato netto `386,52` e costi AI `7,28`; non assumere che siano grandezze equivalenti.
6. Verificare `paper_reduce` tra web, runner e memoria senza modificare EventJournal o sessioni archiviate.
7. Conservare Falco/Toro/Brain classici, EventJournal, archivi, memoria e backup storico non installato.
8. Se una delle due scritture fallisce, il checkpoint successivo deve recuperare prima quella destinazione.

## Azioni escluse

Nessuna modifica di codice operativo, merge, deploy, GitHub Actions, VPS, reboot/riavvio, reset, ordine o API a pagamento. Nessun segreto letto o esposto.
