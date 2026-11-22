# Issue #124 (P0): verifica dei criteri di accettazione (22/11/2026)

**Esito:** criteri 1–8 coperti con evidenze verificabili. **Integrato** nell'integrazione con `5f110379` (gate verde V3 5418). Il criterio 6 (**concorrenza**) **non lo era**: difetto riprodotto e corretto sul branch isolato `claude/p0-124-chiusura-20261122` (`7169558c`, più il lock non bloccante della verifica finale).

**L'Issue NON è chiusa:** la chiusura spetta al proprietario dopo la revisione.

**Codice:**
- `backend/v3/runner/daily_loss.py`, correzioni precedenti `ddd13084` e `a1777291`, già nell'integrazione;
- correzione di concorrenza `7169558c`.

**Test:**
- `backend/v3/runner/test_daily_loss_latch_p0.py` (36 test);
- `backend/tests/test_v3_runner_daily_loss.py`.

**Suite V3 sul branch:** 5414 passati.

## Riproduzione dello scenario dell'Issue (stesso script, due versioni)
Blocco alle 10:01 con scrittura fallita, poi PnL recuperato e riavvio alle 10:03:
- codice **precedente** a `ddd13084`: livello `ok` → **FAIL-OPEN, riapre**;
- codice **attuale**: livello `halt` → **fail-closed**.

Concorrenza: due processi sulla stessa run, solo A vede lo stop alle 10:01, poi il PnL recupera:
- **prima** di `7169558c`: B riscrive il file senza blocco e **apre** alle 10:02;
- **dopo**: B adotta il blocco di A e resta `halt`; il file conserva `loss`.

## Criteri
| # | Criterio | Come è soddisfatto | Evidenza (test) |
|---|---|---|---|
| 1 | Blocco fino al giorno UTC successivo anche dopo riavvio e recupero del PnL | dopo **ogni** avvio la giornata si **ricostruisce** da journal e candele 1m (`max_daily_loss_between`), dall'ultimo istante dimostrato o da mezzanotte; picco ≥ soglia → blocco `loss` fino a mezzanotte | `test_restart_after_unpersisted_halt_with_recovery_stays_halted_by_reconstruction`, `test_owner_scenario_failed_latch_write_then_restart_within_minutes_stays_halted`, `test_any_restart_after_an_unpersisted_crash_minute_reconstructs_it`, `test_restart_at_utc_midnight_releases_yesterdays_halt_and_checks_only_the_new_day` |
| 2 | File corrotto, parziale, cancellato o scrittura fallita non riabilitano le aperture | file non fidato → ricostruzione; scrittura rifiutata → `recheck` solleva `daily_loss_*_not_persisted` e l'apertura è negata | `test_corrupt_file_after_activity_reconstructs_the_day`, `test_deleted_file_after_activity_reconstructs_the_day`, `test_unwritable_disk_denies_new_openings_even_when_the_loss_is_ok` |
| 3 | Distinguere in modo verificabile il primo avvio di una run vergine dalla perdita di stato | la distinzione viene dal **journal**, non da un flag: senza eventi la ricostruzione vale 0 e non chiede prezzi; con attività si ricostruisce | `test_first_start_of_a_virgin_run_is_ok_and_asks_no_price`, `test_first_start_without_any_reconstruction_is_fail_closed_until_proven` |
| 4 | Prova persistente e verificabile, idempotente, legata a `run_id` e giorno UTC; nessun nuovo percorso fail-open | la prova è il journal append-only con catena di hash più le candele: nessun nuovo evento da scrivere, quindi nessun append che possa fallire; ricostruzione idempotente per run e giorno | `test_restarts_are_idempotent`, `test_reconstruction_matches_the_live_formula_at_each_minute`, `test_a_missing_bar_in_the_reconstruction_is_fail_closed` |
| 5 | Un errore blocca solo le nuove aperture; servizio delle uscite e chiusure autonomi | il blocco agisce sul runner e sul ricontrollo prima dell'apertura; il servizio delle uscite è un processo separato | `test_sidecar_exits_stay_owned_elsewhere_while_new_openings_are_blocked`, `test_legacy_mode_monitor_keeps_running_while_new_openings_are_blocked`, `test_end_to_end_a_loss_check_failure_does_not_block_the_exit_monitor` |
| 6 | Nessuna riapertura per errore I/O, riavvio, cambio minuto, recupero PnL, file mancante o corrotto, orologio all'indietro, **concorrenza** | tutti coperti; **concorrenza corretta in `7169558c`**: sezione critica con lock sul file di stato, rilettura e **adozione** di un blocco `loss` dello stesso giorno scritto da un altro processo (solo aggiunta); senza lock lo stato non viene scritto e `recheck` nega | `test_clock_going_backwards_is_fail_closed`, `test_clock_going_backwards_keeps_a_loss_block_as_a_loss_block`, `test_a_minute_skipped_for_missing_prices_in_the_same_process_is_reconstructed`, `test_a_loss_block_is_never_lifted_before_midnight_even_by_a_clean_reconstruction`, **`test_a_second_process_cannot_erase_the_loss_latch_of_the_first`**, **`test_a_process_that_never_saw_the_stop_adopts_it_before_opening`**, **`test_a_loss_latch_of_yesterday_on_disk_is_not_adopted_today`**, **`test_without_the_state_lock_new_openings_are_denied`**, **`test_two_real_os_processes_the_second_cannot_erase_the_loss_latch_of_the_first`** (due processi del sistema operativo con `spawn`, 300 scritture ciascuno, davvero concorrenti), **`test_a_lock_held_by_another_os_process_denies_new_openings_quickly`** |
| 7 | Test locali reali, verdi e rossi sulla baseline | casi richiesti tutti presenti: riavvio dopo HALT con recupero; file corrotto; file assente dopo attività; disco non scrivibile; journal vuoto al primo avvio; riavvio a mezzanotte; idempotenza; file del giorno precedente; blocco post-AI (`recheck` nel percorso serializzato, `daily_loss_halted` in `wiring`); sidecar vivo | **rossi sulla baseline:** i test P0 non si caricano sul codice precedente a `ddd13084` e lo scenario riprodotto riapre; 3 dei 4 nuovi test di concorrenza falliscono sul codice precedente a `7169558c` (il quarto, sul blocco di ieri, verifica un comportamento già corretto) |
| 8 | Documentare migrazione, compatibilità e primo avvio | stato v1 (legacy) accettato in modo conservativo, con ricostruzione; primo avvio di una run vergine `ok` senza prezzi; **nuovo file `.daily_loss.lock`** creato alla prima scrittura (vuoto, permessi 0600, nessun contenuto) | `test_legacy_v1_state_is_migrated_conservatively`, `test_state_file_has_exactly_the_v2_keys_and_no_amounts` |

## Verifica finale richiesta dal proprietario (22/11)
- **Due processi del sistema operativo indipendenti e concorrenti** (`multiprocessing` con `spawn`): A aggancia lo stop dal 20° minuto; B non lo vede mai e scrive per 300 minuti nello stesso periodo.
  - Codice corretto: B finisce `halt` e il file conserva `loss`.
  - Codice precedente a `7169558c`: B finisce **`ok`**, quindi aprirebbe (test rosso).
- **Lock non acquisibile** (tenuto da un altro processo del sistema operativo): lo stato non viene scritto e `recheck` nega l'apertura **in pochi secondi**. Prima il lock era bloccante: con `7169558c` il processo attendeva circa 30 s e poi **non** negava (test rosso). Corretto con tentativi non bloccanti limitati (20 × 0,1 s, poi fail-closed).

## Limiti dichiarati (non riaprono)
- **Candele necessarie:** la ricostruzione richiede le candele 1m del giorno. Se il feed non le fornisce dopo un riavvio, il blocco è `unverified`: nessuna nuova apertura, nuovo tentativo ogni 5 minuti, comunque fino alla mezzanotte UTC. È voluto (fail-closed).
- **Processi concorrenti:** la protezione vale per processi che usano lo stesso file di stato. **Due runner sulla stessa run restano comunque non supportati:** l'installazione ne prevede uno solo, e il pre-collaudo lo verifica.
- **Soglie:** sono configurazione (decisione del proprietario: profilo B, 3 % e 4 %); il codice del blocco non le fissa.

## Per chiudere l'Issue (decisione del proprietario)
1. Approvare e integrare `7169558c`; poi il gate sull'integrazione.
2. Revisione di questo documento.
3. Chiusura dell'Issue da parte del proprietario, con riferimento ai commit.
