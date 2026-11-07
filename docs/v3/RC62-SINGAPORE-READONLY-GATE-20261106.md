# SuperBot V3 — evidenze runtime RC #62 (6 novembre 2026)

**Verdetto: NO-GO all'avvio PAPER sulla VPS.** Il codice della RC è stato testato con esito positivo, ma non è ancora collegato a nuove run indipendenti, e il backup esterno cifrato è guasto. Tutto il lavoro descritto qui è **read-only o documentazione**, senza modifica dei worker, dati o servizi della VPS.

## Evidenze riproducibili

- **GitHub PR:** #62 (`work/v3-release-candidate-gpt6-20261106`, draft).
- **CI codice verificata:** run `42291292574`, commit `027307c4729f7981f4cbe40ee03d8ebd867ca510`: quattro job verdi: `backend`, `frontend`, `v3-suite` (**4073 PASS, 1 SKIP**) e `classics-rc` (PASS).
- **Audit nuovo runtime solo lettura:** run `42295014067`, commit `6939acf01caeb7ca6127a6b58ceab7984663edd4`: audit del 06/11/2026 alle 21:14 UTC, senza comandi Docker di start/stop, senza scrivere journal, config o mandati.
- **Backup esterno:** `superbot-extbackup.service` *failed*, `Result=exit-code`, codice1, timer *active*. Stato: ultimo successo **2026-11-02T03:28:45Z** e ultimo tentativo con errore. Alert schedulato GitHub Actions run `42217335679` del 06/11: «backup del cervello non riuscito (nessuna finestra di fine ciclo verificata o file mancanti)». Il testo non prova quale delle due cause sia effettiva; non bypassare mai il controllo.
- **Backup locale:** archivio `/opt/superbot-backups/rc-v3-20261106T150730Z` presente; rehearsal di ripristino in area temporanea run `42252417296` PASS, comprese vecchie posizioni Falco6, Toro2 e SQLite. **Non certifica l'esistenza di un backup off-host recente.**

## Stato macchina rilevato

| Risorsa | Evidenza | Gate |
|---|---|---|
| Web `superbot` | container running, PAPER; legato a directory classiche legacy | Richiede nuova configurazione di binding prima del deploy V3 |
| Web variabili Brain | `V3_JOURNAL_PATH`, `V3_RUN_ID`, `V3_HEARTBEAT_PATH`, `V3_BUDGET_DB_PATH`, `V3_PAUSE_FLAG_PATH` tutte non configurate | La nuova UI non può ancora mostrare lo stato del Brain V3 reale |
| Falco legacy | worker exited, pause presente, **6 posizioni OPEN storico PAPER** | Nessun reset/riavvio su vecchio volume |
| Toro legacy | worker exited, pause presente, **2 posizioni OPEN storico PAPER** | Nessun reset/riavvio su vecchio volume |
| Brain preparato in precedenza | `/opt/superbot-v3-paper-runs/brain-v3-rc20261106`; `PAUSED`; mandato non approvato; equity 2.000; journal integrity OK | La sua config non corrisponde al profilo 12%/55% della PR #62; NON modificarla in-place |
| Checkout sulla VPS | `/opt/superbot-v3-rc62-src` commit `53b63b6e8` | NON coincide con l'ultima RC: necessita checkout isolato e pin rigoroso del commit dopo i gate |
| Servizio backup esterno | **FAILED** con ultimo successo Nov2 | **Blocco primario di affidabilità** |

## Parametri da conservare esattamente

- Falco 1.000 USDT PAPER, Toro 1.000 USDT PAPER; Claude consultato come prima, strategie SHORT invariate, nuova strategia LONG S25 e segnale cambio trend **soltanto additivi**. Vecchia cronologia, lezioni e posizioni storiche immutate e separate.
- Brain 2.000 USDT PAPER, per-trade perdita **stimata** 75 su350 margine (21,4285714%), max margine/trade400, leva20–50x, max rischio aperto12% (=240 all'inizio), max margine complessivo55% (=1100 iniziali), floor450. Nuova run PAUSED/mandato non approvato.
- Nuova dashboard unica `/overview`, vecchia classici `/classic`; dettagli aperti/chiusi per ciascun bot con leva/margine/P&L/prezzi; portafogli indipendenti e prezzi ignoti mostrati come ignoti.

## Ordine sicuro della ripartenza

1. **Backup esterno (bloccante):** diagnosticare localmente l'unità `superbot-extbackup.service`, lo stato cifrato e i prerequisiti della finestra di snapshot senza diffondere log o segreti su GitHub. Poiché i worker legacy sono spenti, il runbook di backup deve distinguere correttamente *worker spento e dati consistenti* da *ciclo in corso/instabile*, senza eliminare i controlli di consistenza. **Nessuna modifica al servizio senza un piano verificato e autorizzazione.**
2. Completare un backup cifrato **off-host**, attestare timestamp, SHA esterno e un ripristino isolato con confronti a sorgente; una copia locale da sola non basta.
3. Creare directory **nuove** per Falco, Toro e un nuovo Brain2k con config12%/55%. Le run devono rimanere in pausa con mandati/controlli non sbloccati e mai riutilizzare o migrare ciecamente quelle esistenti. Verificare che Claude/S25/trend advisory restino configurati senza alterare SHORT.
4. Validare ownership unica di apertura/uscita PAPER e sidecar EXIT con test di guasto, riavvio e rollback; approvare esplicitamente nuovo mandato Brain SOLO dopo il gate.
5. Con un piano di deploy separato, mappare tutti i volumi nel WEB e le cinque variabili `V3_*`; evitare che il vecchio web mostri stati storici come nuovi. Smoke test autenticato e verifica UI su smartphone 390×844 e desktop prima di qualsiasi trading.
6. **Richiedere specifico OK di avvio PAPER** e riaprire le nuove run con cooldown previsto e supervisione. Mai `docker start` sui vecchi container e mai rimuovere automaticamente i pause flag per aggirare un blocco.

## Cosa significa il verde della CI

Il verde GitHub valida la modifica isolata e le sue regressioni automatiche. **Non dimostra** che i dati V3 siano montati nel web, che il backup esterno sia sano, che i worker siano correttamente supervisionati o che la nuova interfaccia sia stata verificata su dispositivo reale. Il runbook con evidenza runtime attuale rimane **NO-GO**.

**Azioni eseguite in questa fase:** sola verifica GitHub/VPS read-only e aggiornamento documentale sulla PR #62. **Azioni NON eseguite:** merge, deploy, copia/riscrittura di dati, start/stop container, cancellazioni, modifica o riapprovazione mandato, impostazioni chiavi, riavvio app.
