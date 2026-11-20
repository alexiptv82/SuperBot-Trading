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

Dieci skill metodologiche per il trading (fonte e modifiche in `.claude/skills/PROVENIENZA.md`): `risk-management`, `position-sizing`, `exit-strategies`, `trade-journal`, `regime-detection`, `slippage-modeling`, `portfolio-analytics`, `walk-forward-validation`, `signal-classification`, `strategy-framework`.

Regole permanenti (non sostituiscono le regole inviolabili sopra, che prevalgono sempre):

1. Prima di ogni attività di sviluppo, analisi, debugging o miglioramento di SuperBot, valuta quali skill siano pertinenti.
2. Richiama le skill appropriate con lo strumento Skill senza attendere una richiesta esplicita.
3. Capitale, drawdown, esposizione: `risk-management` e `position-sizing`.
4. Take profit, trailing stop, chiusure tardive, restituzione dei profitti: `exit-strategies` e `trade-journal`.
5. Cambi di trend, bias LONG/SHORT, cambi di volatilità: `regime-detection`.
6. Strategie, validazione storica, overfitting: `walk-forward-validation` e `strategy-framework`.
7. Commissioni, slippage, redditività netta: `slippage-modeling` e `portfolio-analytics`.
8. Brain AI e valutazione dei segnali: `signal-classification`, quando pertinente.
9. Carica solo le skill necessarie al compito: nessun caricamento preventivo di tutte.
10. Le skill sono metodologia, **non prova** che un risultato sia corretto. Verifica sempre l'applicabilità ai futures USDT-M di Bitget: `slippage-modeling` è scritta per pool AMM/DEX e `regime-detection` ha una modalità live per Solana (da non usare).

Limiti: le skill servono ad analizzare e proporre. **Non rendono automatici** deploy, invio di ordini, riavvio di servizi né modifiche a parametri, soglie o strategie in esecuzione: restano soggetti alle regole 1–3 sopra e al consenso esplicito del proprietario. Non eseguire gli script delle skill con rete o installare librerie senza necessità.
