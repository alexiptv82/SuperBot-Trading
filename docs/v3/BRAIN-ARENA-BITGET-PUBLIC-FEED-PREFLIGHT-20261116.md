# SuperBot AI Arena — Primo controllo dati Bitget pubblico (16/11/2026)

**Evidenza utente:** alle 15:04 Europe/Rome, Termius ha completato sul checkout temporaneo `work/arena-model-to-brain-offline-integration-20261116`:
```text
Ran 24 tests in 0.056s
OK
```
Erano test **offline** (inclusi i nuovi 8 test di attraversamento Qwen/MiniMax → `BrainEngine._validate_decision`); nessun ordine, nessuna API a pagamento e nessuna modifica ai runner. Questo prova l'integrazione sintetica, **non** la correttezza dei feed Bitget né l'efficacia delle strategie.

## Nuovo ramo di laboratorio
`work/arena-public-market-feed-preflight-20261116` dalla branch offline precedente.

Aggiunto `deploy/scripts/arena-bitget-public-feed-preflight-20261116.py` per verificare i dati pubblici di **BTCUSDT**, **XAUUSDT (oro)** e **XAGUSDT (argento)**, prima di tentare l'universo di 25 strumenti. L'obiettivo finale resta 23 cripto per capitalizzazione + 2 metalli, *stessi snapshot* per DeepSeek/Qwen/MiniMax.

### Contratti e dati verificabili
La documentazione Bitget V2 contiene endpoint pubblici:
- `GET /api/v2/mix/market/contracts?productType=USDT-FUTURES`: `symbol`, `symbolType`, `symbolStatus`, `minLever`, `maxLever`.
- `GET /api/v2/mix/market/tickers?productType=USDT-FUTURES`: `ts`, `bidPr`, `askPr`, `quoteVolume`.
- `GET /api/v2/mix/market/candles?symbol=...&productType=USDT-FUTURES&granularity=15m&limit=64`: OHLC e timestamp in millisecondi.

Fonte: https://www.bitget.com/docs/catalog/classic-contract-market/classic-contract-market

Lo script usa **massimo 5 richieste GET pubbliche**, senza alcuna credenziale. Nessun OpenRouter, nessuna operazione PAPER o LIVE, nessun accesso ai journal, nessuna modifica systemd/Docker e nessun salvataggio su file. Emissione soltanto di una diagnosi stampata in Termius.

La singola coppia è **idonea come fonte dati in ricerca** solo se:
1. È presente nel catalogo `USDT-FUTURES`, perpetuo, status `normal` e leva 20× permessa; 20× è un vincolo di verifica, **non** un ordine.
2. Ha ticker non più vecchio di 3 minuti, bid/ask positivi, spread non oltre 30 basis point e 24h volume quote almeno 1 milione USDT (soglie **provvisorie** da calibrare).
3. Restituisce almeno 30 barre consecutive da 15 minuti, **chiuse**, senza gap, con OHLC e volumi validi, e l'ultima non è vecchia oltre 30 minuti. La candela corrente aperta viene esclusa. Hash SHA256 **troncato** delle ultime 30 barre, utile per confrontare gli snapshot futuri.

Se il contratto oro/argento è assente, non supporta 20× o è illiquido, appare `UNAVAILABLE/UNVERIFIED` anziché essere trattato automaticamente come tradeabile. La quota dei metalli resta riservata nell'universo di ricerca; nessuna sostituzione automatica con altre criptovalute.

### Comandi previsti per Termius
```bash
curl -fsSL https://raw.githubusercontent.com/alexiptv82/SuperBot-Trading/COMMIT_SHA/deploy/scripts/arena-bitget-public-feed-preflight-20261116.py -o /tmp/arena-public-feed.py
python3 -m py_compile /tmp/arena-public-feed.py
python3 /tmp/arena-public-feed.py --selftest
python3 /tmp/arena-public-feed.py --probe
```
Sostituire `COMMIT_SHA` con il commit effettivo **verificato** della branch quando si fornisce il comando all'utente. Il selftest è sintetico e non tocca la rete. Il probe fa esclusivamente dati di mercato pubblici e non necessita di root. L'analisi è diagnostica: non attiva alcun runner né autorizza nuovi simboli.

**Stato test**: script scritto, non ancora eseguito su VPS o localmente in Python; non riportare PASS fittizi. Revisione statica limitata ad allowlist endpoint, assenza richieste private/trading e validazione input.

### Prossimi passaggi
- Acquisire screenshot del diagnostico BTC/XAU/XAG con status candele e contratti reali.
- Dopo passaggio, estendere l'adattatore a tutti i 25: classifica `market_cap_rank` e categorie affidabili, esclusione stablecoin/wrapped/metalli tokenizzati, verifiche contratti e 1m/15m/1h/4h chiusi. CoinGecko documenta la classifica su `/coins/markets`: https://www.coingecko.com/learn/python-query-coingecko-api .
- Generare uno snapshot **identico, verificato e causalmente timestampato**, prima del consumo di credito AI.
- In fase successiva preparare 3 motori PAPER e 3 servizi uscite con run-id e journal distinti, T0 condiviso, capitale 2000 e protezione assoluta 450 USDT; prima backup reale della strategia e dati Falco SHORT sulla VPS. Nessun avvio attuale.
- Qwen/MiniMax chiavi da 2 USD ciascuna, ricarica conto 10 USD dichiarata dall'utente, spend solo dopo consenso e costi misurati. Nessuna richiesta AI a pagamento in questa fase.

**Vincoli:** nessun merge/deploy/pausa/reset; Falco SHORT e Toro intatti, Brain DeepSeek operativo invariato.
