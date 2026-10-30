# Pre-registrazione — replay V1.1 su candele vere Bitget, 30 ottobre 2026

**Questo documento è fissato PRIMA di scaricare qualunque dato dal runner.** Il replay è un esperimento osservativo, non una strategia, un backtest di profitti o un permesso di apertura. Non altera trading, scoring, capitali, indicatori, prompt o guardrail.

## Dataset e accesso

- Exchange: Bitget; prodotto **USDT-FUTURES**, prezzi OHLCV pubblici *trade market*; granularità **1m**.
- Endpoint **V2 historical-candles** pubblico, 200 barre massimo per richiesta, senza chiavi. Solo GitHub Actions runner, non VPS. Solo intervallo UTC chiuso `2026-10-16T00:00Z` fino a `2026-10-23T00:00Z`, 7 giorni.
- Simboli fissati: BTCUSDT, ETHUSDT, SOLUSDT, DOGEUSDT (4 simboli, circa 40.320 minuti in totale). Mai sostituire simboli risultati o date per renderli favorevoli. Se Bitget risponde con 401/403/429, dati vuoti, buchi, revisioni o meno del 95% di copertura per un simbolo, lo riportiamo come `data_unavailable`, **nessun risultato quantitativo per quel simbolo**. Nessun riempimento dei buchi e nessun fall-back su fake.
- Validazione: timestamp integer 60000-aligned, UTC, array OHLCV, positività, high/low, volume non negativo; escludere l'ultima candela non chiusa. Conteggio richieste e copertura nel report. Una risposta puo' includere barre fuori dalla finestra: filtrate e dichiarate; duplicati identici permessi, revisioni conflittuali rifiutate.

## Evento e etichette: non usare il futuro per produrre il segnale

- Il sensore analizza **soltanto candele chiuse**, usare la stessa funzione `safe_indicator` disponibile nel ramo codice con max ultimi 300 minuti. La logica è v1.1, EMA9/21, ATR14, swing confermati. Nessun boost LONG e nessun blocco SHORT.
- Segnale `TRANSITION_UP` valido solo se l'ultima fase confermata nei **180 minuti precedenti** era `BEARISH`; `TRANSITION_DOWN` valido solo se precedeva `BULLISH`. Non conteggiare ripetizioni identiche entro **120 minuti** (cooldown per simbolo/direzione). Nessuna soglia modificata sulla base dei risultati.
- Dal prezzo di **chiusura della candela che rende osservabile l'evento** si controllano SOLO per valutazione i successivi 90 minuti (non visibili al segnale): barriera favorevole +0,35% e sfavorevole -0,35%; per down invertire. Se tocca prima la favorevole => `favorable_first`, se prima la sfavorevole => `adverse_first`, se nessuna => `no_barrier`. Se entrambe sono toccate nella stessa candela usare chiusura a sfavore dell'evento per evitare ottimismo. Non usare prezzi eseguibili, commissioni, spread o leva: non è un test di P&L.
- Un evento entro gli ultimi 90 minuti del dataset senza orizzonte completo è `censored` e non entra nel rate. Report conteggi separati per UP/DOWN e per simbolo, prima-barriera, segnali per giorno, dati censurati, mediana minuti fino alla barriera favorevole e intervallo di incertezza Wilson 95%. Niente soglie di pass/fail finanziarie definite post hoc.
- Baseline non-trading: segnali di direzione casuale deterministica su ogni 120-esima candela valida (offset 45 minuti), non ottimizzati per simbolo e senza escludere periodi sfavorevoli. Mostrare come riferimento descrittivo non rigoroso perché contesto/periodo differiscono.

## Confronto di non regressione

- Congelare fingerprint SHA-256 dei dati concatenati per simbolo. Copiare JSON, CSV solo come artifact di GitHub Actions (accesso dal repo), non committare dati di mercato in repo pubblico.
- Eseguire inoltre comparazione su **100 timestamp deterministici** fra funzione `safe_indicator` e stato ottenuto da una ricostruzione completa sulle stesse candele (non confrontare mai due fonti sconosciute). Verificare il no-lookahead apponendo una candela futura valida: l'osservazione non deve mutare.
- Non copiare le API private/chiavi né lanciare ordini.
- Risultati in logs/Actions artifacts; aggiornare diario solo con **risultati davvero osservati**, non con stime o numeri generati.
