# Checkpoint verificabile SuperBot-Trading — 26/11/2026 09:44 Europe/Rome

## Esito, fonti e limiti

Checkpoint append-only di ripresa di `alexiptv82/SuperBot-Trading`, esclusivamente PAPER. Fonti consultate:

1. GitHub, ramo `diario`: `STATO.md`, checkpoint del 26/11 ore 08:50, branch elencati sotto, RC84 PR #80 e issue #124;
2. `/SuperBot-Ripresa/ULTIMO-STATO-SUPERBOT.md`, Library `libfile_754adf32b63881919d64ef3bc26b222a`, versione 151 prima di questa scrittura;
3. conversazione recente effettivamente accessibile `Ripresa diagnosi Brain Evolution`, limitatamente alle due schermate Chrome/Termius delle 09:33 e 09:40 e al contesto immediatamente precedente.

La schermata Termius mostra l'esito di una query in sola lettura sui registri dell'ultima ora già eseguita dall'utente. Questo checkpoint non ha eseguito comandi sulla VPS, inferenze AI o chiamate a pagamento. Le osservazioni sono puntuali e non certificano lo stato successivo. Nessuna chat persa è stata ricostruita; nessun segreto è stato letto o pubblicato.

## Novità verificata dopo la ricarica

- Schermata Chrome delle 09:33: Brain PAPER mostrato `RUNNING`, modalità `ATTIVO`, versione V2, ultimo ciclo circa 3 minuti prima, `0/10` posizioni. Equity a mercato `2.209,73 USDT`; totale contabile delle sole chiusure `2.393,80 USDT`; netto sessione `-3,54 USDT`. I valori restano grandezze diverse e non sono riconciliati.
- Schermata Termius delle 09:40, finestra dichiarata «ultima ora»: DeepSeek `RISPOSTE_CON_USAGE=50`, `RISPOSTE_SENZA_USAGE=0`, `CHIAMATE_FALLITE=4`.
- Nella stessa finestra: `APERTURE=0`; motivi delle decisioni `{'deepseek:analysis': 50, 'ai_unavailable': 4}`; output finale `VERIFICA_COMPLETATA`.
- Questa è prova post-ricarica che l'analisi DeepSeek ha ripreso a produrre risposte conteggiate con usage e decisioni `deepseek:analysis`. Le quattro chiamate fallite restano da osservare. Non prova il saldo residuo, la qualità delle analisi, la disponibilità di Claude, l'apertura di trade o la redditività.
- Zero aperture non è un errore: `NO_TRADE` e slot vuoti restano esiti validi. Non forzare aperture.

## Obiettivi e decisioni invarianti

- Tre portafogli distinti e confrontabili: Falco, Toro e Brain; capitale simulato, EventJournal, archivi e sessioni di apprendimento preservati.
- Trading esclusivamente PAPER. Nessun passaggio LIVE implicito.
- Nessun reset, merge, deploy, GitHub Actions, modifica VPS, reboot/riavvio, ordine o API a pagamento in questa attività.
- Ogni modifica operativa, di budget o di rischio richiede consenso separato; questo checkpoint registra soltanto fatti osservati o lavori già preparati/eseguiti altrove.

## Tre portafogli PAPER: desiderato contro implementato

| Portafoglio | Desiderato | Implementato/verificato | Stato più recente dimostrabile |
|---|---|---|---|
| Falco | classico distinto, strategia e storico preservati; evoluzione solo con autorizzazione | Falco classico preservato; Falco Evoluto installato il 23/11, poi archiviato/disabilitato con la nuova sessione Brain V2 | nessun nuovo controllo live |
| Toro | classico distinto e storico preservato | storico preservato; resta `semantic_not_certified`, quindi integrità tecnica non equivale a correttezza semantica | non è il bot corrente mostrato dalla dashboard Brain |
| Brain | portafoglio unico PAPER da 2.000 USDT, DeepSeek principale, Claude revisore, memoria collegata | run `brain-scalp-paper-p1`, 27 strumenti, 10 slot; vecchia run archiviata con 539 eventi e tre sessioni collegate in sola lettura | 09:33 RUNNING/ATTIVO V2, 0/10; nell'ultima ora 50 decisioni DeepSeek valide ai fini del contatore, 4 `ai_unavailable`, zero aperture |

## Configurazione e rischio: desiderato contro implementato

- Profilo B precedente: tetto esplicito di quattro posizioni e rischio aperto comprensivo dei costi; integrazione `c11e6d7d…`, piano `302e94d2…`.
- Issue #124: correzione `0f71d0be…`, integrazione `5f110379…`, chiusa il 22/11. Il latch deve bloccare nuove aperture senza impedire le uscite.
- Brain V2 documentato come installato: ciclo 30 minuti; leva dinamica 15–50×; margine massimo 400 USDT per trade; margine totale 55%; rischio per trade 4,3%; rischio aperto 12%; stop giornaliero 25%; 27 strumenti e 10 slot.
- DeepSeek: confidenza minima 0,56. Claude conserva il veto. Fallback senza Claude a rischio dimezzato disattivato. LONG soltanto con trend 1h+4h. Costi e slippage proposti entro il 30% di 1R.
- La schermata 09:33 mostra coerentemente i principali valori V2, ma non sostituisce la verifica dei file di configurazione. Nessuna modifica del profilo V2 è stata approvata da questo checkpoint.

## Servizi, dashboard, contabilità e apprendimento

- Evidenza storica del 25/11: watchdog uscite scaduto alle 18:05:56; `BindsTo` fermò anche il runner; uscite ripartite alle 18:09:01, runner rimasto fermo. Causa originaria del timeout non dimostrata.
- Alle 08:03 del 26/11 servizi/heartbeat erano sani, Guardian `NORMAL`, ma 216/216 decisioni risultavano `ai_unavailable` per credito non utilizzabile. L'utente ha poi dichiarato la ricarica completata.
- La nuova verifica 09:33–09:40 chiude il blocker «nessuna prova post-ricarica»: il runner è mostrato in ciclo e DeepSeek produce 50 risposte con usage. Non chiude i blocker relativi alle quattro chiamate fallite, a Claude, al saldo residuo o alla qualità economica.
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

- `diario` prima di questa scrittura: `0f086990cca548ef0dc700042eafa42ec406e45b`.
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
- Nuova prova post-ricarica: schermate Chrome 09:33 e Termius 09:40; query read-only già eseguita dall'utente. Nessun test software, comando VPS o chiamata AI rilanciato dal checkpoint.

## Eseguito, preparato, non approvato

### Eseguito/verificato prima o fuori da questo checkpoint

- Brain V2 PAPER e web-only; backup cifrato definitivo del 22/11; verifica locale age.
- Ricarica dichiarata dall'utente; successiva ripresa delle risposte DeepSeek verificata nelle schermate 09:33–09:40.
- In questa esecuzione: sole letture e doppia documentazione append-only.

### Preparato ma non installato/completato

- backup storico `work/extbackup-bot-stopped-20261109`;
- restore Windows, procedura Android/Termux e copia aggiuntiva;
- riconciliazione equity/contabilità e certificazione `paper_reduce` tra web, runner e memoria.

### Non approvato e non eseguito qui

- modifica/reset dei budget DeepSeek/Claude, forzatura di aperture o modifica del profilo di rischio;
- modifica watchdog/unità systemd;
- restart, reset, deploy, merge, Actions, modifiche VPS, ordini o API a pagamento.

## Blocker, prossime attività e istruzioni di ripresa

1. Leggere `STATO.md`, questo checkpoint e la prima sezione del file Library; verificarne la coincidenza prima di assumere continuità.
2. Monitorare in sola lettura le quattro chiamate fallite e distinguere errori transitori, saldo, autenticazione o disponibilità modello; non esporre segreti e non forzare trade.
3. Verificare separatamente Claude e il saldo/budget residuo soltanto se necessario; 50 risposte DeepSeek non certificano Claude né sostenibilità del budget.
4. Riconciliare equity `2.209,73`, totale contabile `2.393,80` e netto sessione `-3,54`; non sommare grandezze diverse.
5. Determinare dai log la causa originaria del timeout watchdog del 25/11 senza modificare i servizi.
6. Verificare `paper_reduce` tra web, runner e memoria senza modificare EventJournal o sessioni archiviate.
7. Conservare Falco/Toro/Brain, EventJournal, archivi, memoria e backup storico non installato.
8. Se una delle due scritture fallisce, il checkpoint successivo deve recuperare prima quella destinazione.

## Azioni escluse

Nessuna modifica di codice operativo, merge, deploy, GitHub Actions, VPS, reboot/riavvio, reset, ordine o API a pagamento. Nessun segreto letto o esposto.
