# LONG Shadow — REST pubblico Bitget per candele chiuse, modalità ricerca

## Motivazione

I frame WebSocket `kline update` non contengono nel laboratorio un flag di finalità affidabile. Non possono essere promossi a candele chiuse. Il motore congelato LONG V6.1.1 richiede ≥200 barre causali per 1m, 15m, 1H e 4H e scarta le barre troppo vecchie. Questa modifica aggiunge l'osservazione via GET pubblico, senza toccare il motore né le logiche SHORT.

## Fonte verificata (documentazione ufficiale)

Bitget Market Data: https://www.bitget.com/docs/catalog/market/market-data, GET `https://api.bitget.com/api/v3/market/candles`, `category=USDT-FUTURES`, `symbol=BTCUSDT|ETHUSDT`, `interval=1m|15m|1H|4H`, `type=market`, `limit=500`. Righe `[open_ts,open,high,low,close,volume_base,turnover]`, `requestTime` in millisecondi, `code='00000'` su successo. Endpoint dichiarato 20/s/IP; il nostro batch è 8 GET sequenziali ogni ≥15s. Nessun endpoint privato, chiave o autenticazione.

## Nuovi moduli in PR #26 DRAFT

- `backend/long_shadow_rest_closed.py`: `public_candles()` esegue esclusivamente il GET pubblico sopra (redirect rifiutati, timeout e limite byte). `parse_closed_response()` verifica schema, prezzi e volumi numerici finiti, ordinamento/duplicati/gap, almeno 200 candele chiuse, orologio `requestTime` ±15s e ricezione locale. Esclude anche se Bitget restituisce la candela corrente o una appena chiusa da meno di 2s. Attribuisce `available_at_ms` **alla ricezione locale**, non al timestamp storico. Importante: fine intervallo + grace non è una garanzia commerciale di immutabilità; rimane qualità di analisi e non prova di esecuzione.
- `RestClosedOverlay` aggiorna **atomicamente** 2 simboli × 4 TF = 8 serie; se una risposta è mancante/corrotta, invalida tutto il batch precedente, non conserva dati vecchi per nuovi segnali. Dopo cambio sessione WS invalida overlay; pretende nuova BBO `books1` fresca (≤2s) arrivata DOPO la ricezione REST. REST batch totale ≤30s, cache REST ≤75s, non accetta quote o frame futuri.
- `backend/long_shadow_observer_runner.py` aggiunge `--enable-rest-closed` **facoltativo**. Il flag richiede `--enable-advice` e un percorso del frozen V6.1.1 SHA-pinned. Nessuna richiesta REST col default. Fallimento di HTTP/validazione → status NOT_READY e `NO_TRADE`, senza ordini e senza fallback a un altro provider o ai segnali già scaduti.
- `backend/tests/test_long_shadow_rest_closed.py`: casi di riga 7-colonne, candle corrente/grace, gap, duplicati, nonfinite, server clock, quote e WS session, 8 serie atomiche, HTTP fallito/staleness, nessun ordine. Workflow CI esteso alla nuova suite.

## Esecuzione SOLO in laboratorio con collector pubblico esterno

Il nuovo runner non apre WS né avvia la raccolta; presuppone un collector pubblico che scrive i file `ws_raw_frames_*.jsonl`. Il wallet Brain attivo non è stato identificato su VPS; selezionare `--brain-source free` o `pilot` SOLO dopo attestazione runtime. Esempio **non eseguito** (directory non reali):

```bash
PYTHONPATH=backend python backend/long_shadow_observer_runner.py \
  --input-dir /research/collector-public \
  --output-dir /research/long-advice \
  --hawk-wallet /research/wallets/hawk \
  --bull-wallet /research/wallets/bull \
  --brain-wallet /research/wallets/brain \
  --brain-source free \
  --frozen-engine /research/frozen-long-v611/engine.py \
  --enable-advice --enable-rest-closed --seconds 60
```

La raccolta da 15 minuti già conclusa serve come verifica iniziale: NON usare quel vecchio archivio per fare segnali nuovi di trading. Nel laboratorio con dati storici e snapshot wallet fittizi, NO_TRADE è un esito legittimo. Non utilizzare LIVE/PAPER per nessuna procedura qui.

## Gate

- Il polling è un componente RESEARCH SOLO PREPARATO: non avviato qui né nel VPS, non installato come servizio H24.
- Non confondere `market close time` + grace con un `exchange finality acknowledgement` esplicito; verifiche reali su REST fresh+WS e wallet autentici ancora necessarie.
- No PR merge, deploy, trading, motore LONG congelato, SHORT classici, regole Brain, protezione assoluta 450 USDT invariati.
- PAPER_ELIGIBLE=NO, ECONOMIC_EVIDENCE=INSUFFICIENT, REAL_EXECUTION=UNVERIFIED.