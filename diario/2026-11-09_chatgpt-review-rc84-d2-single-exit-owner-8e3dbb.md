# SuperBot V3 — ChatGPT review D2 ownership Brain, RC84 SHA 8e3dbb (09/11/2026)

## GitHub e fonte di evidenza
- PR #80 Draft, head esatto `8e3dbb9c65b41dc37395081b8771e315d3f4365c`, base PR #79 RC82 `1e64684b9d813aad1ca1c7d344872333e451fd05`, non mergeata.
- Commit codice/test/template `fcaa2758220e5a42a5d2ba8419424ab898d85d2d`, ultimo commit documenta handoff `docs/v3/RC84-P1-TELEGRAM-CLAUDE-HANDOFF-20261108.md`.
- [Review GitHub ChatGPT](https://github.com/alexiptv82/SuperBot-Trading/pull/80#issuecomment-6744890508).
- ChatGPT ha verificato diff e file `backend/v3/runner/{wiring.py,runner.py,exit_worker.py,exit_service.py,legacy_exit_fence.py}`, template `docs/v3/brain-paper-systemd/`, metadata e assenza workflow CI GitHub legato allo SHA. Non ha eseguito test né toccato VPS.

## D2 — PASS limitato ai processi Brain aggiornati, non deploy-ready
- `wiring.main` in legacy acquisisce `LegacyExitFence` su `.exit_service.lock` prima di costruire runner; stesso `flock` posseduto dall'ExitService worker, tenuto per tutta la vita, rifiuta avvio concorrente exit code 3. Sidecar runner non prende questo lock e deve passare il gate exit-service healthy per aprire.
- Worker supporta attesa lease bounded `--wait-lease-s` e rifiuto busy con code 3. Heartbeat runner contiene ora `exit_mode`, attese test aggiornate.
- `foreign_exit_owner` controlla heartbeat senza `exit_mode` recente <45 minuti, segna stato `degraded` e rifiuta worker al startup, ma **NON** garantisce esclusione dei processi legacy NON aggiornati che ignorano lease (es. heartbeat stantio, processi bloccati, riavvio). Migrazione reale Fase A: aggiornamento runner legacy e prova lock; Fase B: sidecar quando il runner legacy è stato fermato, con verifica owner. Nessuna Fase A/B eseguita.
- Sull'handover il kernel rende esclusivi i due owner aggiornati, ma può esistere intervallo senza protezione fino al tick sano; test mostra assenza di overlap, NON stop monitor senza interruzioni. Processo runner sidecar duplicato non escluso dal lock exit owner: richiede supervisore/guard sul deployment, se necessario test aggiuntivi.
- Template `docs/v3/brain-paper-systemd/README.md`, worker notify/watchdog e runner sidecar BindsTo/After presenti, sono **artefatti NON installati**. `systemd-analyze verify` dichiarato passato da Claude con segnaposto fittizi, non prova servizio esistente né compatibilità VPS.

## Test da report Claude, non test ChatGPT
- 21 nuovi test con processi reali indipendenti Python 3.11 (ripetuti 3 volte, 21/21), con lock concorrente, SIGKILL, riavvio, manual close una volta, fail-closed, unpatched heartbeat.
- Suite interessate 298/298 PASS.
- Completa backend Python 3.11: **6.881 PASS / 34 FAIL / 3 xfail**, stessi 34 fail di baseline D1 `c6082df`; NON full suite verde.
- Frontend invariato: **124/124 Jest e build PASS attestati sul precedente SHA D1**, non rieseguiti su questo commit.
- Nessun workflow GitHub Actions attivato su HEAD.

## Decisione e prossima fase
- **D2 accepted a livello code review per processi aggiornati**; l'audit di sicurezza release rimane **NO-GO** finché una fase di migrazione su VPS autorizzata non dimostra che tutti i legacy writer vecchi sono spenti. Nessuna necessità di refactoring architetturale ulteriore senza nuovo difetto riproducibile.
- Prossimo incarico consigliato Claude **Sonnet 5.5**: QA Python 3.11 e CI per risolvere/stabilizzare i 34 fallimenti senza modificare trading, AI, portafogli, cash, ordini; fixture F3 20 fail, contaminazione `os.chdir` import-time in auth/profiles 2 fail, clock live_view, messaggio desk_view, hash S25 valutato, 9 test_superbot segregati con marker/fixture di integrazione e mai spacciati per PASS; pipeline CI senza `[skip ci]`, output/test proof e versioni pinned.
- Restano D1 visibilità già approvata in code review ma non collaudata browser/Android; nota heartbeat-state divergenza fail-visible; PR #76/main da includere/escludere esplicitamente nella RC unica, staging workflow con password bootstrap statica pubblica (non riportarla, audit/rotazione se attivo previa autorizzazione), backup off-host+restore, preflight VPS READ-ONLY previa approvazione, Brain runner legacy migration A→B, stop classici OHLC 15m periodici non continui, nuova run PAPER Falco/Toro 1000 e Brain 2000 solo con consenso espresso e storico preservato.

**Nessun merge, deploy, VPS, restart, reset o ordine.**
