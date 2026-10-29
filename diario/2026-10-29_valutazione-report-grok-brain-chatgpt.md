# Valutazione report Grok — Brain, 29/10/2026

Fonte: report incollato dall'utente. Confronto con baseline Brain Scalp856a5ed095d4, engine.py/config.py/plans.py/scanner.py già verificati. Nessuna patch o nuova policy implementata.

## Esito

Riprende idee già presenti negli altri report (memoria pertinente, JSON compatto, escalation, ranking, gestione attiva) ma attribuisce al progetto interfacce/dati e carenze non verificati. Non adottare come istruzioni direttamente compatibili.

### 1. Rischio dinamico

Il percorso attuale dello scalp è PaperWallet/BrainPair -> _resize_for_budget -> apply condiviso, non il RiskManager.calculate_trade_params presunto. Il contratto Plan non contiene già confidence/ATR/regime. Non intervenire su risk manager dei classici, ormai esclusi dalla nuova direzione progettuale.

Se base_risk è calcolato usando il massimo RISK_PER_TRADE_PERCENT e poi moltiplicato fino a1,8, può superare quel medesimo massimo. Esempio50 ->90USDT, incompatibile col limite scalp50/trade. Applicare min(50,50*mult) evita il superamento ma elimina l'aumento di rischio quando il budget di base è già al cap. Il report non specifica una distinzione validata tra budget base e hard cap.

Confidence dichiarata non calibrata non deve autorizzare più capitale. Regime/ATR/DD e soglie0,5–1,8 sono nuove ipotesi da confrontare isolate. Unità DD incoerenti nel testo: la formula richiede0,25 per25%, non25; atr_pct invece è in punti percentuali. Da tipizzare/testare prima di qualunque integrazione. Clamp finale0,5 impedisce riduzioni ulteriori anche quando prodotto dei fattori è molto basso: non sostituisce daily stop o kill. Nessun vantaggio dimostrato della strategia da moltiplicare.

### 2. Prompt e memoria

Trattenere reason_summary breve, key_factors/evidenze, dati sintetici pertinenti e memoria con provenienza. Non includere sempre8–12trade dello stesso simbolo per principio: servono pertinenza/setup/regime, numerosità e recenza, bilanciamento successi/errori e disponibilità causale. Lo storico dei classici non è esperienza automaticamente trasferibile al nuovo wallet scalp: conti e namespace separati, archivi protetti immutati.

La scala confidence55–65/70–80/>85 è una convenzione non calibrazione. Filtri RR1,8 o WR45% sugli ultimi30 sono nuovi gate non validati. Win rate da solo non determina valore atteso; il caso ipotetico40%vittorie con payoff2:1 ha0,2R lordo medio prima dei costi. Agreement tra prompt o distribuzione confidence non dimostrano selezione migliore.

Output direction/confidence/stop_pct/target_pct non contiene trigger, scadenza, identità snapshot e invalidazione del contratto esistente: usare adattatore/versionamento, non sostituzione ciecamente compatibile. Mantenere1m/5m dello scalp; dati superiori come contesto da valutare.

### 3. Due livelli

La disgiunzione confidence55–78 OPPURE tierA OPPURE gestionecritica OPPURE regimechange può coprire gran parte dei candidati; non dimostra escalation8–15%. IlTierA non è una condizione di routing già implementata. Definire casi risolvibili con secondo parere e registrarne frequenza, costo e opportunità scadute.

Timeout con fallbackFlash non è automaticamente appropriato: seSol era richiesto per risolvere un conflitto, l'assenza del suo responso non risolve il conflitto. Nessuna nuova apertura per decisioni incompiute/scadute; protezioni esistenti indipendenti dalleAPI. Una sola decisione eseguibile, nuova validazione di quote, portafoglio e condizioni dopo la latenza.

Stima20–35USD/mese non verificata: mancano token input/cache/output/thinking, retry, numero simboli per chiamata e frequenza escalation misurata. Non implementare un flag DUAL_LEVEL come se esistesse già il provider; oggi lo scalp rimane offline senza chiamate ai modelli.

### 4. Scanner

Scanner attuale già possiede punteggio e ranking, ma copre solo breakout. L'asserzione troppi falsi negativi non è quantificata. Pesi/soglia45/ATR0,4–3,5/8–12candidati sono ipotesi, non calibrazione. abs(RSI-50) dà punti agli estremi senza assegnare da solo una direzione o uno specifico setup; trend/volume/SR possono condividere informazione. Tenere guardie tecniche obbligatorie distinte da ranking per setup e campione shadow degli esclusi. Recall calcolato solo sui trade storici scelti dalBrain non misura tutte le opportunità mancate.

### 5. Gestione aperti

La premessa mancaBE/trailing/scale-out è falsa per la baseline attuale: implementati e persistenti, compresi flag breakeven_set e scale_out_done. Non duplicare controller o macchina a stati.

Problema numerico rilevante: bufferBE0,05–0,08% non copre neppure le fee A/R del modello corrente (circa0,12%, fee_rate0,0006 per lato), prima di funding e slippage. Il BE attuale risolve il prezzo con contabilità e quantità residua: conservarlo, non sostituire con buffer fisso. R iniziale immutabile, scala parziali, residuo, normalizzazione e stop monotono richiedono stato persistente, non semplici attributi presunti.

PresetBE1R,trail1,2ATR,parziale30–40%a1,5–2R eTP3–4R sono varianti da provare usando meccanismi esistenti. Non sono miglioramenti provati e possono confliggere contake_net/giveback/target esistenti: occorre precedenza esplicita e confronto una variante alla volta. trade_history senza percorso prezzi/quote non basta a ricostruire uscite alternative o ordine intrabar; i540giorni15m classici non sostituiscono scalp1m/5m.

## Sintesi provvisoria dei tre report

- DeepSeek: spunti su routing/memoria/esperimenti; criticità rischio0,5% che riduce taglie, sqrt dichiarata conservativa, fallbackSol50% e gestione già presente.
- ChatGPT esterno: finora traccia più utilizzabile per audit sizing/schema/snapshot/causalità/routing, con rischio0,25% e preset uscite ancora da validare. Distingue esplicitamente progettazione da repository non letto.
- Grok: trattenere sintesi/evidenze e memoria pertinente; non adottare direttamente moltiplicatore rischio, stime costi, filtri hard o bufferBE sottocosto.

Solo valutazione e aggiornamento diario[skip ci]. Baseline856a5ed095d4 e PWA9251e6ddf2d6 invariati. Nessun codice/parametro, merge/deploy, VPS, classici/BrainFree, memoria o dati operativi modificati. Confronto aperto agli altri report.
AI: chatgpt
