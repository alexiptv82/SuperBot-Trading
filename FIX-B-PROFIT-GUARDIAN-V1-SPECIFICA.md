# Fix B — AI Profit Guardian V1 + Portfolio Trend Alert
**Specifica completa approvata il 24 ottobre 2026 — SOLO SHADOW, applied=false.**

## Perimetro autorizzato
Sono autorizzati soltanto: branch work/fix-b-profit-guardian, profit_guardian.py, portfolio_alert.py, test unitari, CI isolata e questa documentazione sul ramo diario. NON sono autorizzati merge su rule-pool o main, deploy, riavvii di Hawk/Bull, nuove chiamate AI sul VPS, modifiche agli ingressi, al motore esecutivo, a Capital V1 o a DeepSeek shadow. Sul VPS Hawk e Bull eseguono il codice 297b126 in PAPER; Capital V1 è installato ma resta OFF. SHA più nuovi di rule-pool non significano nuovo codice eseguito dai container.

## Decisioni dell'utente (cinque + prompt + alert)
1. ROI NETTO dal 12%: osservazione rafforzata, senza ordine automatico. Al 20%: revisione Claude prioritaria. Se il picco osservato ha già raggiunto il 20%, mantenere l'attenzione anche durante il giveback. Il ROI usa il margine di riferimento stabile (ingresso+DCA) e considera risultati parziali una volta sola, fee, slippage e funding. Non usare la variazione % del prezzo né il massimo teorico MFE come profitto effettivamente liquidabile.
2. Le tre sole decisioni Claude sono CLOSE_FULL (chiusura totale), TAKE_PARTIAL (chiusura esattamente 50%) e HOLD_TP (mantenimento TP); nessuna regola tecnica impone un'uscita alla soglia.
3. Per TAKE_PARTIAL Claude deve proporre anche il nuovo stop residuo. Il motore futuro deve verificare che sia più protettivo, dal lato corretto del prezzo e non peggiore di breakeven NETTO stimato con costi sul residuo. Se non applicabile, respingere l'operazione COMPOSTA per intero. Non basta usare la partial_close esistente, che oggi non imposta automaticamente lo stop del residuo. Lo stop stimato non promette riempimento esatto nei gap.
4. Claude Fix B potrà essere consultato in anticipo, a budget separato di circa **0,10 USD per giorno UTC condivisi tra Hawk e Bull**, con pre-prenotazione worst-case e ledger con lock/idempotenza. HARD cooldown di 30 minuti per singola posizione, identificata da bot/run/id/simbolo/orario apertura. Non utilizzare né resettare il budget normale Claude.
5. Meccanismo comune per Hawk e Bull; dati specifici di ciascun portafoglio. Ingressi, DCA, split, slot, stop giornaliero e parametri di Capital V1 invariati.
6. Prompt speciale Fix B separato dal ciclo di decisione entrate. Include ROI netto corrente, MFE come limite superiore e non picco netto eseguibile, distanza dal TP originale in R (misurata dal prezzo corrente), prezzo/SL/TP/qty/margine/rischio, RSI 15m e 1h, EMA20/50 1h, ATR, volumi, momentum, trend e timestamp. Framing obbligatorio, se la soglia di profitto è stata superata: **"QUESTA POSIZIONE HA SUPERATO LA SOGLIA DI PROFITTO — VALUTA SE PROTEGGERE IL GUADAGNO."** Per un alert con ROI inferiore al 20% si utilizza un framing specifico e veritiero.
7. Portfolio Trend Alert: monitora le posizioni SHORT e in più BTC/ETH come sentiment (simboli deduplicati). Usa solo ultime candele 1h CHIUSE e fresche, con dati coerenti e warmup. Soglie V1 SOLO per innescare una revisione: prezzo riconquista EMA20/50 1h, RSI1h >=55 e in salita >=2, volume ultima barra >=1,5× rispetto alle 20 precedenti. Almeno 3 simboli distinti con segnale sulla medesima barra 1h => alert priorità massima, rivedere TUTTE le SHORT anche se non hanno ancora +20%. **Nessuna uscita automatica:** decide Claude.
8. Collisione tra immediato e cooldown: si registra l'alert immediatamente; per le posizioni non ancora revisionate da 30 minuti la review parte subito, per le altre si accoda alla prima scadenza utile. Non violare l'intervallo minimo approvato; una vera eccezione richiederebbe un nuovo OK.

## Tre corsie comparabili, stesso event_id
Per ogni decisione di posizione e per ogni alert di portafoglio registrare:
- corsia Claude operativo: proposta che in una futura fase potrebbe essere eseguita, ma **ORA SOLO PROPOSTA**, applied=false, executed=false;
- corsia Claude shadow: risposta Claude indipendente, raccolta prima della futura esecuzione, confrontata con la prima corsia (agree / diverge / unknown), anch'essa soggetta al budget;
- corsia DeepSeek shadow ESISTENTE: sola lettura delle decisioni del conto virtuale DeepSeek (applied=false), mai co-decisore e mai utilizzabile come ordine. Se orario, simbolo e identità posizione non sono confrontabili, non inventare concordanza: not_comparable/not_collected.

In questa fase non si eseguono nemmeno chiamate Claude in autonomia: i moduli accettano le eventuali risposte tramite un adattatore FUTURO, senza esporre chiavi o invocare client AI. Gli eventi includono bot, run, posizione, ROI, MFE, tipo trigger, eventuale alert_id, le tre corsie, ragioni, validità, timestamp, mode ombra, applied=false, executed=false, execution_result null. Un futuro esito reale va scritto come evento separato, senza modificare a posteriori il registro pre-esecuzione.

**Limite fondamentale DeepSeek:** il servizio preesistente prende decisioni autonome ogni ~15 minuti su un proprio conto; non è garantita una nuova proposta nello stesso identico istante dell'alert Fix B. Poiché l'utente ha vietato modificarne l'architettura, si collega il campione leggibile temporalmente compatibile oppure si dichiara il confronto non disponibile. Mai forzare una chiamata DeepSeek on-demand.

## Moduli sviluppati sul branch di lavoro
- backend/desk/profit_guardian.py: pure functions eligibility ROI 12/20% e peak, cooldown per posizione, prompt dedicato, distanza TP in R, break-even costo/qty, validazione delle tre decisioni e stop residuale LONG/SHORT, budget admission, registro shadow append+fsync/flock con deduplica, ShadowBudgetLedger giornaliero UTC condiviso Hawk/Bull, confronto tre corsie singola posizione e alert di portafoglio. Non importa cli.py né engine.py né live connector.
- backend/desk/portfolio_alert.py: usa solo 60 candele 1h consecutive chiuse, EMA20/50, RSI Wilder14, volume relativo 20, timestamp fresco max 90 minuti, 3 simboli distinti simultanei, include BTC ed ETH una sola volta, produce solo l'evento review-short.
- backend/tests/test_fix_b_guardian.py; backend/tests/test_fix_b_portfolio_alert.py; backend/tests/test_fix_b_shadow_persistence.py.
- .github/workflows/fix-b-shadow-ci.yml: CI soltanto su work/fix-b-profit-guardian, py_compile, 21 test unitari offline e controllo delle importazioni operative.
- Salvataggio opzionale di un evento di confronto SOLO in una cartella esterna denominata fix-b-shadow-data, non nei file di Hawk, Bull o DeepSeek. La chiamata di scrittura è una funzione non collegata ai container e non viene invocata automaticamente.
- Validazione bug-fail-closed: livelli STOP non validi, stop oltre il prezzo, allargamento stop, frazione diversa dal 50%, dati EMA/RSI incompleti, barre non chiuse/stale, orari non simultanei, duplicati log, ledger corrotto, replay su nuovo run.

## Limitazioni EVIDENTI (nessuna falsa certificazione operativa)
- NON implementato un runner VPS, un scheduler, un adattatore delle posizioni reali a Fix B, la chiamata Claude effettiva né un esecutore di ordini. Non ci può essere reale chiamata DeepSeek per evento senza cambiare il servizio indipendente; la sua corsia rimane dato esterno disponibile/non comparabile.
- NON implementata la transazione esecutiva atomica parziale + stop nel motore: attualmente si valida SOLTANTO la proposta e non si chiude alcunché.
- Budget ledger è implementato e testato, ma sarà necessario montare lo stesso storage per i due bot e stimare rigorosamente il costo massimo della chiamata prima del futuro uso AI. La prova definitiva richiede test concorrenza multi-processo e crash.
- Niente risultati reddituali attribuibili alla feature finché non viene eseguita una fase di replay storico/shadow su dati veri, con controlli di costi, tempi ed EV. Alert multi-simbolo correlati possono causare falsi positivi.
- Capital Management V1 rimane OFF. Nessuna modifica a rischio, ai bot o ai prompt di entrata.

## Prossime condizioni prima di qualsiasi operatività
1. Review incrociata con Claude, senza ruoli subordinati: stesso accesso al ramo dedicato, feedback e test di regressione.
2. Test completo replay storico e su dati veri per ROI/posizioni residue/DCA/split/SL/TP e prova fallimenti: stop scartato => nessuna parziale, ricostruzione dopo crash, costo/riserva, dati stale, doppio writer.
3. Comparazione inizialmente in shadow con 3 corsie, misurare profitto NETTO rispetto a baseline, giveback, opportunità perse, falsi alert, costi AI.
4. Backup/restore certificato e rollback prima di un eventuale deploy separato PAPER.
5. Solo con autorizzazione esplicita ulteriore: merge in rule-pool e, molto più tardi, deploy shadow/attivazione operativa. **Al momento nessun merge, nessun deploy, nessun riavvio.**
