# Checkpoint verificabile SuperBot-Trading — 27/11/2026 12:47 Europe/Rome

## Novità verificata e perimetro della prova

Una conversazione recente effettivamente accessibile riporta, alle **12:00:01 Europe/Rome**, output operatore/Termius successivo al checkpoint delle 11:51:

- backup cifrato finale completato per **4/4 run PAPER**;
- **5.843 eventi**, **33 file**, **0 errori** complessivi;
- dettaglio riportato: Scalp P1 4.743 eventi/9 file; V3 Paper 1.058/9; RC storico 1/6; Unico RC1 41/9;
- controlli riportati come superati: integrità SQLite, catena eventi, hash dello script e prova di decifratura/ripristino con chiave temporanea;
- prodotti quattro archivi cifrati e quattro manifest in una directory locale dedicata sulla VPS.

Questa è evidenza recuperata dalla conversazione, non un controllo live ripetuto da questo checkpoint. **Non certifica** copia esterna/SFTP, restore da una destinazione esterna, inclusione delle memorie extra, né recupero mediante la copia cifrata della chiave custodita sul PC.

## Stato consolidato

### Obiettivi e vincoli

- Tre portafogli separati **Falco**, **Toro** e **Brain**, esclusivamente PAPER.
- Preservare storici, database, memoria dei trade ed `EventJournal`; `NO_TRADE` resta valido.
- Nessuna chiusura forzata, perdita di protezioni/uscite, ordine reale, reset, merge, deploy, modifica VPS o consumo API a pagamento senza mandato separato.
- Evolution X Fusion resta distinto dal Brain originale; il checkpoint non ne autorizza installazione o LIVE.

### Falco e Toro

- Nessuna nuova decisione, configurazione o verifica operativa live emersa in questa esecuzione.
- Lo stato resta quello documentato nello storico; non dedurre attività corrente dai soli checkpoint.

### Brain originale / scalp

- Ultima baseline implementata dimostrata: **Brain Evolution V2**.
- Proposta V3 `f9ae6e8bf8`: generata/preparata, non approvata per installazione.
- V2 documentata: ciclo 30 minuti; leva 15–50x; margine massimo 400 USD/trade e 55% totale; rischio 4,3%/trade e 12% aperto; stop giornaliero 25%; confidenza 0,56; veto Claude; niente half-risk; LONG solo con trend 1h+4h; costi stimati entro 30% di 1R.
- **Desiderato:** niente nuove analisi/aperture o costi AI; uscite e protezioni preservate; nessuna chiusura forzata.
- **Osservato prima del backup:** pausa attiva, runner `halted`, quattro journal PAPER con zero posizioni aperte, uscite sane.
- Dipendenze successivamente riportate: l'exit di Brain Unico ha dipendenza dal runner; exit V3 e Close Bridge risultano attivi. È diagnostica da conversazione, non stato live ricontrollato qui.
- Nessun servizio risulta fermato, disabilitato o cancellato; nessun dato risulta eliminato. Il pensionamento reversibile resta soltanto proposto/preparato.

## Backup, chiavi e servizi

- **Backup finale delle quattro run:** eseguito e verificato localmente sulla VPS secondo l'output operatore sopra riportato; 4 archivi cifrati + 4 manifest.
- **Limiti:** copia esterna/SFTP non confermata; destinazione indipendente e restore da essa non verificati; memorie extra/non incluse ancora da inventariare; dipendenze dei servizi ancora da risolvere prima di qualsiasi arresto.
- Backup periodico: ultimo successo riportato alle 04:27 e timer attivo; non sostituisce il test di copia esterna/restore.
- Backup esterno storico `work/extbackup-bot-stopped-20261109` @ `3dc2116a08058f57fc14b695431f6e3fa1a1ca45`: preparato ma **non installato**.
- Copia cifrata chiave `age` sul PC: PowerShell **`ESITO: VERIFICA OK`** e chiave pubblica coincidente; è prova locale e non certifica il backup VPS né la nuova copia esterna. Nessun segreto è riportato.
- I sette servizi precedentemente rilevati (~296,7 MiB, più ~36,7 MiB non identificati) non risultano arrestati o rimossi.

## Branch, PR, SHA e test con fonte

- Ramo `diario` prima di questo aggiornamento: indice commit `07ba87d8e1e09be6316540afc447d2b1876d38e8`; checkpoint 11:51 blob `2af548a7bfcacc86a60975bfe92b348f51250d9f`.
- RC84 PR **#80** verificata ancora open, draft e non mergiata; head `0e29a73a36f668643da4088178bacb8616a45ac0`.
- RC84 storica, fonte run `42681449471`: backend 7.003 passed/9 deselected/3 xfailed; frontend 124/124 e build compilata. Browser 71/71 resta prova riferita su ambiente sintetico, non VPS o Android fisico.
- Brain, non rieseguiti ora: V2/V3 5.588; Builder 158; Jest 212; restart 13/13; simulatore 2/2. Integrazione: 5.500 con 1 skipped; Builder 158; Jest 210; Android 126/126.
- Il controllo del backup è una verifica dati/restore riportata da Termius, non un nuovo test delle strategie di trading.

## Eseguito, preparato, non approvato

- **Eseguito/provato nella conversazione:** backup cifrato finale 4/4 run, manifest, controlli di integrità e prova locale di decifratura/ripristino; precedente pausa e zero posizioni.
- **Preparato/proposto:** pensionamento reversibile; eventuale prosecuzione della diagnostica; ramo esterno storico.
- **Non eseguito/provato:** copia esterna/SFTP, restore da destinazione indipendente, arresto/disabilitazione servizi, archivio definitivo, disinstallazione o cancellazione.
- **Non approvato:** perdita di memoria/storici, reset EventJournal, merge/deploy, ordini, LIVE o API a pagamento. Il “procedi” delle 12:08 autorizza la prosecuzione, ma non prova né autorizza implicitamente arresti o cancellazioni.

## Blocker, prossime attività e istruzioni di ripresa

1. Copiare i nuovi archivi e manifest in una destinazione esterna autorizzata e verificare lì integrità e restore; non confondere questa attività con il ramo storico non installato.
2. Inventariare memorie extra e dipendenze dei servizi, in particolare l'exit di Brain Unico, prima di qualunque fermo.
3. Richiedere decisione esplicita sui servizi da fermare/disabilitare; mantenere la procedura reversibile e non cancellare dati.
4. Dopo un eventuale arresto autorizzato, verificare risparmio RAM/CPU e assenza di interferenze con Evolution X Fusion.
5. Alla ripresa leggere `STATO.md`, questo checkpoint e la versione Library più recente; trattare backup locale 4/4 come eseguito, copia esterna e pensionamento come non eseguiti.
6. Mantenere PAPER e non esporre segreti o dettagli di accesso VPS.
