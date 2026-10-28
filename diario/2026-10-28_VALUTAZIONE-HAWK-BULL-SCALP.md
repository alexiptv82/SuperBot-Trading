# Valutazione nuova direzione Hawk e Bull — 28 ottobre 2026, chat normale

Stato: valutazione e proposta progettuale registrata per continuità con Claude e ChatGPT Work. NON implementata, NON approvazione di merge/deploy/reset o variazione delle soglie operative. Tutto PAPER.

## Obiettivo espresso dal proprietario
Hawk e Bull (i due portafogli esistenti) devono diventare operativi su timeframe 1m/5m: ricerca continua, più ingressi e uscite durante la giornata quando ci sono setup, gestione contemporanea degli slot, close anticipati sul netto, reingresso anche in direzione opposta se un nuovo segnale lo giustifica. Prima priorità della valutazione PAPER: osservare *come* apre/chiude (segnale, simbolo, direzione, margine, leva, esposizione, stop, tempo, uscita, P&L netto), non dimostrare da subito un profitto. La frequenza è un obiettivo di comportamento; nessuna quota obbligatoria di operazioni, nessun ordine artificiale per riempire slot.

Design incollato dall'utente: universo top 30 per market cap CoinMarketCap, dati eseguibili dal suo exchange, contesto 15m/1h, setup 5m, trigger 1m, supporti/resistenze, notizie contestualizzate, AI su candidati, piano strutturato + controllo deterministico + esecutore rapido + UI di diagnosi e report. **L'exchange operativo del progetto è Bitget, non Bybit** (Bybit era solo esempio nel testo): Bitget supporta WS futures candle1m/candle5m e REST storico 1m/5m. Top30 va intersecata con USDT perpetual disponibili e sufficientemente liquidi; CMC come filtro/ranking, non feed dei prezzi eseguibili. Aggiornare la lista senza lookahead, congelare composizione storica per replay.

## Evidenze repo consultate il 28/10
- rule-pool HEAD c1a7c91924c92ff7a2a48988dfa0c3bda96aad48; runtime precedentemente verificati via job Work: classici dc16e0169932c3885908625ce5be321a33b09a0f, Brain V2 e0021488b47e8b245954a708b139bc4785a4b644. In questa verifica SOLO GitHub, non VPS live.
- backend/desk/cli.py a dc16e01: run_cycle e chiamate AI al ciclo di circa 15 minuti; la protezione dinamica _classic.manage viene invocata nel run_cycle. Config Hawk 10 slot e nuovi margini 100–250 USD; Bull 3 slot, 150–350 USD; min leverage 10x e limiti tier/kill già esistenti. Non cambiare tali valori automaticamente.
- backend/desk/classic_opportunities.py: combine di regole/AI, skip/veto per simbolo, log opportunity_cycle, manage con deadline24h ed estensione condizionata fino48h, profit lock netto dopo +1R. Una buona base di contabilità, NON un esecutore scalp 1m.
- backend/desk/deepseek_collab.py: Claude può opporre veto su proposte DeepSeek. Audit precedente nel diario: 3 candidati sopra soglia numerica per bot ma selezionati zero, causa veti AI; nessuna prova delle loro prestazioni ipotetiche.
- backend/desk/turbo_scalp/strategy.py e runner.py: prototipo shadow su barre 5m chiuse (EMA20/EMA50 rimbalzo simmetrico long/short), ingresso next bar, stop-first, fee+slippage, max3 posizioni e cooldown; NON agganciato ai portafogli operativi e senza rischio di conto completo. Riusare solo le parti valide, non distribuire direttamente.

## Architettura raccomandata, in sequenza
1. Scanner asincrono WS 1m/5m e ticker/book dove disponibili; clock/timestamp/freschezza, elenco valutazioni per tutti i mercati; segnale long/short da breakout, rimbalzi/retest e momentum con setup distinti. 15m/1h solo contesto, non divieto assoluto al controtrend scalp.
2. Rank di candidati e payload AI breve 3–5 mercati pertinenti; mai aspettare una analisi da 26 mercati da 78k token per eseguire un piano già valido. Sia long che short devono passare test simmetrici/specializzati; memoria di vecchie run non è veto globale contro una direzione.
3. AI emette piano condizionale con id, simbolo, direzione, trigger, stop, scadenza, invalidazione, durata, uscita, motivo e timestamp dati. Contraddizioni open/skip dello stesso simbolo rifiutate con diagnosi, non risolte in silenzio. Calcoli netti e sizing sono in codice, non testo AI. Ruolo veto Claude da rivedere come policy distinta (mai disabilitare controlli fisici).
4. Unico esecutore PAPER per portafoglio, controllo trigger e quote con loop rapido / eventi (obiettivo 1–5 s), expiry, prenotazione slot e margine anche per pending, idempotenza, stop e uscite senza richiamare l'AI. Non duplicare writer del portafoglio. Usare prezzi effettivamente osservati: no fill retroattivi sul massimo/minimo della candela.
5. Profit Manager netto frequente e orientato a minuti/ore: traiettoria del profitto, take/partial/hold basati sul rischio attuale e momentum; 25–30% ROI netto su margine iniziale preferenza non vincolo. Parziali contabilizzati, fee+slippage+funding/spread, stop senza aumento del rischio.
6. Report UI/debug per simbolo e portafoglio: feed, segnali proposti, passati/invalidati/vetati, scadenza piano, margine/leva/nozionale, tempo apertura-chiusura, motivi close, drawdown, P&L netto realizzato, uso slot e inattività per causa. Misurare la frequenza senza incentivare ingressi insensati.
7. Test offline stesso dataset, replay causale long/short per regime, shock di volatilità, stop/target stessa candela pessimista, costi realistici, dati stantii, funding, correlazione e budget. Comparazione A/B variante vs baseline prima del rilascio. Alla prima attivazione PAPER: backup+restore verificati, conservazione storici/run/memoria, no nuove istanze, deploy solo su OK esplicito separato.

## Proposta divisione del lavoro (non prenotazione attiva)
ChatGPT: scanner 1m/5m + contratto piano/trigger + profit manager net e test unitari, ramo isolato con owner dichiarato prima di scrivere. Claude: audit storico e simmetria long/short + framework replay/validazione avversariale e review rischio, su file e branch propri. DeepSeek: valutazione indipendente di setup/casi contrari, non arbitro di deployment. Evitare modifiche simultanee agli stessi file; scambiare risultati a checkpoint via diario.

## Regole
Nessun reset o perdita di posizioni, SQLite, Vault, storici o memoria. Non cambiare il portafoglio Brain indipendente. Nessun passaggio LIVE. Nessun deploy senza nuova autorizzazione. Mai promettere un certo numero di trade o profitto. Questo documento è un handoff di analisi, non codice eseguito.

AI: chatgpt (chat normale)
