# Checkpoint verificabile SuperBot-Trading — 27/11/2026 08:46 Europe/Rome

## Novità verificata: diagnostica F0 ristretta e di sola lettura

- Fonte primaria: GitHub Actions run [#45958637995](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/45958637995), job `status` `140370929233`, concluso `success` alle 08:28 Europe/Rome.
- Il log conferma che la credenziale F0 è stata accettata e che l'accesso ha eseguito soltanto il comando forzato di stato: risposta `read_only=true`, `status=OBSERVATION_ONLY`, operatore ristretto. Nessun valore di chiave viene riportato in questo checkpoint.
- Osservato sulla VPS: radice backup `PRESENT`; database Brain e relativi file WAL/SHM `PRESENT`; 10 processi corrispondenti e 11 unità systemd marcati soltanto `POSSIBLE_ACTIVE`.
- Per Falco/Toro classici le directory risultano `PRESENT`, ma archivio e file richiesti sono `UNAVAILABLE` nel perimetro F0: non è prova di assenza, integrità o completezza degli storici.
- Il risultato dichiara esplicitamente `not_a_backup_certificate=true`: non certifica contenuto/ripristinabilità dei backup, salute reale dei servizi, stato dei runner, posizioni, P&L o ordini; nessuna modifica VPS è stata eseguita.
- Questa verifica è distinta dalla prova locale age sul PC (`ESITO: VERIFICA OK`, chiave pubblica coincidente), che resta locale e non certifica il backup sulla VPS.

## Stato consolidato utilizzabile per la ripresa

- **Obiettivo e confine:** tre portafogli esclusivamente PAPER; `NO_TRADE` è valido; preservare EventJournal, archivi, memoria e storici. Nessun LIVE, merge, deploy, reset, ordine o spesa API senza gate e autorizzazione separati.
- **Falco:** classico preservato; Falco Evoluto archiviato/disabilitato per Brain V2. La nuova F0 prova solo la presenza della directory classica, non contenuto o salute.
- **Toro:** storico preservato, stato `semantic_not_certified`; non è il bot corrente della dashboard. La nuova F0 prova solo la presenza della directory classica. Le vecchie associazioni Bitget riferite dall'utente non sono state inventariate, riusate, revocate o convertite.
- **Brain:** run `brain-scalp-paper-p1`, capitale operativo 2.000 USDT, 27 strumenti e 10 slot; vecchia run con 539 eventi e tre sessioni collegate in sola lettura. V2 resta l'ultima versione attiva dimostrata; V3 `f9ae6e8bf8` è stata generata ma non approvata.
- **Brain V2 implementato:** ciclo 30m, leva 15–50×, margine massimo 400/trade e 55% totale, rischio 4,3%/trade e 12% aperto, stop giornaliero 25%, confidenza 0,56, veto Claude, fallback dimezzato spento, LONG soltanto con trend 1h+4h, costi/slippage entro 30% di 1R.
- **Desiderato ma non implementato sul Brain originale:** ridurre costi AI e aumentare opportunità valide a portafoglio vuoto, con più prudenza a 3–4 posizioni o dopo profitto. Smart AI Router, Opportunity Discovery e Adaptive Selectivity appartengono alla roadmap Evolution X PAPER separata.
- **Pausa:** il diario conserva la pausa eseguita il 24/11 alle 17:21:47 UTC, con uscite sane e nessuna nuova apertura dopo la pausa; successivamente V2 è stata avviata. La nuova pausa raccomandata il 26/11 per contenere costi non risulta autorizzata o eseguita.
- **Servizi:** prova dettagliata precedente del 26/11 11:28: runner `running`, uscite `healthy`, 146 `NO_TRADE`, 16 `ai_unavailable`, zero aperture, budget applicativo DeepSeek 3,8811/4 USD. La F0 del 27/11 è più recente ma più limitata: prova soltanto presenza di artefatti e possibili processi/unità, non salute live.
- **Contabilità:** ultimi valori dashboard documentati 26/11 09:33: equity 2.209,73, totale contabile 2.393,80, netto sessione -3,54; differenza da riconciliare, non saldo corrente.
- **Backup e chiavi:** backup cifrato del 22/11 documentato verificato da clone nuovo; restore Windows incompleto, Android/Termux preparato non eseguito. Sul PC la copia cifrata della chiave age ha restituito PowerShell `ESITO: VERIFICA OK` e la chiave pubblica derivata coincide: prova locale soltanto. `work/extbackup-bot-stopped-20261109` @ `3dc2116a08058f57fc14b695431f6e3fa1a1ca45` resta preparato, non installato né certificato.
- **GitHub verificato:** RC84 PR [#80](https://github.com/alexiptv82/SuperBot-Trading/pull/80) resta open/draft/non merged, head `0e29a73a36f668643da4088178bacb8616a45ac0`, aggiornata l'ultima volta il 09/11. Riferimenti consolidati invariati: `main` `a1e9722a1a9af32ee045ebf61d7e43858c9a1d5e`, integrazione `f50f7ae40c78e7994f33d0dabf40f91d57d7873f`, tetto posizioni `887fc9616b5eedc2b4441357618fd5469ab5977d`, backup `1588c95af8411b48616d73203d5d10211d38e246`, Live Evolution `d1bc0628bb0fea6f1f5012ede6148cb1d93c0ccd`, web counts `6e305ed027e6aca132b0b3c1f27f42933ef902cd`.
- **Test con fonte:** Brain V2 documenta V3 5.588, Builder 158, Jest 212, restart 13/13 e simulatore 2/2; integrazione documenta V3 5.500 con 1 skipped, Builder 158, Jest 210 e Android 126/126. La novità odierna è una diagnostica F0, non un nuovo test funzionale del trading.

## Eseguito, preparato e non approvato

- **Eseguito/verificato:** diagnostica F0 ristretta e read-only; Brain V2 PAPER e web-only già documentati; backup cifrato e verifica locale age; proposta V3 generata; sviluppo strategico separato su Evolution X PAPER.
- **Preparato/proposto:** V3 `f9ae6e8bf8`, nuova pausa controllata, restore e riconciliazioni, `work/extbackup-bot-stopped-20261109`, futura automazione Evolution X e inventario non sensibile delle vecchie associazioni Bitget.
- **Non approvato/non provato:** nuova pausa Brain, V3, installazione backup esterno, completezza/ripristinabilità backup VPS, salute live dei servizi dal solo F0, riuso/revoca/rotazione credenziali, LIVE, variazioni di rischio/budget, merge/deploy/restart/reset/VPS/ordini/API a pagamento.

## Blocker, prossime attività e istruzioni di ripresa

1. Trattare la F0 come osservazione limitata: `POSSIBLE_ACTIVE` non equivale a servizio sano; `PRESENT` non equivale a backup verificato.
2. Non assumere contenuto mancante per Falco/Toro: `UNAVAILABLE` indica che F0 non può provarlo. Verifica più profonda richiede mandato separato e resta fuori da questo checkpoint.
3. Trattare V2 come ultima attiva dimostrata; non assumere V3 o la nuova pausa del 26/11 applicate.
4. Mantenere Evolution X separata e PAPER; non riutilizzare automaticamente vecchie credenziali Bitget.
5. Preservare Falco, Toro, Brain, EventJournal, archivi, memoria, backup e tutte le sezioni storiche.

