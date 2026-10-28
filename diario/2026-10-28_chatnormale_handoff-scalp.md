# Passaggio ChatGPT Work → chat normale — 28 ottobre 2026

## Scopo
Ripresa dopo esaurimento temporaneo di Work, per richiesta utente: ripristinare un trading PAPER bidirezionale, frequente e basato su netto, ispirato al ritmo delle prime run profittevoli ma senza ripetere il bias short. Verifica esclusivamente repository, nessun controllo VPS contemporaneo e nessun intervento operativo.

## Fonti e stato verificati via GitHub
- Repo pubblico: alexiptv82/SuperBot-Trading. Ramo rule-pool al momento del controllo: c1a7c91924c92ff7a2a48988dfa0c3bda96aad48 (commit di audit, non runtime).
- Ramo diario: STATO.md e diario/SCALP-1M-5M-PIANO-2026-10-28.md, già registrato dall'ultima Work. Piano esplicitamente NON implementato.
- Ultimi runtime documentati dal postflight Work: Hawk/Bull dc16e0169932c3885908625ce5be321a33b09a0f; Brain Free V2 e0021488b47e8b245954a708b139bc4785a4b644. Questi sono snapshot storici verificati nei run del 28/10, NON uno status VPS in tempo reale.
- Il codice originale Turbo Scalp esiste su rule-pool: backend/desk/turbo_scalp/{strategy,runner,report,healthcheck}.py e backend/desk/test_turbo_scalp.py. È un simulatore shadow (applied=false) su barre chiuse 5m: EMA20/50 e rimbalzo simmetrici long/short, entry next bar, stop-first su intrabar ambiguo, fee/slippage, target 1.5R, massimo 3 trade. Non è un esecutore PAPER intraday collegato al Brain.
- Brain Free V2 è sul ramo separato work/brain-free-scalp-reframe-20261028: backend/director/brain_free/*. Questo ramo è DIVERGENTE rispetto a rule-pool, non trattarlo come fast-forward né fare merge automatico; su rule-pool la directory brain_free non compare. Il runtime Brain V2 ha protezioni locali a 5 secondi, ma le chiamate full/management sono più lente, e manca la catena scanner→piano condizionale→trigger veloce.
- Ramo storico work/brain-scalp-design fermo al 26/10: non usarlo come base senza riconciliare i cambi successivi.
- Unica PR aperta osservata: #16 (Brain: profit-first mandate and attributed Run #2 research context, rule-pool → main). Non confonderla con un nuovo implementativo scalp.

## Diagnosi da conservare
Work aveva verificato classici a cicli 15m e veti AI per simbolo che nell'ultimo ciclo rendevano selected vuoto; Brain full circa 78.6k input token, latenza 20–30s, copertura esplicita 4–5 assessment su 26. Non prova che gli ingressi esclusi sarebbero stati profittevoli. I benchmark $35–75/operazione e +$1000 delle prime run sono obiettivi di comportamento da analizzare su netto, non promesse. L'esperimento richiede replay causale e valutazione long/short separata.

## Proposta di divisione, NON ancora assegnazione attiva
- ChatGPT chat normale: proposta schema comune di piano condizionale, shortlist/scanner 1m/5m, dati compatti, modello netto/ROI e prototipo offline, esclusivamente su nuovo ramo isolato; nessun cambio al runtime di Hawk/Bull/Brain.
- Claude: audit storico indipendente Run 1/Run 2, differenza long/short e veti, replay causale con fee/slippage e test avversariali su stale quote, spike, stop/target, correlazione e copertura mercati. Usare branch e file non sovrapposti rispetto a ChatGPT; NON modificare backend/director/brain_free nel ramo di ChatGPT. Fare review incrociata del contratto, poi decidere integrazione.
- DeepSeek: idee e controesempi sul timing/mercato; non conferisce approvazione né bypass ai controlli.
- Nessuno dei due deve lavorare contemporaneamente sugli stessi componenti: prima di scrivere codice prenotare con owner/branch/base SHA su STATO.md e verificare stato GitHub; coordinare eventuale ripresa Work.

## Regole
Solo PAPER, mai toccare i dati o i conti esistenti, mai alterare/levarsi di torno i guardrail fisici. Nessun rilascio, riavvio, reset, modifica alle strategie/soglie/veti o merge verso branch operativo senza specifica approvazione dell'utente. Backup, restore, writer unico, nessun lookahead, misurare expectancy netta, drawdown, latenze, open/skip, distribuzione long/short, ROI su margine iniziale, gestione slot e costo per trade. Il diario è pubblico, non depositare segreti.

## Prossimo passo
Concordare la suddivisione con Claude e fissare un contratto condiviso leggibile; preparare prototipo e replay interamente isolati, confrontandoli sulla stessa storia/snapshot con le versioni PAPER correnti. La prima fase non giustifica deploy.
AI: chatgpt (chat normale)
