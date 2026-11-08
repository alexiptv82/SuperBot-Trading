# 08/11/2026 — RC82 revisione indipendente ChatGPT: REQUEST CHANGES P0

**Riferimento:** PR Draft #79 https://github.com/alexiptv82/SuperBot-Trading/pull/79, branch `cursor/rc82-active-paper-stops-31c4`, HEAD esatto `49b1a73f92904cac63c31c51ef2537254172d2ad`, base RC81 PR #78 `29eb75750625a8819cd2db71dc2459d164c3199c`. Solo `backend/desk/cli.py` modificato quale modulo runtime + test/diario/handoff. Nessun merge, deploy, reset, accesso VPS/riavvio. Nessuna CI GitHub associata allo SHA.

## Risultati consegnati da Grok
Report utente `RAPPORTO-RC82.md` + `HANDOFF-RC82.md`: test locale sintetico RC82 **11 PASS**; RC82+test_desk **95 PASS**, exit-only+RC78+RC80 **67 PASS** (7 warning), Python 3.12.3. Questi numeri sono riferiti da Grok, non ri-eseguiti indipendentemente da ChatGPT né verificati in GitHub Actions.

Modifiche staticamente confermate: `_bar_usable` rifiuta OHLC zero/impossibili, timestamp futuro non passa `on_bar`, `stop_feed` annota allarme `missing/stale/future/unusable` e `stop_certified=False`, applicazione stop prima di Claude/DCA + dopo i cambiamenti, deduplica history sul singolo close. Il modello RUNNING usa high/low 15m e mantiene cicli ~900s scalp / ~1800s medio. Claude ancora consultato con chiave/calendario, verificato con stub dall'autore.

## Due P0 individuati nella review del codice
**P0-A — registro economico/learning non fail-closed.** `apply_paper_protective_exits` effettua `record_close` e subito `save_state`, ma `append_trade_history` in `desk/brain.py` assorbe `Exception` senza segnalarlo e `learning.log_event` restituisce `False` senza sollevare; `record_close` ignora entrambi gli esiti. Una chiusura PAPER può quindi sparire dal conto senza history o senza learning. Al riavvio `_same_protective_close` vede solo la history e non recupera il learning mancante. Test RC82 copre solo save_state fallito dopo due registri scritti correttamente. Richiesto test con append fallito e log_event=False, fail-closed e proof di entrambi con identità/riconciliazione, storico intatto.

**P0-B — prezzo rifiutato per stop ancora alimenta aperture/DCA.** `get_prices` legge senza validazione `arr[-1][4]` prima di `apply_paper_protective_exits`, che filtra solo il percorso `on_bar` ma lascia `prices`/candles non validi. Decisioni `open_long/open_short/dca` usano `prices.get(sym)`: possibile apertura o DCA PAPER su close di candela future/invalid benché stop correttamente rifiutato. Test negativo e validazione prices per nuove aperture/DCA richiesti, mantenendo la capacità di chiudere stop storici validi.

Commento completo con istruzioni per Grok: https://github.com/alexiptv82/SuperBot-Trading/pull/79#issuecomment-6723555505. Sono osservazioni di code review statica basate sui sorgenti, non test live né prova che si sia verificato sulla VPS.

## Gate separati per nuova run
- RC81 mostra stato `exit_only_heartbeat` di MANUTENZIONE, non `stop_feed` del runner RUNNING. Dashboard deve visualizzare stato specifico RUNNING.
- Scalp PAPER attualmente esamina lo stop ogni 15 minuti + tempo fetch/ciclo; MEDIO ogni 30. Non è un ordine stop exchange garantito o protezione tick-by-tick. Politica intrabar/entry candle da dichiarare prima di ripartenza.
- Brain ha protezioni/run/exit-service proprie, da collaudare. Backup esterno non certificato, collaudo browser autentico e preflight VPS solo read-only su mandato separato.
- Nuova run indipendente Falco=1000/Toro=1000/Brain=2000 PAPER non autorizzata; storico preservato. **NO MERGE/DEPLOY/RESTART/RESET/VPS/ORDINI**.
