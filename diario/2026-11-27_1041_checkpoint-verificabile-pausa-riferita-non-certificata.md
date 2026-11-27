# Checkpoint verificabile SuperBot-Trading — 27/11/2026 10:41 Europe/Rome

## Novità verificata e livello di prova

Alle **10:34:04 Europe/Rome del 27/11/2026**, in una conversazione recente effettivamente accessibile, l'utente ha riferito che il **Brain originale / Evolution V3 (`scalp`) è stato messo in pausa** a causa di problemi nelle chiamate DeepSeek e del costo AI elevato, per concentrarsi su **Evolution X Fusion**.

Questo aggiorna il checkpoint delle 09:50 da “pausa autorizzata ma non eseguita” a **“esecuzione riferita dall'utente”**. Non equivale però a una certificazione tecnica: non è disponibile un output VPS successivo con `pausa: ATTIVA`, non è provato l'arresto completo dei processi e non è stato eseguito qui alcun controllo live. L'assistente della conversazione ha mantenuto esplicitamente questa riserva: nuove aperture considerate sospese sul piano operativo, arresto dei processi non verificato.

## Fonti consultate

- GitHub `alexiptv82/SuperBot-Trading`, ramo `diario`: `STATO.md`, checkpoint 09:50, PR #80 e relativi SHA.
- Library `/SuperBot-Ripresa/ULTIMO-STATO-SUPERBOT.md`, ID `libfile_754adf32b63881919d64ef3bc26b222a`, versione 159 prima di questa scrittura.
- Conversazioni recenti recuperabili: messaggio utente delle 10:34:04 e risposta immediatamente successiva. Nessuna trascrizione persa è stata ricostruita o presunta.
- Nessuna interrogazione live della VPS in questa esecuzione.

## Obiettivo e vincoli permanenti

- Tre portafogli separati **Falco**, **Toro**, **Brain**, esclusivamente PAPER.
- Preservare storici, database ed `EventJournal`; `NO_TRADE` resta un esito valido.
- Nessun ordine reale, reset, merge, deploy, Action operativa, modifica VPS o API a pagamento senza autorizzazione separata.
- Evolution X Fusion è ora il focus dichiarato, ma resta un progetto distinto: nessun deploy o passaggio LIVE è autorizzato da questa decisione.

## Portafogli: desiderato rispetto a implementato/provato

### Falco

- PAPER; nessuna nuova decisione, modifica o verifica live in questa esecuzione.
- Lo stato resta quello documentato nello storico; non dedurre operatività corrente.

### Toro

- PAPER; nessuna nuova decisione, modifica o verifica live in questa esecuzione.
- Lo stato resta quello documentato nello storico; non dedurre operatività corrente.

### Brain originale / scalp

- Ultima baseline implementata dimostrata: **Brain Evolution V2**. La proposta V3 `f9ae6e8bf8` resta preparata/generata e non approvata per installazione.
- Parametri V2 documentati: ciclo 30 minuti; leva 15–50x; margine massimo 400 USD per trade; margine totale massimo 55%; rischio 4,3% per trade; rischio aperto massimo 12%; stop giornaliero 25%; confidenza minima 0,56; Claude con veto; niente half-risk; LONG solo con trend 1h+4h; costi stimati non oltre il 30% di 1R.
- **Desiderato:** nessuna nuova analisi/apertura e nessun nuovo consumo AI, mantenendo protezioni e uscite; nessuna chiusura forzata.
- **Riferito come eseguito:** l'utente dichiara che il bot è stato messo in pausa.
- **Non ancora provato tecnicamente:** stato VPS, output `pausa: ATTIVA`, arresto completo dei processi e comportamento successivo delle aperture.
- La pausa storica del 24/11/2026 alle 17:21:47 UTC fu verificata; non usarla come prova automatica della nuova pausa del 27/11.

## Servizi, backup e chiavi

- Ultima prova operativa dettagliata disponibile resta quella del 26/11/2026 11:28 Europe/Rome: runner V2 riportato `running`, uscite sane, 146 `NO_TRADE`, 16 `ai_unavailable`, zero aperture, budget applicativo 3,8811/4 USD. È storica, non live.
- F0 del 27/11/2026 08:28 Europe/Rome: Action `45958637995`, job `140370929233`, `success`, perimetro `read_only`/`OBSERVATION_ONLY`; backup root e artefatti Brain DB/WAL/SHM presenti. Dieci processi e undici unità erano soltanto `POSSIBLE_ACTIVE`. Non certifica salute, pausa, posizioni o ripristinabilità del backup.
- Copia cifrata della chiave `age` sul PC: output PowerShell esatto **`ESITO: VERIFICA OK`** e chiave pubblica derivata coincidente. È prova locale e **non certifica il backup sulla VPS**; nessun segreto è riportato.
- Backup esterno: `work/extbackup-bot-stopped-20261109` @ `3dc211...`, preparato ma **non installato**.

## Branch, PR, SHA e test

- Prima di questo checkpoint, ramo `diario` indicizzato dal commit `9aa87a899c6bcce9754b35f13e0317301e376cae`; checkpoint 09:50 blob `467a2890b010a5c00179d112349323712bfabc35`.
- RC84 PR **#80**: ancora open, draft, non mergiata; head `0e29a73a36f668643da4088178bacb8616a45ac0`.
- Test RC84 verificati nei log storici della run `42681449471`: backend 7.003 passed, 9 deselected, 3 xfailed; frontend 124/124 e build compilata. Browser Claude 71/71 resta evidenza riferita su ambiente sintetico, non VPS/Android fisico.
- Test Brain già documentati, non rieseguiti ora: V2/V3 5.588; Builder 158; Jest 212; restart 13/13; simulatore 2/2. Suite integrazione: 5.500 con 1 skipped; Builder 158; Jest 210; Android 126/126.

## Eseguito, preparato, non approvato

- **Eseguito in questo checkpoint:** sola documentazione del nuovo livello di evidenza sulla pausa.
- **Riferito dall'utente:** pausa del Brain originale/scalp per fermare nuove aperture e costi AI.
- **Da verificare:** output di stato successivo, assenza di nuove analisi/aperture, protezioni/uscite ancora operative, processi realmente fermati o mantenuti solo per le uscite.
- **Non approvato:** chiusure forzate, arresto delle uscite, V3/Evolution X deploy, installazione backup esterno, merge, reset, ordini o consumo API.

## Blocker, prossime attività e ripresa

1. Ottenere, solo tramite operatore autorizzato, un riscontro read-only post-pausa che distingua pausa nuove aperture, stato processi e salute delle uscite.
2. Non trasformare il racconto dell'utente in certificazione VPS; finché manca il riscontro usare la formula **“pausa riferita come eseguita, non tecnicamente certificata”**.
3. Verificare che storici ed `EventJournal` restino intatti e che nessuna nuova spesa AI sia stata generata dopo la pausa.
4. Leggere `STATO.md`, questo checkpoint e la versione Library più recente prima di riprendere; non confondere Brain originale con Evolution X Fusion.
5. Mantenere PAPER e non pubblicare segreti, dati personali o dettagli che facilitino accessi alla VPS.

