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
