# SuperBot-Trading V3 — RC81 collaudo finale PASS (offline), piano RC82 RUNNING PAPER

Data: 8 novembre 2026. Perimetro: sola lettura GitHub e documentazione. Non è un permesso di merge, deploy, riavvio, reset o ordini.

## Stato RC81 verificato
- PR #78 https://github.com/alexiptv82/SuperBot-Trading/pull/78, branch `cursor/rc81-stop-telemetry-ui-chatgpt-20261108`, HEAD esatto `29eb75750625a8819cd2db71dc2459d164c3199c`, base RC80 `50b75b9643680b9c758047d3890f3599b051f325`, Draft, unmerged.
- Grok riporta sullo SHA corrente, VM Cursor:
  * test Jest `ClassicStopNotice.test.js` 12 PASS, 0 FAIL;
  * Jest completo 13 suite, 99 PASS, 0 FAIL/skip, 4 warning deprecazione `act`;
  * build isolata `CI=true BUILD_PATH=/tmp/rc81-frontend-build-29eb757 npx --no-install react-scripts build` — compiled successfully;
  * caso `covered` ma `quote_coverage=false` rende `Copertura prezzi non dimostrata`, non annuncia prezzi recenti, mantiene diniego di stop certificato;
  * checkout pulito e SHA invariato. Nessuna modifica/merge/push/deploy/VPS di Grok.
- Il backend **NON è stato rieseguito sullo SHA corrente**. Nel collaudo precedente su SHA `c980489...` erano 82 pytest PASS, 86 Jest filtrati PASS e build riuscita. Diff successivo verso `29eb757...` limitato a componente frontend `ClassicStopNotice.js` e suo test. Non è CI, non collaudo su browser autenticato, non VPS né prova di stop/restart.
- Review GitHub finale https://github.com/alexiptv82/SuperBot-Trading/pull/78#issuecomment-6722966198 .

## Osservazione codice RUNNING (statico, senza test operativi)
Nel ramo antenato di RC81, `backend/desk/cli.py`:
- `fetch_candles(symbol,bar="15m")` legge candele Bitget e le ordina; in `run_cycle` popola `candles_map`.
- `get_prices` usa `arr[-1][4]` senza controllo esplicito timestamp della quotazione.
- In `run_cycle` il ciclo per posizioni aperte salta la protezione `if arr is None: continue`.
- `PaperAccount.on_bar` in `backend/desk/engine.py` (high/low delle candele 15m) può chiudere per liquidazione, SL, TP, in quest'ordine, per LONG/SHORT. È DISTINTO dal sidecar RC80 che opera solo con legacy spenti e `closed_1m_close_only`. Non attribuire le protezioni RC80 al runner attivo.
- `loop_step` scrive heartbeat periodico e `cycle_interval_s` varia il periodo secondo aperti/scalp/pausa; un heartbeat vivo non dimostra di per sé feed valido e posizione realmente sorvegliata.
- I punti sopra sono indizi da testare, non constatazione di perdite operative né collaudo del runtime.

## Prossimo incarico RC82 (Grok audit offline, NO codice/PR finché non concordato)
**Obiettivo:** attestare il comportamento reale e i limiti della gestione stop/TP/liquidazione dei classici con ciclo RUNNING usando dati sintetici, senza contattare Bitget/VPS/Claude. Non toccare strategie, leva, size, rischio, capitale, storico e componenti Brain.

1. Stabilire frequenza del controllo stop per scalp/medio e durata massima senza prezzi; distinguere heartbeat vivo da quotazioni fresche per ciascun simbolo.
2. Testare per LONG e SHORT la priorità liq > SL > TP, wick OHLC, open/close della candela e gap rispetto a livello di stop.
3. Verificare comportamento con no candles, array vecchi, timestamp futuro, barre non concluse, duplicati/out-of-order, dati malformed, feed parziali, exchange outage; evitare conclusioni basate su quotazioni inventate o cache.
4. Simulare apertura durante candela (t < open_ms), ordine delle chiamate AI e gestione stop, errore nel ciclo e riavvio, conservazione journal/storico/fondi.
5. Inventario protezione Brain attiva come gate separato: health `run_id`, runner exit-service, stop/TP/liq, fail-closed quando AI o prezzi mancanti. Non usare RC80 e non modificare Brain.
6. Consegna rapporto con SHA, comandi, PASS/FAIL, prove di gap, scenari non coperti, priorità P0/P1, piano di correzioni minime in branch isolato *solo dopo incarico*. Un bug provato deve essere supportato da un test sintetico riproducibile.

## Gate successivi
RC81 test offline: PASS limitato. Browser autenticato/tablet Android, stop RUNNING RC82, protezioni Brain, chiusura manuale Brain PR74, backup esterno & restore, nuova run PAPER (Falco=1000, Toro=1000, Brain=2000, storici conservati), verifiche autorizzate VPS: ANCORA APERTI.

**Nessun merge, deploy, restart, reset, API live, VPS o operazione di trading autorizzati da questa nota.**
