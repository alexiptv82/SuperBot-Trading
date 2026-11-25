# Checkpoint verificabile SuperBot-Trading — 25/11/2026 21:50 Europe/Rome

## Scopo, fonti e limiti

Checkpoint append-only di ripresa del progetto `alexiptv82/SuperBot-Trading`, esclusivamente PAPER. Fonti consultate in questa esecuzione:

1. ramo GitHub `diario`, `STATO.md`, ultimo checkpoint del 25/11 ore 20:48, branch indicati sotto, PR #80 e issue #124;
2. `/SuperBot-Ripresa/ULTIMO-STATO-SUPERBOT.md`, Library `libfile_754adf32b63881919d64ef3bc26b222a`, versione 148 prima di questa scrittura;
3. conversazioni recenti effettivamente accessibili, in particolare il riepilogo della diagnosi Brain Evolution delle 21:13–21:24 Europe/Rome.

Non è stata effettuata una nuova ispezione live della VPS. I riscontri recenti da conversazione sono registrati come osservazioni/dichiarazioni del relativo controllo Termius e dei log, non come stato corrente garantito. Nessuna trascrizione persa è ricostruita. Nessun segreto è stato letto o pubblicato.

## Sintesi operativa e decisioni invarianti

- Obiettivo: tre portafogli distinti e confrontabili — Falco, Toro e Brain — con capitale simulato, journal e storici preservati; `NO_TRADE` è un esito valido.
- Trading esclusivamente PAPER. Vietati in questa attività ordini reali, reset, merge, deploy, GitHub Actions, modifiche VPS, reboot/riavvii e API a pagamento.
- Ogni modifica operativa richiede consenso separato; questo checkpoint documenta soltanto fatti già osservati o modifiche già preparate/eseguite altrove.
- EventJournal, archivi e sessioni di apprendimento non vanno cancellati, riusati o riscritti.

## Tre portafogli PAPER: desiderato contro implementato

| Portafoglio | Desiderato | Implementato/verificato | Stato più recente dimostrabile |
|---|---|---|---|
| Falco | Portafoglio classico distinto, storico preservato; evoluzione solo con autorizzazione | Falco classico preservato. Falco Evoluto è stato installato il 23/11, poi archiviato/disabilitato all'avvio della nuova sessione Brain V2 | nessun nuovo controllo live in questa esecuzione |
| Toro | Portafoglio classico distinto e storico preservato | storico preservato; resta `semantic_not_certified`, quindi integrità tecnica non equivale a correttezza semantica | non è il bot corrente mostrato dalla dashboard Brain |
| Brain | Portafoglio unico PAPER da 2.000 USDT, DeepSeek principale e Claude revisore, memoria collegata | run `brain-scalp-paper-p1`, 27 strumenti, 10 slot; vecchia run archiviata con 539 eventi e tre sessioni collegate in sola lettura | nella conversazione recente: ripartito dopo riavvio utente, poi nuovamente `HALTED` per budget; nessuna prova di stato successivo |

## Configurazione e rischio: desiderato contro implementato

- Il profilo B precedente ha ricevuto tetto esplicito di quattro posizioni e rischio aperto comprensivo dei costi; integrazione documentata da `c11e6d7d…` e piano `302e94d2…`.
- Issue #124: correzione `0f71d0be…`, integrazione `5f110379…`, issue chiusa il 22/11. Il latch deve bloccare nuove aperture senza impedire le uscite.
- Brain V2 documentato come installato usa un profilo successivo e più aggressivo: ciclo 30 minuti; leva dinamica 15–50×; margine massimo 400 USDT per trade; margine totale 55%; rischio per trade 4,3%; rischio aperto 12%; stop giornaliero 25%; 27 strumenti e 10 slot.
- DeepSeek: confidenza minima 0,56. Claude mantiene il veto. Fallback senza Claude a rischio dimezzato disattivato. LONG ammessi solo con trend 1h+4h. Costi e slippage proposti entro il 30% di 1R.
- Nessuna modifica del profilo V2 risulta approvata dopo l'avvio. Il nuovo arresto per budget non autorizza aumento del tetto o aggiramento del gate.

## Novità verificata dalla conversazione recente: diagnosi del precedente HALT e nuovo gate budget

### Fatti riportati come osservati nei log/Termius

1. La scadenza del watchdog del servizio uscite è stata registrata alle 18:05:56 Europe/Rome.
2. Per il legame systemd `BindsTo`, l'arresto del servizio uscite ha terminato anche il runner.
3. Il servizio uscite è ripartito alle 18:09:01, mentre il runner era rimasto fermo. Questo spiega il precedente quadro `halted:exit_service_unhealthy` con uscite successivamente sane e heartbeat Brain vecchio.
4. Un riavvio è stato eseguito dall'utente nella conversazione, non da questo checkpoint. Subito dopo il runner è stato osservato `running`, con heartbeat aggiornato e ciclo 1.
5. In seguito il runner è stato osservato di nuovo `HALTED`, questa volta con motivo `halted:budget`.
6. I contatori riportati erano DeepSeek 4,0025/4,00 USD con 953 chiamate e Claude 0,81/3,00 USD con 58 chiamate.

### Conclusioni ammesse e non ammesse

- Ammesso: il precedente stop era collegato alla scadenza del watchdog uscite e all'accoppiamento systemd; il runner non era ripartito automaticamente quando le uscite erano tornate sane.
- Non dimostrato: la causa tecnica che ha fatto scadere il watchdog alle 18:05:56.
- Ammesso: il successivo stop `halted:budget` è coerente con il contatore DeepSeek appena oltre il tetto documentato.
- Non ammesso: assumere che il runner sia ora attivo, che il budget sia stato aumentato/resettato, che vi siano posizioni aperte o che la VPS sia sana dopo le 21:24. Serve una nuova verifica read-only.
- Il checkpoint precedente riportava dashboard con equity 2.249,64 USDT, netto sessione 195,86 USDT e “trade chiusi” 2.393,80 non coerenti. L'anomalia resta da riconciliare; non viene reinterpretata né corretta qui.

## Dashboard, apprendimento, Live Evolution e attività non collegate

- Web-only del 25/11 ore 06:35: `APP_PAPER_INSTALLATA_E_VERIFICATA`, `WEB_EXIT_CODE=0`; runner, uscite e bridge non riavviati in quell'operazione.
- Correzione conteggi `work/brain-v2-web-counts-20261125` @ `6e305ed027e6aca132b0b3c1f27f42933ef902cd`: arrotondamento `paper_reduce` corretto nella web; runner/memoria delle riduzioni parziali non ancora certificati.
- Live Evolution risulta implementato/installato; simulazione V2→V3 con posizione aperta passata. Collaudo operativo completo ancora pendente.
- Signal Lab, Evolution X, modelli predittivi e Ghost Trading offline emersi in altre conversazioni restano separati dal Brain operativo e non sono trattati come modifiche al repository originale o alla VPS.

## Backup, chiavi e servizi — senza dati sensibili

- `claude/extbackup-storici-20261121` @ `1588c95af8411b48616d73203d5d10211d38e246`.
- Il 22/11 il proprietario ha eseguito il backup definitivo cifrato e lo ha verificato da clone nuovo: indispensabili tecnicamente certificati; storici tecnicamente integri; Falco/Toro non certificati semanticamente.
- Restore Windows dei nuovi archivi ancora incompleto. Procedura Android/Termux e copia aggiuntiva degli indispensabili preparate ma non eseguite.
- `work/extbackup-bot-stopped-20261109` @ `3dc2116a08058f57fc14b695431f6e3fa1a1ca45`: artefatto storico preparato, non installato né certificato; preservato.
- Copia cifrata della chiave age sul PC: output PowerShell `ESITO: VERIFICA OK`; chiave pubblica derivata coincidente. È una prova locale e non certifica presenza, backup o ripristinabilità sulla VPS.
- Stato servizi dimostrabile solo nel punto temporale della conversazione: uscite ripartite, runner riavviato dall'utente e poi fermato dal gate budget. Nessuna asserzione live successiva.

## Branch, PR, issue e SHA verificati

- `diario` prima di questa scrittura: `53f2bc6a6647df03324ea45702bff4bb81b50a5b`.
- `main`: `a1e9722a1a9af32ee045ebf61d7e43858c9a1d5e`.
- `integration/brain-unico-20261119`: `f50f7ae40c78e7994f33d0dabf40f91d57d7873f`.
- `claude/tetto-posizioni-20261121`: `887fc9616b5eedc2b4441357618fd5469ab5977d`.
- `claude/extbackup-storici-20261121`: `1588c95af8411b48616d73203d5d10211d38e246`.
- `claude/live-evolution-20261124`: `d1bc0628bb0fea6f1f5012ede6148cb1d93c0ccd`.
- `work/brain-v2-web-counts-20261125`: `6e305ed027e6aca132b0b3c1f27f42933ef902cd`.
- `work/extbackup-bot-stopped-20261109`: `3dc2116a08058f57fc14b695431f6e3fa1a1ca45`.
- `claude/brain-unico-2000-20261124`: `c5d05f3f3a31e8b0cfe51949fa06fa4ec04c398b`.
- `claude/ingresso-unico-20261124`: `612f6b4b868bb0828a23792f0f46e5946c7ddf6d`.
- RC84 PR #80: open, draft, non merged; head `0e29a73a36f668643da4088178bacb8616a45ac0`; aggiornata l'ultima volta il 09/11. I test della PR sono scritti ma non dichiarabili indipendentemente eseguiti/verdi.
- Issue #124: closed/completed il 22/11.

## Test e fonte dei risultati

- Tetto quattro posizioni/rischio: ramo `887fc961…`; integrazione/piano sopra. Risultati ereditati dal repository, non rilanciati in questa esecuzione.
- Issue #124: quattro test dedicati; tre rossi prima della correzione; suite V3 dichiarata 5.414.
- Brain V2 `6a96e599…`: suite dichiarate V3 5.588, Builder 158, Jest 212; ripartenza 13/13; simulatore 2/2.
- Integrazione app `f50f7ae4…`: V3 5.500 con un test skipped, Builder 158, Jest 210, Android 126/126.
- Correzione conteggi `6e305ed…`: regressione mirata documentata; nessuna full suite o GitHub Actions rilanciata da questo checkpoint.
- La diagnosi del watchdog e i contatori budget provengono dalla conversazione recente e dai log mostrati lì; questo checkpoint non ha rieseguito comandi sulla VPS.

## Eseguito, preparato, non approvato

### Eseguito/verificato prima o fuori da questo checkpoint

- Brain V2 PAPER e web-only come sopra; backup cifrato definitivo del 22/11; verifica locale age; riavvio utente seguito dalla breve osservazione `running`.
- Questo checkpoint: sole letture e documentazione append-only.

### Preparato ma non installato/completato

- backup storico `work/extbackup-bot-stopped-20261109`;
- restore Windows, procedura Android/Termux e copia aggiuntiva;
- attività di riconciliazione conteggi e certificazione riduzioni parziali runner/memoria.

### Non approvato e non eseguito qui

- aumento/reset del budget DeepSeek o Claude;
- modifica di watchdog, unità systemd o servizi;
- riavvio ulteriore, reset, deploy, merge, Actions, modifiche VPS, nuovi ordini o API a pagamento.

## Blocker, prossime attività e istruzioni di ripresa

1. Leggere prima `STATO.md`, questo checkpoint e la sezione più recente del file Library; verificare che i due testi coincidano prima di assumere continuità.
2. Eseguire solo se autorizzato un controllo read-only: stato runner/uscite, motivo HALT, heartbeat e ciclo, posizioni PAPER, ultime righe EventJournal; non riavviare nulla durante la diagnosi.
3. Acquisire i log attorno alle 18:05:56 per determinare la causa del timeout watchdog senza confondere il meccanismo systemd già dimostrato con la causa originaria ancora ignota.
4. Trattare `halted:budget` come gate corretto finché il proprietario non decide esplicitamente se attendere il rinnovo, modificare il budget o lasciare il runner fermo. Non aggirare il limite.
5. Riconciliare in sola lettura equity, netto sessione e contatore “trade chiusi”; verificare anche `paper_reduce` tra web, runner e memoria.
6. Conservare EventJournal, run archiviate e sessioni di apprendimento. Non toccare Falco/Toro/Brain classici né il backup storico non installato.
7. Se una destinazione del doppio salvataggio risultasse non aggiornata, il checkpoint successivo deve recuperarla prima di aggiungere altre novità.

## Azioni escluse in questa esecuzione

Nessuna modifica di codice operativo, merge, deploy, GitHub Actions, VPS, reboot, riavvio, reset, ordine o API a pagamento. Nessun segreto letto o esposto.
