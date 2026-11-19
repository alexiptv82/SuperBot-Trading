# Evidenze P0 #124 — blocco giornaliero (richieste dal proprietario)

**Correzione:** commit **`ddd130847ae6ccdd2300b4d4ceba1ccde7e2a75e`**, impilato su PR #121 `5b7403aa333b43d801ca7e28825ea4707f6847b4`; integrato nel ramo `integration/brain-unico-20261119` con il merge `46e18096`. File: `backend/v3/runner/daily_loss.py`, `wiring.py`, test.

**Risultati:** suite V3 su `33a0de7` = 5023; con #121 = 5031; con #121 + P0 = **5063 superati**, 0 falliti, 1 saltato. Le soglie 35 % / 50 % e il pavimento 450 USDT non sono modificati.

| Requisito | Test (file `test_daily_loss_latch_p0.py` salvo indicazione) | Esito |
|---|---|---|
| Riavvio dopo HALT | `test_restart_after_unpersisted_halt_with_recovery_stays_halted_by_reconstruction`; (esistente) `test_v3_runner_daily_loss::test_halt_latch_survives_a_restart_and_is_released_by_the_next_day` | PASS |
| File corrotto | `test_corrupt_file_after_activity_reconstructs_the_day` (5 varianti) | PASS |
| File mancante | `test_deleted_file_after_activity_reconstructs_the_day` | PASS |
| Errore di scrittura | `test_unwritable_disk_denies_new_openings_even_when_the_loss_is_ok`; `test_restart_after_unpersisted_halt_with_recovery_stays_halted_by_reconstruction` (HALT raggiunto con il disco che rifiuta la scrittura, poi riavvio); (esistente) `test_v3_split_runtime_integrated::test_post_ai_daily_loss_disk_write_failure_denies_open` | PASS |
| PnL recuperato sotto soglia | `test_halt_is_latched_for_the_rest_of_the_utc_day_even_if_the_loss_recovers`; `test_a_loss_block_is_never_lifted_before_midnight_even_by_a_clean_reconstruction` | PASS |
| Sblocco al giorno UTC successivo | `test_restart_at_utc_midnight_releases_yesterdays_halt_and_checks_only_the_new_day`; `test_a_state_file_of_the_previous_day_does_not_hide_a_crash_of_today`; `test_a_fresh_state_of_yesterday_does_not_skip_the_first_minutes_of_today` | PASS |
| Portafoglio nuovo | `test_first_start_of_a_virgin_run_is_ok_and_asks_no_price` | PASS |
| Orologio indietro, idempotenza, ricostruzione impossibile | `test_clock_going_backwards_*`, `test_restarts_are_idempotent`, `test_unverified_block_is_lifted_only_by_a_later_successful_reconstruction`, `test_a_missing_bar_in_the_reconstruction_is_fail_closed` | PASS |
| Indipendenza dell'ExitService | `test_sidecar_exits_stay_owned_elsewhere_while_new_openings_are_blocked`; `test_legacy_mode_monitor_keeps_running_while_new_openings_are_blocked` (monitor/uscite attive, nuove aperture ferme) | PASS |
| Compatibilità con PR #121 | `test_daily_loss_mark_failclosed.py` 8/8 invariati; due test legacy aggiornati da ChatGPT passano; rig dei test adattato solo per iniettare la ricostruzione | PASS |

**Prova che il difetto esisteva:** con la sola interfaccia vecchia, nei tre scenari (file corrotto, file cancellato, scrittura fallita) un riavvio con perdita rientrata dava `ok` (riapertura); con la correzione dà `halt`. Mutazioni: 14/15 più il wiring (la sopravvissuta è una guardia difensiva equivalente).

**Cinque fallimenti "preesistenti":** erano `test_v3_rc84_import_paths` (5 test). **Non erano difetti del codice**: nell'ambiente di prova mancava `numpy`. Con le dipendenze installate passano (6 passed, 1 skipped) sia sulla base sia con le correzioni. **Nuove regressioni: 0.**

**Limiti:** la ricostruzione vede gli stessi istanti del controllo vivo (chiusura di ogni minuto), non i picchi intra-minuto. Senza rete al riavvio il blocco `unverified` ferma le nuove aperture (le uscite no) finché una ricostruzione non riesce. Non provato su VPS: nessun deploy.
