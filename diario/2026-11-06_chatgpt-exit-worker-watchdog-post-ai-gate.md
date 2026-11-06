# SuperBot V3 — Exit worker PAPER, watchdog e veto post-AI (ChatGPT, 6 novembre 2026)

**Stato:** codice e test locali, revisione richiesta a Claude, NESSUN merge, deploy, avvio, riavvio, alterazione dei dati o interazione VPS. PAPER esclusivo.

## Baseline e dipendenze
- PR #57 runner HEAD `e25c8dd8db88fd6994e3b7a75ecfdec5ff258421` e PR #61 dashboard HEAD `a9044b6759da327b44da04f9e7f51e211d44e03f`, entrambe open/draft non unite al momento della verifica.
- 385/385 file originali dello ZIP e25 byte-identici. `exit_service.py` è il prototipo separato P0 già consegnato, senza modifiche in questa fase.

## Nuovi componenti NON collegati
- `backend/v3/runner/exit_worker.py`: processo foreground opt-in per `run_manual_close` + `run_exit_monitor`; `--validate-only` controlla journal esistente, hash chain, run Brain, non crea DB. Avvio solo con `DESK_MODE=paper`, `--start-paper`, e dichiarazione `--legacy-exits-disabled`. Questa dichiarazione NON dimostra che il vecchio worker sia spento.
- `systemd_notify` su UNIX socket: READY/WATCHDOG emessi soltanto quando il tick uscite è healthy, supporto per supervisore esterno. Unit `.service.example` volutamente non installabile; path reali, ownership singola, restart e alert ancora da rivedere.
- `backend/v3/runner/post_ai_guard.py`: verifica dopo AI evento Brain collegato e immutabile (symbol/time/kind/status/rationale), exit lease, pause, mandato, budget, daily loss, feed fresco, divergenza prezzo e nuovo RiskQuote su journal corrente. È un VETO, non esegue trade e non modifica size; nuova protezione da stale open.
- 3 nuovi moduli test con controlli anti-corruzione, mancato journal/typo run, restart lease, dual-owner existing sidecar, rischio consumato durante AI, callback che falliscono e `sd_notify` finto su socket UNIX astratto.

## Test (verificati)
- Regresso mirato dei test runner, risk, events, exit + nuovi worker/gate: **1088 passed in 11.87s**, exit code 0.
- Test nuovi gate/worker da `/tmp`: **51 passed in 1.50s**, exit code 0.
- Full V3 ~6k NON eseguita in questa fase; nessun systemd reale, CI Jest, VPS, DeepSeek o Bitget live.

## P0 blocchi al rilascio
1. Owner unico delle uscite NON dimostrato tra vecchio e nuovo runner: vecchio processo non usa il lock sidecar. Serve stop vecchio worker, modifica del wiring, restart supervisionato, rollback sicuro e prova a due processi.
2. Il veto post-AI non è atomico con `execute_paper`: rimane TOCTOU se due writer possono aprire. Occorre single-writer OPEN o transazione comune; nessuna release prima di test multiprocesso.
3. Watchdog riavvia un processo in stallo, ma se feed fallisce ripetutamente non protegge da solo posizioni PAPER già aperte. Necessari test in ambiente simulato e monitoraggio/allerta.
4. Collegamento post-AI a `run_brain_cycle` NON fatto; soglia tempo 120s e divergenza prezzo max 0.5% sono proposte conservative, non un nuovo mandato operativo.

## Consegne conservate nella Libreria `/SuperBot-Trading`
- `SuperBot-V3-Exit-Worker-Watchdog-PostAI-Gate-2026-11-06.zip` SHA256 `e7c5192b408865a0ca6193c5ac12e2736da7e54ee54e989087f9bf0ca61d97af` (libfile_ada44985071881918aa8ff5e7896bf31).
- `RAPPORTO-SUPERBOT-V3-EXIT-WORKER-GATE-2026-11-06.md` SHA256 `bac193a78ca752d63f09e2cc11e4e159a3b61b3462934da02acd0f48faf81399` (libfile_d2484d7f29dc8191bf2d045eac2dbb0f).
- `SUPERBOT-V3-HANDOFF-CLAUDE-EXIT-WORKER-2026-11-06.md` SHA256 `9a17f01d0a0385c7d234401315a5cac6daeb85fecc0176159621b0c495da1bc8` (libfile_4512a61b2638819197b361a7ba0fd183).

**Prossimo step:** revisione Claude, branch di integrazione sicuro PR #57/#61 + S0/S1/S2, unit tests di crash/restart/cutover, quote+append atomica e prove di monitor sotto AI bloccata. Nessun merge/deploy o riavvio senza OK utente. Soglie 2% trade, 5% open, daily warn 35%, halt 50%, floor 450 USDT immutate.