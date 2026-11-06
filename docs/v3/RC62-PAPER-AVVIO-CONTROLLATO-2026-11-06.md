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
| Brain | **2.000 USDT proposti, NON ancora confermati per l'avvio** | DeepSeek, runner V3 PAPER, EXIT worker indipendente | Nuova directory V3 con journal/budget propri | Confermare capitale, config e mandato esplicito |

### Storico e memoria
- Storico vecchio intoccabile, mantenuto e identificato per run. Le 8 posizioni storiche NON devono essere computate nell'equity del nuovo Falco/Toro né presentate come aperte in una run V3.
- Se si desidera usare lessons/trade_history precedenti, usare accesso in sola lettura o import verificato con provenance e run ID, senza alterare gli originali. Non supporre che il nuovo Brain apprenda già dai classici: la connessione continua va verificata separatamente.
- Evitare la duplicazione dell'app/runner. L'API web deve conoscere i percorsi *nuovi* tramite `DESK_DATA_DIR`, `DESK_DATA_DIR_BULL`, `V3_JOURNAL_PATH`, `V3_BUDGET_DB_PATH`, `V3_HEARTBEAT_PATH`, `V3_PAUSE_FLAG_PATH`, `V3_RUN_ID`; controllare l'accesso ai volumi nei container.

## Gate sequenziali di rilascio
1. **Config approvata:** tutti PAPER, 1k Falco/Toro, capitale Brain deciso (config di esempio è 1k; non usarlo accidentalmente), policy rischio hash e mandato Brain esplicitamente firmato. Verificare quali limiti classici differiscono dalle specifiche nuove; NON modificare di nascosto.
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
