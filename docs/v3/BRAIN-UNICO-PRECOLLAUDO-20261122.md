# Brain Unico: pre-collaudo del servizio delle uscite e del rollback (preparazione, 22/11/2026)

**Stato:** procedura preparata. **Nulla è stato eseguito sulla VPS:** nessuna unità creata, avviata o fermata, nessuna run creata, mandato non approvato.
**Versione di riferimento:** integrazione @ `302e94d2`, gate verde (V3 5410, builder 158, Jest 153). Include tetto di 4 posizioni e rischio aperto con i costi stimati.

## Stato attuale della VPS (lettura senza privilegi, 22/11)
- `superbot-v3-paper-brain-exit.service`:
  - **attivo**;
  - proprietario delle uscite della run in pausa `brain-v3-paper20261111` (`PREPARED_PAUSED_ONLY.json`);
  - codice da `/opt/superbot-v3-rc84-repair-ab7e0b7`.
- **Runner del Brain:** nessuna unità attiva.
- `superbot-v3-falco-exit.service` e `superbot-v3-toro-exit.service`: `failed`. Solo annotato: nessuna indagine, come da decisione del proprietario.

## Disegno dell'installazione (da autorizzare)
- **Nuova cartella di codice** al commit della RC verificato dal gate. Nessuna modifica alle cartelle esistenti.
- **Nuova run** con `run_id` `brain-unico-paper-rc1` (legato dal mandato) nella cartella `brain-v3-unico-paper-rc1` (`prepare_paper_run` accetta solo cartelle `brain-v3-*`):
  - journal nuovo;
  - configurazione del profilo B, con impronta verificata (`BRAIN-UNICO-MANDATO-PROFILO-B-20261121.md`).
- **Due unità nuove**, separate:
  1. **servizio delle uscite** della nuova run (`exit_worker`), avviato **per primo**;
  2. **runner** in modalità `sidecar`, avviato solo con il servizio delle uscite sano.
- **Nessun intervento sugli esistenti:** run storiche, servizio delle uscite della vecchia run, Falco, Toro e Arena non si toccano.

## Controlli del pre-collaudo (prima di approvare il mandato)
Ogni controllo ha un esito PASS o FAIL. Un FAIL ferma tutto.

| # | Controllo | PASS se | Già coperto offline da |
|---|---|---|---|
| 1 | Codice installato | commit = RC; `sha256sum --strict` della configurazione = impronta registrata | — |
| 2 | Servizio delle uscite della nuova run | lease acquisito, battito fresco, monitor riuscito di recente: `exit_service_healthy(...)` vero | `test_v3_rc84_brain_single_exit_owner.py` |
| 3 | Runner senza mandato | battito `halted` con motivo del **mandato** (`mandate_not_approved`); **nessuna** chiamata al modello (`budget.db` vuoto); nessuna apertura | `test_v3_runner_e2e.py` (`test_mandate_problem_codes`, `test_changing_the_risk_limits_voids_the_mandate`) |
| 4 | Servizio delle uscite fermato | **controllo diretto** `exit_service_healthy` = NON sano entro 75 s (le aperture sono negate dal percorso serializzato); al riavvio torna sano **senza** ereditare un certificato vecchio. **Attenzione:** il battito del runner mostra un solo motivo, con priorità al mandato. Senza mandato resta `mandate_not_approved` anche con le uscite ferme (verificato nella prova offline), quindi il blocco per uscite non sane si legge **solo** dal controllo diretto | `test_split_rechecks_health_each_tick`, `test_restart_after_crash_never_inherits_a_previous_healthy_certificate` |
| 5 | Unico proprietario delle uscite | un secondo processo di uscita sulla stessa run non parte | `test_concurrent_acquisition_by_independent_processes_yields_exactly_one_owner` |
| 6 | Pausa | con `pause.flag` nessun nuovo giro; le uscite proseguono | `test_v3_runner_e2e.py` (`test_pause_flag_stops_new_openings_and_spending_...`, `test_open_positions_keep_being_monitored_while_paused`) |
| 7a | **Rollback del backend** | si fermano e si rimuovono le due unità nuove; il servizio delle uscite della vecchia run resta invariato (PID e stato); il journal della nuova run resta (append-only) | `90-rollback.sh` |
| 7b | **Rollback web, solo in ambiente isolato** | nel pre-collaudo la **dashboard attiva non si tocca**. La prova del ripristino web (meccanismo RC71: vecchio container e frontend conservati) si fa su una copia isolata, e un intervento sulla dashboard attiva richiede un'autorizzazione separata | `v3-rc71-web-cutover.py` (funzione `rollback`) |

**Criterio di uscita del pre-collaudo:** tutti i controlli PASS. **Non autorizzano da soli il mandato.** Per approvare il mandato e avviare la Fase 1 di 72 ore servono **anche**:
- zero P0 aperti (Issue #124 chiusa dal proprietario);
- backup certificato;
- ripristino verificato sul PC del proprietario;
- l'approvazione esplicita del proprietario.

## Che cosa serve dal proprietario
1. **Autorizzazione** a creare la cartella di codice, la nuova run e le due unità, e ad avviarle **senza mandato**. Il runner resta `halted` e non spende nulla.
2. **Autorizzazione** alla prova di arresto e riavvio del servizio delle uscite della **nuova** run (controllo 4) e alla prova di rollback (controllo 7).
3. Dopo i 7 PASS: approvazione del mandato e avvio della Fase 1.

## Pacchetto preparato (`deploy/brain-unico/precollaudo/`, NON eseguito sulla VPS)
| Script | Cosa fa | Privilegi |
|---|---|---|
| `comune.sh` | valori comuni: percorsi, impronta della configurazione, nomi delle unità | — |
| `10-installa.sh <commit>` | codice al commit da `git archive` del laboratorio, impronta verificata, `prepare_paper_run` (run in pausa, mandato `approved:false`), due unità **non abilitate e non avviate** | root |
| `20-avvia-senza-mandato.sh` | verifica `approved:false`, avvia le uscite, attende che siano sane, poi avvia il runner | root |
| `30-controlli.sh` / `controlli.py` | controlli in sola lettura; salute delle uscite letta **direttamente**, separata dal motivo del runner | lettura |
| `40-prova-arresto-uscite.sh` | arresto e riavvio delle uscite della **nuova** run; verifica che la vecchia sia invariata | root |
| `90-rollback.sh` | ferma e rimuove solo le unità nuove; vecchia run invariata; nessuna cancellazione di dati; dashboard non toccata | root |

**Prova offline nel laboratorio** (22/11, senza root, senza rete, processi reali in una cartella temporanea):
1. run preparata con il profilo B;
2. servizio delle uscite avviato: SANE;
3. un giro del runner in sidecar: `halted:mandate_not_approved`;
4. `controlli.py`: **7 PASS**;
5. servizio delle uscite fermato: NON SANE dopo l'uscita del processo, mentre il runner mostrava ancora il motivo del mandato.

Test nel gate: `test_v3_precollaudo_controls.py`.

**Nota:** il vincolo `brain-v3-*` sul nome della cartella è stato scoperto in questa prova.
