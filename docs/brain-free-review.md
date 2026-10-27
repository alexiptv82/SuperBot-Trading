# Brain AI libero — candidato da revisionare, NON distribuito

Decisione operatore: 27 ottobre2026, 10slot, implementazione/testoffline approvati. Deploy richiede conferma separata. Nessun accessoVPS, stop, inizializzazione operativa, chiamata modello a pagamento o Telegram effettuati durante lo sviluppo.

## Differenza architetturale

Nuovo namespace `backend/director/brain_free/`, base129547ed. Non importa `desk`, `classical_adaptive` o `brain_pilot`; Docker copia solo il nuovo componente. Il codice preesistente resta byteidentico. App in ramo distinto da main56dc, nessun merge cross-history.

Account nuovo2000PAPER; 10slot e1600margine totale, cassa reale del simulatore per fee/margine. Leve massime45BTC/XAU/XAG,30ETH,25altcoin o limite inferiore del contratto. Nessun pertrade100/350, rischio1%, daily stop/kill450, RR, ATR, confidence, regime, orari, cooldown o fallbackdi aperture classico. Nessun Salvadanaio ereditato dal conto classico.

Quantità/tick/minimi contratto rispettati; size/leva ridotte quando fisicamente necessario, proposta e risultato registrati. TickSL arrotondato verso ingresso e annotato, nessun allargamento automatico per far passare l'ordine. DCA non contiene un limite strategico di numero: stop invariato se non esplicitamente proposto dall'AI. L'AI può proporre modifiche di stop anche più largo, purché valide e motivate: non viene ereditata una policy strategica nascosta. Parziali normalizzate ai lotti, eventuale chiusura integrale per residuo sotto minimo esplicitamente registrata.

## Decisione, dati e memoria

Ogni apertura è preceduta dal commit della motivazioneAI. Account+esecuzione+outbox nello stesso commitSQLite successivo, idrichiesta/eventi unici, unico writer con flock e CAS; crash non ricrea conto né riesegue la vecchia risposta. Ultimi10trade sono posizioni completate con parziali aggregate, costi/netto/esito/tesioriginale; nessuna riga inventata alla partenza. Seed Hawk/Bull etichettati sintetici/nonverificati, facoltativi, non regole.

Analisi completa15min, gestioneAI5min quando ci sono posizioni, supervisore5s indipendente daAPI/Telegram. Risposte vecchie o su esposizione cambiata non vengono applicate; si richiede una nuova valutazione. Nessuna apertura se quote>30s, barre1mchiuse>90s, gap irrisolto o vincoli fisici non validi. Gap del simbolo non ferma gli altri. Minuto contenente l'ingresso non usato retroattivamente; quote osservate proteggono subito. Barre successive causali con stopprima target se entrambi toccati: approssimazionePAPER dichiarata, non tickbacktest.

DominanzaCoinGecko, FearGreedAlternative.me con timestamp/attribuzione, calendarioForexFactory/FairEconomy e comunicatiFed: fonti opzionali, cache, missing/nonfinite diventa unavailable, nessun veto. Storico/news come dati, mai istruzioni. Mercati: gli effettivi26simboli della base129, non27 dichiarati approssimativamente nel brief.

## Costi, risorse e limiti di simulazione

DeepSeek `deepseek-flash`, thinking `low` e maxoutput8192 congelati nelconfig; prefisso istruzioni+seed stabile. Nessun cap monetario giornaliero/mensile/settimanale né pacing finanziario. Rate-limit/credito/APIerrore: allarme, retrytecnico con backoff30–300s, protezione locale continua, nessuna apertura a regole.

Ledger per requestid, cachehit/miss e completiontokens; reasoning compreso neglioutput, non fatturato duevolte. Tariffa ufficiale27/10, stima a consumo non fattura, riferimenti1.50giorno non cap/garanzia. Costi sconosciuti dopo timeout/crash preservati come incerti. Keyassente non genera finto addebito. Vecchio ledger non resettato/importato nel nuovo totale.

Fee0.06%/lato e slippage0.02% sono assunzioniPAPER versionate, non tariffe personali Bitget. Funding da tassi storici pubblici e prezzo1m stimato al settlement, non esatto markstorico; indisponibilità e gap segnalati. Liquidazione approssimata isolata con maintenancecontratto se disponibile o ipotesi0.5%, buffer0.75 e costi; non è il calcolo completo per tutti i tier Bitget né promessa di eseguibilità live. Il sistema è strettamente PAPER e non ha chiavi trading/ordineexchange.

ContestoAI non richiede EMA200/historyestesa per consentire trade; feature indisponibili non costruiscono filtri. Feed quotes indipendente dagli storici, cache per timeframe e simbolo per evitare raffiche di richieste. Spesa e token reali da misurare solo dopo un futuro rilascio autorizzato; non provata redditività o costo1.50.

## Report e dashboard

Telegram `[BRAIN]` su apertura/chiusura/parziale/DCA/livelli/pausa/APIerrore/feedstale; motivi, margine,leva,notional,qty e PnL/costi. Outbox persistente e retry: indisponibilitàTelegram non blocca conto. Consegna almeno-una-volta: un crash dopo invio primaACK può duplicare la notifica, non il trade.

Report22Europe/Rome con cash/equity/margine/floating, netto realizzato anche parziale, fee pagate anche su posizioni aperte, WR/PF/durate dei trade completati, LONG/SHORT, occupazione/inattività/rifiuti/spesaUTC+cumulata; confronto descrittivo con storiciPAPERclassici montatiRO. Report finale168h dall'avvio verificato, nessun autotuning o stop automatico dopo168h.

NuovoGETautenticato `/api/brain/free`, no-store, SQLiteRO con deadline; nessun reset/controllo tramiteAPI. Dashboard unico conto con size/leva/motivi, proposte vs eseguito, rifiuti fisici e contatore. Archivi dei tre profili precedenti consultabili separatamente, risultati non sommati. Salvadanaio/classici invariati.

## Futuro rilascio, non eseguito

1. Integrare/revisionare app e workflow dedicato su rispettivi rami solo dopo OKseparato. Trigger app `action=none/approved=no` in questo candidato.
2. App ufficiale con nuovo mount `/opt/superbot-brain-free:ro`, vecchi mount conservati; backupDB/restore/rollbackfrontend e app esistenti. Il nuovo reader non sostituisce i vecchi conti finché non esiste un account attivato.
3. Trigger worker disarmato `action=none/approved=no`. Futuroapplyrichiede `approved=yes`, SHA40worker/app, sorgente/checkoutimmutabili, runtimeprecedenti esatti/PAPER, rootnuovovuoto e sorgentibackup presenti, chiavehost verificata e provider disponibile (nessun saldo stampato).
4. Build prima di fermare; backupSQLiteAPI+restorefile e hash degli archivi prima del fermo, stop soli3Brain, snapshotfinali quiescenti di profili+ledger. Nessuna chiusura fittizia delle posizioni aperte archiviate.
5. Nuovo account solo con inizializzazione esplicita su directory vuota, worker singolo in standby; feed pronti e poi attivazione con hashconfig. Verifica rispostaAI e stessiID/StartedAt dei servizi non coinvolti, classici compresi.
6. Se fallisce: ferma nuovo worker, conserva dati del tentativo, ripartevano i vecchi container senza ripristinare/azzerare database. Flagretired evita presentare conto fallito come nuovo profilo attivo. Riprova su directory nonvuota bloccata fino a review, nessun reset automatico.

Codice/prompt/config versionati; avvio verificato, non data del piano, avvia le168ore. Hash cambiato o build diversa richiede migrazione esplicita per bug, non silenzioso adattamento della policy. Autoreimplementazione ChatGPT; nessuna reviewClaude indipendente dichiarata.

## Verifica

38 test offline motore/provider/store/rollout iniziali PASS;91test lettori app/legacy/Salvadanaio PASS. Build e React daCI dopo pubblicazione rami. Ultimi esiti/SHA e diff nel diario aggiornato; questa nota è il documento iniziale di revisione.
