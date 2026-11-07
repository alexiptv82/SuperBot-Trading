## Aggiornamento vincolante — 7 novembre 2026 (precedenza sulle righe storiche sopra)

**Non utilizzare come istruzioni operative i vecchi valori 2%/5% o le descrizioni “rules-only / nessuna chiave Anthropic” riportate nelle sezioni storiche di questo documento.** Queste sezioni rappresentano checkpoint superati, non la configurazione approvata per la nuova run.

- **Falco e Toro:** conservare la consultazione di **Claude** come nella versione precedente. La strategia SHORT esistente resta invariata; S25 LONG e indicatore consultivo di cambio trend sono integrazioni additive. Le credenziali non vanno inserite nei log, nel frontend o in GitHub; verificare come il servizio le carica senza modificarle in questa fase.
- **Brain:** capitale PAPER **2.000 USDT**; profilo attuale della PR #62: rischio aggregato **12%**, tetto di margine aggregato **55%**, rischio stimato per operazione fino a 75 USDT su 350 USDT di margine, margine singolo fino a 400 USDT, leva 20–50×, protezione equity 450 USDT. Il mandato non è ancora approvato e la vecchia run PAUSED non va modificata in-place.
- **Conferma runtime 6/11:** audit Singapore in sola lettura, report `docs/v3/RC62-SINGAPORE-READONLY-GATE-20261106.md`. Backup esterno cifrato **FAILED** (ultimo successo 2/11), non risolto dalla prova di ripristino locale. Nuove run e nuovi volumi web non configurati. **NO-GO deploy e start**.
- **CI ultimo commit 14ac880dd:** run GitHub `42295814354`, quattro job SUCCESS (backend, frontend, v3-suite, classics-rc). Non equivale a collaudo VPS.
- **Prossima priorità:** diagnosticare e ripristinare backup esterno con attestazione off-host e restore isolato; poi nuove run PAUSED, collegamento web e prova UI. Nessun merge, deploy, start/stop, reset, cambio di rischio o firma del mandato senza specifica procedura approvata.

---

# SuperBot V3 — checklist di avvio controllato (PR #62)
**Stato:** NO-GO per il deploy. Preparazione e test soltanto. NESSUN ordine LIVE.

## Evidenza verificata
- PR #62 draft su base PR #57; dashboard PR #60/#61, runner Brain V3 split, modulo monitor EXIT e Supervisore in unico ramo. Al 6 novembre 2026 la CI GitHub è verde (backend, suite V3, React, build). Non equivale a prova dei processi sulla VPS.
- Inventario Singapore read-only: container web `superbot` running PAPER; container vecchi `superbot-desk-hawk`, `superbot-desk-bull`, `superbot-brain-free` exited. `pause.flag` presente per i tre.
- Legacy Falco: **6** posizioni PAPER ancora contabilizzate come aperte; Toro: **2**. **Non usare reset_portfolio.flag né close-all né `docker start` sul vecchio storage**.
- Brain legacy ha `brain.sqlite3`; il runner V3 richiede `journal.db` append-only + budget + run riconoscibile. La PR #62 include un UNICO preparatore `backend.v3.runner.prepare_paper_run` (bootstrap duplicato eliminato), che crea soltanto nuove directory in pausa.
- Backup VPS `/opt/superbot-backups/rc-v3-20261106T150730Z`: tarball controllati, SQLite integrity_check eseguito. Prova di ripristino in directory temporanea superata: 6/2 posizioni e due database recuperati.

## Le tre run da avviare senza contaminazione
| Portafoglio | Capitale di riferimento | Motore | Storage | Prima condizione |
|---|---:|---|---|---|
| Falco | 1.000 USDT PAPER | Regole classiche, nessuna chiave Anthropic nel container | Nuova directory distinta da `/opt/superbot-desk-data/hawk` | Preparazione dati iniziali separati dallo storico |
| Toro | 1.000 USDT PAPER | Regole classiche, nessuna chiave Anthropic nel container | Nuova directory distinta da `/opt/superbot-desk-data/bull` | Preparazione dati iniziali separati dallo storico |
| Brain | **2.000 USDT PAPER confermati dall'utente (6/11/2026)** | DeepSeek, runner V3 PAPER, EXIT worker indipendente | Nuova directory V3 con journal/budget propri | Config 2.000 confermata; mandato esplicito ancora da approvare |

### Storico e memoria
- Storico vecchio intoccabile, mantenuto e identificato per run. Le 8 posizioni storiche NON devono essere computate nell'equity del nuovo Falco/Toro né presentate come aperte in una run V3.
- Se si desidera usare lessons/trade_history precedenti, usare accesso in sola lettura o import verificato con provenance e run ID, senza alterare gli originali. Non supporre che il nuovo Brain apprenda già dai classici: la connessione continua va verificata separatamente.
- Evitare la duplicazione dell'app/runner. L'API web deve conoscere i percorsi *nuovi* tramite `DESK_DATA_DIR`, `DESK_DATA_DIR_BULL`, `V3_JOURNAL_PATH`, `V3_BUDGET_DB_PATH`, `V3_HEARTBEAT_PATH`, `V3_PAUSE_FLAG_PATH`, `V3_RUN_ID`; controllare l'accesso ai volumi nei container.

## Gate sequenziali di rilascio
1. **Config capitale confermata:** tutti PAPER; 1.000 USDT Falco, 1.000 USDT Toro, 2.000 USDT Brain. Per la nuova run Brain selezionare esplicitamente `backend/v3/runner/runner_config_brain2000_paper.json` (il file standard `runner_config.json` resta 1.000 come fixture/base). Il preparatore riceve `--expected-initial-equity 2000`, salva il file effettivo come `<nuova_run>/runner_config.json` e crea un mandato NON approvato. Una volta scelto il nuovo run_id verificare policy hash e ottenere il mandato approvato prima di qualunque apertura. Verificare quali limiti classici differiscono dalle specifiche nuove; NON modificare di nascosto.
2. **Backup/restore:** snapshot fresco, checksum/manifest e ripristino in copia, storico e posizioni intatti; operazione verificabile. Backup vecchi non rimossi.
3. **Owner unico:** impedire a legacy e sidecar di gestire contemporaneamente stop, close e OPEN. Prima installare sidecar in PAUSA e verificare heartbeat e lock, poi solo uno scrittore Brain autorizzato, mai due OPEN concorrenti.
4. **Run nuove:** usare il preparatore in modalità PAPER con directory inesistente e `--expected-initial-equity` esatto; prova `check_existing_data`. Il preparatore NON avvia il bot, crea mandato NON approvato e pause.flag.
5. **Classici:** due processi PAPER isolati, senza segreti Anthropic o LIVE, con run nuove e pause flag. Non premere reset sui vecchi 6+2 trade.
6. **Dashboard:** montare i nuovi path, verificare sessione, 3 portafogli, comandi Chiudi e Chiudi tutte PAPER, timer e banner PAUSED, terminale Supervisore; controllare il comportamento con dati mancanti.
7. **Smoke test runtime:** feed Bitget pubblico, DeepSeek key solo Brain, 30s modello bloccato, stop e manual-close devono continuare, fault restart EXIT deve bloccare nuove aperture, nessuna apertura in PAUSA, rollback solo tramite riattivazione della versione precedente su dati separati.
8. **Sblocco PAPER:** solo dopo esplicito via libera dell'utente, rimuovere pause flag *delle nuove run* e monitorare prime ore. Nessun merge/deploy/riavvio in automatico a seguito della sola CI.

## Stato GO/NO-GO
- **GO**: sviluppo RC #62, test CI, backup e prova di ripristino temporanea, preparatore nuovo in pausa.
- **NO-GO**: deployment e avvio effettivo finché non sono verificati collegamenti runtime, storage nuovo per classici, isolamento owner exit, capitale Brain, manodato/chiavi/config, smoke VPS e modalità di rollback.
- Non fare prove di profitto infinite prima dell'avvio; **sicurezza, contabilità, isolamento e recupero sì**.

## Decisione capitale Brain 6 novembre — confermata
La nuova run Brain parte con **2.000 USDT PAPER**, senza trasferire posizioni o PnL legacy. Gli altri capitali sono Falco 1.000 e Toro 1.000, totale iniziale 4.000 USDT PAPER. Il profilo opt-in `runner_config_brain2000_paper.json` differisce dal vecchio esempio soltanto nel capitale iniziale. Con i limiti invariati 2%/5%, il rischio per trade è 40 USDT e l'open risk aggregato 100 USDT; il floor di 450 USDT resta invariato. Non cambiare la politica né aggiornare la configurazione di una run già avviata senza procedura di migrazione. **Usare il file di configurazione copiato all'interno della nuova run per ENTRAMBI i processi**: Brain runner e exit worker, senza mai fare affidamento sul file standard da 1.000.

**Non ancora eseguito:** preparazione della run sulla VPS, creazione delle nuove run Falco/Toro, firma del mandato, avvio di un servizio, rimozione dei pause flag. Prima del deploy controllare che l'interfaccia e tutti i servizi puntino alla nuova directory e allo stesso run_id; le 6+2 posizioni legacy restano soltanto nello storico.
