# Checkpoint verificabile SuperBot-Trading — 20/11/2026 09:53 Europe/Rome

## Esito e fonti

Checkpoint esclusivamente documentale. Consultati: ramo GitHub `diario`, `STATO.md`, ultimi commit/PR/issue e ramo `integration/brain-unico-20261119`; Library `ULTIMO-STATO-SUPERBOT.md` v132; contesto recente effettivamente accessibile. Nessun controllo live autonomo della VPS e nessuna ricostruzione di chat eliminate.

## Stato consolidato per la ripresa

### Obiettivo e portafogli

- Sistema esclusivamente **PAPER** con tre portafogli distinti: **Falco**, **Toro**, **Brain**.
- Falco e Toro restano strategie deterministiche separate; Brain è il percorso adattivo/ML, con tracciabilità, guardrail, validazione walk-forward e rollback.
- Desiderato: capitale/rischio isolati, sizing e limiti espliciti, stop/circuit breaker, confronto su dati coerenti, apprendimento solo da eventi verificabili.
- Implementato provato: infrastruttura PAPER e tre portafogli documentati. Configurazioni runtime, valori di rischio desiderati e stato servizi non controllati live in questa esecuzione; non vanno descritti come attivi senza prova.
- Storici ed EventJournal devono essere preservati. Chiusure manuali sono eventi operatore e non segnali da imitare.

### Novità verificata: skill attivate e integrate in laboratorio

- Ramo laboratorio verificato: `integration/brain-unico-20261119` @ `3a231dd1824846ad0737b3d90ff5fbc361ed8fb8`.
- Il commit contiene solo 32 file di skill/documentazione: exit-strategies, risk-management, position-sizing, trade-journal, walk-forward-validation, provenienza/licenza, appendice `CLAUDE.md` e confronto offline.
- Fonte GitHub/diario: le cinque skill sono state copiate nella directory personale della sessione Claude Code sulla VPS e richiamate realmente tramite lo strumento Skill; tutte e cinque risultano caricate. Questa è un'evidenza documentata dalla sessione/commit, **non un controllo live indipendente eseguito da questo checkpoint**.
- Le skill sono ora integrate nel ramo laboratorio come materiale **consultivo**. Nessuna modifica a strategie, soglie, rischio, codice operativo o servizi; nessun merge in `main` e nessun deploy.
- Test riferiti dalla stessa fonte: V3 **5.311**, builder **157**, Jest **137**, zero fallimenti.
- Limiti già registrati: formula Deflated Sharpe Ratio errata nella skill walk-forward; formato trade-journal poco adatto perché confligge con EventJournal; nessuna skill ha corretto l'analisi di base. Parti AMM/Solana escluse.
- Il precedente stato “skill isolate/non riconosciute” è quindi superato per il ramo laboratorio; non implica adozione automatica nelle decisioni operative.

### Acquisizione candele e feed

- Manifest `candles-20261120T064955Z-95a00e9b`; SHA-256 `4c982882e53324ce944279b3e016cc8b71f4b96e64e76e7a03afa0021aecf407`.
- 24 file (8 simboli × 15m/1h/4h), 47.352/47.376 righe, 8,47 MB; 266/350 tentativi complessivi inclusi due probe.
- Integrità `intact`, provenienza `manifest_unanchored`: l'anchor corretto è noto ma non risulta registrato dal proprietario. Nessun training autorizzato.
- Difetto verificato: Bitget `history-candles` ometteva l'ultima candela chiusa, causando fino a una candela di ritardo; stesso schema nel monitor stop 1m.
- Fix offline @ `315edf155655b963952ff1ebf4fbcfbd5e90e2ec`. Non ancora confermato contro API reale: serve consenso esplicito per un probe con massimo 3 tentativi.

### Brain Unico, validatore e RC

- Brain Unico @ `095a0432d8ccbea82fd72abdd4872323246f8107`: vista unificata di risultati, posizioni, memoria/tesi/apprendimento e storico Falco/Toro/Brain; Arena non integrata.
- Chiusure manuali conservate con semantica operatore, expectancy separata, escluse da scoreboard strategico e imitazione.
- Validatore reale @ `733182f6e3e8760aaf900c24215f51e8ed380154`: corretto il rifiuto delle feature con finestre a quattro cifre; 24/24 campioni reali verificati e 24/24 manomissioni rilevate.
- Piano RC PAPER @ `8fa61d18e615533cb428911b751811f2fd846595`: preparato, non approvato né distribuito; richiede GO/NO-GO, backup/restore attestato, mandato, validazione 14 giorni e rollback.

### PR, issue, backup e chiavi

- PR #80 RC84: open/draft @ `0e29a73a36f668643da4088178bacb8616a45ac0`, non unita.
- PR #120 `f4f745788e4514d01dc11e11402eb689a2ec7c74`, #121 `5b7403aa333b43d801ca7e28825ea4707f6847b4`, #122 `513448e57747f381e11ce23ab09788d6a41e6cb0`, #123 `c51c7520b35640518baea217404da9657702d4f5`: open/draft, non unite.
- Issue #124 P0 latch perdita giornaliera: aperta; resta NO-GO a nuovi deploy Brain Unico finché non chiusa e verificata.
- Backup esterno `work/extbackup-bot-stopped-20261109` @ `3dc2116a08058f57fc14b695431f6e3fa1a1ca45`: preparato, **non installato e non certificato**.
- Copia cifrata age sul PC: PowerShell `ESITO: VERIFICA OK`, chiave pubblica coincidente. Prova locale soltanto; non certifica backup o restore VPS.
- Nessun segreto letto o pubblicato. Stato live servizi/backup/chiavi VPS non verificato.

### Eseguito / preparato / non approvato

- **Eseguito e verificato documentalmente:** acquisizione 24 file; difetto feed; fix offline; Brain Unico; validatore dati reali; integrazione consultiva e richiamo delle cinque skill nel ramo laboratorio; test indicati.
- **Preparato:** RC PAPER, backup esterno, anchor corretto noto.
- **Non approvato/non eseguito:** registrazione anchor, training Brain, probe reale del fix feed, chiusura Issue #124, merge/deploy, installazione backup, restore test VPS, integrazione Arena, trading reale.

### Blocker e prossime attività

1. Registrare e verificare persistentemente l'anchor dell'archivio.
2. Con consenso esplicito, eseguire soltanto il probe reale del feed, massimo 3 tentativi.
3. Correggere e verificare il P0 dell'Issue #124 prima di qualsiasi RC/deploy Brain Unico.
4. Integrare la vista storica Arena senza perdere EventJournal.
5. Certificare backup/restore e completare GO/NO-GO PAPER, 14 giorni e rollback.
6. Usare le skill solo come consulenza, rispettandone i limiti documentati; nessuna promozione automatica.

## Istruzioni di ripresa

1. Leggere `STATO.md`, questo checkpoint e il file Library stabile.
2. Usare `3a231dd1824846ad0737b3d90ff5fbc361ed8fb8` come ultimo HEAD documentato del ramo laboratorio, non come deploy VPS.
3. Distinguere sempre documentato, testato, approvato e distribuito.
4. Archivio integro ma non attestato finché l'anchor non è persistito; fix feed soltanto offline finché non passa il probe.
5. Issue #124 resta un NO-GO operativo.
6. Tutto resta PAPER; nessun segreto o inferenza sullo stato live VPS.
