# SuperBot V3 — RC82 terza revisione ChatGPT sul commit 1e64684 (08/11/2026)

## Fonte e SHA
- PR Draft [#79](https://github.com/alexiptv82/SuperBot-Trading/pull/79): branch `cursor/rc82-active-paper-stops-31c4` HEAD **`1e64684b9d813aad1ca1c7d344872333e451fd05`**, parent `bccfddfb98e6ee0213962951879426fc61ef6f13`, base PR #78 **`29eb75750625a8819cd2db71dc2459d164c3199c`** invariata. PR resta Draft, non mergeata.
- Allegati utente: `RAPPORTO-RC82-RESIDUI.md` e `HANDOFF-RC82-RESIDUI.md`. Test locali dichiarati da Grok in VM: 19 RC82, 84 `test_desk.py`, 67 exit-only/RC78/RC80 = **170 PASS, 0 FAIL finale**, 7 warning; due failure intermedi riprodotti/corretti e annotati da Grok. Non sono test GitHub CI (0 workflow PR sul commit) né rieseguiti autonomamente da ChatGPT.
- Review con dettagli nel [commento ChatGPT PR #79](https://github.com/alexiptv82/SuperBot-Trading/pull/79#issuecomment-6725619713).

## Esito code-review: due P0 residui richiesti CHIUSI
1. **Quote freshness:** `_quote_fresh()` richiede ultima barra OHLC coerente, timestamp non futuro, age dall'apertura <= 2x15m (30min). `operational_prices()` prende solo l'ultima riga, senza fallback a barra precedente; nuova apertura e DCA privi di prezzo valido non avvengono. `HB.new_exposure.blocked_symbols` segnala prezzi rifiutati e `stop_feed.alarm` rimane true; stop su barre storiche valide comunque elaborati. Test sintetici con barra 6h vecchia, futura con vecchia precedente, DCA e caso positivo fresco.
2. **DCA post-crash:** prima del secondo passaggio stop si salva su disco la posizione dopo DCA (`save_account` + `save_state`); se learning/history non provati, `close_not_durable` non salva il terminale. Riavvio dal conto post-DCA riproduce il netto, chiude una sola volta senza posizione fantasma. `_scan_close` rifiuta terminali discordanti (identità inclusiva `side`). Test verifica un solo record storico e un solo learning, stesso netto.
Le due correzioni sono confermate dalla lettura statica sullo SHA esatto. Non si certifica stop-loss reale, dati exchange, né nuova run.

## Nota integrativa P1 per RC84 prima del deploy
In `backend/desk/cli.py:apply_paper_protective_exits`, la chiamata `notify_close(sym,...)` PRECEDE `_prove_protective_close`, `save_account` e `save_state`: possibile notifica Telegram «CHIUSO» quando fallisce la prova dei registri o il commit e la posizione resta sul disco. Nel prossimo intervento isolato spostare la notifica dopo prova + commit (senza fare affidamento su Telegram per persistenza) e aggiungere test: close_not_durable=>nessun messaggio; retry OK=>un messaggio. È una correzione di sequenza notifications, non strategia.
Nota tecnica P2: il file di test `backend/tests/test_desk.py` sostituisce `cli.run_cycle` in fase di import per coordinare le fixture candele/orologio; collaudare che non influenzi altri test in una suite totale V3.

## Blocchi di release ancora aperti
- Stop attivi Falco/Toro: cadenzati 15min scalp / 30min medio + durata ciclo, non protezione continua. Wick della candela in cui si è aperta la posizione non tracciato. Da decidere modello exit PAPER adeguato allo scalp.
- RC81 dashboard/API mostra `exit_only_heartbeat` del monitor di manutenzione ma NON l'allarme `HB.stop_feed` del runner classico in esecuzione; RC84 deve integrare stato RUNNING distinto e warning fail-visible, senza promettere stop certificati.
- Brain RC83 audit 4.849 PASS offline dichiarato da Claude, nessun P0/P1 nel perimetro, ma exit-worker sidecar non installato/certificato su VPS; flag `--legacy-exits-disabled` non disabilita il vecchio owner: handover single-owner reale obbligatorio.
- Backup off-host verificato+restore, browser/app autenticata, piano integrato su commit pinned, preflight VPS sola lettura autorizzato e consenso puntuale prima del deploy, reset e riavvio PAPER con Falco/Toro 1.000 e Brain 2.000 USDT e storici preservati.

## Decisione
**RC82 CODE REVIEW PER DUE P0: PASS. PR #79: ANCORA DRAFT, NO MERGE, NO DEPLOY.** Il prossimo incremento è RC84 integrazione limitata (notifica post-commit + avvisi stop RUNNING), senza altre strategie, AI, rischio, size, leva o reset. Il diario canonico resta gestito da ChatGPT.

Nessuna operazione VPS, ordine reale, merge, deploy, restart o reset è stata eseguita in questa review.
