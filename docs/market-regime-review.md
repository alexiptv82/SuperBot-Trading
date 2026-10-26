# Market Regime + Episode Memory — consegna per review

Base: rule-pool dbddc2403bfd5fd9c7444b97185ae60071f81ee5.
Solo proposta su work/market-regime-episode-memory. Nessun merge/deploy.

## Provenienza e limiti
Implementazione dal prompt dell'utente: il sorgente DeepSeek completo non era
allegato e non è presente nei file pertinenti di rule-pool. Non è possibile
certificare parità con tutti i suoi fallback o con la sua API originale.
Le perdite Bull e il ritardo di 2–5 ore sono segnalazioni dell'utente, non risultati
di un audit runtime effettuato in questa sessione.

## Consegna
- backend/desk/market_regime.py: OHLCV ndarray/list o DataFrame nominato;
  rilevazione price action 15m, momentum, volume, divergenza RSI 1h posizionale;
  ADX Wilder finito; 6 regimi + UNKNOWN neutro; lock e stato separato per simbolo.
- backend/desk/episode_memory.py: metodo EpisodeMemory.get_bias(path, hours=3),
  schema nativo close_ms/side/net/id/open_ms; lettura binaria senza scritture.
- docs/brain_regime_additions.py: SOLO aggiunte proposte a brain.py, non applicate.
  Import opzionali e try/except separati; wrapper context_rules_decisions mantiene
  le uscite sui punteggi originali e P2 only_manage; penalizza solo le aperture.
- backend/tests/test_market_regime_episode_memory.py: unittest, fixture sintetiche.

## Scelte da revisionare (non calibrazione)
Momentum 15m sulle ultime 5 chiusure >0,3%; breakout su 4 barre precedenti e
volume >=1,3x media precedente di 20 barre, oppure divergenza nella finestra 20h.
Bullish divergence: minimo LOW negli ultimi 5 bar, inferiore al LOW iniziale,
RSI in quel punto maggiore dell'RSI iniziale. Bearish speculare su HIGH.
L'RSI usa close; non vengono confrontati idxmin/idxmax con sé stessi.
REVERSING_UP penalizza SHORT a 0,30; REVERSING_DOWN penalizza LONG a 0,30.
Trend ADX>=25: lato contrario x0,70; volatilità std log-return 15m >2%: entrambi
x0,70; RANGING/UNKNOWN x1. Nessun moltiplicatore aumenta gli score.
Isteresi ordinaria: 2 nuove barre 15m consecutive; reversal immediato.
Richiamare sulla stessa barra non aumenta il conteggio; un gap resetta conferme.

Memory: almeno 3 identità di posizione con realizzi nella finestra, >=2/3 in
perdita e somma netta negativa => lato perdente x0,50. Parziali aggregati per
account/run/symbol/id/open_ms/side; duplicati eliminati. È memoria di realizzi
recenti, non rendimento totale lifetime della posizione. Record senza identità
completa vengono ignorati. Nessun filtro run corrente: finestra temporale come
richiesta. File per bot separati: NON usare storico combinato Hawk/Bull.

## Fallback
Dati mancanti, non finiti, disordinati, duplicati, OHLC incoerenti, barre aperte,
serie corte (<40) o vecchie => neutro. Timestamp apertura in millisecondi UTC,
passo esatto 1h/15m. Il caller può passare now_ms per replay deterministico.
File mancante/illeggibile/>64MiB o riga >64KiB => memoria neutra; righe JSON
invalide saltate; ultima riga incompleta ignorata; snapshot dimensione per evitare
di seguire append concorrenti. Future close_ms ignorate. Nessun log con dati.
Nessuna promessa di protezione quando un modulo fallisce: come richiesto,
il fallback ripristina il comportamento originario. Il reader va chiamato una
volta per ciclo, non per simbolo, per contenere I/O.

## Integrazione necessaria dopo review
brain.py NON riceve le candele. Aggiungere le sole funzioni proposte non attiva
la feature. In cli.py occorre conservare per simbolo le barre chiuse già raccolte
e quelle 1h ottenute da signals.resample(arr, H1), creare classifier e memory UNA
volta per istanza bot, poi passare quel mapping e DATA_DIR/trade_history.jsonl
al wrapper al posto delle chiamate rules_decisions, preservando only_manage.
Queste modifiche al runner NON sono applicate in questa consegna.

prepare_entry_readings può fornire copie per il prompt AI ma gli score non sono
un veto sull'AI: senza validazione aggiuntiva delle aperture AI, split e DCA, il
wrapper protegge solo il fallback a regole. Per la copertura di TUTTI i percorsi
serve una successiva patch cli/validazione con review e test end-to-end.
Non cambiare readings_map usato dalle posizioni aperte; non applicare i modifier
due volte. Leva/margine delle aperture a regole seguono lo score ridotto come
già previsto da rules_decisions; SL/TP e trade_type restano quelli originali.

## Validazione e prossimo passo
Test locali sintetici, Python 3.12.14, numpy 2.3.5, pandas 2.2.3; sintassi compatibile
Python 3.10 (nessuna esecuzione 3.10 verificata). Nessuna dipendenza runtime extra.
Prima del deploy: review Claude, verifica contro sorgente DeepSeek se disponibile,
cablaggio runner completo e replay fuori campione che confronti drawdown,
aperture evitate e opportunità perse. I test unitari non dimostrano redditività
né certificano questa proposta come pronta per la produzione.
