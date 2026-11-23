# 2026-11-23 — Priorità strategica: trattenere profitti, non inseguire target

## Contesto riportato dal proprietario
- Nei test passati Falco, Toro e alcuni Brain, in particolare DeepSeek, hanno prodotto fasi con profitti importanti, ma successivamente li hanno spesso restituiti al mercato. Falco/Toro hanno avuto anche problemi di LONG. Il proprietario vuole preservare più PnL, evitare aperture compulsive e imparare ad accettare giornate già molto redditizie.
- Sogno/range illustrativo: circa +250–500 USDT/giorno per Brain 2.000 USDT, non una quota obbligatoria né una promessa. Dopo profitti consistenti il bot deve rallentare, valutare operazioni solo davvero valide e saper attendere la sessione successiva, senza chiusura automatica a mezzanotte. Attività H24 per MONITOR e uscite; aperture selettive.
- Non assumere che esista un edge dimostrato dai resoconti qualitativi: misurare PnL realizzato netto, unrealized, picco sessione, giveback, entrate successive e reingressi, fees/AI.

## Fonte GIÀ ESISTENTE da RIUSARE — NON inventare un Guardian nuovo
- `docs/v3/BRAIN-UNICO-SMART-PROFIT-GUARDIAN-PROPOSTA-20261119.md`: analisi e proposta di laboratorio, non deployment. Già suggerisce floor mobile tipo CPPI in percentuale/equity mark-to-market stressata, stato NORMAL/SELECTIVE/PROTECTED/LOCKED, limiter del rischio nuove aperture, anti-reingresso per thesis_id, gate indipendente dall'LLM, niente eccezioni iniziali senza EV validato, sessioni Europe/Rome con reset proposto alle 08:00, nessuna chiusura forzata.
- `ops/brain-unico/guardian/sim_policies.py` e `e0_measure.py`: test sintetici e strumenti E0 per verificare se le aperture dopo alti profitti / il 3° reingresso hanno expectancy peggiore; i numeri sintetici non dimostrano rendimento reale.
- `backend/v3/runner/thesis.py`: ReentryPolicy oggi default observe, non blocca. Attivazione enforce richiede evidenza/mandato e test.
- `backend/v3/runner/daily_loss.py`: limite perdite già implementato e controllato, da non duplicare. La gestione profitti non deve bypassare perdita giornaliera, floor equity o guard in esecuzione.
- `claude/falco-evoluto-20261123` commit a6661a0d: uscite protettive per singola posizione già preparate su branch isolato, non installate. Manca la politica di portafoglio sui nuovi ingressi.

## Proposta operativa per Claude: guard comune, istanze indipendenti Falco / Brain
- Stati derivati dal budget al floor, con attivazione dopo una soglia di profitto (da comparare su dati PAPER, NON fissare arbitrariamente). Floor mobile monotono dopo attivazione: baseline sessione + 75% del picco utile (giveback massimo obiettivo 25% del profitto maturato, NON garanzia per posizioni esistenti, gap/slippage). Ogni nuovo rischio usa il minimo fra tetti precedenti percentuali (4% equity/trade, 20% margine/trade, 10% equity rischio aperto), budget residuo del floor e altri limiti. Ridurre size/nuovi ingressi automaticamente, nessun obbligo di usare 4 slot.
- Indicazioni user-facing: per Brain 2.000 USDT, 250–500 equivalgono al 12.5–25% di ritorno al giorno; per Falco 1.000 equivalgono al 25–50%. Sono rendimenti eccezionalmente elevati e NON target garantiti, NON usare 250/500 come obiettivo che spinge il bot a rischiare di più.
- Dopo picco notevole: SELECTIVE/PROTECTED con solo opportunità che superino **gate oggettivi** (filtro trend/regime, RR netto, dati freschi, non stesso thesis/reentry, rischio extra sotto budget); in LOCKED nessuna nuova apertura né eccezioni AI discrezionali fino a reset o sblocco policy. Il semplice confidence score AI non è prova di edge.
- Proteggere PnL ed equity per ogni run, separare contabilità realizzato/netto, MTM e spesa AI; no duplicazione fra sessioni e posizioni carry-over; log di motivazione per ogni block, snapshot stato in journal/dashboard; usare session_key Europe/Rome e test DST (prima opzione 08:00 da proposta 19/11), no chiusure trade per reset.
- Anti-reingresso: misurare EV/tempi dal TP o SL e stato tesi, valutare enforce solo se la ricognizione E0 sui dati effettivi lo supporta. Mai disattivare monitor uscite o chiedere LLM quando LOCKED.
- Una regola di profit lock non crea un edge; misura se gli ingressi successivi sono peggiori. Comparare baseline vs floor + filtro reentry in replay/shadow e poi PAPER, niente ottimizzazione sui 3 giorni Arena.

## Processo
- Nessuna autorizzazione implicita a cambiare produzione o a riavviare Falco/Brain: solo sviluppo sul branch isolato, test, report; eventuale deploy con OK esplicito.
- Stato di pausa Brain RC1 non attestato da account root secondo ultimo report Claude. Chiedere verifica live tramite modalità admin autorizzata; non proclamare 'pausato' senza prova.