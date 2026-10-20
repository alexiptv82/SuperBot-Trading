# Director — Contratti v1.1 (aggiuntivi, non sostituiscono v1)

**20 ottobre 2026 — codice da revisionare, NON integrato nel runtime.** La v1 e le otto fixture degli esiti restano immutate. Import esplicito dal modulo backend/director/contracts/v1_1.py. Il formato trasporta schema_version=1 (major) e contract_version="1.1" (minor); non sostituire silenziosamente gli import di Claude.

## Risposte ai rilievi C1–C5

**C1 — PARTIAL_CLOSE:** obbligatoria close_fraction strettamente fra zero e uno, riferita alla quantità RESIDUA della posizione indicata da position_key. Non è un importo, non un ordine e non può apparire in altre azioni. La conferma del fill e gli arrotondamenti rimangono all'arbitro e al motore.

**C2 — Coerenza azioni:** selected_candidate_id esiste solo in OPEN e deve comparire fra gli evaluated_candidate_ids. NO_TRADE ha no_trade_reason e non può selezionare candidati né indicare una posizione. CLOSE, HOLD, REASSESS, PARTIAL_CLOSE richiedono position_key. HOLD/REASSESS richiedono hold_conviction_0_100 e possono proporre review_after_bars con review_timeframe_ms. OPEN richiede open_conviction_0_100 intero 0–100; vieta position_key e close_fraction. Questi due punteggi AI sono OPINIONI SOGGETTIVE, non probabilità calibrate.

**Chi assegna il margine:** NON l'AI. Il modello seleziona una Candidate e dichiara la convinzione; l'arbitro (proprietà Claude, ancora da progettare e approvare) determina una quantità legalmente ammissibile usando budget, distanza dello stop, rischio, cash, margine, concentrazione e dati calibrati. NON è autorizzata una mappatura automatica 0–100 → 150–350 USD. Se il minimo del conto non è disponibile, preferire il rifiuto all'aumento silenzioso del rischio. La decisione Bull A/B sul margine residuo sotto 150 USD rimane separata e in attesa dell'utente.

**C3 — Confine numerico:** i contratti accettano soltanto numeri primitivi Python finiti e timestamp interi reali. Se il feed usa NumPy, chiamare normalize_boundary su mapping plain prima di from_payload; gli array vanno convertiti esplicitamente in liste e i float timestamp NON vanno troncati a int senza controllo. NaN e inf sono invalidi. Nessuna dipendenza NumPy per importare i contratti.

**C4 — Immutabilità:** MarketFrame.features viene copiato e congelato ricorsivamente (mapping di sola lettura, tuple), e as_payload crea una copia modificabile indipendente. hash(MarketFrame) è definito sul JSON canonico di TUTTI i campi incluse le feature (SHA-256 troncato), uguale per frame equivalenti. L'hash di oggetto non sostituisce l'identificatore di mercato versionato nella catena di audit.

**C5 — Entrata ritardata:** la Candidate originale conserva sempre signal_bar_open_ms e earliest_entry_ms. L'adattatore puro outcomes_v1_1.evaluate_candidate_path riceve una sequenza CONTIGUA di candele chiuse a partire dalla barra immediatamente seguente il segnale e trova la prima OPEN il cui timestamp è >= earliest_entry_ms. Rifiuta buchi anche PRIMA dell'ingresso. Per il calcolo delega alla funzione originale outcomes.evaluate_path della v1 SENZA modificarla; restituisce UNRESOLVED se non esiste ancora una barra ammissibile. Non retrodata mai il segnale.

## Fixture e test

- Fixture contratti: backend/director/contracts/fixtures/contract_cases_v1_1.json (7 oggetti: market frame, candidate, HOLD, OPEN, PARTIAL_CLOSE, NO_TRADE, portfolio).
- Fixture degli esiti: invariata backend/director/contracts/fixtures/outcome_cases_v1.json; Claude ha dichiarato 38.000 confronti senza divergenze su causa/tempo/prezzo di uscita.
- Test dedicati: backend/tests/test_director_contracts_v1_1.py (8 casi; incluso hash/immutabilità, frazione parziale, vincoli azioni, NumPy, ingresso in ritardo).
- Comando: PYTHONPATH=backend PYTHONDONTWRITEBYTECODE=1 python -B -m unittest discover -s backend/tests -p 'test_director_contracts_v1*.py' -v
- Non sono stati eseguiti test di integrazione con i bot o sul VPS, né richieste exchange/API LLM.

**Invariante di rischio:** nessuna proposta AI può modificare kill switch, spostare stop in direzione sfavorevole o superare un limite. Questi contratti rappresentano dati e opinioni, non permessi di trading. Nessun LIVE.
