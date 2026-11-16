# Brain AI Arena — 100/100 MTF e requisito reale di storico lungo (16/11/2026)

## Evidenza VPS dell'utente, screenshot 15:59
Script `deploy/scripts/arena-public-25-mtf-candles-20261116.py` completato:
- `ARENA_MTF closed_frame_checks=100/100`
- **25 mercati** (23 crypto selezionate provvisoriamente + XAUUSDT oro + XAGUSDT argento); per ciascuno `1m`, `15m`, `1H`, `4H` risultano `CLOSED_VERIFIED`.
- Nel log: 74 candele chiuse da 1m; 79 da 15m; 89 da 1H; 239 da 4H, per mercato.
- `orders=0 paid_ai_calls=0 services_changed=0`
- `RESULT=PUBLIC_DATA_PREVIEW_NOT_TRADE_APPROVED`.

**Limite scoperto verificando direttamente il codice di Brain**:
Il file `backend/v3/brain_market/market_view_params.json` contiene percentili ATR con `pct_window=2880` su 15m, `720` su 1h, `180` su 4h e `atr_n=14`. La funzione ufficiale `backend/v3/brain_market/view.py::min_bars` richiede rispettivamente **2893**, **733**, **193** candele chiuse e consecutive, oltre al requisito diagnostico **60** per 1m. Il test 100/100 certifica correttezza/continuità dei campioni brevi, **NON** completa predisposizione del modello con indicatori riscaldati. Con sole 79 candele 15m e 89 candele 1h il `build_market_view` ritornerebbe `insufficient_history`. NON attivare alcuna AI Arena su questi dati parziali.

## Nuovo lavoro isolato
Branch: `work/arena-frozen-snapshot-longhistory-20261116` dalla branch `work/arena-public-25-mtf-candles-20261116`.

- `backend/v3/arena/frozen_market.py`: **funzioni pure**, nessun network, file I/O, ordini, journal o servizi. Verifica ogni simbolo/TF, storico necessario, assenza gap/duplicati, validità OHLC, numeri finiti, timestamp causali, freschezza dell'ultima candela. Scarta la candela corrente ancora in formazione. Crea payload JSON canonico in byte e hash completo SHA-256; `for_provider("deepseek"|"qwen"|"minimax")` consegna **identici byte e hash**, senza alterazioni/provider injection.
- `backend/v3/arena/test_frozen_market.py`: 11 test unitari Python **eseguiti localmente** da ChatGPT nel container con esito `Ran 11 tests ... OK` (0.499 secondi). I file pubblicati sono stati confrontati tramite SHA Git blob e corrispondono esattamente ai file collaudati. Questi test non coprono provider reali o i servizi VPS.
- `deploy/scripts/arena-historical-warmup-20261116.py`: diagnostico **solo BTCUSDT** con API pubblica Bitget V2 `GET /api/v2/mix/market/history-candles`, pagine di massimo 190 candele richieste (`limit=200` e margine per il rounding degli estremi). Calcola i minimi interrogando la **configurazione Brain presente nel checkout**, tramite `load_default_params()` e `min_bars()`. Al massimo **25 GET pubblici**, 23 previsti, no retry, nessuna chiave API e nessuna operazione. `--selftest` inietta un'API finta in memoria: la logica di paginazione è stata collaudata offline con stub coerenti con i minimi del codice attuale; il test **del programma completo con gli import del checkout** e il `--sample` HTTP reale **non sono ancora stati eseguiti su VPS**.
- Anche con storico completo e digest valido, lo snapshot è **`PROVISIONAL_NOT_TRADE_APPROVED`**. Manca classificazione nativa completa, legame definitivo CoinGecko/Bitget, gestione funding, commissioni, rischio, apertura/uscite e collegamento diretto ai prompt AI. Lo snapshot completo dei 25 mercati verrà costruito solo dopo la verifica su un singolo BTC.

**Importante per i costi:** la conservazione dell'intero storico serve localmente a calcolare gli indicatori; **non va inviato tutto il raw OHLC alle API a pagamento**. Ogni AI riceverà un riepilogo identico degli indicatori e dei candidati; dataset grezzo rimane lato VPS/PAPER. La comparabilità riguarda lo snapshot di mercato; le memorie e la valutazione personalizzata di ciascun modello devono essere tracciate separatamente.

## Fonti API storiche
Bitget V2 historical candle endpoint: https://www.bitget.com/docs/catalog/classic-contract-market/classic-contract-market ; pagina massima **200 candele**, `startTime`/`endTime` e possibili arrotondamenti degli intervalli. Non fare scraping né richieste AI per creare lo storico. Il programma rifiuta un periodo mancante invece di inventare candele.

## Cosa non è cambiato
Nessun merge/deploy, nessun container o systemd modificato, nessuna modifica a Falco SHORT/Toro/Brain, nessun reset dei portafogli e nessun consumo OpenRouter. Qwen/MiniMax mantengono limiti di 2 USD ciascuna; saldo ricaricato 10 USD dichiarato dall'utente. Comparazione PAPER di 14 giorni non iniziata. Prima di qualsiasi futura pausa di Falco, backup coerente della strategia e del runtime VPS.
