# SuperBot V3 — Prima revisione esterna ricevuta (Claude), 2026-11-02

Fonte allegata in chat: `SuperBot-Trading V3 — Revisione tecnica indipendente.pdf`, 25 pagine, datato 2026-11-02. Sintesi preliminare di ChatGPT; **NON** è un'approvazione finale e non autorizza deploy, merge, reset o riavvio. Seconda revisione esterna (Grok/altra AI) ancora attesa.

## Quadro della proposta di Claude
- Brain V3 non "AI completamente libera": DeepSeek classifica strategie validate o NO_TRADE, propone gestione delle posizioni dentro bande; motore di rischio deterministico calcola size e leva e applica limiti. Claude revisore su trigger con budget.
- Architettura a eventi: feed mercato → classificatore regime (direzione/volatilità, con isteresi) → catalogo versionato → AI → rischio → tre esecutori isolati → registro append-only → analisi/teaching, dashboard.
- Memoria a 5 livelli: L0 eventi, L1 episodi, L2 statistiche per regime, L3 ipotesi da testare, L4 strategie approvate; chiusure utente con motivo, ID, ricevuta, controfattuale e controllo della loro efficacia.
- Gemello Brain deterministico senza AI, controllo casuale e misure per regime/costi/rischio; protocollo di confronto pre-registrato.
- Capitale uguale: **1000 USDT PAPER per Falco, Toro e Brain**, conferma di decisione già adottata dall'utente. Gemello è solo comparator shadow, non quarto wallet attivo.
- Roadmap F0 conservazione, F1 registro/rischio, F2 esecutori e comandi per ID, F3 dashboard, F4 catalogo, F5 shadow Brain, F6 valutazione prospettica, F7 promozioni con OK.

## Problemi di rischio / verifica ChatGPT sul codice
`backend/desk/engine.py` su branch `rule-pool`: `Limits.max_margin_trade=400`, `max_leverage=45`, `sl_liq_frac=0.75`, `daily_stop=0.12`, `kill_equity=450`, `fee_bp_side=6`, `slip_bp_side=2`. `open()` a righe circa 176-184 limita margine/leva ma non dimensiona il lotto in base alla perdita a SL. Uno stop largo quanto il massimo consentito con margine 400 e leva 45 può teoricamente costare intorno a un quarto del capitale PAPER 1000, inclusi i costi simulati, nei simboli con tier appropriato: numero illustrativo, non risultato storico di trade. `halted()` ricalcola stop giorno dal valore corrente della equity; senza latch persistente, al recupero può riaprire nello stesso giorno. Funding nel `close()`: `funding_bp_8h_long=1` è addebitato solo per `pos.side==1`; gli SHORT restano senza costo/credito. Queste sono criticità reali per confronti LONG/SHORT e confronto V3.

`backend/director/brain_free/execution.py` ramo `work/brain-completion-20261031` usa invece transazioni funding con rate e mark per i due lati: conferma che esistono implementazioni da riusare selettivamente, non che siano già integrate nei classici.

## Criticità e correzioni all'analisi esterna
- Stato VPS nel PDF (p. 3, 24): **superato**. Abbiamo già eseguito autonomamente via GitHub Actions, **dopo** la rilevazione della fonte, stop completo di Falco, Toro, Brain Free, Turbo, AI Shadow, Sidecar, Pool, restart=no, app rimasta running. Esecuzione 41464111891 PASS, inventario indipendente 41465049997 PASS.
- Backup generale sette cartelle dei worker `/opt/superbot-v3-backups/20261102T144010Z/worker-data.tar.gz` SHA, estrazione, diff e integrità SQLite Brain/Pool PASS; **seconda copia esterna non ancora attestata**.
- Quota capitali PDF dubitativa 1000/2000: **già risolta** in favore di 1000/1000/1000 per la comparativa. La ripartenza non è autorizzata.
- `2/3 software presente`, `5-7 settimane`, `20-35 USD/mese`, sample size 300/360, soglie 30/100 interventi e 1,5% per trade/4% giornaliero sono **stime/proposte non validate**; nessuna cifra diventa requisito senza decisione.
- F4 iniziale: SHORT classici sono candidati, NON strategie già validate OOS. 100 trade positivi fuori campione non bastano da soli: considerare qualità dati, confidence bounds, multiple testing, condizioni differenti.
- Richiesta prioritaria utente: Brain che apprende adattivamente senza restare fisso. Distinguere adattamento dinamico e automatico a strategie **già validate** (consentito nella stessa run con regole pre-registrate) dalla promozione di **nuove ipotesi** (non consentita durante run comparativa).
- Manual actions: apertura/manual close/take profit sempre attribuiti all'operatore, non confusi con merito AI; la chiusura per riduzione rischio deve essere rapida e non bloccare su gating riservato alle nuove aperture. Controfattuali dipendono dalle ipotesi e non dimostrano causalità.
- Classici "invariati F1" non può giustificare rischio per trade potenziale elevato nel confronto V3; valutare due dataset separati: benchmark legacy storico e nuova comparativa omogenea con guardrail di rischio comuni, versioni etichettate.
- Tutte le modifiche restano non implementate finché non è completato il confronto con secondo rapporto e il piano finale è approvato dall'utente.

## Prossimi passi
1. Integrare la seconda revisione indipendente.
2. Check backup esterno cifrato, salvare file sorgente/review e audit di compatibilità.
3. Scrivere schema V3 finale, gate per rischi/dati, MVP app, test, scelta catalogo con prove.
4. Nessuna riattivazione AI prima di autorizzazione. Nessun reset del vecchio storico.
