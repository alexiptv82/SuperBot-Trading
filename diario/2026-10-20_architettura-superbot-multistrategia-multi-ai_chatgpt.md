# SuperBot-Trading — Architettura multi-strategia e multi-AI (proposta ChatGPT v0.1)

Data: 20 ottobre 2026. Stato: **SPECIFICA IN REVISIONE**, non autorizza codice, merge o deploy.

## 0. Intento dell'utente

Un trader algoritmico H24 che osserva simultaneamente long e short su tutti i mercati disponibili, riconosce trend, range, supporti/resistenze, medie, pullback, breakout, pattern, rimbalzi e inversioni; sceglie fra strategie diverse o decide di NON operare. Dopo l'ingresso rivaluta il motivo del trade, protegge i profitti e confronta il mantenimento di una posizione con nuove opportunita'. Memorizza tutte le decisioni e ne misura la qualita'. Nessun modello promette profitti certi.

L'obiettivo e' un **sistema integrato e completo di ricerca/ombra + paper controllato**, non un bot che operi solo in range, ne' sei strategie indipendenti slegate. La messa in funzione richiede una conferma separata di Alessandro. Prima la revisione indipendente di Claude; DeepSeek solo consulenza se serve.

## 1. Stato del codice letto (non testato da ChatGPT in questa sessione)

- backend/desk/cli.py: Hawk (10 slot, margine massimo 100 USD/trade) e Bull (3 slot, max 350 USD/trade), 26 simboli, ciclo di mercato su candele 15m chiuse, stop e TP prima delle decisioni. A ottobre 2026 la soglia Tier C nel ramo work/salto-qualita e' 63, Tier A/B 60. Non cambiare queste soglie in questo progetto.
- backend/desk/brain.py: provider Claude direttamente collegato al motore attuale; prompt contenente L e S, ma l'azione proposta usa l'interfaccia storica di apertura/chiusura. Conservare l'attuale cervello e non sostituirlo finche' il nuovo e' validato.
- backend/desk/learning.py: registra gia' sig_long e sig_short per i candidati con reading, ma non ogni opportunita' valutata su tutti i simboli. La registrazione di candidati ha un tetto; non confondere candidate scartato con universo completo di opportunita'.
- backend/desk/profit_sidecar e backend/desk/profit: Profit Manager esiste in **ombra**, con valutazioni del profitto netto, inversione, dati mancanti e decisioni advisory. Non farlo diventare attivo implicitamente.
- backend/desk/turbo_scalp: strategia pura step su 5m chiuse, in ombra, con cooldown 2 barre intere; va confrontata con alternativa 3 senza cambiare la strategia di riferimento.
- backend/rule_pool: regole, controlli casuali e criteri statistici gia' presenti; riutilizzare il processo di validazione, non duplicarlo.
- Motore PaperAccount/limiti di rischio rimane l'unica autorita' per vincoli di cassa, margini, exposure, stop e kill switch. Nessuna connessione nuova all'exchange.

## 2. Architettura proposta

Flusso unidirezionale, con versionamento e journaling:

1. Market Observer: barre pubbliche 5m/15m/1h/4h/1D **chiuse e regolari**; prezzo osservato e timestamp distinti dalla chiusura della barra. Disponibilita' e qualita' per strumento. Funding, OI, volumi, calendario macro solo se timestamp validi. Niente segreti.
2. Chart & Regime Engine **deterministico**: swing-high/low causali, supporti/resistenze e numero di tocchi confermati, retest, canali/range, ATR, ADX, Bollinger, trend multi-TF, pattern triangolo/bandiera (solo se definibili senza lookahead), volatilita', regime trend/range/transizione/unknown. Per qualunque campo mantenere timestamp di disponibilita', finestra, parametri e prova; evitare lettura di futuri estremi.
3. Strategy Library: plugin puri versionati (id + versione + hash parametri) emettono contemporaneamente candidati LONG/SHORT per simbolo, inclusa l'astensione. Strategia iniziale L1 pullback/EMA, L2 livelli/swing, L3 breakout/retest, L4 range ping-pong, L5 inversione dopo uscita, L6 triangoli/bandiere (ultima priorita'), piu' regole gia' presenti e Turbo Scalp. Ogni plugin deve definire universo, timeframe, ingresso dalla barra successiva, invalidazione, stop, target, uscita a tempo, costi, tipo di mercato, conflitti e uno scenario di controllo.
4. Opportunity Evaluator: normalizza tutti i candidati al netto dei costi; applica gates empirici (campione, qualita' e regime) e stima utile atteso e incertezza per ogni lato. Il punteggio storico 0–100 non e' una probabilita' calibrata.
5. AI Director: riceve solo snapshot strutturato, posizioni aperte, candidati con prove numeriche e storici consentiti. Confronta lato e strategia per ogni opportunita'; propone aprire / non aprire / tenere / rivalutare / uscire. Motivazione obbligatoria, controtesi, dati contrari, incertezza ed evento che invaliderebbe la tesi. Non si crede a prezzi, livelli, ordini o P&L **inventati** dal modello.
6. Deterministic Arbiter: ricontrolla simbolo, timeframe, timestamp, data freshness, limiti Hawk/Bull, score minimo vigente, esposizione correlata, fee/slippage/funding, stop, min R:R, massimo slot, margine e cooldown; puo' rifiutare o limitare, mai ampliare il rischio su richiesta AI. Se AI/API non funziona: NO nuovi ingressi del nuovo direttore; stop/TP e gestione prevista dal motore esistente restano operativi.
7. Profit & Position Advisor: collega (senza attivare) gli output del Profit Manager all'opportunity evaluator. Valuta HOLD, protezione e uscita rispetto a rischio marginale e alternative; pavimento protettivo monotono nei casi applicabili; evita churn e inversioni solo per liberare slot.
8. Decision Journal + Outcome Labeler: salva anche no-trade, entrambi i lati e tutte le strategie valutate; attributi e prove verificabili, outcome a orizzonti prefissati, risultati in R e netto costi, cambi di regime, modello/versione/prompt/parametri, e collegamento allo snapshot. Append-only e idempotente con identita' evento stabile.

Il modello AI e' un **analista/selettore**; pattern, livelli, calcoli, rischio e tracciabilita' rimangono deterministici. Su candidati finalisti si potranno generare grafici statici per un modello multimodale, ma l'immagine non sostituisce le feature verificabili.

## 3. Contratti dati e portabilita'

Tutti gli oggetti hanno schema_version, computed_at_ms, source_asof_ms, data_quality, producer_version e ref/hash input. I campi numerici devono essere finiti e dentro limiti. Regime e probabilita' possono essere UNKNOWN/null quando il campione non consente stime affidabili.

### MarketFrame v1
- symbol (canonical), market_type, availability/market_hours; 5m/15m/1h/4h/1D last_closed_open_ms, current_observed_price e timestamp.
- technical: trend_by_tf, ATR, RSI, EMA, ADX, Bollinger, volume, funding/OI se presenti.
- levels: tipo support/resistance, prezzo, tolerance_bp, confirmation_count, last_touch_ms, invalidation, lookback_start/end, algorithm/version.
- regime: trend_up/trend_down/range/transitional/unknown, score e ragioni, asof_ms.
- data_quality: gap_count, stale_ms, coverage, data_source; mai interpolare buchi senza segnalarli.

### Candidate v1
- candidate_id, strategy_id/version/params_hash, frame_hash, symbol, side LONG/SHORT, signal_bar_open_ms, earliest_entry_ms.
- trigger, proposed_entry, stop, take_profit, time_exit_bars, setup_invalidation; livelli con riferimenti.
- gross_R_estimate / net_R_estimate con provenance: se manca una stima empirica valida usare null, NON il giudizio della AI come valore atteso dimostrato.
- fee_bp_roundtrip, slip_bp_roundtrip, funding_model, execution_assumptions, fill_uncertainty, data_quality.
- regime_match, calibration_sample_n, confidence_raw, confidence_calibrated (null finche' non stimata), risk_flags.
- candidate_status: proposed/rejected/selected/skipped; motivo e versionamento; registrazione di **entrambi i lati** anche senza trade.

### DirectorAdvice v1
- market_frame_id, portfolio_id, model_provider/model_id, model_version, prompt_version, generated_at_ms, cost_usd, latency_ms.
- evaluated_candidate_ids (anche i rifiutati), selected_candidate_ids, action: OPEN/HOLD/CLOSE/PARTIAL_CLOSE/NO_TRADE/REASSESS.
- evidence_refs, thesis, counterthesis, invalidate_if, uncertainty_0_1, tradeoff_vs_best_alternative, explicit no_trade_reason.
- approved_by_arbiter boolean e reject_reason: popolati solo dall'arbitro, mai dall'AI.
- Niente testo del provider interpretato come ordine diretto. Parsing JSON con schema severo, whitelist azioni, id e timestamp verificati.

Il contratto comprende anche PortfolioSnapshot v1: Hawk e Bull hanno vincoli e posizioni distinti, ma utilizzano lo **stesso** MarketFrame condiviso. Il Direttore deve sapere che i 26 simboli non equivalgono a 26 posizioni ammissibili. Rischio correlato e conflitti tra bot hanno una policy esplicita ancora da deliberare.

## 4. Processi e integrazione senza contaminare bot attivi

A. Processo **superbot-director-shadow** separato, senza API exchange o credenziali Bitget, volume scrivibile proprio e, solo se indispensabile, stati Hawk/Bull montati read-only. Il calcolo di candele e candidati opera anche senza stato del bot; l'accesso agli stati avviene tramite un reader validato e snapshots coerenti. Nessun side effect nei bot.
B. Scanner di mercato deterministico su barre 5m chiuse; invocazione AI aggregata dopo i cicli 15m, piu' eventi materiali limitati (regime cambiato, invalidazione, risk event), con rate limit/cooldown. In particolare il modello H24 non esegue un ordine ad ogni refresh di prezzo.
C. Due advisory di portafoglio (Hawk/Bull), stesso contesto mercato, decisioni separate e tracciate; eventuale priorita' del Profit Manager da stimare in shadow. Durante pausa/orari non proporre ingressi; la regola orari e' attualmente configurabile e spenta per default, dunque verificare configurazione runtime prima di dichiarare 24/7.
D. La modalita' integrated-paper pilot usa un conto simulato isolato e la medesima pipeline di signal->arbiter->execution; solo dopo verifica/OK si valuta un adapter dietro flag disabilitato di default ai bot Hawk/Bull, con rollback e test per non alterare order-of-operations, state_v2 e journaling. Zero cambi live.
E. Provider adapter swappable: DeepSeek Flash / Gemini Flash-Lite / Gemini Flash; chiave soltanto env/VPS secret o GitHub Actions Secrets, mai codice o registri; budget giornaliero e mensile rigido, limite token/call, retry bounded, timeout, no HTTP tools arbitrari, sanitize delle news (contenuto non fidato). Se il provider cambia, l'intero audit trail conserva modello, hash prompt e costo.

## 5. Confronto AI e costo (listini pubblici consultati il 20/10/2026)

- DeepSeek V4.1 Flash: peak 0.30 USD / milione token input (cache miss), 1.20 output; off-peak 0.15 e 0.60. API JSON e tool calls. Prezzi da riconfermare al momento dell'attivazione.
- Gemini 3.5 Flash-Lite: 0.30 input, 2.50 output / milione nel tier pagato, con free tier subject to limits. 
- Gemini 3.8 Flash: prezzo promozionale 0.75 input, 3.75 output / milione fino al 31/12/2026, poi piu' alto. Potrebbe essere l'escalation su casi complessi.
- Groq free: adatto a prova/benchmark di alcuni modelli, non fare affidamento su disponibilita' H24 illimitata.
- Ipotesi 96 chiamate/giorno da 8.000 input e 1.500 output: DeepSeek 0.20–0.40 USD/giorno con min/max fascia, Gemini 3.5 Flash-Lite 0.59, Gemini 3.8 Flash 1.12; **non** comprende retries, token ragionamento extra, analisi doppie per bot, immagini, caching, escalation o servizi VPS. Definire il consumo dai log reali durante shadow.
- Criteri comparativi: accuratezza dei campi JSON, zero livelli inventati, rispetto del NO_TRADE, ragioni controfattuali, latency, stabilita' provider, precisione delle scelte comparate a benchmark regole, costo effettivo e termini sui dati. LLM piu' caro non significa migliore.
- Privacy: mandare soltanto dati di mercato pubblici e stato portfolio minimizzato; mai API keys, file di stato grezzi con dettagli non necessari o segreti. Per Gemini valutare termini account/territorio/tier free; nel tier pagato Google dichiara non utilizzo di prompt/risposte per migliorare i prodotti. Verificare i termini DeepSeek prima del collegamento.

## 6. Ricerca Fase 0 e validazione prima del pilot

1. Universo reale: 26 simboli Hawk/Bull, 6 Turbo gia' inclusi. Catalogare listing, mercato, copertura 5m/15m e buchi. Usare almeno 90 giorni 5m per Turbo, per range preferibilmente 12 mesi laddove disponibili. Gli ultimi 60 giorni sono HOLDOUT non esplorato, fatta eccezione per metadata/integrita' puramente tecnica.
2. Rilevatore di range causalmente calcolato da candele disponibili; specificare ora finestre, numero tocchi e tolleranze, ADX/slope, rottura e invalidazione. Misurare episodi distinti, durata, ampiezza bp, escursione **realisticamente catturabile** (non high-low futuro), rimbalzi/tocchi, percentili, lateralita' vs trend, regime e volatilita'.
3. Strategie L1...L6 con parametri congelati e benchmark casuale, long/short specchiati quando sensato; costi 12/16/20 bp + stress altcoin, funding, ingresso barra successiva, stop prima di TP nella stessa barra, gap/ambiguita' esplicitati. Controllo casuale simile per orario/regime/simbolo, non un controllo facile da battere.
4. Criteri statistici del rule-pool su campioni indipendenti, split temporali e K predefinito, block bootstrap per giorno e shock correlati; non ottimizzare sull'holdout. Out-of-sample finale da usare una sola volta. Evitare selezione a posteriori del miglior sottoinsieme di simboli.
5. Backtest Turbo usa **strategy.step del repository**, non una ricostruzione; confronto cooldown 2 vs 3; aggregati per lato, simbolo, regime, net R, holding, stop/TP/tempo, IC per giorno. Replay A–E Hawk 3–4 Bull 2–3 una correzione alla volta e quota hold_min <= 15.
6. Valutazione AI nello stesso contesto, cieca rispetto alle candele future: confronto contro regole pure, baseline casuale accoppiata, AI solo, AI+arbitro, con risultati netti; misurare NO_TRADE corretti ed errori evitati, costo per decisione e costo per trade selezionato.
7. I primi 7 giorni di shadow continuo e successivo pilot paper di 7–14 giorni (durata da confermare) valutano sicurezza operativa, doppio lato, qualitá dati e costo; non dimostrano redditivita' statisticamente stabile. Traguardo 400–500 trade e' un obiettivo di campione, non quota che giustifichi overtrading.

## 7. Gate prima di una futura attivazione paper

- 100% chiamate AI mai dirette a Bitget o al motore di ordini; assenza di API keys exchange nel Director.
- Ogni candidato/decisione riproducibile da versioni e input disponibili al timestamp; nessun lookahead negli indicatori e livelli; timestamp di barre e prezzi validati.
- Ogni decisione ammessa o rifiutata dall'arbitro, con motivazione. Nessun bypass di limiti del conto, nessuna apertura con dati stale/inesistenti, schema invalido o budget superato.
- Tutti i test dei bot preesistenti e i nuovi test di regressione (incluse seconde gambe, partial, paper/live, pause, reset, shadow healthcheck) verdi; differenze comprese e approvate. Failure injection API down, 429, JSON invalido, buco di serie, timestamp ripetuto, riavvio/corruzione stato, conflitti long/short nello stesso simbolo, stop e segnale stessa candela.
- Shadow journaling idempotente, posizione e run identity stabili, reconcile outcomes, real cost usage e allarme budget; no secrets nei log; rollout/rollback documentati.
- Separazione formale: approvazione del codice/merge, autorizzazione a deploy PAPER e qualunque eventuale LIVE sono tre decisioni distinte di Alessandro.

## 8. Collaborazione e proprieta' dei file

ChatGPT: specifica, test di causalita'/misure, audit indipendente, registrazione delle assunzioni; Claude: **revisione di questa specifica prima del codice**, implementazione modulare dopo approvazione, test con mutazioni, integrazione senza toccare il cervello storico di nascosto. DeepSeek: terzo revisore soltanto se divergenza rilevante, forte in analisi controfattuale/prezzi/rischio. Alessandro decide prioritá, provider e approvazione del rilascio.

Proposta ripartizione concreta dopo la revisione:
- ChatGPT: contratti MarketFrame/Candidate/DirectorAdvice, spec Fase 0, test metodologici, replay/backtest;
- Claude: provider adapters, Director shadow/registri, bridge del PM e integrazione paper isolata;
- doppia revisione incrociata prima del merge. Niente split di proprietà ambiguo nello stesso file.

## 9. Questioni aperte da risolvere con Claude e Alessandro prima di implementare

1. Strategia di selezione: modello unico economico sui 26 mercati con shortlist deterministica, oppure prima scout separato e poi planner AI? Confrontare costi e qualita'.
2. Vincoli di correlazione e conflitto Hawk/Bull: quando possono detenere lati opposti sullo stesso asset? Non inventare un vincolo senza decisione.
3. Frequenza di reevaluation open trade e chi controlla priorita' di uscite quando Profit Manager consiglia exit e AI HOLD; motore/guardrail prevalgono sempre.
4. Rappresentazione causale di range e swing: parametri congelati prima del dataset, no ottimizzazione retrospettiva.
5. Posizione di un'inversione nella stessa barra (L5) e deroga cooldown: deve essere una decisione transazionale con verifica costi e nessun conflitto di slot; solo se dimostra valore netto.
6. Disponibilita' 5m su 26 mercati, XAU/XAG e sessioni non 24/7; confine di holdout e parametri di costo per simbolo.
7. Provider AI: iniziare con DeepSeek Flash + Gemini comparator in shadow, finalizzare dopo prove e verifica privacy. Quali costi massimi al giorno/mese approva Alessandro?
8. Schede L1–L6: si intendono tutte disponibili nel catalogo del pilot, ma quelle non promosse rimangono disabilitate per aperture; testarle in shadow non significa attivarle come strategie esecutive.

**STATO REALE AL MOMENTO DELLA SPECIFICA:** documento e verifica di file del repo, NON sistema implementato. Nessuna analisi storica nuova, nessun test dei bot eseguito da ChatGPT, nessun merge, deploy o trigger. Questo documento NON autorizza alcuna scrittura del codice operativo.