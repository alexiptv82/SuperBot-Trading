# Checkpoint verificabile SuperBot-Trading — 26/11/2026 13:43 Europe/Rome

## Esito, fonti e limiti

Checkpoint append-only di ripresa di `alexiptv82/SuperBot-Trading`, esclusivamente PAPER. Fonti consultate:

1. GitHub, ramo `diario`: `STATO.md`, checkpoint delle 12:53, ultimi commit visibili, branch elencati sotto e RC84 PR #80;
2. `/SuperBot-Ripresa/ULTIMO-STATO-SUPERBOT.md`, Library `libfile_754adf32b63881919d64ef3bc26b222a`, versione 154 prima di questa scrittura;
3. conversazioni recenti effettivamente accessibili dopo le 12:53 e screenshot Termius delle 13:00.

Lo screenshot è una prova puntuale dell'output dei comandi già eseguiti dall'utente; non certifica lo stato live successivo. Questo checkpoint non ha eseguito comandi sulla VPS, test, chiamate AI a pagamento o azioni operative. Nessuna chat persa è stata ricostruita e nessun segreto o identificativo di accesso è stato pubblicato.

## Novità verificata: proposta V3 generata, non approvata

- Lo screenshot Termius delle 13:00 mostra `superbot-strategia stato`: versione attiva per le nuove aperture `V2`, configurazione di base della run, frequenza di analisi 30 minuti.
- Il comando `superbot-strategia proponi` è stato effettivamente eseguito dall'utente e ha generato la proposta `f9ae6e8bf8`, descritta come nuova versione `V3`, mentre V2 è rimasta attiva.
- Nota proposta: cercare prioritariamente opportunità coerenti con trend 1h e 4h; valutare SHORT su trend ribassisti con pullback/breakdown confermati e LONG soltanto su trend rialzisti concordi; considerare momentum, volumi, costi e rapporto rendimento/rischio; non forzare aperture e scegliere `NO_TRADE` quando il vantaggio è insufficiente.
- L'output dichiara che, se approvata, V3 varrebbe per le nuove aperture dal giro successivo e le posizioni già aperte completerebbero la loro versione. Non risulta eseguita l'approvazione: nessuna prova di attivazione V3 o di modifica delle aperture.
- Correzione del checkpoint 12:53: allora la proposta era documentata soltanto come preparata; lo screenshot successivo prova che è stata generata, ma non approvata.

## Decisione utente e roadmap

- L'utente ha deciso di dedicare lo sviluppo direttamente a SuperBot Evolution X, lasciando invariato il Brain originale salvo manutenzione e sicurezza.
- Obiettivi spostati nella roadmap Evolution X: ridurre i costi AI e aumentare la capacità di trovare opportunità valide quando il portafoglio è vuoto, rendendo il sistema più reattivo ma non più aggressivo.
- Con tre o quattro posizioni aperte, o dopo profitto già realizzato, il sistema deve restare più prudente. `NO_TRADE`, protezioni e qualità minima non vanno rimossi.
- Componenti indicati per Evolution X: Smart AI Router, Opportunity Discovery e Adaptive Selectivity; DeepSeek trader e Claude consulente. Tutto resta PAPER, subordinato a validazione e approvazione; EX-08C dashboard resta l'attività corrente riportata dalla conversazione Evolution X.
- Nessuna nuova prova o azione sul Brain originale è disponibile dopo lo screenshot delle 13:00.

## Tre portafogli PAPER: desiderato contro implementato

| Portafoglio | Desiderato | Implementato/verificato | Stato più recente dimostrabile |
|---|---|---|---|
| Falco | classico distinto, strategia e storico preservati; evoluzione solo con autorizzazione | Falco classico preservato; Falco Evoluto installato il 23/11, poi archiviato/disabilitato con la nuova sessione Brain V2 | nessun nuovo controllo live |
| Toro | classico distinto e storico preservato | storico preservato; resta `semantic_not_certified`, quindi integrità tecnica non equivale a correttezza semantica | non è il bot corrente mostrato dalla dashboard Brain |
| Brain | portafoglio unico PAPER da 2.000 USDT, DeepSeek principale, Claude revisore, memoria collegata | run `brain-scalp-paper-p1`, 27 strumenti, 10 slot; vecchia run archiviata con 539 eventi e tre sessioni collegate in sola lettura | ore 13:00: V2 ancora attiva; proposta V3 generata ma non approvata; nessuna nuova prova live di runner, posizioni o aperture |

## Configurazione e rischio: desiderato contro implementato

- Profilo B precedente: tetto esplicito di quattro posizioni e rischio aperto comprensivo dei costi; integrazione `c11e6d7d…`, piano `302e94d2…`.
- Issue #124: correzione `0f71d0be…`, integrazione `5f110379…`, chiusa il 22/11. Il latch deve bloccare nuove aperture senza impedire le uscite.
- Brain V2 documentato come installato: ciclo 30 minuti; leva dinamica 15–50×; margine massimo 400 USDT per trade; margine totale 55%; rischio per trade 4,3%; rischio aperto 12%; stop giornaliero 25%; 27 strumenti e 10 slot.
- DeepSeek: confidenza minima 0,56. Claude conserva il veto. Fallback senza Claude a rischio dimezzato disattivato. LONG soltanto con trend 1h+4h. Costi e slippage proposti entro il 30% di 1R.
- La proposta V3 non risulta approvata e non modifica ancora questi valori. Non contiene autorizzazione ad abbassare automaticamente la qualità per aprire più rapidamente.

## Servizi, dashboard, contabilità e apprendimento

- Ultima prova di servizi resta quella delle 11:28: runner `running`, uscite `healthy`, errori `None`, heartbeat recenti; 146 `NO_TRADE`, 16 `ai_unavailable`, zero aperture nelle tre ore precedenti.
- Filtri osservati: 25 `long_against_trend`, 19 `confidence_below_floor`, 3 `cost_too_high_for_stop`, 3 `claude_contested`; budget applicativo DeepSeek 3,8811/4 USD. Non è saldo provider o fattura certificata.
- Lo screenshot 13:00 certifica soltanto stato strategia/proposta, non salute dei servizi, posizioni o budget successivi.
- Dashboard 09:33: equity 2.209,73 USDT, totale contabile 2.393,80 USDT, netto sessione -3,54 USDT; valori ancora non riconciliati.
- Web-only del 25/11: `APP_PAPER_INSTALLATA_E_VERIFICATA`, `WEB_EXIT_CODE=0`, senza riavvio di runner, uscite o bridge.
- `work/brain-v2-web-counts-20261125` @ `6e305ed027e6aca132b0b3c1f27f42933ef902cd`: correzione web verificata; runner/memoria delle riduzioni parziali non certificati.

## Backup e chiavi, senza dati sensibili

- `claude/extbackup-storici-20261121` @ `1588c95af8411b48616d73203d5d10211d38e246`.
- Backup cifrato definitivo del 22/11 documentato come inviato e verificato da clone nuovo; restore Windows incompleto; Android/Termux e copia aggiuntiva preparati ma non eseguiti.
- `work/extbackup-bot-stopped-20261109` @ `3dc2116a08058f57fc14b695431f6e3fa1a1ca45`: backup esterno storico preparato, non installato né certificato; preservato.
- Copia cifrata della chiave age sul PC: PowerShell `ESITO: VERIFICA OK`; chiave pubblica derivata coincidente. È prova locale e non certifica backup, presenza o ripristinabilità sulla VPS.

## Branch, PR, issue e SHA verificati

- `diario` prima di questa scrittura: `1886ec12dfb613bf9d2906bf901a139bf685286d`.
- `main`: `a1e9722a1a9af32ee045ebf61d7e43858c9a1d5e`.
- `integration/brain-unico-20261119`: `f50f7ae40c78e7994f33d0dabf40f91d57d7873f`.
- `claude/tetto-posizioni-20261121`: `887fc9616b5eedc2b4441357618fd5469ab5977d`.
- `claude/extbackup-storici-20261121`: `1588c95af8411b48616d73203d5d10211d38e246`.
- `claude/live-evolution-20261124`: `d1bc0628bb0fea6f1f5012ede6148cb1d93c0ccd`.
- `work/brain-v2-web-counts-20261125`: `6e305ed027e6aca132b0b3c1f27f42933ef902cd`.
- `work/extbackup-bot-stopped-20261109`: `3dc2116a08058f57fc14b695431f6e3fa1a1ca45`.
- RC84 PR #80: open, draft, non merged; head `0e29a73a36f668643da4088178bacb8616a45ac0`; ultimo aggiornamento 09/11/2026.
- Issue #124: closed/completed il 22/11/2026.
- EX-08B `cb31997f` resta non riscontrato nel repository SuperBot-Trading e non va trattato come SHA verificato di questo progetto.

## Test e fonte

- Tetto quattro posizioni/rischio: ramo `887fc961…`; risultati ereditati, non rilanciati qui.
- Issue #124: quattro test dedicati; tre rossi prima della correzione; suite V3 dichiarata 5.414.
- Brain V2 `6a96e599…`: V3 5.588, Builder 158, Jest 212, ripartenza 13/13, simulatore 2/2, dai materiali di rilascio.
- Integrazione app `f50f7ae4…`: V3 5.500 con un test skipped, Builder 158, Jest 210, Android 126/126.
- Correzione conteggi `6e305ed…`: regressione mirata documentata; nessuna full suite o GitHub Actions rilanciata dal checkpoint.
- Nuova fonte: screenshot Termius delle 13:00, ispezionato visivamente. Nessun nuovo test è stato eseguito per generare la proposta V3.

## Eseguito, preparato, non approvato

### Eseguito/verificato prima o fuori da questo checkpoint

- Brain V2 PAPER e web-only; backup cifrato definitivo; verifica locale age; diagnostica read-only delle 11:28.
- Comandi `superbot-strategia stato` e `proponi` eseguiti dall'utente; proposta V3 `f9ae6e8bf8` generata.
- Decisione utente: sviluppo strategico spostato su Evolution X, Brain originale invariato.
- In questa esecuzione: sole letture e doppia documentazione append-only.

### Preparato ma non installato/completato

- proposta strategica V3 `f9ae6e8bf8`, in attesa di approvazione esplicita;
- Smart AI Router, Opportunity Discovery e Adaptive Selectivity nella roadmap Evolution X;
- backup storico `work/extbackup-bot-stopped-20261109`;
- restore Windows, procedura Android/Termux, riconciliazione contabile e certificazione `paper_reduce`.

### Non approvato e non eseguito qui

- approvazione/attivazione della proposta V3;
- modifica di soglie, capitale, leva, stop, budget, watchdog o servizi;
- restart, reset, deploy, merge, Actions, modifiche VPS, ordini o API a pagamento.

## Blocker, prossime attività e istruzioni di ripresa

1. Leggere `STATO.md`, questo checkpoint e la prima sezione del file Library; verificarne la coincidenza.
2. Brain originale: considerare V2 ancora attiva finché non esiste prova esplicita di approvazione/attivazione della proposta V3. Non approvarla automaticamente.
3. Proseguire il lavoro strategico su Evolution X in PAPER, integrando ottimizzazione costi e reattività a portafoglio vuoto senza abbassare automaticamente qualità e protezioni.
4. Non confondere la proposta Live Evolution del Brain originale con Smart Router/Adaptive Selectivity di Evolution X.
5. Riconciliare equity 2.209,73, totale 2.393,80 e netto -3,54; verificare watchdog e `paper_reduce` soltanto in lettura.
6. Riconciliare EX-08B con SHA completo/branch corretto prima di attribuire codice o test.
7. Preservare Falco, Toro, Brain, EventJournal, archivi, memoria e backup storico.
8. Se una delle due scritture fallisce, il checkpoint successivo deve recuperare prima quella destinazione.

## Azioni escluse

Nessuna modifica di codice operativo, merge, deploy, GitHub Actions, VPS, reboot/riavvio, reset, ordine o API a pagamento. Nessun segreto letto o esposto.

