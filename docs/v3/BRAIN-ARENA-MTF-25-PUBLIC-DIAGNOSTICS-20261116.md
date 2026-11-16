# AI Arena — Candele pubbliche multi-timeframe, snapshot diagnostico (16/11/2026)

## Stato precedente verificato sulla VPS — screenshot 15:48
La correzione del test per ticker duplicati è stata eseguita con successo nel ramo `work/arena-identity-provenance-gate-20261116`:
- `ARENA_CAP crypto_found=23/23`, `excluded_ambiguous_tickers=0`.
- `excluded_obvious_nonnative=11`, `contracts_unavailable_or_illiquid=6`.
- Metalli riservati `XAUUSDT,XAGUSDT`.
- `tradable_or_approved=NO`, `RESULT=PROVISIONAL_LIST_CATEGORY_AND_CANDLES_PENDING`.
- Nessuna richiesta OpenRouter, nessun ordine, nessuna modifica ai servizi.

La lista è provvisoria. Non è stata verificata in modo esaustivo la classificazione stablecoin/wrapped/tokenized, né l'identità cross-source; il nome da solo non basta.

## Nuova funzione su ramo isolato
`work/arena-public-25-mtf-candles-20261116`

Script: `deploy/scripts/arena-public-25-mtf-candles-20261116.py`.
Il codice esegue prima la selezione aggiornata delle 23 criptovalute utilizzando il modulo sorella `arena-public-marketcap-preview-20261116.py` nello **stesso checkout GitHub**; XAUUSDT e XAGUSDT si aggiungono come due mercati fissi. Usa un'unica classifica CoinGecko ed esattamente due cataloghi Bitget per la selezione, poi verifica i timeframe di candele tramite GET pubblici Bitget V2.

Due modalità:
- `--selftest`: solo in memoria (senza chiavi né rete), prova 1m/15m/1H/4H con candele sintetiche, rifiuto di 4H insufficienti, gap, duplicati, future, OHLC errati, prezzi NaN, feed stale. Test **eseguito localmente da ChatGPT** il 16/11 con risultato `ARENA_MTF SELFTEST=PASS_OFFLINE` e `api_calls=0`, non ancora sulla VPS.
- `--sample`: 3 GET per selezionare universo + 4 timeframe per BTC, XAU e XAG, **massimo 15 GET**.
- `--full`: 3 GET per universo + 4 timeframe per ciascuno dei 25 strumenti, **massimo 103 GET**, con breve intervallo fra le richieste per rispettare i limiti Bitget. Non ha retry automatici su HTTP 429.
- I timeframe sono **`1m`, `15m`, `1H`, `4H`**, con esattamente il formato previsto da Bitget per futures V2. Richieste: 75,80,90,240 candele per frame; minimi rispettivamente 60,60,60,200 candele **chiuse e consecutive**. Per 4H avere 200 barre storiche è prerequisito per una EMA200 non inventata; non affermiamo che sia stata calcolata qui.
- Il programma usa solo i dati pubblici senza credenziali. Ogni frame ha codice `CLOSED_VERIFIED`, `INSUFFICIENT_HISTORY`, `CLOSED_BAR_GAPS`, `STALE_LAST_BAR` o errore controllato, e fingerprint SHA256 delle sole barre chiuse. La candela in formazione viene esclusa.
- Gli hash a 16 cifre hex sono **diagnostici**. Non costituiscono ancora uno snapshot immutabile completo condiviso dalle tre AI: in una fase futura il runner dovrà congelare e memorizzare per evento *tutte* le barre, timestamp, classificazioni, hash e contesto, garantendo input identici.
- `RESULT=PUBLIC_DATA_PREVIEW_NOT_TRADE_APPROVED` anche quando tutti i timeframe risultano verificati. Nessun output autorizza un trade.

## Evidenza tecnica esterna
Bitget V2 `GET /api/v2/mix/market/candles`, `productType=USDT-FUTURES`, intervalli `1m`, `15m`, `1H`, `4H` e limite massimo di 1000 barre per richiesta: https://www.bitget.com/docs/catalog/classic-contract-market/classic-contract-market

## Vincoli di rilascio
- Falco SHORT preservato; archivio GitHub esistente, backup VPS da fare prima di eventuale pausa. Toro e Brain DeepSeek corrente non modificati.
- Nuovi runner Qwen/MiniMax ancora non avviati; nessun reset, ordini o deploy. I 10 USD ricaricati sull'account OpenRouter non sono consumati da questo script; chiavi da 2 USD ciascuna.
- Restano da implementare controlli asset identity/categorie affidabili, funding/commissioni/slippage, candele causali nello stesso snapshot per tutte e tre, eventuale shortlist e gestione degli exit quando i simboli escono dalla classifica.
- Non è iniziato il confronto PAPER di 14 giorni.
