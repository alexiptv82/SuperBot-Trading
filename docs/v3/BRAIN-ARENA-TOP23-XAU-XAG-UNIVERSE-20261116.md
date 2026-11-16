# Brain AI Arena — Universo dinamico TOP 23 + Oro e Argento (16/11/2026)

**Decisione utente:** ampliare Brain per dargli scelta fra **25 mercati complessivi**, includendo esplicitamente **oro e argento**, senza riempire obbligatoriamente gli slot e senza toccare Falco SHORT. L'interpretazione adottata e' **23 criptovalute + XAUUSDT + XAGUSDT = 25 strumenti**. Se l'utente desiderera' 25 crypto *piu'* due metalli, la quota va decisa separatamente; questa fase segue la scelta "inclusi nei 25".

**Branch:** `work/brain-arena-top23-metals-universe-20261116`. **Solo ricerca PAPER offline**. Nessuna chiamata alle API a pagamento, nessuna modifica a `runner_config_brain2000_paper.json`, nessuna apertura, chiusura, deploy, merge o pausa bot. L'osservazione del mercato non genera di per se' ordini.

## Riscontro Bitget e selezione degli strumenti

- Bitget documenta ufficialmente futures USDT su **XAUUSDT** e **XAGUSDT**: https://www.bitget.com/support/articles/12560603885038.
- Stato attuale di singoli contratti **non verificato sulla VPS in questa fase**. Prima di considerarli tradabili, serve leggere il catalogo contratti `GET /api/v2/mix/market/contracts?productType=USDT-FUTURES` e volume/bid/ask da tickers: https://www.bitget.com/docs/catalog/classic-contract-market/classic-contract-market. Sono API di dati pubblici, non ordini.
- Classifica: fonte esterna da scegliere/validare (es. CoinGecko `/coins/markets` con `market_cap_rank`), conservando `coin_id`, timestamp, classifica e capitalizzazione al momento del controllo. La classifica non e' una lista statica "oggi = sempre".
- **Esclusioni** da quote crypto: stablecoin, wrapped e token di staking/reipotecati, oro/argento tokenizzati e classificazioni sconosciute, evitando doppioni del medesimo sottostante. CoinGecko ha una metodologia dedicata per token reipotecati, e una classifica per capitalizzazione che puo' cambiarne l'ordinamento: https://support.coingecko.com/articles/9423171520-upcoming-changes-to-market-cap-rankings-and-api-for-rehypothecated-tokens. Il codice richiede un'etichetta di classificazione **gia' verificata** da un adattatore dati da implementare; non ne inventa una.
- Se una crypto alta in classifica non ha il contratto Bitget, viene scartata per nuove aperture e si controlla la successiva fino ad arrivare a 23 eleggibili. I metalli **occupano due slot fissi**: se il contratto non e' valido, restano visibili come indisponibili, senza sostituirli con altre crypto.
- Un contratto e' un candidato PAPER solo se: USDT-FUTURES, perpetuo, `symbolStatus=normal`, liquidita' e spread verificati, leva richiesta consentita, e candele chiuse verificate. La soglia di ricerca **1 milione USDT volume quote nelle ultime 24h / 30 punti base spread** e' *provvisoria*: va calibrata fuori campione prima del runtime.

## Due livelli di analisi, per costi e maggiore scelta

1. **Sorveglianza pubblica 25/25:** dati di mercato, ranking, spread, liquidita', volatilita' e direzione. La selezione di 25 non implica 25 chiamate a Qwen/MiniMax e non e' una decisione OPEN.
2. **Analisi approfondita AI su shortlist dinamica:** prima proposta `slots=8`, configurabile da 1 a 25, basata soltanto su segnali tempestivi di candele chiuse, qualita' e liquidita'. L'algoritmo riserva fino a meta' shortlist ai LONG e meta' agli SHORT *se ce ne sono*: non forza trade, e recupera gli slot non utilizzati dall'altra direzione.
3. La **stessa shortlist e lo stesso snapshot** vanno inviati a tutte e tre le AI per un confronto corretto. In una fase futura si puo' proporre un singolo riepilogo batch dei 25 mercati a ciascuna AI, per rendere la scelta finale piu' libera senza 25 chiamate per ciclo; **il batch AI non e' implementato in questo ramo**.
4. Ogni modello puo' sempre restituire `NO_TRADE`. Il numero di posizioni aperte rimane determinato da rischio, margine, fondi e disponibilita' degli slot, non dal numero dei 25 mercati.

**Protezione cruciale:** se una crypto esce dalla top 23 per market cap mentre e' gia' aperto un trade, la posizione **rimane nell'insieme `exit_monitor_symbols`** anche se non figura piu' nei nuovi candidati; nessuna nuova apertura duplicata sullo stesso simbolo. Il cambio ranking non puo' interrompere stop, monitor e chiusure. Il futuro runner dovra' unire quest'insieme all'exit service esistente e verificare questa proprieta' durante test di failure/recovery.

## Codice e test

- `backend/v3/arena/universe.py`: funzioni pure `build_universe` e `pick_ai_shortlist`, classi immutabili `RankedAsset`, `FuturesContract`, `SignalScreen`, `UniverseSnapshot`; nessun import di trading, rete o journaling; `mode=PAPER_OFFLINE_READONLY`.
- `backend/v3/arena/test_universe.py`: **17 test offline** sintetici per 23+2, stablecoin/wrapped, rank duplicati o vecchi, liquidi, leva, metalli non disponibili, shortlist 8 o 12, LONG/SHORT bilanciati, NO_TRADE, dati vecchi, posizioni aperte uscite dai primi 23. **Test scritti, ma non ancora eseguiti in CI o sulla VPS.**
- Il codice non e' ancora cablato al runner e non ha un adattatore reale CoinGecko/Bitget: non e' stato verificato l'effettivo elenco corrente delle 23 crypto.
- Tutte le righe di input devono essere fornite da fonti affidabili con timestamp e classificazione; dati invalidi o mancanti chiudono l'accesso al trading, non vengono approssimati in silenzio.

## Fase di integrazione prima del test di 14 giorni

A. Implementare recupero **read-only** classifica e categorie CoinGecko e catalogo/quote Bitget, aggiungere controllo di 1m/15m/1h/4h chiusi, snapshot verificabile per data e hash.
B. Condividere identici snapshot tra DeepSeek, Qwen e MiniMax, osservare i 25, creare shortlist 8 (o valore successivamente approvato), eseguire test con casi LONG/SHORT e varianti di mercato.
C. Verificare costo per analisi approfondita e saldo **account OpenRouter 0,00 USD** confermato dall'utente alle 12:46; i 2 USD per chiave sono limiti di utilizzo e non saldo. Nessun acquisto o avvio a pagamento prima di conferma.
D. Verificare che i 3 servizi uscite PAPER possano mantenere e chiudere posizioni su simboli rimossi dalla classifica, mantenendo protezione 450 USDT e monitor stabile.
E. Solo dopo test, backup VPS di Falco SHORT, readiness per le tre run da 2.000 USDT e autorizzazione esplicita, programmare T0 del confronto di 14 giorni.

Nessuna modifica a Falco/Toro/Brain V3 operativo; l'archivio GitHub Falco e' `archive/falco-short-before-ai-arena-20261116`, ma manca ancora il backup coerente del runtime VPS.
