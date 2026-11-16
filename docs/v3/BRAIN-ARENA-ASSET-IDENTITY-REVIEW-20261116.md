# AI Arena — controllo identità asset e risultato Top23 (16/11/2026)

## Evidenza reale VPS alle 15:30
Il preview pubblico CoinGecko/Bitget, su commit e48269b, ha completato `ARENA_CAP SELFTEST=PASS_OFFLINE` e restituito:
- `crypto_found=23/23`, `excluded_obvious_nonnative=11`, `contracts_unavailable_or_illiquid=6`
- `metals_reserved=XAUUSDT,XAGUSDT`, `tradable_or_approved=NO`, `RESULT=PROVISIONAL_LIST_CATEGORY_AND_CANDLES_PENDING`
- Ordini = 0, servizi invariati, consumo OpenRouter = 0.

Candidati esatti della preview 15:30, in ordine per market cap *al momento dello screenshot* (NON una whitelist definitiva):
BTC (rank 1), ETH (2), BNB (4), XRP (6), SOL (7), HYPE (10), ZEC (11), XMR (12), DOGE (13), LINK (17), ADA (18), XLM (20), BCH (23), NEAR (24), LTC (25), AVAX (27), UNI (29), SUI (31), GRAM (32), HBAR (35), SHIB (38), QNT (39), TAO (41).
I rank saltati includono stablecoin e strumenti che non soddisfacevano i filtri preliminari.

## Caso GRAM risolto, non eliminare automaticamente
`coin_id=the-open-network`, ticker `GRAM` è coerente: l'asset prima indicato come Toncoin (TON) è stato rinominato Gram (GRAM) dal giugno 2026. CoinGecko usa ancora lo stesso Coin ID storico e Bitget ha annunciato GRAMUSDT futures il 15 giugno 2026.
Fonti:
- https://www.coingecko.com/en/coins/gram
- https://www.bitget.com/support/articles/12560603885855
- https://www.sec.gov/Archives/edgar/data/1566610/000149315226037002/form10-q.htm

Questo caso chiarisce perché occorre usare identificativi univoci e controlli di rebranding; il ticker da solo non identifica univocamente un asset.

## Correzione isolata al selettore
Branch `work/arena-identity-provenance-gate-20261116`, file `deploy/scripts/arena-public-marketcap-preview-20261116.py`:
1. Nel batch CoinGecko, se due Coin ID differenti condividono lo stesso ticker, nessuno dei due è selezionato automaticamente. Conteggio `excluded_ambiguous_tickers`.
2. Ogni contratto Bitget deve avere `baseCoin` corrispondente al prefisso del simbolo USDT, oltre ai controlli già presenti su tipo perpetuo, status, bid/ask, volume, timestamp e leva.
3. I candidati mantengono `identity_status=SYMBOL_MATCH_ONLY_REVIEW_REQUIRED`. **Il controllo baseCoin non dimostra da solo che il ticker CoinGecko e il sottostante Bitget siano identici**: per il via libera servono categorie e identificativi verificati anche su cambi nome/migrazioni.
4. Aggiunti casi sintetici offline nel `--selftest` per collisioni di ticker CoinGecko e `baseCoin` Bitget discordante. **Questa nuova revisione non è ancora stata eseguita sulla VPS**.
5. Sempre al massimo 3 GET pubblici su CoinGecko + Bitget, niente chiavi, nessuna scrittura, nessun ordine, nessun servizio toccato.

Documentazione Bitget campi `baseCoin` e `quoteCoin`:
https://www.bitget.com/docs/catalog/classic-contract-market/classic-contract-market

## Limiti e prossimi passaggi
- La selezione resta `PROVISIONAL_REQUIRES_CATEGORY_AND_CANDLE_AUDIT`, `tradable_or_approved=false`. Verificare categorie native/wrapped/stablecoin/tokenized e mapping cross-source in un successivo adattatore, poi candele chiuse 1m/15m/1h/4h e funding/commissioni/slippage specifici.
- Nessun incremento automatico di frequenza API: shortlist comune alle tre AI, senza trade forzati. Verificare i 25 strumenti prima del primo avvio PAPER Arena.
- Conservare uscite anche se un simbolo scompare dalla classifica. Tutti i tre wallet inizieranno con 2.000 PAPER soltanto dopo test, backup Falco SHORT su VPS e autorizzazione alla messa in servizio.
- Falco, Toro e Brain operativi invariati; zero chiamate API AI da questa fase. Limiti chiavi OpenRouter Qwen e MiniMax ancora 2 USD ciascuna, saldo conto ricaricato 10 USD dichiarato dall'utente.
