# 12 novembre 2026 — Verifica Bitget sulla VPS e correzione candidata boundary/freschezza Brain

## Prova originale utente: Termius Singapore, 12/11/2026 04:55 Europe/Rome
L'utente ha eseguito lo script pinned su VPS `rc84-public-feed-diagnostic-readonly.py` tramite `curl`, hash Git object `184e5cd54410924c3ce433feb57fb93ebe7e8c9e`, successivamente `python3 -I`. Output screenshot **diretto utente**, non esito GitHub Actions:
- `RC84_FEED_UTC=2026-11-12T03:55:26.570877+00:00` e `RC84_FEED_COMPLETE=TRUE`, `RC84_FEED_NO_TRADING_OR_SECRET_ACCESS=PASS`.
- Contratti pubblici Bitget: `HTTP=200`, `code=00000`, `count=884`.
- BTCUSDT `maxLever=150`, `sizeMultiplier=0.0001`, `minTradeUSDT=5`, `symbolStatus=normal`; ETHUSDT `maxLever=150`; SOLUSDT `maxLever=100`; XRPUSDT=125; BNBUSDT/DOGEUSDT/ADAUSDT/LINKUSDT=75, tutti status normal.
- BTCUSDT timeframe 15m: `count=2999 contiguous_tail=2999 latest_age_candles=1 required_minimum=2893 first_error='' pages=15 can_warmup=false`.
- BTCUSDT 1H: `count=759 contiguous_tail=759 latest_age_candles=1 required_minimum=733` e 4H: `count=209 contiguous_tail=209 latest_age_candles=1 required_minimum=193`; entrambi `can_warmup=false` solo per freschezza.
- SOLUSDT 15m `count=1200 contiguous_tail=1200 latest_age=1 required_minimum=2893`, `pages=7`, quindi insufficiente. SOL 1H `count=0`, `first_error=http_0_code_HTTPError`, non si conosce ancora status HTTP preciso; SOL 4H `count=209 latest_age=1` con minimo193.
- Nessuna chiave o posizione PAPER toccata da questa lettura pubblica.

## Causa tecnica identificata
- Il parser contratti attivo sul codice pinned scarta `maxLever > 125`, quindi BTC e ETH a **150** erano rifiutati come `no_market_rules`, malgrado siano normali. La PR Draft #85 cambia massimo accettato per *metadata* a 200, **non** varia min20/max50 del Brain.
- Il runner usa `MarketViewParams.max_age_candles=1` per tutti i timeframe. `backend/v3/lab_tools/fetch_candles.py` usa un cursor storico `endTime=end_ms-1`: Bitget richiede l'allineamento dei timestamp a inizio timeframe e può arrotondare i limiti. Questo spiega `latest_age_candles=1` per BTC in tutte le granularità, e fa fallire il controllo freshness anche se ci sono abbastanza barre. Documentazione ufficiale: https://www.bitget.com/docs/catalog/classic-contract-market/classic-contract-market .
- SOL insufficienza storia non è risolta semplicemente con la barra più recente. La causa della history SOL 15m solo 1200, 1H HTTPError **non è ancora verificata**: non abbassare lookback (2893/733/193), non inventare dati.

## Lavoro su GitHub (NON in VPS)
- PR **Draft #85** https://github.com/alexiptv82/SuperBot-Trading/pull/85 aggiornato su `work/rc84-fix-classic-divergence-brain-market-20261111`, SHA HEAD `1753280763f9874a1bd002dafa1bb9b6cf5c181d`.
- Modifica staged `backend/v3/lab_tools/fetch_candles.py`: quando manca solo l'ultima candela chiusa, tenta una GET pubblica ulteriore con `startTime=end-2*step` e `endTime=end` **allineati**, recupera solo `ts=end-step` dopo la stessa validazione `_row`. Se il record non esiste, rimane missing/stale. Nessuna chiamata exchange privata.
- Test aggiunti `backend/tests/test_v3_lab_fetch_candles.py`: Bitget con floor(endTime) riprodotto sinteticamente e candela mancante autentica non interpolata. Test ancora NON ESEGUITI per GitHub Actions in coda.
- Patch classici nella stessa PR: non nuove entrate S25 duplicate senza opt-in, conservata gestione S25 vecchi trade; LONG/SHORT originali rimangono. Patch diagnostica sticky last_cycle in heartbeat Brain. **Nessun rilascio / reset effettuato.**
- Script aggiuntivo SOLO LETTURA disponibile su main pinned commit **`55c465bf458ecd0e8aa3a75fe64e7bbfd01ec039`**, path `deploy/scripts/rc84-bitget-live-vs-history-aligned-readonly.py`, blob Git SHA **`a51ee5ba737edb3e8f2c637577994eb369f1f04f`**. Confronta v2 `/history-candles` e v2 `/candles` usando limiti allineati per SOL 15m+1H e BTC 15m; max 18 chiamate per coppia, solo HTTP GET, nessun segreto, posizioni o servizi. Prossimo passo importante: farlo eseguire in Termius se GitHub Actions rimane in coda, poi fare fix feed compatibile e test.
- Gli Actions #43095712678 (pausa nuovi ingressi) e #43096514061 (probe dati Bitget) erano **ancora queued** all'ultimo controllo 12/11; il comando manuale `touch pause.flag` è stato proposto all'utente ma **non è noto** se sia stato eseguito. Non dichiarare pausa applicata senza evidenze.

## Vincoli invariati
- Solamente PAPER: Falco 1000, Toro 1000, Brain 2000, Fable OFF, nessun LIVE o ordine reale.
- Non resettare/stoppare servizi e non fare merge finché non esistono test offline veri, backup verificato e una diagnostica feed che spieghi SOL. Non promettere che tutti i bug siano eliminati.
- Verificare stato pause dei 3 wallet; se non ancora create e si vuole bloccare ingressi, usare comando idempotente già fornito. Preservare exit workers e le eventuali posizioni PAPER aperte fino a reset esplicito e backup.
