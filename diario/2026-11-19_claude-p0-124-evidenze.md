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

---

## Seconda verifica richiesta dal proprietario (scenario 10:00 / 10:01 / 10:02) — **era un fail-open reale, corretto**

**Scenario:** stato `ok` persistito alle 10:00; alle 10:01 la perdita supera lo stop ma il latch non si scrive (disco); il PnL rientra; riavvio alle 10:02.

**Riprodotto sul codice reale `ddd1308`:** il riavvio dava **`ok`** senza ricostruzione. `_reconcile()` considerava valido lo stato del disco perché era entro la tolleranza di 3 minuti, ma quella tolleranza presumeva che il disco avesse visto tutto ciò che il processo aveva visto.

**Correzione:** commit **`a177729107231199f802f38e5592ab6e5373ea48`** (ramo `claude/brain-unico-daily-loss-latch-p0-20261119`), integrata con il merge `cc35f532`.
- La finestra di tolleranza non esiste più.
- La ricostruzione si salta **solo nello stesso processo** e solo se **nessuna chiusura di minuto è stata saltata** dall'ultima valutazione riuscita.
- **Al primo controllo dopo ogni avvio si ricostruisce sempre** dall'ultimo istante persistito.
- Copre anche la variante senza riavvio: il minuto del crollo saltato per prezzi mancanti viene ricostruito.

| Test (`test_daily_loss_latch_p0.py`) | Codice `ddd1308` | Correzione |
|---|---|---|
| `test_owner_scenario_failed_latch_write_then_restart_within_minutes_stays_halted` | **FAIL** (riapre) | PASS |
| `test_any_restart_after_an_unpersisted_crash_minute_reconstructs_it` (riavvio 10:01:50, 10:02, 10:02:59, 10:03) | **FAIL** ×3, pass ×1 | PASS ×4 |
| `test_a_minute_skipped_for_missing_prices_in_the_same_process_is_reconstructed` | **FAIL** | PASS |
| `test_restart_reconstruction_failing_is_not_a_permanent_block` | **FAIL** | PASS |
| `test_a_normal_restart_without_any_crash_is_not_blocked` | pass | PASS |
| `test_continuous_operation_in_the_same_process_does_not_reconstruct` | — | PASS |

**Nessun blocco permanente:**
- un riavvio normale resta `ok`;
- una ricostruzione fallita al riavvio dà `unverified`, che si toglie alla prima ricostruzione riuscita (riprovata entro 5 minuti) o con il nuovo giorno UTC.

**Uscite:** i test sidecar e legacy restano verdi; il freno non è sul percorso delle uscite.

**Suite V3:** ramo P0 **5071**; ramo di integrazione 5087 → **5095**; 0 falliti.

**Mutazioni:**
- riportare la tolleranza di 3 minuti → **rilevata**;
- non azzerare `fresh_start` → **rilevata**;
- togliere la ricostruzione forzata al riavvio → **equivalente** con valutazioni al minuto: un riavvio nello stesso minuto rivaluta la stessa barra e vede il crollo. La tengo come difesa in profondità; costa una lettura del journal e al più pochi minuti di candele per avvio.

**Stato P0:** corretta e verificata offline sul ramo di integrazione. Resta in bozza, nessun deploy.
