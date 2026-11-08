# RC84 — correzione P1 Telegram sulle chiusure PAPER non protettive (Claude, 08/11/2026)

**Base:** `bfe5ab9bd13005a37dc39918a33d9f8cac8c3adc`. **Commit codice+test:** `bbecbf976813cf69948d43026d6e0e1f18ff6085`.
Branch `cursor/rc84-running-stop-health-telegram-20261108`, PR #80 DRAFT. Nessun merge/deploy/VPS/riavvio/reset/ordine.

## Cosa cambia (solo `backend/desk/cli.py` + nuovo test)
- **Outbox in memoria** (`_queue_close_notice`, `_flush_close_notices`, `_save_state_then_notify`): regole/Claude, manuale singola, parziale e S25 non chiamano più `notify_close` prima del commit. L'avviso parte **dopo `save_state` riuscito** e **solo se** la stessa chiusura (symbol, id, open_ms, close_ms, why, net, run_no; per le parziali anche `fraction`) è in `trade_history.jsonl` **e** `learning_log.jsonl`. Altrimenti: nessun avviso e riga di log `[TELEGRAM] ... avviso omesso`.
- Se `save_state` solleva, la coda viene scartata; viene scartata anche all'inizio di ogni `run_cycle` e di ogni chiusura manuale (nessun avviso di un ciclo fallito passa nel commit successivo).
- `record_close` **non riscrive** una riga identica già presente (ripresa dopo salvataggio fallito: niente duplicati); non cancella né modifica righe. `_close_row_matches` accetta `partial=` (default `False`: comportamento invariato).
- Errore di Telegram: ignorato dopo il commit, non annulla la chiusura.
- **LIVE invariato:** stesso ordine di prima (notify poi record) nei rami `LIVE._live`; manuale e S25 sono già solo-PAPER. `long_s25.py`, stop protettivi, strategie, Claude, formule, parametri, formati degli storici: non toccati.

## Test
Nuovo `backend/tests/test_v3_rc84_telegram_durable_close.py` (27 test): per ciascun percorso (`rules`, `manual`, `partial`, `s25`) positivo (ordine e contenuto su disco al momento dell'invio), negativo con `save_state` fallito, storico non scritto, learning non scritto, Telegram giù, ripresa dopo crash con righe identiche (1 avviso, 1+1 righe); in più: nessuna fuga di avvisi fra cicli, LIVE invariato, ripresa manuale a istante diverso. Sul `cli.py` di partenza **24 su 27 falliscono** (tutti i 12 negativi), con la correzione 27/27.

## Esecuzioni (sandbox, rete rifiutata, nessun segreto)
- Nuovo test 27/27; RC84+RC82+RC81+RC80+RC78+exit-only e `test_long_s25.py` come nel log sotto.
- Intera `backend/tests/` (escl. `test_auth_flow.py`, `test_profiles_engine.py` per `sqlalchemy`): **6 770 PASS, 32 FAIL, 3 xfail**. Le 32: 9 `test_superbot.py` (richiedono un server live), 20 `test_brain_f3_boundaries.py` (`PolicyFixture` senza `max_loss_margin_fraction`), `test_desk_view.py`, `test_live_view.py`, `test_long_s25.py::test_engine_and_brain_files_are_unchanged_by_this_work` (hash fissato di `brain.py`, cambiato da RC82). **Le 23 non-rete falliscono identiche sul SHA di partenza** `bfe5ab9`.
- Frontend (nessun file toccato): Jest **109/109** in 13 suite, build `CI=true` **Compiled successfully**.

## Residui
1. Una ripetizione **a istante diverso** dopo un salvataggio fallito è un nuovo fill: la riga orfana del tentativo fallito resta (storico append-only, non riscritto) e ne segue una seconda. Nessun avviso falso; coperto da test.
2. Chiusure con riga di learning non scrivibile (limite di dimensione) non ricevono avviso Telegram.
3. 23 fallimenti preesistenti sopra elencati (fixture/hash obsoleti): da trattare a parte.
4. Restano i gate di handoff RC84 (browser autenticato/Android, cadenza stop 15m, sidecar Brain, backup off-host, nuova run solo con OK).
