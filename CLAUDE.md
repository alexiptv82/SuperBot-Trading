# Istruzioni per le AI che lavorano su questo repository (ChatGPT, Claude)

**Prima di fare qualunque cosa, leggi il ramo `diario`:**
`LEGGIMI.md`, `STATO.md`, `MANUALE-OPERATIVO.md` e le ultime tre voci della cartella `diario/`.
(`git fetch origin diario && git show origin/diario:STATO.md`, oppure apri il ramo `diario` su GitHub.)
Dopo il lavoro, **aggiorna il diario** (`STATO.md` e la voce del giorno): è la memoria condivisa che permette all'altra AI di proseguire se tu non ci sei.

Regole inviolabili (decisioni dell'utente, sempre valide):

1. Nessun redeploy dei bot (Hawk, Bull) senza OK esplicito dell'utente.
2. Niente live trading: il Secret `DESK_MODE` resta `paper` finché l'utente non dice esplicitamente di passare a live.
3. Nessuna modifica a strategia, soglie, limiti di rischio, prompt di Claude senza decisione dell'utente.
4. Il "cervello" (`trade_history.jsonl`, `lessons.md`, `errors.md`, `learning_log.jsonl` in `/opt/superbot-desk-data/{hawk,bull}/`) non si cancella, non si azzera, non si modifica: solo cresce.
5. Le API key di trading mai nel codice, solo nei GitHub Secrets.
6. Mai toccare HI-TV / `hitvprime` (nginx, DNS, container su Strasburgo).
7. Il repository è **pubblico**: nessun segreto, nessun importo o saldo reale di Bitget in codice, log, commit o diario.
8. Mai `git push --force`; non unire `work/backend-singapore-audit`; nessun push su `stable/*` e `v0.5`.
9. Un solo autore alla volta per componente.

Le commit che non devono far partire nulla (documenti, diario) portano `[skip ci]` nel messaggio.

## Skill specialistiche (`.claude/skills/`)

Prima selezione (supporto metodologico, fonte in `.claude/skills/PROVENIENZA.md`): `exit-strategies`, `risk-management`, `position-sizing`, `trade-journal`, `walk-forward-validation`.

1. Prima di sviluppo, analisi, debugging o miglioramento di SuperBot valuta quali skill sono **davvero pertinenti** e richiama solo quelle, senza attendere una richiesta esplicita. Nessuna skill e' obbligatoria per ogni attivita'.
2. Uscite, take profit, trailing, chiusure tardive, restituzione dei profitti: `exit-strategies` (e `trade-journal` per l'analisi dei trade chiusi).
3. Capitale, margine, leva, drawdown, esposizione: `risk-management` e `position-sizing`.
4. Validazione storica, split, leakage temporale, overfitting: `walk-forward-validation`.
5. Leggi sempre la sezione "SuperBot: leggere prima" della skill: futures USDT-M Bitget (non DEX/Solana), capitale/margine/leva distinti, costi e funding reali.
6. Le regole approvate del progetto **prevalgono** sulle skill: regole inviolabili qui sopra, protezioni P0, RiskManager, NO_TRADE sempre consentito, EventJournal e storico mai riscritti, nessun apprendimento su dati non attestati.
7. Le skill sono metodologia, **non prova** di correttezza: possono contenere errori (vedi l'avviso in `walk-forward-validation`).
8. Le skill non rendono automatici deploy, ordini, riavvii, merge o modifiche a parametri, soglie e strategie: servono ad analizzare e proporre. Non eseguire i loro script con rete e non installare dipendenze senza necessita'.

## TOKEN EFFICIENCY POLICY

Ridurre token, chiamate e letture inutili **senza** toccare qualità, sicurezza, affidabilità e verificabilità. Priorità assoluta: completare Brain Unico. Se efficienza e correttezza entrano in conflitto, prevalgono sicurezza e correttezza. Questa sezione non modifica le regole inviolabili, le autorizzazioni, i vincoli di sicurezza né il gate di pubblicazione, e non sostituisce la lettura iniziale del diario richiesta all'inizio del file.

1. **Analisi mirata:** individua prima i file pertinenti; ricerche specifiche e letture parziali (intervalli di righe) quando bastano; nessuna scansione completa non necessaria.
2. **Contesto:** non rileggere ciò che è già disponibile e invariato (es. il diario letto a inizio sessione); riusa i risultati verificati, ma rileggi se il file può essere cambiato (altro autore, push, rebase).
3. **Test proporzionati:** in sviluppo test mirati ai file toccati. **Prima di ogni pubblicazione restano obbligatori tutti i controlli del gate** (suite V3, Dataset Builder, frontend quando richiesti): mai saltarli né alterare il gate per risparmiare.
4. **Output essenziale:** mostra risultati, errori, rischi e decisioni; niente log prolissi né aggiornamenti ripetitivi; conserva (anche su file) i dettagli diagnostici necessari a ricostruire un fallimento.
5. **Skill e strumenti:** carica solo le skill pertinenti; subagenti, MCP e strumenti aggiuntivi solo se il beneficio supera il costo di gestione.
6. **Modifiche minime:** interventi localizzati; nessun refactoring, audit esteso o funzionalità estranea al compito.
7. **Diario:** si mantiene secondo le regole approvate; registra in forma sintetica decisioni, commit, test, incidenti e problemi aperti, con riferimenti verificabili (commit, file) invece di duplicare rapporti già archiviati.
8. **Compattazione:** conserva obiettivo e stato, branch e commit, decisioni e autorizzazioni, modifiche da verificare, test e risultati, problemi irrisolti, prossimo passo; elimina narrazione e ripetizioni. Non forzare compattazioni frequenti se il costo supera il beneficio.
9. **Completamento:** a compito terminato e verificato non avviare lavori aggiuntivi senza un motivo concreto o un mandato già esistente.
