# Checkpoint verificabile SuperBot-Trading — 27/11/2026 11:51 Europe/Rome

## Novità verificata e perimetro della prova

Le conversazioni recenti effettivamente accessibili contengono ora output Termius/VPS successivi alla decisione di pausa:

- alle **11:03:19 Europe/Rome** è stato riportato `pausa attiva`, runner `halted`, con processi/heartbeat e servizi di uscita ancora operativi;
- alle **11:30:01** sono stati verificati quattro journal PAPER con **zero posizioni aperte**, runner `halted`, pausa attiva e uscite sane;
- nessuna cancellazione, disinstallazione o arresto definitivo del vecchio Brain risulta eseguito.

Questa evidenza supera il precedente livello “pausa riferita dall'utente”: la pausa e l'assenza di posizioni aperte risultano osservate tramite diagnostica operatore. Non è però una misura live eseguita da questo checkpoint e non dimostra che ogni processo sia fermo o che nessuna risorsa venga ancora consumata.

## Decisione sul vecchio Brain e stato delle attività

- L'utente vuole dedicarsi al 100% a **Evolution X Fusion** e valuta di mettere da parte operativamente il vecchio Brain, preservando memoria dei trade, journal e backup.
- Alle **11:25:39** sono stati riportati sette servizi per circa **296,7 MiB** complessivi, più circa 36,7 MiB non identificati. È una fotografia diagnostica della conversazione, non una misura ripetuta qui.
- È stato proposto un pensionamento/archivio reversibile, senza cancellare memoria o dati e senza confonderlo con Evolution X Fusion.
- Le risposte utente “procedi” hanno consentito la prosecuzione della diagnostica/preparazione; non costituiscono prova che servizi siano stati fermati o dati eliminati.
- Il backup finale cifrato delle quattro run risulta **proposto e comandato/preparato, ma non eseguito né verificato** alle 11:33:40.

## Fonti consultate

- GitHub `alexiptv82/SuperBot-Trading`, ramo `diario`: `STATO.md`, checkpoint 10:41, PR #80 e SHA associati.
- Library `/SuperBot-Ripresa/ULTIMO-STATO-SUPERBOT.md`, ID `libfile_754adf32b63881919d64ef3bc26b222a`, versione 160 prima di questa scrittura.
- Conversazioni recenti recuperabili con diagnostica Termius e decisioni utente sopra indicate. Nessuna chat persa è stata ricostruita.
- Nessun nuovo comando VPS, GitHub Action operativa o controllo live è stato eseguito da questo checkpoint.

## Obiettivo e vincoli permanenti

- Portafogli **Falco**, **Toro** e **Brain** esclusivamente PAPER; preservare storici, database ed `EventJournal`.
- `NO_TRADE` resta valido; nessuna chiusura forzata; protezioni e uscite hanno precedenza.
- Nessun ordine reale, reset, merge, deploy, modifica VPS o API a pagamento senza mandato separato.
- Evolution X Fusion resta distinto dal Brain originale; nessun passaggio LIVE o deploy è implicito.

## Portafogli e configurazioni

### Falco e Toro

- Nessuna nuova decisione o modifica verificata; stato operativo live non ricontrollato in questa esecuzione.
- Non dedurre operatività corrente dai soli checkpoint storici.

### Brain originale / scalp

- Ultima baseline implementata dimostrata: **Brain Evolution V2**; proposta V3 `f9ae6e8bf8` preparata/generata ma non approvata per installazione.
- V2 documentata: ciclo 30 minuti; leva 15–50x; margine massimo 400 USD/trade; margine totale 55%; rischio 4,3%/trade; rischio aperto 12%; stop giornaliero 25%; confidenza 0,56; veto Claude; niente half-risk; LONG solo trend 1h+4h; costi stimati ≤30% di 1R.
- Stato osservato nella diagnostica recente: pausa attiva, runner halted, quattro journal PAPER con zero posizioni aperte, uscite sane.
- Non osservato/eseguito: arresto definitivo dei sette servizi, disinstallazione, rimozione codice, cancellazione dati, reset dei journal o pensionamento completo.

## Backup, chiavi e servizi

- Backup periodico: ultimo esito riuscito riportato alle **04:27** e timer attivo; copertura di tutte le run e ripristinabilità restano non verificate.
- Backup finale cifrato delle quattro run: preparato/proposto, **non eseguito** per quanto provato.
- Backup esterno storico `work/extbackup-bot-stopped-20261109` @ `3dc211...`: preparato ma **non installato**.
- Copia cifrata chiave `age` sul PC: PowerShell **`ESITO: VERIFICA OK`** e chiave pubblica coincidente; prova locale, non certificazione del backup VPS. Nessun segreto è riportato.
- Diagnostica F0 precedente `45958637995`/job `140370929233` resta read-only e non è certificato di backup o restore.

## Branch, PR, SHA e test

- Prima di questo checkpoint, ramo `diario` indicizzato dal commit `df45a642a7fbcc17ef198bb1db9d836ccaaadda6`; checkpoint 10:41 blob `6a8a15f838a01bbe0cbe6372ff5b872d382937e5`.
- RC84 PR **#80** resta open, draft, non mergiata; head `0e29a73a36f668643da4088178bacb8616a45ac0`.
- RC84 storica: run `42681449471`, backend 7.003 passed/9 deselected/3 xfailed; frontend 124/124 e build compilata. Browser 71/71 è prova riferita su ambiente sintetico, non VPS o Android fisico.
- Brain, non rieseguiti ora: V2/V3 5.588; Builder 158; Jest 212; restart 13/13; simulatore 2/2. Integrazione: 5.500 con 1 skipped; Builder 158; Jest 210; Android 126/126.

## Eseguito, preparato, non approvato

- **Eseguito/provato nella conversazione:** diagnostica pausa, runner, uscite e quattro journal; zero posizioni aperte.
- **Preparato/proposto:** pensionamento reversibile e backup finale cifrato delle quattro run.
- **Non eseguito/provato:** backup finale, arresto/disabilitazione servizi, archivio definitivo, disinstallazione o cancellazione.
- **Non approvato:** perdita di memoria/storici, reset EventJournal, merge/deploy, ordini, LIVE, API a pagamento.

## Blocker, prossime attività e ripresa

1. Prima di mettere da parte il vecchio Brain, completare e verificare il backup cifrato finale delle quattro run e un controllo di copertura/restore in destinazione nuova.
2. Solo dopo il backup, definire esplicitamente quali servizi fermare/disabilitare mantenendo una procedura reversibile; nessuna cancellazione automatica.
3. Verificare dopo l'eventuale arresto l'effettivo risparmio RAM/CPU e l'assenza di interferenze, senza toccare Evolution X Fusion.
4. Alla ripresa leggere `STATO.md`, questo checkpoint e la versione Library più recente; trattare la pausa come verificata, il pensionamento come non eseguito.
5. Mantenere PAPER e non esporre segreti o dettagli di accesso VPS.

