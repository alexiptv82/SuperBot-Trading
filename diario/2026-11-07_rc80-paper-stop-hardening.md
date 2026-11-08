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

## Correzione dopo review ChatGPT, 8 novembre 2026

Fonte: commento https://github.com/alexiptv82/SuperBot-Trading/pull/77#issuecomment-6713923063 sul commit `9dedf5dc9ea0586e854afc59ebc050f9574f62c0`. REQUEST CHANGES. Questa patch è un commit aggiuntivo sullo stesso branch della PR #77. Il diario canonico (`e0a0da89d83671274a2484feb849535d0ec8de30` al momento della lettura) non è stato modificato.

| Rilievo | Esito |
|---|---|
| P0-A lock: il path dell'fd non prova il flock | Corretto. `flock(fd, LOCK_EX\|NB)` sullo stesso fd. Un fd aperto ma non lockato, mentre un altro processo tiene il lock, viene rifiutato. Test di processo separato. |
| P0-B identità `symbol,id` | Corretto. La prova richiede `open_ms` e non conta i fill parziali. Un record di un'altra run con lo stesso id non blocca né risolve la posizione nuova. Senza `open_ms` il claim resta `unproven`. `resolved` esige storico e learning. |
| P1-C candela aperta e wick | Scelta documentata, non è un cambio di formula economica. Vale solo la chiusura di una barra 1m già conclusa (`60s <= età apertura <= 120s`). La barra in formazione non è `covered` e non chiude. Il wick non è un fill: telemetria `execution=closed_1m_close_only`, `intrabar_wick=not_a_fill`. |
| P1-D health e allarme | Se la scrittura health fallisce, lo stato è `telemetry_failed` e non si chiude. `stop_certified` resta false. `protection_alarm` segnala heartbeat vecchio, `ready` senza copertura, e il limite del wick. La dashboard non è stata modificata: l'allarme è nel file di heartbeat, non in UI. |

Prove locali dopo la patch, non CI GitHub: stesso comando pytest dei tre file. Il numero aggiornato è nel messaggio di consegna e nel handoff. Nessuna Actions attesa, perché il branch non entra nei filtri dei workflow.

## Seconda review, 8 novembre 2026 — due P0 residui

Fonte: https://github.com/alexiptv82/SuperBot-Trading/pull/77#issuecomment-6720701115 sull'HEAD `b64519346cbe0c928cd29d3e9d57c619b472ac78`. I quattro rilievi precedenti sono confermati da ChatGPT. Questa patch copre solo P0-E e P0-F.

**P0-E.** `resolved` non basta più se storico e learning parlano della stessa posizione. Devono essere la stessa chiusura: stesso `close_ms`, stesso `why`, stesso `net` (quattro decimali) e, se presenti, `gross`, `fees`, `exit`. `close_ms` 2000 nello storico e 3000 nel learning, o un netto diverso, resta `unproven`. Un fill parziale non conta. Test: `test_history_and_learning_must_be_the_same_closure`.

**P0-F.** Il riavvio non richiede più che i file vivi siano identici allo snapshot originale, e non lo ricopia sopra i dati. Lo snapshot storico resta intatto. Lo stato vivo deve esserne un'estensione: log solo in append, lezioni invariate, una posizione sparita solo se storico e learning hanno la stessa chiusura. I checkpoint nuovi stanno in una cartella sorella `*.paper-stop-recovery`, mai dentro il backup. Un manifest corrotto blocca l'avvio senza ripristinare nulla. Manca il manifest dopo un crash ma la discendenza è coerente: l'altra posizione resta sorvegliabile. Test: `test_restart_after_one_of_two_closes_keeps_the_other_and_the_backup` (BTC chiuso, ETH ancora aperto, backup byte-identico, poi ETH chiudibile) e i due test di manifest corrotto / learning tolto.

Non è una certificazione di stop in produzione. Dashboard, wick intrabar, backup esterno e VPS restano fuori. Nessun merge o deploy.

## Terza review, 8 novembre 2026 — terminali contraddittori

Fonte: https://github.com/alexiptv82/SuperBot-Trading/pull/77#issuecomment-6720918518 sull'HEAD `34a4abe6ac80b5d65bfc12fbfdbe40d131124b4d`. ChatGPT conferma P0-E e P0-F. Resta un solo caso: `find_same_closure` accettava una coppia history/learning anche se nello stesso registro c'era un'altra chiusura terminale diversa.

Ora ogni riga terminale della stessa posizione deve avere la stessa impronta (`close_ms`, `why`, `net` e gli importi presenti). Una seconda riga con `close_ms` o netto diverso, nello storico, nel learning o in entrambi, rende la prova `discordant`: il claim non si archivia e il restart non dà la posizione per chiusa. Le righe non si cancellano. Due copie identiche dello stesso fill restano ammesse. I parziali non sono terminali. Test: `test_conflicting_terminal_closes_are_not_a_unique_proof`.

Prova locale, non CI: 66 passed, 0 failed sui tre file pytest già usati (29 RC80, 22 RC78, 15 exit-only). Nessuna Actions su questo branch.

## Review del 8 novembre 2026, 12:21 UTC — gruppo di claim

Fonte: https://github.com/alexiptv82/SuperBot-Trading/pull/77#issuecomment-6721423727 sull'HEAD `9bdb82cef48bc22df399ac2a5ac9b8481ad9305b`. La correzione sui terminali contraddittori è confermata. Regressione: `inspect_claims` faceva `return "resolved"` dentro il ciclo, quindi un file con BTC già provato ed ETH ancora aperto veniva archiviato per intero.

Ora il verdetto si accumula. Il gruppo è `resolved` solo se ogni claim lo è. Basta un `mismatch`, un `open` o un `unproven` per bloccare l'archivio, in qualunque ordine. Il test `test_a_claim_group_is_resolved_only_when_every_claim_is` controlla il file su disco: nei casi misti `paper_stop_protect.work` resta byte-identico e non compare un `reconciled-*.json`; solo il gruppo tutto provato viene archiviato, con tutti i simboli. Prova locale successiva sullo stesso comando: 67 passed, 0 failed (30 RC80, 22 RC78, 15 exit-only). Non è CI GitHub. Non è un deploy.
