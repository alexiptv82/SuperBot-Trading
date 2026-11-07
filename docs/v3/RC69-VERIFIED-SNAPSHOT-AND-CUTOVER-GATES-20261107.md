# SuperBot V3 — RC69: backup storico verificato e gate per rilascio PAPER

**Data:** 7 novembre 2026. **Stato:** PREPARAZIONE / NO-GO per deploy, merge, restart e chiusura ordini.

## 1. Verifica VPS Singapore (esecuzione effettiva, sola lettura)

CI: [audit #42366163684](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/42366163684), 7/11/2026 alle 10:58 UTC; nuovo audit del medesimo job dopo la copia.

- Falco `superbot-desk-hawk`: `running=false`, `restart=no`, `DESK_MODE=paper`, `pause.flag` presente, **6 posizioni PAPER**, nessuna chiusura in sospeso. Tutti i quattro file essenziali presenti.
- Toro `superbot-desk-bull`: condizioni identiche, **2 posizioni PAPER**.
- `superbot` web app: container in esecuzione, source mount delle due directory legacy presente. **Mancano nel container installato** le variabili `V3_JOURNAL_PATH`, `V3_RUN_ID`, `V3_RUNNER_CONFIG_PATH`, `V3_CLOSE_REQUEST_PATH`. La nuova pagina React e le API V3 della PR #68 NON sono per ciò stesso installate.
- Spazio disponibile al preflight: circa 31.155 MiB.
- Prima dello snapshot non esisteva nessuna cartella di backup non compressa con i 4 file essenziali byte-identici al dato attuale.

## 2. Snapshot locale creato, ripristinato e attestato

Workflow che ha scritto **solo nuova destinazione backup** sulla VPS:
[RC69 local snapshot + restore #42366491343](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/42366491343).

- Directory verificata: `/opt/superbot-backups/rc69-paper-legacy-20261107T110255Z-142218/`.
- Sottodirectory `hawk/` e `bull/`, file completi, con `MANIFEST.json` tipizzato nel root.
- Falco: **38 file**, 6 posizioni. Toro: **36 file**, 2 posizioni.
- Ogni file copiato confrontato SHA-256 con la fonte; dati originali non mutati dall'azione di snapshot; prova di restore in cartelle temporanee separate con stessi hash e posizioni. Tutti i gate PASS.
- [Verifica indipendente read-only #42366742253](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/42366742253): **1 snapshot con manifest integro**, completo e corrispondente agli attuali 38+36 file.
- Esiste anche una **prima cartella RC69 con manifest non valido** (bug metadato contatore): *non usarla* come riferimento di avvio o come prova. La cartella selezionata sopra è quella corretta e certificata.
- Questa è una copia **LOCALE** sulla stessa VPS. Non equivale a backup cifrato esterno, non copre guasti fisici o cancellazione del server intero. Utente informato della differenza.

## 3. Preparazione del cutover: due perimetri distinti

**A. Chiusure storiche** (Falco/Toro, 6+2 PAPER):
1. Mantenere i vecchi container stopped + restart `no`, senza riattivarne scanner, strategie, Claude o cicli automatici per gestire vecchie posizioni.
2. Installare soltanto dopo specifico OK due servizi **exit-only** (PR #65), con dir dati `/opt/superbot-desk-data/{hawk,bull}` e snapshot sopra `.../hawk`, `.../bull`. Worker richiede `DESK_MODE=paper`, `DESK_PORTFOLIO=hawk|bull`, `DESK_DATA_DIR` esatta, `pause.flag`, preflight ownership, snapshot SHA e lock unico. **Mai** avvio implicito dei motori classici.
3. Web app aggiornata in modalità sicura deve poter **vedere** heartbeat `exit_only_heartbeat.json`, inviare richiesta singola/tutte autenticata, attendere esito verificato dal bot e registrare `closed_by=utente`, P&L netto, costo, `manual_learning` come esempio **non** strategia convalidata.
4. Test su una **copia isolata** prima di accettare qualunque chiusura storica. Nessuna delle otto posizioni deve essere chiusa automaticamente: l'utente sceglie singolarmente dall'app.

**B. Nuova run V3 PAPER** (nuovi storici separati, Falco 1.000, Toro 1.000, Brain 2.000 USDT):
1. I tre portafogli restano indipendenti per fondi, posizioni, rischi e storico; stessa presentazione e funzioni UI. Non ricostruire i classici: mantenere consultazione Claude, strategie SHORT funzionanti, miglioramento LONG e cambio trend senza stravolgimenti.
2. Brain: run ID nuovo, journal/ledger e servizi preparati; config specifica `backend/v3/runner/runner_config_brain2000_paper.json` **pinned all'hash di release** e esposta al web come `V3_RUNNER_CONFIG_PATH`. Non sostituire con `runner_config.json` predefinito, che può appartenere ad altra run.
3. `V3_JOURNAL_PATH`, `V3_RUN_ID`, `V3_HEARTBEAT_PATH`, `V3_BUDGET_DB_PATH`, `V3_PAUSE_FLAG_PATH`, `V3_CLOSE_REQUEST_PATH` e relativo result: percorsi coerenti fra processi e web, senza inferire valori sconosciuti. In assenza, mostrare dati non disponibili.
4. Brain osservatore classici: `V3_BRAIN_PEER_OBSERVATIONS` disattivato di default; l'opzione `paper_readonly` richiede mount validi e snapshot recenti (<=60 secondi) per `V3_FALCO_DATA_DIR` e `V3_TORO_DATA_DIR`, senza poter copiare ordini o condividere capitali. Classic stoppati => nessun dato da consumare, non un segnale falsificato.
5. Per testare una nuova run, utilizzare dataset di test / staging e verifica mandato di rischio; nessun reset dei dati legacy, nessuna equity fittizia mostrata come capitale realmente in uso.
6. Non promuovere alle strategie l'apprendimento da un'uscita manuale senza validazioni/outcome indipendenti.

## 4. Gate del rilascio Web e test su smartphone

- Sono attualmente in bozza le PR #64, #65, #66, #67, #68, e la RC #62. Non fare merge non revisionati: controllare la sequenza del ramo e le CI complete prima del rilascio.
- Preparare la UI con Falco/Toro/Brain **identici nell'uso** (posizioni, prezzi, leva, margine, TP/SL, P&L/ROI, chiusura singola e totale, storico, statistiche); moduli AI Brain aggiuntivi, non un portafoglio diverso.
- Prima prova senza modifiche ai bot: autenticazione reale, permessi, montaggi e visibilità delle 8 posizioni PAPER storiche senza prezzi inventati, indicazione esplicita che il worker è offline se non avviato.
- Solo su successiva autorizzazione ad installare i due worker su VPS: preflight SHA contro snapshot, prova click singola con quote fresh, risultato PnL NETTO e learning, verifica delle posizioni restanti e stato originale dei container.
- Eseguire nuova copia locale dopo chiusure storiche e **prima** della nuova run; non azzerare né cancellare mai lo storico.

## 5. Dichiarazione del lavoro svolto

In RC69 finora sono stati eseguiti solo: GitHub branch/CI e uno snapshot locale verificato degli **storici** in una nuova directory separata. Nessun servizio installato, avviato, fermato, riavviato; nessun merge, deploy, ordine o reset. La ripartenza ufficiale resta **NO-GO fino a OK specifico** e prove smartphone effettive.
