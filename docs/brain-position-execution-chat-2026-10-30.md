# Brain — gestione AI delle posizioni PAPER (preparazione offline)

Data: 30 ottobre 2026 · autore: ChatGPT chat normale · ramo `work/brain-position-execution-chat-20261030`

## Ambito
Questa patch prosegue la revisione periodica delle posizioni del ramo `work/brain-position-review-chat-20261030` senza introdurre live trading e senza toccare i bot classici. Il supervisore continua a chiamare `account.tick` per le protezioni locali PRIMA di interagire con l'AI.

La revisione non richiede candidati scanner. Con candidati e posizioni, il primo giro mantiene la precedenza preesistente delle nuove proposte; i giri successivi alternano ingressi/revisioni sotto **un solo** worker, budget giornaliero e cooldown.

## Contratto delle azioni
`BRAIN_AI_POSITION_ACTIONS=off` (default) registra solo l'osservazione. Il valore `paper` abilita esclusivamente azioni riduttive sul conto single-BRAIN PAPER (senza ordini exchange). Nessun altro valore, incluso `live`, è accettato. L'abilitazione NON è impostata da questo ramo, e nessun servizio è stato avviato.

Risposte: `HOLD`, `SUGGEST_CLOSE`, `SUGGEST_TIGHTEN` (+ `stop_price` obbligatorio numerico). Una raccomandazione non è autorizzazione a operare. DeepSeek propone, Claude rivede i casi non-HOLD. Per eseguire serve accordo sullo stesso simbolo, position_id e azione (e stesso stop prezzo, se richiesto). In assenza/fallimento Claude si registra `deferred` e non si modifica la posizione.

Il proprietario SQLite ricontrolla hash esposizione e id posizione, scadenza, prezzo recente (<=3s), deriva massima del mark 0,1%, copertura storica, assenza gap e clock non arretrato. Stop arrotondato al tick in direzione di maggior protezione e mai oltre il mark; se invalido viene rifiutata l'intera operazione, non convertita in close. Nuove aperture, DCA, leva e allargamento stop non sono consentiti da questo percorso.

Chiusura PAPER: funzione di regolamento esistente `brain_free.execution.close`, fee, slippage, contabilità e aggiornamento metriche già usati dall'engine; evento `trade_closed` con fonte AI (non `manual_user`), ricevuta `ai_position_review_observed`, checkpoint idempotente nella **stessa transazione SQLite**. Un errore di stop, sorgente, quota, posizione o hash impedisce l'intero commit. Backup SQLite esistente resta compatibile, nessun reset schema o cancellazione di memoria.

## Vincoli e verifiche pre-rilascio
- Basi: `895b34a64058b1321ba5ad372e8de435f3e7fec0` (integrazione) e `f825a62a5592f95693378435421f8c8ddc1fc5e4` (review).
- Test unitari su profitti/chiusure, stop LONG, consenso/no consenso, risposta obsoleta, cambio ID, clock, startup, idempotenza, rollback di failure e backup. GitHub Actions Python3.10/3.11 è la verifica; **non dichiarare verde fino al run HEAD**.
- Gate automatico diff: `backend/desk`, `backend/director/brain_free`, `engine.py`, `scanner.py`, `frontend`, `deploy` byte invariati.
- Non equivalgono a test API DeepSeek/Claude reali, alimentazione Bitget live, simulazione realistica su periodo fuori campione né collaudo UI/VPS. Conto e budget operativi non approvati.
- Prima dell'eventuale rilascio: consolidare branch Work locale e codice, consultare diario e CI finale, validare mandato finanziario e tetti economici AI, backup+restore reali, staging feed pubblico/quote scadute/protezione, PWA/Telegram e piano di rollback; chiedere autorizzazione specifica merge e deploy. Inizializzazione di un conto e attivazione sono operazioni SEPARATE, vietate ora.

## Stato
**Codice PREPARATO offline**; nessun merge, deploy, servizio, API pagata, posizione, storico o VPS modificato.
