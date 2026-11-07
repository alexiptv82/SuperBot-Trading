# RC80 — indurimento offline del monitor PAPER di stop

**Il ramo canonico `diario` non è stato aggiornato.** Questa voce sta solo sul branch `cursor/rc80-paper-stop-hardening-31c4`. Il diario canonico resta `85e84cc485001b9c81ff392c5668114034f73eac` (RC77, 7 novembre 2026, 20:00:54 CET).

Puntatore: questo file e `docs/v3/RC80-PAPER-STOP-HARDENING-HANDOFF-20261107.md`.

## Base

- PR #75 / RC78: `cursor/rc78-paper-stop-offline-31c4` @ `b6eaa173c12c241647f89f730e1430a841cade3a`. Branch non sovrascritto.
- Base di RC78: `work/v3-rc77-post-arb-close-backup-20261107` @ `52c21b5ea219bb864b8748ba1b2cfe109349a2e7`.
- PR #76 (RC79, ChatGPT) e PR #74 (Brain, offline) lette e non modificate.
- L'audit VPS RC77 (Falco 0, Toro 0, Brain in pausa, backup locale PASS, esterno `exit-code`) è storico. Nessun audit nuovo.

## Problemi trovati nel monitor RC78 e correzioni

1. Con l'opt-in acceso il worker poteva restare `ready` anche senza un prezzo fresco per ogni posizione. Ora `stop_protection` è distinto: `off`, `unverified` all'avvio, `covered` solo se ogni posizione aperta ha una barra 1m valida, altrimenti `partial`, `blind`, `idle` o `blocked`.
2. Un claim con id stringa non combaciava con l'id intero: il claim poteva risultare già chiuso e la stessa posizione venire chiusa di nuovo. Ora gli id numerici si confrontano come interi. Un claim è risolto solo se la posizione non è aperta e lo storico contiene quella chiusura. Se lo storico ha la chiusura e la posizione è ancora aperta, lo stato è `mismatch` e non si scrive una seconda riga.
3. `record_close` inghiotte gli errori di scrittura. Si poteva salvare il portafoglio senza riga di storico. Ora, prima di `save_state`, si fa fsync e si rilegge storico e learning. Se manca uno dei due, non si salva lo stato e il claim resta.
4. Un crash dopo il salvataggio e prima della cancellazione del claim bloccava per sempre l'avvio, anche quando stato e storico erano coerenti. All'avvio un claim già provato viene archiviato in `paper_stop_protect.reconciled-*.json`, senza una seconda chiusura. Un claim aperto, non provato o malformato blocca l'avvio.
5. `lock_held=True` era solo un booleano. Ora il chiamante deve tenere il file di lock dell'exit writer, oppure questa funzione lo prende in esclusiva. Un secondo processo riceve `ownership_lock_required`.
6. Non c'era distinzione fra feed perso, timestamp futuro, barra vecchia e barra OHLC incoerente. `classify_candle` non restituisce un prezzo in quei casi. Un massimo che buca lo stop ma una chiusura rientrata non chiude: non si inventa il wick come prezzo eseguibile.
7. Il container legacy va ridimostrato fermo prima delle scritture. Se non lo è, nessuna chiusura.

La formula di liquidazione e il netto oltre il margine delle chiusure non-liquidazione non sono stati cambiati. La chiusura manuale continua a usare il controllo prezzi RC78 (`recent_minute_prices`), senza il nuovo controllo OHLC.

## Prove locali, non CI

`PYTHONPATH=.:backend python3 -m pytest -q -p no:cacheprovider backend/tests/test_v3_rc80_paper_stop_hardening.py backend/tests/test_v3_rc78_paper_stop_monitor.py backend/tests/test_v3_classic_exit_only.py`

Risultato locale: **56 passed, 0 failed** (19 RC80, 22 RC78, 15 exit-only). Nessun workflow è stato aggiunto. Il push di questo branch non coincide con nessun filtro `push` dei workflow presenti nel tree. Non c'è CI di GitHub su questo branch: non va spacciata per eseguita.

## Non fatto e non pronto

- Nessun merge, deploy, riavvio, ordine, accesso VPS.
- Backup esterno ancora non certificato. Brain PR #74 non deployata.
- Un `mismatch` (storico chiuso, posizione ancora aperta) resta bloccato finché non lo ricompone una persona. Non si cancella lo storico da soli.
- L'età della barra è l'apertura della candela 1m, non l'ora dello scambio. Oltre 120 secondi il prezzo è stale.
- Il monitor resta spento senza `DESK_PAPER_STOP_MONITOR=1` e `DESK_MODE=paper`.
- Non è pronto per la produzione. La revisione indipendente è di ChatGPT. Nessuna fase successiva è stata avviata.
