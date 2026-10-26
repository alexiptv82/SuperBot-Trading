# Brain PAPER — riallineamento all'operatività scalp
Data: 26 ottobre 2026. Direttiva utente: operazioni brevi, rotazione del capitale, chiusura quando il profitto utile è disponibile; evitare posizioni mantenute per ore in attesa di obiettivi elevati.

## Riscontro sul codice attuale
Base letta: rule-pool 9e703b100c0c0b28dc0b4966855b9626071e2118; Brain runtime documentato 1f2edeb6182029adc96ba7218ad145a7503472a3.
- pilot.py: BAR=900000, ciclo e pianificazione degli ordini sulla successiva apertura 15m.
- portfolio.py: trade_type="medio"; ATR14(1h), budget di rischio indipendente dalla durata dell'operazione.
- prompt_builder.py: valutazione top-down 1d/4h e uscita anticipata attorno a 25–30% net margin ROI quando target improbabile.
Queste scelte non realizzano il comportamento scalp richiesto. Cambiare soltanto l'etichetta o il prompt non risolve cadenza dati/esecuzione/uscite.

## Direzione confermata dall'utente
- Il Brain deve cercare opportunità a breve durata e liberare capitale alla conclusione di ciascuna operazione.
- Privilegiare profitti netti utili senza attendere sistematicamente grandi estensioni o ore di permanenza.
- Riaprire quando esiste una nuova opportunità valida; non imporre una quota di operazioni giornaliere.
- LONG e SHORT restano eleggibili in base al mercato.
- Questa direttiva riguarda il Brain; nessuna modifica implicita di Hawk/Bull, capitale o rischio.

## Architettura proposta per rendere operativo l'obiettivo
1. Separare analisi AI e gestione rapida locale: prezzi freschi e controllo frequente di profitto, stop e tempo di permanenza; nessuna chiamata DeepSeek a ogni aggiornamento prezzo. Budget API esistenti conservati.
2. Aggiungere dati/candele brevi idonei allo scalp; il contesto macro resta informazione, evitando di trasformare un trade breve in una posizione lunga quando il mercato non conferma.
3. Definire una presa profitto basata sul netto atteso dopo commissioni, slippage e funding applicabile. Un floating lordo appena positivo non è necessariamente guadagno.
4. Definire una finestra temporale e una regola di uscita/rivalutazione per operazioni ferme o invalidate, anche se l'uscita comporta una perdita. Una perdita non va mantenuta indefinitamente aspettando che torni positiva.
5. Riesaminare i timeframe di ATR/stop e l'interazione tra take-profit breve, costi e R/R. Evitare di stringere stop arbitrariamente o aumentare leva per simulare attività scalp.
6. Persistenza/riavvio: gestione protettiva indipendente dalla disponibilità AI; prezzi mancanti/stale espliciti; nessun doppio ordine o doppia elaborazione.
7. PAPER realistico: esecuzione su prezzi osservabili dopo la decisione, niente uso di massimi/minimi futuri per certificare uscite favorevoli; journal di decisione, prezzo e costi.
8. Memoria PR#12: nuova identità di strategia/versione per episodi scalp. Il precedente Brain medio e i bot classici restano fonti storiche separate, senza cancellare o mescolare statistiche.
9. Dashboard: margine/leva/ROI (PR#13), durata del trade e motivo di uscita; in seguito statistiche di rotazione, costi per trade e profitto netto per periodo, non solo numero operazioni/win rate.

## Parametri ancora da definire, non autorizzati per inferenza
- Regola di rivalutazione/stagnazione e criteri di prosecuzione: la durata è adattiva, senza chiusura automatica a 5 o 15 minuti.
- Frequenza dei controlli locali, dei dati brevi e delle rivalutazioni AI entro budget.
- Soglia di profitto netto utile e protezione dal ritorno del profitto.
- Politica temporale/di uscita per trade senza sviluppo.
- Timeframe/multiplicatori stop e compatibilità con R/R.
- Qualsiasi nuova percentuale di rischio, margine, leva, numero slot o averaging.
Non assegnare numeri definitivi senza valutazione e confronto con l'utente. La richiesta di scalp non autorizza automaticamente maggiore rischio o una soglia di profitto specifica.

## Consegna e stato
Documento di riallineamento, non implementazione runtime. Conservare storico, posizioni, budget e memoria esistenti. Nessun reset, merge o deploy; nessuna chiusura forzata o riavvio. Prossimo passo: tradurre la durata adattiva e il profitto netto utile in criteri verificabili e implementare su ramo separato con test/review prima di un rilascio PAPER autorizzato.

## Precisazione utente: durata adattiva
L'utente chiarisce che Bull, più aggressivo, può operare per 1–5 minuti, 5–15 minuti o oltre quando ne vale la pena. L'obiettivo non è uno scalp necessariamente fulmineo né una permanenza di ore in attesa. Per il Brain questi intervalli sono riferimenti, non timer obbligatori o nuove impostazioni per Bull.

Criterio da implementare: continuare quando esistono ancora evidenze favorevoli e una ragione concreta per la prosecuzione; rivalutare e proteggere il profitto netto quando il movimento rallenta, si esaurisce o compare un'invalidazione. Il trascorrere del tempo da solo non impone la chiusura a 5/15 minuti, ma una posizione stagnante non deve diventare automaticamente un'operazione lunga. Stop e gestione delle perdite restano necessari: non attendere indefinitamente il ritorno in profitto. Ogni prosecuzione deve essere spiegabile nel journal. Le soglie numeriche di profitto, stallo e protezione non sono state assegnate dall'utente.

## Margine significativo e riferimento Bull — nuova precisazione utente
L'utente vuole che il nuovo Brain scalp utilizzi margini significativi su un conto PAPER di1000USD, simili aBull. Fonte verificata nella configurazione Bull corrente: guardrail_min_margin=150USD, max_margin_trade=350USD; leva minima guardrail10x, forzata15x quando interviene il relativo guardrail. Queste sono caratteristiche diBull, non un profilo già applicato o approvato automaticamente perBrain.

Brain attuale: max_margin_trade=100USD e rischio iniziale equity×1%×size_pct×conviction/100. Prima del riallineamento occorre definire esplicitamente come conciliare intervallo margini desiderato, leva e rischio allo stop. Alzare il solo cap può non aumentare la size perché la determina il budget di rischio; abbassare la leva per impegnare più margine a notional invariato non equivale ad aumentare l'aggressività richiesta. Non forzare un margine minimo restringendo artificialmente lo stop o scavalcando la liquidazione. Nessuna variazione numerica al rischio è stata applicata.

La dashboard margine/leva/esposizione/ROI è implementata inPR#13, ancora aperta su main alla verifica: non distribuita nell'app. Il refresh non può renderla visibile. Per il rilascio occorrono integrazione e deployapp separati dai bot, nel rispetto del precedente vincolo utente nessun deploy. Nessun intervento è stato avviato.
