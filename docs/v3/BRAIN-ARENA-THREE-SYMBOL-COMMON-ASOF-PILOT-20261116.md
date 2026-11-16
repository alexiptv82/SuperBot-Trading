# AI Arena — BTC historical warmup verified, 3-market same-asof pilot

**Data:** 16 novembre 2026. **Branch di ricerca:** `work/arena-three-market-shared-history-20261116`; nessuna modifica ai bot in esecuzione.

## Evidenza reale dell'utente, VPS 16:16

- `Ran 11 tests in 1.263s`; `OK` per `backend.v3.arena.test_frozen_market`.
- `ARENA_HISTORY SELFTEST=PASS_OFFLINE`.
- Storico completo richiesto Brain: `{'1m': 60, '15m': 2893, '1h': 733, '4h': 193}`.
- Storico storico pubblico BTCUSDT realmente verificato: `public_GETs=23`; `BTC_snapshot_sha256=5e305118b0ee096dbbfd561c752a95e405ac09c921afbbda8b306a69e97940a9`.
- `ARENA_HISTORY RESULT=FULL_BRAIN_WARMUP_BTC_VERIFIED_NO_DEPLOY`.
- `paid_ai_calls=0 orders=0 services_changed=0`. Nessun credito OpenRouter speso e nessuna API di trading.

Questa prova **non** dimostra che le AI abbiano già ricevuto dati; il modulo ha soltanto calcolato un hash dello storico BTC nel laboratorio.

## Nuovo lavoro (ancora da collaudare su VPS)

1. Generalizzato `deploy/scripts/arena-historical-warmup-20261116.py` per consentire un `symbol` dichiarato in `_fetch_frame` e in `_sample`, preservando il default BTC precedente. La GET HTTPS accetta solo ticker dal formato valido. Nessuna modifica al runner Brain.
2. Aggiunto `deploy/scripts/arena-shared-three-fullhistory-20261116.py`: **pilot a 3 mercati soltanto**, BTCUSDT, XAUUSDT (oro), XAGUSDT (argento). Fissa un unico `asof_ms` **prima della prima richiesta**; richiede a Bitget lo storico esatto necessario su 1m, 15m, 1h e 4h per tutti e tre; 23 GET previste a mercato, 69 totali, **75 massimo**, senza retry. Le candele incomplete non vengono fabricate o interpolate e invalidano l'intero snapshot.
3. Il risultato è un batch canonico `FrozenMarketBatch` con un solo hash SHA256; `for_provider(deepseek/qwen/minimax)` deve restituire **byte e hash identici**. Controllo solo locale, **nessuna AI viene chiamata** e lo snapshot non entra ancora nella pipeline di esecuzione.
4. `--selftest`: programma senza rete; endpoint storico finto per tre simboli, stesso `asof_ms`, 69 richieste simulate, 4 timeframe, hash comune, rifiuto di storia XAG incompleta e di una lista parziale. Questo nuovo test deve ancora essere eseguito sul checkout isolato.
5. `--pilot`: GET pubbliche HTTPS, accesso solo in lettura, senza secret, senza ordini, senza servizio restart e senza file persistenti. Un malfunzionamento della fonte è segnalato come `NOT_VERIFIED`, mai interpretato come permesso a tradare.

## Cosa significa un PASS

Solo se il test reale riporta `THREE_MARKET_FROZEN_HISTORY_VERIFIED_NO_DEPLOY`, abbiamo dimostrato che **BTC, oro e argento** dispongono delle quantità di candele richieste da Brain a un orario comune. Il passaggio successivo sarà estendere il meccanismo (con limiti HTTP più elevati da gestire con attenzione) a 25 mercati e calcolare *localmente* gli indicatori, anziché inviare migliaia di candele crude a Qwen/MiniMax/DeepSeek a pagamento.

**Ancora da completare**: categorie e identità native/wrapped, snapshot completo 25, parità input prompt, test trading PAPER triplo con risk engine/exit indipendenti, UI, backup VPS della strategia Falco SHORT prima di pausa, via libera esplicito dell'utente per ogni deploy. Toro e Brain DeepSeek corrente invariati.

Nessun merge, nessuna nuova run Arena e test comparativo 14 giorni **non iniziato**.
