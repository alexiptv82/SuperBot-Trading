# Checkpoint verificabile SuperBot-Trading — 26/11/2026 16:45 Europe/Rome

## Novità verificata: automazione futura e separazione netta delle credenziali LIVE

- L'utente desidera che l'eventuale messa in funzione futura di Evolution X sia più automatizzata e non ripeta il lungo percorso manuale del Brain originale. È un requisito di roadmap, non prova di installazione o prontezza operativa.
- L'utente ha segnalato di vedere ancora in Bitget le vecchie associazioni reali usate storicamente con Toro/Falco e ha chiesto se riutilizzarle o trasformarle per Evolution X.
- Piano proposto e vincolo di sicurezza: non riutilizzare automaticamente quelle credenziali; inventariarle senza leggerne o esporne i valori e valutare la revoca di quelle inutilizzate solo dopo verifica. Evolution X resta PAPER e LIVE disabilitato; un eventuale futuro LIVE richiederà una credenziale dedicata e un'autorizzazione esplicita separata.
- Non risultano inventario, revoca, rotazione, nuova associazione, attivazione LIVE, ordine reale o altra azione eseguita. Lo stato, l'ambito e la validità delle vecchie associazioni Bitget non sono stati verificati in questa esecuzione.
- Gli avanzamenti recenti EX-09A* appartengono allo sviluppo isolato Evolution X PAPER e non modificano il Brain originale; non sono stati usati per attribuire deploy o stato operativo a SuperBot-Trading.

## Stato consolidato utilizzabile per la ripresa

- **Obiettivo e confine:** tre portafogli esclusivamente PAPER, decisioni prudenti e `NO_TRADE` valido; preservare EventJournal, archivi, memoria e storici. Nessun passaggio a denaro reale senza un gate separato e autorizzazione esplicita.
- **Falco:** classico preservato; Falco Evoluto installato in precedenza e poi archiviato/disabilitato per Brain V2. Nessuna prova live fresca.
- **Toro:** storico preservato, stato `semantic_not_certified`; non è il bot corrente della dashboard. Le vecchie associazioni Bitget riferite dall'utente non sono state controllate né convertite.
- **Brain:** run `brain-scalp-paper-p1`, capitale operativo 2.000 USDT, 27 strumenti e 10 slot; vecchia run con 539 eventi e tre sessioni collegate in sola lettura. V2 resta l'ultima versione attiva dimostrata; V3 `f9ae6e8bf8` è stata generata ma non approvata.
- **Brain V2 implementato:** ciclo 30m, leva 15–50×, margine massimo 400/trade e 55% totale, rischio 4,3%/trade e 12% aperto, stop giornaliero 25%, confidenza 0,56, veto Claude, fallback dimezzato spento, LONG soltanto con trend 1h+4h, costi/slippage entro 30% di 1R.
- **Desiderato ma non implementato sul Brain originale:** ridurre costi AI e aumentare la ricerca di opportunità valide a portafoglio vuoto, con più prudenza a 3–4 posizioni o dopo profitto; Smart AI Router, Opportunity Discovery e Adaptive Selectivity sono roadmap Evolution X PAPER. La futura attivazione dovrebbe essere automatizzata, ma non è certificata pronta.
- **Servizi:** ultima prova diretta resta 11:28 Europe/Rome: runner `running`, uscite `healthy`, nessun errore, 146 `NO_TRADE`, 16 `ai_unavailable`, zero aperture; budget applicativo DeepSeek 3,8811/4 USD, non saldo provider. Screenshot 13:00 prova V2 attiva e proposta V3 generata, non lo stato live successivo. La pausa controllata delle nuove aperture è soltanto raccomandata, non autorizzata né provata eseguita.
- **Contabilità:** ultimi valori dashboard 09:33: equity 2.209,73, totale contabile 2.393,80, netto sessione -3,54; differenza da riconciliare, non prova di saldo corrente.
- **Backup e chiavi:** backup cifrato definitivo del 22/11 documentato verificato da clone nuovo; restore Windows incompleto, Android/Termux preparato non eseguito. Sul PC la copia cifrata della chiave age ha restituito PowerShell `ESITO: VERIFICA OK` e la chiave pubblica derivata coincide: prova locale soltanto, non certificazione del backup sulla VPS. `work/extbackup-bot-stopped-20261109` @ `3dc2116a08058f57fc14b695431f6e3fa1a1ca45` resta preparato, non installato né certificato.
- **GitHub verificato:** RC84 PR #80 resta open/draft/non merged, head `0e29a73a36f668643da4088178bacb8616a45ac0`, base RC82 `1e64684b9d813aad1ca1c7d344872333e451fd05`; nessun nuovo test indipendente dichiarato dalla PR. Ultimi SHA di riferimento invariati: `main` `a1e9722a1a9af32ee045ebf61d7e43858c9a1d5e`, integrazione `f50f7ae40c78e7994f33d0dabf40f91d57d7873f`, tetto posizioni `887fc9616b5eedc2b4441357618fd5469ab5977d`, backup `1588c95af8411b48616d73203d5d10211d38e246`, Live Evolution `d1bc0628bb0fea6f1f5012ede6148cb1d93c0ccd`, web counts `6e305ed027e6aca132b0b3c1f27f42933ef902cd`. EX-08B `cb31997f` resta non riscontrato nel repository.
- **Test con fonte:** Brain V2 documenta V3 5.588, Builder 158, Jest 212, restart 13/13 e simulatore 2/2; integrazione documenta V3 5.500 con 1 skipped, Builder 158, Jest 210 e Android 126/126. Nessun test rilanciato in questo checkpoint.

## Eseguito, preparato e non approvato

- **Eseguito/verificato:** Brain V2 PAPER e web-only; backup cifrato e verifica locale age; diagnostica read-only 11:28; proposta V3 generata; decisione di concentrare lo sviluppo strategico su Evolution X PAPER.
- **Preparato o proposto:** V3 `f9ae6e8bf8`, pausa controllata, roadmap Evolution X, futura automazione di attivazione, inventario/revoca prudente delle vecchie associazioni Bitget, restore e riconciliazioni.
- **Non approvato/non provato:** pausa Brain, approvazione V3, riuso/revoca/rotazione di credenziali, integrazione provider reale, LIVE, cambi soglie/rischio/budget/servizi, restart/reset/deploy/merge/GitHub Actions/VPS/ordini/API a pagamento.

## Blocker, prossime attività e istruzioni di ripresa

1. Non assumere stato live VPS o validità delle vecchie associazioni Bitget; non leggere o copiare segreti. Se l'utente autorizzerà una verifica futura, limitarsi prima a un inventario non sensibile e separare revoca/rotazione da qualsiasi integrazione.
2. Mantenere Evolution X in PAPER e progettare una procedura di attivazione ripetibile; il gate LIVE deve restare disabilitato finché non esistono validazione, credenziale dedicata e autorizzazione esplicita.
3. Trattare V2 come attiva finché non esiste prova dell'approvazione V3; non assumere che la pausa raccomandata sia stata applicata.
4. Prima di nuovo credito AI, verificare in sola lettura limite e scarti; non aumentare budget né abbassare filtri automaticamente.
5. Preservare Falco, Toro, Brain, EventJournal, archivi, memoria, backup e tutte le sezioni storiche.

---

