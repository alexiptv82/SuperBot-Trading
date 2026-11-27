# Checkpoint verificabile SuperBot-Trading — 27/11/2026 09:50 Europe/Rome

## Esito sintetico

Novità verificata rispetto al checkpoint precedente: alle **08:55:25 Europe/Rome del 27/11/2026** l'utente ha chiesto esplicitamente di mettere in pausa il **Brain originale / Evolution V3 (`scalp`)** per evitare ulteriore consumo di crediti e dedicarsi a **Evolution X**. La decisione autorizza la pausa, ma **non prova che sia stata eseguita**: nella conversazione accessibile il comando operativo è stato soltanto preparato/verificato e non è disponibile una conferma `pausa: ATTIVA` né un controllo live della VPS.

Effetto desiderato della pausa: impedire nuove analisi AI e nuove aperture del Brain originale, mantenendo attive le protezioni e le uscite delle eventuali posizioni già aperte; nessuna chiusura forzata. Questa decisione sostituisce soltanto la precedente classificazione “pausa non autorizzata”; lo stato implementato resta **non verificato / non eseguito per quanto provato**.

## Perimetro e fonti

- GitHub `alexiptv82/SuperBot-Trading`, ramo `diario`: `STATO.md`, checkpoint più recente, PR #80 e relativi SHA.
- Libreria ChatGPT `/SuperBot-Ripresa/ULTIMO-STATO-SUPERBOT.md`, ID stabile `libfile_754adf32b63881919d64ef3bc26b222a`, versione 158 prima di questa scrittura.
- Conversazione recente del progetto effettivamente accessibile: richiesta utente delle 08:55:25 Europe/Rome e risposta successiva. Non sono state presunte trascrizioni di chat perse.
- Nessuna verifica live della VPS in questa esecuzione. Il controllo F0 del checkpoint precedente è read-only e non abilita né certifica la pausa.

## Obiettivo e vincoli permanenti

- Sistema di trading automatico esclusivamente **PAPER**, con tre portafogli separati: **Falco**, **Toro**, **Brain**.
- Preservare storici, database ed `EventJournal`; nessun reset distruttivo.
- `NO_TRADE` è un esito valido; sicurezza e uscite hanno precedenza sulle aperture.
- Vietati ordini reali, merge/deploy non approvati, modifiche operative automatiche e consumo di API a pagamento senza autorizzazione.

## Portafogli e stato desiderato rispetto a quello provato

### Falco

- Portafoglio PAPER esistente; nessuna nuova decisione o modifica verificata in questa esecuzione.
- Configurazione e stato operativo live non ricontrollati oggi: restano quelli documentati nei checkpoint storici, senza nuove assunzioni.

### Toro

- Portafoglio PAPER esistente; nessuna nuova decisione o modifica verificata in questa esecuzione.
- Configurazione e stato operativo live non ricontrollati oggi: restano quelli documentati nei checkpoint storici, senza nuove assunzioni.

### Brain originale / Evolution V3 (`scalp`)

- Ultima baseline implementata dimostrata: **Brain Evolution V2**. La V3 con SHA `f9ae6e8bf8` risulta generata/preparata ma non approvata per installazione.
- Parametri V2 documentati: ciclo 30 minuti; leva 15–50x; margine massimo 400 USD per trade; margine totale massimo 55%; rischio 4,3% per trade; rischio aperto massimo 12%; stop giornaliero 25%; confidenza minima 0,56; Claude con veto; niente half-risk; LONG vincolati al trend 1h+4h; costi stimati non oltre il 30% di 1R.
- **Desiderato dal 27/11/2026 08:55:** pausa di nuove analisi/aperture, con protezioni/uscite preservate e nessuna chiusura forzata.
- **Implementato/provato:** nessuna prova di attivazione della nuova pausa. L'ultimo messaggio accessibile prepara l'azione ma dichiara assenza di accesso diretto alla VPS.
- La pausa storica del 24/11/2026 alle 17:21:47 UTC fu eseguita; in seguito V2 fu avviata. La decisione odierna è distinta e necessita nuova esecuzione e prova.

### Brain Evolution X

- È il filone al quale l'utente vuole dedicarsi completamente; la richiesta odierna non autorizza merge, deploy o attivazioni operative di Evolution X.
- Nessuna nuova modifica tecnica verificata in questa esecuzione.

## Servizi, backup e chiavi — solo fatti provati

- Ultima verifica operativa dettagliata disponibile (26/11/2026 11:28 Europe/Rome): runner Brain V2 riportato `running`, uscite sane, 146 esiti `NO_TRADE`, 16 `ai_unavailable`, zero aperture e budget applicativo 3,8811/4 USD. È una fotografia storica, non stato live odierno.
- Controllo F0 del 27/11/2026 08:28 Europe/Rome: workflow Actions `45958637995`, job `status` `140370929233`, conclusione `success`; prova read-only della presenza del root di backup e degli artefatti Brain DB/WAL/SHM. Dieci processi compatibili e undici unità systemd sono soltanto **POSSIBLE_ACTIVE**, non una certificazione di salute o stato live. Archivio/file richiesti non erano accessibili nel perimetro F0.
- Copia cifrata della chiave `age` sul PC: verifica PowerShell con output esatto **`ESITO: VERIFICA OK`** e chiave pubblica derivata coincidente. Prova la copia locale verificata; **non certifica il backup sulla VPS** e non espone chiave privata, passphrase o altri segreti.
- Backup esterno: ramo `work/extbackup-bot-stopped-20261109` al commit `3dc211...`, preparato ma **non installato**.

## Git, PR e test verificati

- Ramo diario prima di questo checkpoint: commit `83ef1275d53a9534246f4601234f2dcba7d2e989`; checkpoint precedente `diario/2026-11-27_0846_checkpoint-verificabile-f0-readonly.md` con blob `ebdaf7322eb45a4648d69b5fdbe4e1420b7131f9`.
- RC84: PR **#80** ancora aperta, draft e non mergiata; head `0e29a73a36f668643da4088178bacb8616a45ac0`, ultimo aggiornamento verificato 09/11/2026.
- Test già documentati, senza nuova esecuzione in questo checkpoint: Brain V2/V3 5.588; Builder 158; Jest 212; restart 13/13; simulator 2/2. Suite integrazione: 5.500 con 1 skipped; Builder 158; Jest 210; Android 126/126. La fonte resta nei checkpoint/PR storici; questa esecuzione non li attribuisce a una prova live odierna.

## Eseguito, preparato, non approvato

- **Eseguito ora:** sola documentazione del cambio di decisione e consolidamento dello stato.
- **Preparato ma non eseguito:** procedura di pausa del Brain originale/scalp; richiede operatore autorizzato e riscontro read-only successivo.
- **Non approvato:** chiusura forzata di posizioni, stop delle protezioni/uscite, merge/deploy di V3 o Evolution X, installazione del backup esterno, modifiche di codice operativo, Actions operative, reboot/reset, ordini o API a pagamento.

## Blocker e prossime attività

1. Un operatore autorizzato deve eseguire la pausa del Brain originale/scalp preservando le uscite.
2. Ottenere una prova read-only successiva che mostri esplicitamente la pausa attiva e l'assenza di nuove analisi/aperture; non dedurla da processi o unità “possible active”.
3. Verificare separatamente che le protezioni/uscite restino operative e che storici ed `EventJournal` siano preservati.
4. Non modificare Falco, Toro, Evolution X, backup o servizi senza nuova autorizzazione specifica.

## Istruzioni di ripresa per un'altra AI

1. Leggere `STATO.md`, questo checkpoint e la versione più recente del file Library indicato.
2. Trattare la pausa come **autorizzata ma non ancora provata attiva** finché non esiste un riscontro read-only successivo all'esecuzione.
3. Non confondere Brain originale/scalp con Evolution X e non trasformare l'autorizzazione alla pausa in autorizzazione a deploy, merge o chiusure forzate.
4. Conservare il perimetro PAPER e non esporre segreti o dettagli che facilitino accessi alla VPS.
5. Al prossimo checkpoint, riconciliare entrambe le copie e recuperare qualunque scrittura eventualmente fallita.

