# Checkpoint verificabile SuperBot-Trading — 20/11/2026 11:46 Europe/Rome

## Esito e limiti

Checkpoint esclusivamente documentale. Consultati GitHub (`diario`, `STATO.md`, ultimi commit/PR/issue, ramo laboratorio), Library `ULTIMO-STATO-SUPERBOT.md` v133 e conversazioni recenti effettivamente accessibili. Nessun controllo live autonomo della VPS, nessuna ricostruzione di chat eliminate, nessuna modifica operativa.

## Novità verificata: richiesta di politica token, non ancora applicata

- L'utente ha proposto una politica permanente di ottimizzazione token per Claude Code nel repository, chiedendo una valutazione prima dell'invio/applicazione.
- Destinazione proposta: integrare le regole nel `CLAUDE.md` esistente senza sovrascrivere configurazioni e senza duplicare regole.
- Vincoli espliciti: nessuna modifica al codice applicativo; nessun nuovo agente o plugin; ridurre chiamate inutili, operazioni ridondanti e spreco di token senza compromettere qualità, sicurezza, affidabilità, correttezza o test.
- Stato corretto: **richiesta/proposta da valutare; non risulta applicata, committata o testata**. Il ramo laboratorio resta invariato @ `3a231dd1824846ad0737b3d90ff5fbc361ed8fb8`.
- Una futura modifica, se approvata, dovrà essere solo istruzionale/documentale, con diff minimo e controllo anti-duplicazione; non autorizza codice operativo, merge, deploy o nuovi strumenti.

## Stato consolidato per la ripresa

### Obiettivo e portafogli

- Trading esclusivamente **PAPER** con tre portafogli distinti: **Falco**, **Toro**, **Brain**.
- Falco/Toro restano strategie deterministiche separate; Brain è adattivo/ML con tracciabilità, guardrail, validazione walk-forward e rollback.
- Desiderato: capitale/rischio isolati, sizing e limiti espliciti, stop/circuit breaker, dati coerenti, apprendimento soltanto da eventi verificabili.
- Implementato provato: infrastruttura PAPER e tre portafogli documentati. Configurazioni runtime e stato servizi non verificati live; non descriverli come attivi senza prova.
- Storici ed EventJournal devono essere preservati; chiusure manuali restano eventi operatore non imitabili.

### Ramo laboratorio, skill e test

- `integration/brain-unico-20261119` @ `3a231dd1824846ad0737b3d90ff5fbc361ed8fb8`.
- Cinque skill consultive attivate e integrate: exit-strategies, risk-management, position-sizing, trade-journal, walk-forward-validation.
- Il commit contiene skill/documentazione soltanto; nessuna modifica a strategie, soglie, rischio, servizi o `main`.
- Test riferiti dalla sessione/diario: V3 5.311, builder 157, Jest 137, zero fallimenti.
- Limiti: formula Deflated Sharpe Ratio errata nella skill walk-forward; trade-journal poco compatibile con EventJournal; nessuna promozione automatica nelle decisioni operative.

### Candele, feed e validatore

- Manifest `candles-20261120T064955Z-95a00e9b`; SHA-256 `4c982882e53324ce944279b3e016cc8b71f4b96e64e76e7a03afa0021aecf407`.
- 24 file, 47.352/47.376 righe, 8,47 MB; integrità `intact`, provenienza `manifest_unanchored`. Anchor non registrato: training non autorizzato.
- Difetto ultima candela chiusa corretto offline @ `315edf155655b963952ff1ebf4fbcfbd5e90e2ec`; manca prova reale autorizzata, massimo 3 tentativi.
- Validatore reale @ `733182f6e3e8760aaf900c24215f51e8ed380154`: 24/24 campioni verificati, 24/24 manomissioni rilevate.

### Brain Unico, RC e stato revisioni

- Brain Unico @ `095a0432d8ccbea82fd72abdd4872323246f8107`; Arena non integrata; chiusure manuali escluse da scoreboard/imitazione.
- Piano RC PAPER @ `8fa61d18e615533cb428911b751811f2fd846595`: preparato, non approvato né distribuito.
- PR #80 RC84 open/draft @ `0e29a73a36f668643da4088178bacb8616a45ac0`; non unita.
- PR Brain Unico recenti #114–#123 risultano ancora open/draft secondo la verifica GitHub; nessun merge recente. Fra quelle già consolidate: #120 `f4f74578`, #121 `5b7403aa`, #122 `513448e5`, #123 `c51c7520`.
- Issue #124 P0 latch perdita giornaliera aperta: NO-GO a nuovi deploy Brain Unico finché non chiusa e verificata.

### Backup, chiavi e servizi

- Backup esterno `work/extbackup-bot-stopped-20261109` @ `3dc2116a08058f57fc14b695431f6e3fa1a1ca45`: preparato, non installato, non certificato.
- Copia cifrata age sul PC: PowerShell `ESITO: VERIFICA OK`, confronto chiave pubblica coincidente. Prova locale; non certifica backup o restore VPS.
- Nessun segreto letto o pubblicato. Stato live servizi, backup e chiavi VPS non verificato.

## Eseguito / preparato / non approvato

- **Eseguito e verificato documentalmente:** acquisizione 24 file; rilevazione difetto feed e fix offline; Brain Unico; validatore reale; attivazione/integrazione consultiva delle cinque skill; test indicati.
- **Preparato:** piano RC PAPER, backup esterno, anchor corretto noto.
- **Proposto ma non applicato:** politica permanente di ottimizzazione token in `CLAUDE.md`.
- **Non approvato/non eseguito:** registrazione anchor, training Brain, probe reale feed, chiusura Issue #124, merge/deploy, installazione backup, restore VPS, Arena, trading reale.

## Blocker e prossime attività

1. Valutare la proposta token e, solo dopo approvazione, deduplicarla rispetto al `CLAUDE.md` esistente con modifica esclusivamente istruzionale.
2. Registrare/verificare persistentemente l'anchor.
3. Con consenso esplicito, probe reale del feed con massimo 3 tentativi.
4. Correggere/verificare Issue #124 prima di RC/deploy Brain Unico.
5. Integrare storico Arena preservando EventJournal.
6. Certificare backup/restore, GO/NO-GO PAPER, 14 giorni e rollback.

## Istruzioni di ripresa

1. Leggere `STATO.md`, questo checkpoint e il file Library stabile.
2. Trattare `3a231dd1824846ad0737b3d90ff5fbc361ed8fb8` come HEAD laboratorio documentato, non come deploy VPS.
3. Non assumere che la politica token sia già attiva: è soltanto proposta.
4. Archivio integro ma non attestato; fix feed soltanto offline; Issue #124 resta NO-GO.
5. Separare sempre documentato, testato, approvato e distribuito. Tutto resta PAPER.
