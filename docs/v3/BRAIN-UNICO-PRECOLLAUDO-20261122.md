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
- **Nuova run** `brain-unico-paper-rc1`:
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
| 3 | Runner senza mandato | battito `halted` con `no_mandate` / `mandate_not_approved`; **nessuna** chiamata al modello (`budget.db` vuoto); nessuna apertura | `test_v3_runner_e2e.py` (`test_mandate_problem_codes`, `test_changing_the_risk_limits_voids_the_mandate`) |
| 4 | Servizio delle uscite fermato | entro 2 minuti il runner rifiuta le aperture (`exit_service_unhealthy`); al riavvio torna sano **senza** ereditare un certificato vecchio | `test_split_rechecks_health_each_tick`, `test_restart_after_crash_never_inherits_a_previous_healthy_certificate` |
| 5 | Unico proprietario delle uscite | un secondo processo di uscita sulla stessa run non parte | `test_concurrent_acquisition_by_independent_processes_yields_exactly_one_owner` |
| 6 | Pausa | con `pause.flag` nessun nuovo giro; le uscite proseguono | `test_v3_runner_e2e.py` (`test_pause_flag_stops_new_openings_and_spending_...`, `test_open_positions_keep_being_monitored_while_paused`) |
| 7 | **Rollback provato** | si fermano le due unità nuove; il servizio delle uscite della vecchia run resta attivo e invariato; il journal della nuova run resta (append-only) e la web precedente si ripristina con il meccanismo di cutover esistente (RC71: vecchio container e frontend conservati) | `v3-rc71-web-cutover.py` (funzione `rollback`) |

**Criterio di uscita:** 7 PASS. Poi il proprietario approva il mandato (`mandate.json`) e parte la **Fase 1 di 72 ore**.

## Che cosa serve dal proprietario
1. **Autorizzazione** a creare la cartella di codice, la nuova run e le due unità, e ad avviarle **senza mandato**. Il runner resta `halted` e non spende nulla.
2. **Autorizzazione** alla prova di arresto e riavvio del servizio delle uscite della **nuova** run (controllo 4) e alla prova di rollback (controllo 7).
3. Dopo i 7 PASS: approvazione del mandato e avvio della Fase 1.

Con la prima autorizzazione si preparano gli script esatti (comandi concatenati con `&&`, impronte verificate, nessun tocco alle unità esistenti), come per l'extbackup.
